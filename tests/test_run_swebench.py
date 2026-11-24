import json
import random
import sys
import types
import subprocess

import pytest

import run_swebench as driver


@pytest.fixture
def rows():
    return [{"instance_id": f"issue-{i}"} for i in range(10)]


@pytest.fixture
def run_driver(rows, tmp_path, monkeypatch, capsys):
    def run(*args, dataset_rows=None):
        dataset = types.ModuleType("datasets")
        dataset.load_dataset = lambda name, split: rows if dataset_rows is None else dataset_rows
        monkeypatch.setitem(sys.modules, "datasets", dataset)
        monkeypatch.setattr(sys, "argv", ["driver", "--root", str(tmp_path), "--dry-run", *args])
        try:
            result = driver.main()
        except SystemExit as exc:
            result = exc.code
        output = capsys.readouterr()
        return result, output.out, output.err

    return run


@pytest.fixture
def run_actual(tmp_path, monkeypatch, capsys):
    issue = {
        "instance_id": "issue-0",
        "problem_statement": "Fix the reported issue.",
        "repo": "org/repo",
        "base_commit": "abc123",
    }
    dataset = types.ModuleType("datasets")
    dataset.load_dataset = lambda name, split: [issue]
    monkeypatch.setitem(sys.modules, "datasets", dataset)
    sb_dir = tmp_path / "SWE-bench"
    task_repo = tmp_path / "swe-bench-tasks"
    sb_dir.mkdir()
    monkeypatch.setattr("shutil.which", lambda executable: f"/usr/bin/{executable}")
    # Keep elapsed durations deterministic while avoiding wall-clock delays in tests.
    monkeypatch.setattr(driver.time, "perf_counter", iter([100.0, 102.5, 200.0, 205.0]).__next__)

    def run(*, generate_patch=True, eval_returncode=0, skip_eval=False, extra_args=(),
            assistant_returncode=0, empty_patch=False, eval_raises=False, use_task_repo=True):
        argv = [
            "driver", "--root", str(tmp_path), "--run-id", "test-run",
            "--swebench-dir", str(sb_dir), "--ids", "issue-0",
        ]
        task_args = []
        if use_task_repo:
            task_repo.mkdir(exist_ok=True)
            task_args = ["--task-repo", str(task_repo)]
            argv.extend(task_args)
        if skip_eval:
            argv.append("--skip-eval")
        argv.extend(extra_args)
        monkeypatch.setattr(sys, "argv", argv)

        def fake_command(args, **kwargs):
            if args[0] == "git" and args[1] == "clone" and not generate_patch:
                raise RuntimeError("simulated generation failure")
            if args[0] == "git" and args[1:3] == ["rev-parse", "HEAD"]:
                stdout = "abc123\n"
            elif args[0] == "git" and args[1:3] == ["diff", "--binary"]:
                stdout = "" if empty_patch else "diff --git a/file.py b/file.py\n"
            else:
                stdout = ""
            returncode = assistant_returncode if args[0] in ("codex", "copilot") else 0
            return subprocess.CompletedProcess(args, returncode, stdout=stdout)

        def fake_evaluation(args, *, cwd, log):
            assert args == [
                "swebench", "eval", "lite", "-p", str(log.parent / "predictions.jsonl"),
                "--run-id", "test-run", *task_args, "-j", "1",
            ]
            if eval_raises:
                raise OSError("cannot launch evaluator")
            return eval_returncode

        monkeypatch.setattr(driver, "command", fake_command)
        monkeypatch.setattr(driver, "_stream_evaluation", fake_evaluation)
        try:
            result = driver.main()
        except SystemExit as exc:
            result = exc.code
        output = capsys.readouterr()
        metadata_path = tmp_path / "runs" / "test-run" / "run_metadata.json"
        metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else None
        return result, output.out, output.err, metadata

    return run


