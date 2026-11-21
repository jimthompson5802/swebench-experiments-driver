import json
import random
import sys
import types
import subprocess

import pytest

import run_swebench_codex as driver


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
    task_repo.mkdir()
    monkeypatch.setattr("shutil.which", lambda executable: f"/usr/bin/{executable}")
    # Keep elapsed durations deterministic while avoiding wall-clock delays in tests.
    monkeypatch.setattr(driver.time, "perf_counter", iter([100.0, 102.5, 200.0, 205.0]).__next__)

    def run(*, generate_patch=True, eval_returncode=0, skip_eval=False):
        argv = [
            "driver", "--root", str(tmp_path), "--run-id", "test-run",
            "--swebench-dir", str(sb_dir), "--task-repo", str(task_repo), "--ids", "issue-0",
        ]
        if skip_eval:
            argv.append("--skip-eval")
        monkeypatch.setattr(sys, "argv", argv)

        def fake_command(args, **kwargs):
            if args[0] == "git" and args[1] == "clone" and not generate_patch:
                raise RuntimeError("simulated generation failure")
            if args[0] == "git" and args[1:3] == ["rev-parse", "HEAD"]:
                stdout = "abc123\n"
            elif args[0] == "git" and args[1:3] == ["diff", "--binary"]:
                stdout = "diff --git a/file.py b/file.py\n"
            else:
                stdout = ""
            returncode = eval_returncode if args[0] == "swebench" else 0
            return subprocess.CompletedProcess(args, returncode, stdout=stdout)

        monkeypatch.setattr(driver, "command", fake_command)
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
    assert "--count must be nonnegative and --workers must be positive" in error


def test_invalid_workers(run_driver):
    result, _, error = run_driver("--workers", "0")
    assert result == 2
    assert "--workers must be positive" in error


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


def test_actual_run_records_separate_generation_and_evaluation_durations(run_actual):
    result, output, _, metadata = run_actual()

    assert result == 0
    assert metadata == {
        "run_id": "test-run",
        "generation_duration_seconds": 2.5,
        "evaluation_duration_seconds": 5.0,
    }
    assert "Generation duration: 2.50 seconds" in output
    assert "SWE-bench evaluation duration: 5.00 seconds" in output
    assert output.rstrip().splitlines()[-1].startswith("Run metadata: ")


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