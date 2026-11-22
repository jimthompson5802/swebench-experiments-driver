|Test Cases|Coding Assistant|Model|Reasoning|Usage|Resolution %|
|----------|:--------------:|---------|-----|-----|------------|
|SWEBench Lite (300)|Codex|gpt-6.2-sol|Medium| ~64% of weekly quota| |


Example evaluation command

```bash
SWEBENCH_EXPERIMENTS_DIR="/Volumes/Extreme SSD/swebench-experiment-results/swebench-experiments"

cd $SWEBENCH_EXPERIMENTS_DIR

swebench eval lite -p "$SWEBENCH_EXPERIMENTS_DIR/runs/codex-lite/predictions.jsonl" --run-id codex-lite --task-repo "$SWEBENCH_EXPERIMENTS_DIR/swe-bench-tasks" -j 6
```

```
python run_swebench.py --root "$SWEBENCH_EXPERIMENTS_DIR" \
    --skip-generation --run-id codex-10 \
    --evaluation-workers 4
```