def selected(output):
    line = next(line for line in output.splitlines() if line.startswith("Selected ("))
    return line.split(": ", 1)[1].split(", ")


def test_command_saves_raw_jsonl_and_readable_log(tmp_path, monkeypatch):
    raw_jsonl = (
        '{"type":"item.completed","item":{"type":"agent_message","text":"Fixed the issue."}}\n'
        '{"type":"turn.completed","usage":{"input_tokens":12,"output_tokens":4}}\n'
    )
    monkeypatch.setattr(
        driver.subprocess, "run",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args, 3, stdout=raw_jsonl, stderr="provider diagnostic\n"),
    )
    raw_path = tmp_path / "codex.jsonl"
    readable_path = tmp_path / "codex.log"

    result = driver.command(["codex", "exec", "--json"], stdin="exact prompt",
                            log=readable_path, json_log=raw_path, check=False)

    assert result.returncode == 3
    assert result.stdout == raw_jsonl + "provider diagnostic\n"
    assert raw_path.read_text() == raw_jsonl
    assert "Fixed the issue." in readable_path.read_text()
    assert "turn.completed" in readable_path.read_text()
    assert "provider diagnostic" in readable_path.read_text()
    assert "input_tokens" in raw_path.read_text()


def test_evaluation_streams_progress_before_exit(tmp_path, monkeypatch, capsys):
    log = tmp_path / "evaluation.log"
    acknowledged = tmp_path / "progress-seen"
    stdout = sys.stdout

    class Console:
        def write(self, output):
            if "\rEvaluating 1/2" in output:
                acknowledged.touch()
            return stdout.write(output)

        def flush(self):
            stdout.flush()

    monkeypatch.setattr(sys, "stdout", Console())
    script = r"""
import sys
import time
from pathlib import Path

sys.stderr.write("\rEvaluating 1/2")
sys.stderr.flush()
acknowledged = Path(sys.argv[1])
deadline = time.monotonic() + 3
while not acknowledged.exists():
    if time.monotonic() >= deadline:
        sys.exit(99)
    time.sleep(0.01)
sys.stderr.write("\rEvaluating 2/2\n")
sys.stderr.flush()
print("Evaluation summary", flush=True)
sys.exit(3)
"""
    returncode = driver._stream_evaluation(
        [sys.executable, "-c", script, str(acknowledged)], cwd=tmp_path, log=log)

    assert returncode == 3
    progress = "\rEvaluating 1/2\rEvaluating 2/2\n"
    assert progress in capsys.readouterr().out
    assert progress.encode() in log.read_bytes()
    assert b"Evaluation summary" in log.read_bytes()


def test_default_sample_and_dataset_size(run_driver, rows):
    result, output, _ = run_driver()
    assert result == 0
    assert "Dataset: SWE-bench/SWE-bench_Lite (test split, 10 instances)" in output
    assert selected(output) == [r["instance_id"] for r in random.Random(0).sample(rows, 1)]


def test_seeded_sample_is_reproducible_and_distinct(run_driver, rows):
    result, output, _ = run_driver("--count", "4", "--seed", "42")
    assert result == 0
    sample = selected(output)
    assert sample == [r["instance_id"] for r in random.Random(42).sample(rows, 4)]
    assert len(set(sample)) == 4
    assert sample == selected(run_driver("--count", "4", "--seed", "42")[1])
    assert sample != selected(run_driver("--count", "4", "--seed", "43")[1])


def test_select_all_and_negative_seed(run_driver, rows):
    result, output, _ = run_driver("--count", "10", "--seed", "-1")
    assert result == 0
    assert set(selected(output)) == {r["instance_id"] for r in rows}


@pytest.mark.parametrize("seed", ["0", "42", "-1"])
def test_zero_count_selects_all_in_dataset_order_regardless_of_seed(run_driver, rows, seed):
    result, output, _ = run_driver("--count", "0", "--seed", seed)
    assert result == 0
    assert selected(output) == [r["instance_id"] for r in rows]


