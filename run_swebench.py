#!/usr/bin/env python3
"""Run a coding assistant on SWE-bench Lite instances and evaluate resulting patches.

Requirements: pip install datasets; git, the selected assistant, swebench, docker on PATH.
Run from any directory; paths default to ~/swebench-experiments.
"""
from __future__ import annotations

import argparse
import codecs
import json
import locale
import random
import re
import shlex
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from assistants.codex import CodexAssistant
from assistants.copilot import CopilotAssistant
from assistants.interface import AssistantFactory

DATASET = "SWE-bench/SWE-bench_Lite"
ASSISTANTS: dict[str, AssistantFactory] = {"codex": CodexAssistant, "copilot": CopilotAssistant}


def command(args: list[str], *, cwd: Path | None = None, stdin: str | None = None,
            log: Path | None = None, json_log: Path | None = None, check: bool = True,
            env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    # Echo commands so a run can be reproduced or diagnosed from its console output.
    print("+", shlex.join(args), flush=True)
    proc = subprocess.run(args, cwd=cwd, input=stdin, text=True, env=env,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE if json_log is not None else subprocess.STDOUT)
    output = proc.stdout + (proc.stderr or "") if json_log is not None else proc.stdout
    if json_log is not None:
        json_log.parent.mkdir(parents=True, exist_ok=True)
        json_log.write_text(proc.stdout)
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
        readable = _readable_jsonl(proc.stdout) if json_log is not None else proc.stdout
        if json_log is not None and proc.stderr:
            readable += f"\n[stderr]\n{proc.stderr}"
        log.write_text(readable)
        print(f"  Output saved: {log}", flush=True)
        if json_log is not None:
            print(f"  Raw JSONL saved: {json_log}", flush=True)
    elif proc.returncode != 0 or args[:2] == ["git", "status"]:
        print(output[-4000:], flush=True)
    if check and proc.returncode:
        raise RuntimeError(f"Command failed ({proc.returncode}): {shlex.join(args)}\n{output[-3000:]}")
    if json_log is not None:
        return subprocess.CompletedProcess(args, proc.returncode, output, proc.stderr)
    return proc


def _stream_evaluation(args: list[str], *, cwd: Path, log: Path) -> int:
    print("+", shlex.join(args), flush=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    encoding = locale.getpreferredencoding(False)
    decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
    with log.open("w", encoding=encoding, newline="") as transcript:
        with subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT) as child:
            assert child.stdout is not None
            while chunk := child.stdout.read1(8192):
                # Preserve carriage returns and forward updates before a newline arrives.
                output = decoder.decode(chunk)
                print(output, end="", flush=True)
                transcript.write(output)
                transcript.flush()
            remaining = decoder.decode(b"", final=True)
            if remaining:
                print(remaining, end="", flush=True)
                transcript.write(remaining)
    print(f"  Output saved: {log}", flush=True)
    return child.returncode


def _readable_jsonl(output: str) -> str:
    """Render useful event text while retaining the original stream separately."""
    lines = []
    for line in output.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            lines.append(line)
            continue
        if not isinstance(event, dict):
            lines.append(str(event))
            continue

        event_type = event.get("type", "event")
        item = event.get("item")
        data = event.get("data")
        text = None
        if event_type == "item.completed" and isinstance(item, dict):
            text = item.get("text") or item.get("aggregated_output")
        elif event_type == "assistant.message" and isinstance(data, dict):
            text = data.get("content")
        if isinstance(text, str) and text:
            lines.append(text)
        elif event_type not in {"assistant.message_delta", "assistant.message_start"}:
            details = data if isinstance(data, dict) else item if isinstance(item, dict) else {}
            summary = {key: value for key, value in details.items()
                       if not isinstance(value, (dict, list))}
            suffix = f" {json.dumps(summary, ensure_ascii=False)}" if summary else ""
            lines.append(f"[{event_type}]{suffix}")
    return "\n".join(lines) + ("\n" if lines else "")


def parser(argv: list[str] | None = None) -> argparse.ArgumentParser:
    # Select the adapter first so its options and help reflect the chosen assistant.
    selector = argparse.ArgumentParser(add_help=False)
    selector.add_argument("--assistant", choices=ASSISTANTS, default="codex")
    selected, _ = selector.parse_known_args(argv)
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--assistant", choices=ASSISTANTS, default="codex", help="Coding assistant to run")
    p.add_argument("--count", type=int, default=1, help="Number of random instances to attempt; 0 selects all in dataset order")
    p.add_argument("--seed", type=int, default=0, help="Random seed for dataset sampling")
    p.add_argument("--ids", nargs="+", help="Exact SWE-bench instance IDs, instead of --count/--seed")
    p.add_argument("--root", type=Path, default=Path.home() / "swebench-experiments")
    p.add_argument("--swebench-dir", type=Path, help="Directory of installed SWE-bench checkout")
    p.add_argument("--task-repo", type=Path, help="Directory of swe-bench-tasks checkout")
    p.add_argument("--run-id", help="Unique run ID; auto-generated when omitted")
    p.add_argument("--generation-workers", type=int, default=1,
                   help="Number of patch-generation instances to run in parallel")
    p.add_argument("--evaluation-workers", "--workers", dest="evaluation_workers", type=int, default=1,
                   help="SWE-bench evaluation workers (deprecated alias: --workers)")
    ASSISTANTS[selected.assistant].add_arguments(p)
    p.add_argument("--skip-generation", action="store_true",
                   help="Evaluate saved predictions for an existing --run-id")
    p.add_argument("--skip-eval", action="store_true", help="Generate patches and predictions only")
    p.add_argument("--dry-run", action="store_true", help="Print selected issues without cloning or running an assistant")
    p.add_argument("--overwrite", action="store_true", help="Delete and recreate existing per-run workspaces")
    return p


def make_prompt(problem: str) -> str:
    return f"""Solve the following SWE-bench Lite issue in this checked-out repository.

Issue description:
{problem}

Instructions:
- Work only in this repository and implement a minimal source-code fix.
- Do not search the web or consult original PRs, reference solutions, or hidden tests.
- Do not change or add tests, fixtures, or benchmark files.
- Do not create commits or change the checked-out branch/commit.
- Run focused existing tests when feasible; report any limitations.
- Leave all implementation changes in the working tree.
"""


def generate_instance(index: int, issue: dict, total: int, run_dir: Path,
                      assistant: AssistantFactory, overwrite: bool,
                      on_progress=None) -> tuple[dict | None, dict]:
    iid = issue["instance_id"]
    idir = run_dir / iid
    workspace = idir / "repo"
    if on_progress:
        on_progress(iid)
    try:
        if idir.exists() and overwrite:
            import shutil
            shutil.rmtree(idir)
        idir.mkdir(parents=True, exist_ok=True)
        (idir / "issue.txt").write_text(issue["problem_statement"])
        (idir / "metadata.json").write_text(json.dumps({
            "instance_id": iid,
            "repo": issue["repo"],
            "base_commit": issue["base_commit"],
        }, indent=2) + "\n")
        prompt = make_prompt(issue["problem_statement"])
        (idir / "prompt.txt").write_text(prompt)

        command(["git", "clone", "--quiet", f"https://github.com/{issue['repo']}.git", str(workspace)])
        command(["git", "checkout", "--detach", issue["base_commit"]], cwd=workspace)
        actual = command(["git", "rev-parse", "HEAD"], cwd=workspace).stdout.strip()
        if actual != issue["base_commit"]:
            raise RuntimeError(f"Wrong checkout: {actual}")

        assistant.run(workspace, prompt, idir, command)

        untracked = command(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=workspace).stdout
        files = [item for item in untracked.split("\0") if item]
        if files:
            command(["git", "add", "-N", "--", *files], cwd=workspace)
        command(["git", "diff", "--check", "HEAD"], cwd=workspace)
        patch = command(["git", "diff", "--binary", "HEAD"], cwd=workspace).stdout
        (idir / "model.patch").write_text(patch)
        if not patch.strip():
            raise RuntimeError(f"{assistant.display_name} produced no patch")

        return ({
            "instance_id": iid,
            "model_name_or_path": assistant.prediction_name,
            "model_patch": patch,
        }, {"instance_id": iid, "status": "patch_generated", "patch_bytes": len(patch.encode())})
    except Exception as exc:
        return None, {"instance_id": iid, "status": "generation_failed", "error": str(exc)}


def _evaluate(a: argparse.Namespace, sb_dir: Path, task_repo: Path | None,
              run_id: str, pred_path: Path) -> int:
    eval_cmd = ["swebench", "eval", "lite", "-p", str(pred_path),
                "--run-id", run_id]
    if task_repo is not None:
        eval_cmd.extend(["--task-repo", str(task_repo)])
    eval_cmd.extend(["-j", str(a.evaluation_workers)])
    log = pred_path.parent / "evaluation.log"
    try:
        returncode = _stream_evaluation(eval_cmd, cwd=sb_dir, log=log)
    except Exception as exc:
        print(f"Evaluation failed to run: {exc}", file=sys.stderr)
        return 1
    print(f"Evaluation logs: {sb_dir / 'logs' / 'evaluation' / run_id}")
    print(f"Evaluation command exit code: {returncode}")
    if returncode:
        print(f"See {log}", file=sys.stderr)
    return returncode if returncode >= 0 else 128 - returncode


def _evaluate_saved(p: argparse.ArgumentParser, a: argparse.Namespace) -> int:
    if not a.run_id:
        p.error("--skip-generation requires --run-id")
    for flag in ("skip_eval", "dry_run", "overwrite"):
        if getattr(a, flag):
            p.error(f"--skip-generation cannot be combined with --{flag.replace('_', '-')}")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", a.run_id) or a.run_id in (".", ".."):
        p.error("Invalid --run-id")

    root = a.root.expanduser().resolve()
    sb_dir = (a.swebench_dir or root / "SWE-bench").expanduser().resolve()
    task_repo = a.task_repo.expanduser().resolve() if a.task_repo is not None else None
    pred_path = root / "runs" / a.run_id / "predictions.jsonl"
    try:
        with pred_path.open(encoding="utf-8") as predictions:
            count = 0
            for line_number, line in enumerate(predictions, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                required = ("instance_id", "model_name_or_path", "model_patch")
                if not isinstance(row, dict) or any(
                    not isinstance(row.get(key), str) or not row[key].strip() for key in required
                ):
                    p.error(f"Invalid prediction at {pred_path}:{line_number}")
                count += 1
    except (OSError, ValueError) as exc:
        p.error(f"Cannot read predictions from {pred_path}: {exc}")
    if not count:
        p.error(f"No predictions in {pred_path}")

    _check_dependencies(p, sb_dir, task_repo, ("swebench", "docker"))
    print(f"Evaluating {count} saved predictions from {pred_path}")
    return _evaluate(a, sb_dir, task_repo, a.run_id, pred_path)


def _check_dependencies(p: argparse.ArgumentParser, sb_dir: Path, task_repo: Path | None,
                        executables: tuple[str, ...]) -> None:
    if not sb_dir.is_dir():
        p.error(f"SWE-bench checkout not found: {sb_dir}")
    if task_repo is not None and not task_repo.is_dir():
        p.error(f"Task repository not found: {task_repo}")
    for exe in executables:
        if shutil.which(exe) is None:
            p.error(f"Executable not found on PATH: {exe}")


def main() -> int:
    p = parser()
    a = p.parse_args()
    if a.evaluation_workers < 1:
        p.error("--evaluation-workers must be positive")
    if a.skip_generation:
        return _evaluate_saved(p, a)
    assistant = ASSISTANTS[a.assistant](a)
    if a.count < 0:
        p.error("--count must be nonnegative")
    if a.generation_workers < 1:
        p.error("--generation-workers must be positive")
    if a.ids and (a.count != 1 or a.seed != 0):
        p.error("Use --ids alone, not with --count or --seed")
    from datasets import load_dataset

    # Materialize the split once so IDs can be validated and selection is deterministic.
    rows = list(load_dataset(DATASET, split="test"))
    by_id = {r["instance_id"]: r for r in rows}
    # Explicit IDs take precedence; otherwise choose all rows or sample without replacement.
    if a.ids:
        missing = [i for i in a.ids if i not in by_id]
        if missing:
            p.error("Unknown instance IDs: " + ", ".join(missing))
        chosen = [by_id[i] for i in dict.fromkeys(a.ids)]
    elif a.count == 0:
        chosen = rows
    else:
        if a.count > len(rows):
            p.error(f"Requested {a.count} instances, but the dataset contains only {len(rows)}")
        chosen = random.Random(a.seed).sample(rows, a.count)

    # Resolve all paths up front so subprocesses and saved artifacts use absolute locations.
    root = a.root.expanduser().resolve()
    sb_dir = (a.swebench_dir or root / "SWE-bench").expanduser().resolve()
    task_repo = a.task_repo.expanduser().resolve() if a.task_repo is not None else None
    run_id = a.run_id or assistant.run_prefix + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id):
        p.error("--run-id may contain only letters, digits, dot, underscore, hyphen")
    run_dir = root / "runs" / run_id
    if run_dir.exists() and any(run_dir.iterdir()) and not a.overwrite:
        p.error(f"Run directory already exists: {run_dir}. Choose a new --run-id")

    print(f"Dataset: {DATASET} (test split, {len(rows)} instances)")
    print(f"Run ID: {run_id}")
    print(f"Selected ({len(chosen)}): " + ", ".join(r["instance_id"] for r in chosen))
    if a.dry_run:
        return 0

    _check_dependencies(p, sb_dir, task_repo, ("git", assistant.executable, "swebench", "docker"))

    if assistant.name == "copilot":
        print("WARNING: Copilot sandbox and network restrictions depend on the host and CLI configuration; "
              "network isolation and Codex-equivalent protections are not guaranteed.",
              file=sys.stderr, flush=True)

    run_dir.mkdir(parents=True, exist_ok=True)
    predictions_by_index = {}
    statuses_by_index = {}
    generation_started = time.perf_counter()

    with ThreadPoolExecutor(max_workers=a.generation_workers) as executor:
        future_to_index = {
            executor.submit(generate_instance, index, issue, len(chosen), run_dir,
                            assistant, a.overwrite): index
            for index, issue in enumerate(chosen, 1)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            iid = chosen[index - 1]["instance_id"]
            print(f"\n[{index}/{len(chosen)}] {iid}", flush=True)
            try:
                prediction, status = future.result()
            except Exception as exc:
                print(f"  FAILED: {exc}", file=sys.stderr, flush=True)
                prediction = None
                status = {"instance_id": iid, "status": "generation_failed", "error": str(exc)}
            if prediction is not None:
                predictions_by_index[index] = prediction
            statuses_by_index[index] = status
            if status["status"] == "generation_failed":
                print(f"  FAILED: {status['error']}", file=sys.stderr, flush=True)

    predictions = [predictions_by_index[index] for index in sorted(predictions_by_index)]
    statuses = [statuses_by_index[index] for index in sorted(statuses_by_index)]
    (run_dir / "generation_status.json").write_text(json.dumps(statuses, indent=2) + "\n")
    generation_duration = time.perf_counter() - generation_started

    # SWE-bench consumes one JSON object per line, including only successfully generated patches.
    pred_path = run_dir / "predictions.jsonl"
    with pred_path.open("w") as f:
        for prediction in predictions:
            f.write(json.dumps(prediction) + "\n")
    print(f"\nGenerated {len(predictions)}/{len(chosen)} patches: {pred_path}")
    evaluation_duration = None
    exit_code = 1
    if not predictions:
        print("No patches to evaluate.", file=sys.stderr)
    elif a.skip_eval:
        print("Evaluation skipped (--skip-eval).")
        exit_code = 0 if len(predictions) == len(chosen) else 1
    else:
        evaluation_started = time.perf_counter()
        returncode = _evaluate(a, sb_dir, task_repo, run_id, pred_path)
        evaluation_duration = time.perf_counter() - evaluation_started
        exit_code = 0 if returncode == 0 and len(predictions) == len(chosen) else 1

    run_metadata = {
        "run_id": run_id,
        "assistant": assistant.name,
        "model": assistant.model,
        "reasoning_effort": assistant.reasoning_effort,
        "generation_duration_seconds": generation_duration,
        "evaluation_duration_seconds": evaluation_duration,
    }
    (run_dir / "run_metadata.json").write_text(json.dumps(run_metadata, indent=2) + "\n")
    print(f"Generation duration: {generation_duration:.2f} seconds")
    if evaluation_duration is None:
        print("SWE-bench evaluation duration: not run")
    else:
        print(f"SWE-bench evaluation duration: {evaluation_duration:.2f} seconds")
    print(f"Run metadata: {run_dir / 'run_metadata.json'}")
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        sys.exit(130)
