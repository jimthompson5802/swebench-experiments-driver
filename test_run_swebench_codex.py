import io
import random
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import run_swebench_codex as driver


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{"instance_id": f"issue-{i}"} for i in range(10)]
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)

    def run_driver(self, *args, rows=None):
        dataset = types.ModuleType("datasets")
        dataset.load_dataset = lambda name, split: self.rows if rows is None else rows
        stdout, stderr = io.StringIO(), io.StringIO()
        argv = ["driver", "--root", self.root.name, "--dry-run", *args]
        with patch.dict(sys.modules, {"datasets": dataset}), patch.object(sys, "argv", argv):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                try:
                    result = driver.main()
                except SystemExit as exc:
                    result = exc.code
        return result, stdout.getvalue(), stderr.getvalue()

    def selected(self, output):
        line = next(line for line in output.splitlines() if line.startswith("Selected ("))
        return line.split(": ", 1)[1].split(", ")

    def test_default_sample_and_dataset_size(self):
        result, output, _ = self.run_driver()
        self.assertEqual(result, 0)
        self.assertIn("Dataset: SWE-bench/SWE-bench_Lite (test split, 10 instances)", output)
        self.assertEqual(self.selected(output), [r["instance_id"] for r in random.Random(0).sample(self.rows, 1)])

    def test_seeded_sample_is_reproducible_and_distinct(self):
        result, output, _ = self.run_driver("--count", "4", "--seed", "42")
        self.assertEqual(result, 0)
        selected = self.selected(output)
        self.assertEqual(selected, [r["instance_id"] for r in random.Random(42).sample(self.rows, 4)])
        self.assertEqual(len(set(selected)), 4)
        self.assertEqual(selected, self.selected(self.run_driver("--count", "4", "--seed", "42")[1]))
        self.assertNotEqual(selected, self.selected(self.run_driver("--count", "4", "--seed", "43")[1]))

    def test_select_all_and_negative_seed(self):
        result, output, _ = self.run_driver("--count", "10", "--seed", "-1")
        self.assertEqual(result, 0)
        self.assertEqual(set(self.selected(output)), {r["instance_id"] for r in self.rows})

    def test_count_exceeding_dataset_and_empty_dataset(self):
        for rows, count in ((self.rows, "11"), ([], "1")):
            with self.subTest(count=count):
                result, _, error = self.run_driver("--count", count, rows=rows)
                self.assertEqual(result, 2)
                self.assertIn(f"dataset contains only {len(rows)}", error)

    def test_invalid_count(self):
        result, _, error = self.run_driver("--count", "0")
        self.assertEqual(result, 2)
        self.assertIn("--count and --workers must be positive", error)

    def test_exact_ids_preserve_order_and_remove_duplicates(self):
        result, output, _ = self.run_driver("--ids", "issue-2", "issue-1", "issue-2")
        self.assertEqual(result, 0)
        self.assertEqual(self.selected(output), ["issue-2", "issue-1"])

    def test_unknown_ids_and_incompatible_options(self):
        for args, message in (
            (("--ids", "missing"), "Unknown instance IDs: missing"),
            (("--ids", "issue-1", "--count", "2"), "Use --ids alone"),
            (("--ids", "issue-1", "--seed", "1"), "Use --ids alone"),
            (("--start", "1"), "unrecognized arguments: --start 1"),
        ):
            with self.subTest(args=args):
                result, _, error = self.run_driver(*args)
                self.assertEqual(result, 2)
                self.assertIn(message, error)


if __name__ == "__main__":
    unittest.main()