def test_zero_count_with_empty_dataset(run_driver):
    result, output, _ = run_driver("--count", "0", dataset_rows=[])
    assert result == 0
    assert "Dataset: SWE-bench/SWE-bench_Lite (test split, 0 instances)" in output
    assert "Selected (0): " in output


@pytest.mark.parametrize("empty,count,available", [(False, "11", 10), (True, "1", 0)])
def test_count_exceeding_dataset_and_empty_dataset(run_driver, empty, count, available):
    result, _, error = run_driver("--count", count, dataset_rows=[] if empty else None)
    assert result == 2
    assert f"dataset contains only {available}" in error


def test_invalid_count(run_driver):
    result, _, error = run_driver("--count", "-1")
    assert result == 2
    assert "--count must be nonnegative" in error


def test_invalid_workers(run_driver):
    result, _, error = run_driver("--evaluation-workers", "0")
    assert result == 2
    assert "--evaluation-workers must be positive" in error


@pytest.mark.parametrize("option", ["--generation-workers", "--evaluation-workers"])
def test_invalid_worker_options(run_driver, option):
    result, _, error = run_driver(option, "0")
    assert result == 2
    assert f"{option} must be positive" in error


def test_exact_ids_preserve_order_and_remove_duplicates(run_driver):
    result, output, _ = run_driver("--ids", "issue-2", "issue-1", "issue-2")
    assert result == 0
    assert selected(output) == ["issue-2", "issue-1"]


@pytest.mark.parametrize(
    "args,message",
    [
        (("--ids", "missing"), "Unknown instance IDs: missing"),
        (("--ids", "issue-1", "--count", "2"), "Use --ids alone"),
        (("--ids", "issue-1", "--count", "0"), "Use --ids alone"),
        (("--ids", "issue-1", "--seed", "1"), "Use --ids alone"),
        (("--start", "1"), "unrecognized arguments: --start 1"),
    ],
)
def test_unknown_ids_and_incompatible_options(run_driver, args, message):
    result, _, error = run_driver(*args)
    assert result == 2
    assert message in error


@pytest.mark.parametrize("use_task_repo", [False, True])
def test_actual_run_records_separate_generation_and_evaluation_durations(run_actual, use_task_repo):
    result, output, _, metadata = run_actual(use_task_repo=use_task_repo)

    assert result == 0
    assert metadata == {
        "run_id": "test-run",
        "assistant": "codex",
        "model": None,
        "reasoning_effort": None,
        "generation_duration_seconds": 2.5,
        "evaluation_duration_seconds": 5.0,
    }
    assert "Generation duration: 2.50 seconds" in output
    assert "SWE-bench evaluation duration: 5.00 seconds" in output
    assert output.rstrip().splitlines()[-1].startswith("Run metadata: ")


def test_explicit_missing_task_repo_is_rejected(run_actual, tmp_path):
    missing_repo = tmp_path / "missing"
    result, _, error, _ = run_actual(use_task_repo=False, extra_args=("--task-repo", str(missing_repo)))

    assert result == 2
    assert f"Task repository not found: {missing_repo}" in error


def test_skipped_evaluation_records_null_duration(run_actual):
    result, output, _, metadata = run_actual(skip_eval=True)

    assert result == 0
    assert metadata["evaluation_duration_seconds"] is None
    assert "SWE-bench evaluation duration: not run" in output


def test_generation_failure_still_writes_metadata_without_evaluation(run_actual):
    result, output, error, metadata = run_actual(generate_patch=False)

    assert result == 1
    assert metadata["generation_duration_seconds"] == 2.5
    assert metadata["evaluation_duration_seconds"] is None
    assert "Generation duration: 2.50 seconds" in output
    assert "SWE-bench evaluation duration: not run" in output
    assert "No patches to evaluate." in error


