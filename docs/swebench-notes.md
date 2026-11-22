|Test Cases|Coding Assistant|Model|Reasoning|Usage|Resolution %|
|----------|:--------------:|---------|-----|-----|------------|
|SWEBench Lite (300)|Codex|gpt-6.2-sol|Medium| ~64% of weekly quota| |


Example evaluation command

```bash
swebench eval lite -p $SWEBENCH_EXPERIMENTS_DIR/runs/codex-lite/predictions.jsonl --run-id codex-lite --task-repo $SWEBENCH_EXPERIMENTS_DIR/swe-bench-tasks -j 4
```