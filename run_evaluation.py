
import argparse
import json
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--predictions", required=True)
parser.add_argument("--task-repo", required=True)
parser.add_argument("--run-id", default="codex-lite")
parser.add_argument("--batch-size", type=int, default=10)
parser.add_argument("--workers", type=int, default=4)
args = parser.parse_args()

if args.batch_size < 1 or args.workers < 1:
    parser.error("batch-size and workers must be positive")

predictions = Path(args.predictions).expanduser().resolve()
with predictions.open() as f:
    ids = list(dict.fromkeys(
        row["instance_id"]
        for line in f
        if line.strip()
        for row in [json.loads(line)]
        if row.get("model_patch")
    ))

for start in range(0, len(ids), args.batch_size):
    batch = ids[start:start + args.batch_size]
    print(
        f"\nBatch {start // args.batch_size + 1}: "
        f"{len(batch)} instances",
        flush=True,
    )

    cmd = [
        "swebench", "eval", "lite",
        "-p", str(predictions),
        "--run-id", args.run_id,
        "--task-repo", args.task_repo,
        "-j", str(args.workers),
    ]
    for instance_id in batch:
        cmd.extend(["-i", instance_id])

    subprocess.run(cmd, check=True)

print("\nAll batches finished.")