def test_evaluation_failure_records_elapsed_duration(run_actual):
    result, output, _, metadata = run_actual(eval_returncode=1)

    assert result == 1
    assert metadata["evaluation_duration_seconds"] == 5.0
    assert "SWE-bench evaluation duration: 5.00 seconds" in output


def test_evaluation_launch_exception_records_metadata(run_actual):
    result, _, error, metadata = run_actual(eval_raises=True, extra_args=("--model", "example"))
    assert result == 1
    assert "Evaluation failed to run: cannot launch evaluator" in error
    assert metadata["model"] == "example"
    assert metadata["evaluation_duration_seconds"] == 5.0


@pytest.mark.parametrize("assistant,effort", [("codex", "minimal"), ("copilot", "max")])
def test_selected_assistant_metadata_and_predictions(run_actual, tmp_path, assistant, effort):
    result, _, error, metadata = run_actual(
        skip_eval=True, extra_args=("--model", "example-model", "--reasoning-effort", effort,
                                    "--assistant", assistant))
    assert result == 0
    assert metadata["assistant"] == assistant
    assert metadata["model"] == "example-model"
    assert metadata["reasoning_effort"] == effort
    predictions = (tmp_path / "runs" / "test-run" / "predictions.jsonl").read_text().splitlines()
    assert json.loads(predictions[0])["model_name_or_path"] == f"{assistant}-cli"
    assert ("WARNING: Copilot sandbox" in error) == (assistant == "copilot")


@pytest.mark.parametrize("failure", ["assistant", "empty", "checkout"])
def test_copilot_failure_preserves_metadata(run_actual, failure):
    result, _, error, metadata = run_actual(
        extra_args=("--assistant", "copilot", "--model", "example", "--reasoning-effort", "high"),
        generate_patch=failure != "checkout", assistant_returncode=3 if failure == "assistant" else 0,
        empty_patch=failure == "empty")
    assert result == 1
    assert metadata["assistant"] == "copilot"
    assert metadata["model"] == "example"
    assert metadata["reasoning_effort"] == "high"
    assert metadata["evaluation_duration_seconds"] is None
    if failure == "assistant":
        assert "Copilot failed with exit code 3; see copilot.log" in error
    elif failure == "empty":
        assert "Copilot produced no patch" in error


@pytest.mark.parametrize("args", [
    ("--assistant", "other"),
    ("--assistant", "copilot", "--allow-network"),
    ("--assistant", "copilot", "--reasoning-effort", "minimal"),
    ("--assistant", "codex", "--reasoning-effort", "max"),
])
def test_invalid_assistant_options(run_driver, args):
    result, _, _ = run_driver(*args)
    assert result == 2


def test_assistant_specific_help(capsys):
    with pytest.raises(SystemExit) as exc:
        driver.parser(["--assistant", "copilot", "--help"]).parse_args(["--assistant", "copilot", "--help"])
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "--allow-network" not in output
    assert "--reasoning-effort {low,medium,high,xhigh,max}" in output


def test_codex_option_abbreviations_remain_supported(run_driver):
    result, _, _ = run_driver("--allow-net", "--skip-e")
    assert result == 0


def test_abbreviated_assistant_selects_correct_options(run_driver):
    result, _, _ = run_driver("--assist", "copilot", "--reasoning-effort", "max")
    assert result == 0


def test_only_selected_executable_is_checked(tmp_path, monkeypatch, capsys):
    dataset = types.ModuleType("datasets")
    dataset.load_dataset = lambda name, split: [{"instance_id": "issue-0"}]
    monkeypatch.setitem(sys.modules, "datasets", dataset)
    (tmp_path / "SWE-bench").mkdir()
    (tmp_path / "swe-bench-tasks").mkdir()
    checked = []

    def which(executable):
        checked.append(executable)
        return None if executable == "copilot" else f"/usr/bin/{executable}"

    monkeypatch.setattr("shutil.which", which)
    monkeypatch.setattr(sys, "argv", ["driver", "--root", str(tmp_path), "--assistant", "copilot"])
    with pytest.raises(SystemExit) as exc:
        driver.main()
    assert exc.value.code == 2
    assert checked == ["git", "copilot"]
    assert "Executable not found on PATH: copilot" in capsys.readouterr().err


