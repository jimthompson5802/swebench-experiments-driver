|Test Cases|Coding Assistant|Model|Reasoning|Usage|Resolution %|
|----------|:--------------:|---------|-----|-----|------------|
|SWEBench Lite (300)|Codex|gpt-6.2-sol|Medium| ~64% of weekly quota| Insufficient Resources for Evaluation |
|SWEBench Lite (100)|Codex|gpt-6.2-sol|Medium| ~27% of weekly quota| 74% (74 out of 100)|



Example evaluation command

```bash
SWEBENCH_EXPERIMENTS_DIR="/Volumes/Extreme SSD/swebench-experiment-results/swebench-experiments"

cd $SWEBENCH_EXPERIMENTS_DIR

swebench eval lite -p "$SWEBENCH_EXPERIMENTS_DIR/runs/codex-lite/predictions.jsonl" --run-id codex-lite --task-repo "$SWEBENCH_EXPERIMENTS_DIR/swe-bench-tasks" -j 6
```


## Results codex-100

```
python run_swebench.py --root "$SWEBENCH_EXPERIMENTS_DIR" \
    --skip-generation --run-id codex-10 \
    --evaluation-workers 4
```

### Run Metadata JSON ([run_metadata.json](./artifacts/codex-100-run-metadata.json))

```
  "run_id": "codex-100",
  "assistant": "codex",
  "model": "gpt-6.2-sol",
  "reasoning_effort": "medium",
```

### Evaluation Log ([`evaluation.log`](./artifacts/codex-100-evaluation.log))

Summary

```
Total instances: 2294
Instances submitted: 100
Instances completed: 100
Instances incomplete: 2194
Instances resolved: 74
Instances unresolved: 26
Instances with likely infrastructure failures: 0
Instances with ambiguous failures: 0
Instances with empty patches: 0
Instances with errors: 0
Unstopped containers: 0
Unremoved images: 100
Report written to logs/evaluation/codex-100/results.json

```

### Test Case Results JSON

Over all summary of the 100 test cases: [`results.json](./artifacts/codex-100-results.json)

- Example of **resolved** test case ["matplotlib__matplotlib-23476"](./artifacts/codex-100-test-case-resolved-example.json)

- Example of **unresolved** test case ["scikit-learn__scikit-learn-10508"](./artifacts/codex-100-test-case-unresolved-example.json)