def test_partial_failure_still_evaluates_successful_patch(tmp_path, monkeypatch):
    dataset = types.ModuleType("datasets")
    dataset.load_dataset = lambda name, split: [
        {"instance_id": f"issue-{i}", "problem_statement": "Fix it", "repo": "org/repo", "base_commit": "abc"}
        for i in range(2)
    ]
    monkeypatch.setitem(sys.modules, "datasets", dataset)
    (tmp_path / "SWE-bench").mkdir()
    (tmp_path / "swe-bench-tasks").mkdir()
    monkeypatch.setattr("shutil.which", lambda exe: f"/usr/bin/{exe}")
    monkeypatch.setattr(sys, "argv", ["driver", "--root", str(tmp_path), "--run-id", "partial",
                                     "--count", "0", "--assistant", "copilot"])
    commands = []

    def fake_command(args, **kwargs):
        commands.append(args)
        if args[0] == "copilot" and kwargs["cwd"].parent.name == "issue-0":
            return subprocess.CompletedProcess(args, 1, stdout="failed")
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            stdout = "abc\n"
        elif args[:3] == ["git", "diff", "--binary"]:
            stdout = "diff --git a/file b/file\n"
        else:
            stdout = ""
        return subprocess.CompletedProcess(args, 0, stdout=stdout)

    def fake_evaluation(args, *, cwd, log):
        commands.append(args)
        return 0

    monkeypatch.setattr(driver, "command", fake_command)
    monkeypatch.setattr(driver, "_stream_evaluation", fake_evaluation)
    assert driver.main() == 1
    run_dir = tmp_path / "runs" / "partial"
    statuses = json.loads((run_dir / "generation_status.json").read_text())
    assert [status["status"] for status in statuses] == ["generation_failed", "patch_generated"]
    predictions = [json.loads(line) for line in (run_dir / "predictions.jsonl").read_text().splitlines()]
    assert [prediction["instance_id"] for prediction in predictions] == ["issue-1"]
    assert any(args[0] == "swebench" for args in commands)


def test_workers_alias_remains_evaluation_compatibility(run_driver):
    args = run_driver("--workers", "2")
    assert args[0] == 0


def test_generation_workers_limit_concurrency_and_preserve_order(tmp_path, monkeypatch):
    dataset = types.ModuleType("datasets")
    dataset.load_dataset = lambda name, split: [
        {"instance_id": f"issue-{i}", "problem_statement": "Fix it",
         "repo": "org/repo", "base_commit": "abc"}
        for i in range(3)
    ]
    monkeypatch.setitem(sys.modules, "datasets", dataset)
    (tmp_path / "SWE-bench").mkdir()
    (tmp_path / "swe-bench-tasks").mkdir()
    monkeypatch.setattr("shutil.which", lambda exe: f"/usr/bin/{exe}")
    monkeypatch.setattr(sys, "argv", [
        "driver", "--root", str(tmp_path), "--run-id", "parallel",
        "--count", "0", "--generation-workers", "2", "--skip-eval",
    ])

    active = 0
    maximum = 0

    def fake_command(args, **kwargs):
        nonlocal active, maximum
        if args[0] in ("codex", "copilot"):
            active += 1
            maximum = max(maximum, active)
            try:
                import time
                time.sleep(0.01)
            finally:
                active -= 1
            return subprocess.CompletedProcess(args, 0, stdout="")
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, stdout="abc\n")
        if args[:3] == ["git", "diff", "--binary"]:
            return subprocess.CompletedProcess(args, 0, stdout="diff --git a/file b/file\n")
        return subprocess.CompletedProcess(args, 0, stdout="")

    monkeypatch.setattr(driver, "command", fake_command)
    assert driver.main() == 0
    assert maximum == 2

    run_dir = tmp_path / "runs" / "parallel"
    statuses = json.loads((run_dir / "generation_status.json").read_text())
    assert [status["instance_id"] for status in statuses] == ["issue-0", "issue-1", "issue-2"]
    predictions = [json.loads(line) for line in (run_dir / "predictions.jsonl").read_text().splitlines()]
    assert [prediction["instance_id"] for prediction in predictions] == ["issue-0", "issue-1", "issue-2"]


@pytest.mark.parametrize("returncode", [0, 7])
@pytest.mark.parametrize("use_task_repo", [False, True])
def test_skip_generation_evaluates_saved_predictions(tmp_path, monkeypatch, returncode, use_task_repo):
    run_dir = tmp_path / "runs" / "saved"
    run_dir.mkdir(parents=True)
    sb_dir = tmp_path / "SWE-bench"
    sb_dir.mkdir()
    task_repo = tmp_path / "swe-bench-tasks"
    task_args = []
    if use_task_repo:
        task_repo.mkdir()
        task_args = ["--task-repo", str(task_repo)]
    artifacts = {
        "predictions.jsonl": json.dumps({
            "instance_id": "issue-0", "model_name_or_path": "codex-cli", "model_patch": "patch",
        }) + "\n",
        "run_metadata.json": '{"generation_duration_seconds": 42}\n',
        "generation_status.json": "[]\n",
    }
    for name, content in artifacts.items():
        (run_dir / name).write_text(content)

    monkeypatch.setitem(sys.modules, "datasets", None)
    monkeypatch.setattr("shutil.which", {"swebench": "/bin/swebench", "docker": "/bin/docker"}.get)
    monkeypatch.setattr(sys, "argv", [
        "driver", "--root", str(tmp_path), "--skip-generation", "--run-id", "saved",
        "--evaluation-workers", "3", *task_args,
    ])

    def evaluate(args, *, cwd, log):
        assert args == [
            "swebench", "eval", "lite", "-p", str(run_dir / "predictions.jsonl"),
            "--run-id", "saved", *task_args, "-j", "3",
        ]
        assert cwd == sb_dir
        assert log == run_dir / "evaluation.log"
        log.write_text("evaluation output")
        return returncode

    monkeypatch.setattr(driver, "_stream_evaluation", evaluate)
    assert driver.main() == returncode
    assert (run_dir / "evaluation.log").read_text() == "evaluation output"
    for name, content in artifacts.items():
        assert (run_dir / name).read_text() == content


@pytest.mark.parametrize(("args", "content", "message"), [
    ([], None, "requires --run-id"),
    (["--run-id", "saved", "--skip-eval"], None, "cannot be combined with --skip-eval"),
    (["--run-id", "saved", "--dry-run"], None, "cannot be combined with --dry-run"),
    (["--run-id", "saved", "--overwrite"], None, "cannot be combined with --overwrite"),
    (["--run-id", "saved"], None, "Cannot read predictions"),
    (["--run-id", "saved"], "\n", "No predictions"),
    (["--run-id", "saved"], "this is not JSON", "Cannot read predictions"),
    (["--run-id", "saved"], "{}", "Invalid prediction"),
])
def test_skip_generation_rejects_invalid_input(tmp_path, monkeypatch, capsys, args, content, message):
    if content is not None:
        run_dir = tmp_path / "runs" / "saved"
        run_dir.mkdir(parents=True)
        (run_dir / "predictions.jsonl").write_text(content)
    monkeypatch.setattr(sys, "argv", ["driver", "--root", str(tmp_path), "--skip-generation", *args])
    with pytest.raises(SystemExit) as exc:
        driver.main()
    assert exc.value.code == 2
    assert message in capsys.readouterr().err
