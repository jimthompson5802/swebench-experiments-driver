---
title: SWE-bench Experiments Driver
description: Run and evaluate coding assistants on SWE-bench Lite issues.
---

`run_swebench.py` runs Codex CLI or GitHub Copilot CLI on issues from the SWE-bench Lite test split. It checks out each issue's base commit, saves the assistant's changes as a patch, and evaluates the generated patches with the SWE-bench Docker harness. Codex remains the default assistant.

## Setup

Install Python 3.10 or later, Git, and the authenticated CLI for the assistant you select. Install Docker and start it before running the benchmark. See the [SWE-bench Docker setup guide](https://www.swebench.com/SWE-bench/guides/docker_setup/) and the [GitHub Copilot CLI setup guide](https://docs.github.com/en/copilot/how-tos/copilot-cli/cli-getting-started).

From the driver directory, create and activate a local virtual environment, then install the packages captured from the workspace environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The requirements file captures the test environment, including pytest. The driver also needs the `datasets` package and the SWE-bench CLI, which are installed separately below.

Set `SWEBENCH_EXPERIMENTS_DIR` to an absolute path of your choice for the checkouts and run artifacts. If you already have the checkouts elsewhere, skip cloning them, install from your existing SWE-bench checkout, and pass their locations with `--swebench-dir` and `--task-repo` when running the driver.

```bash
SWEBENCH_EXPERIMENTS_DIR="/path/to/swebench-experiments"
mkdir -p "$SWEBENCH_EXPERIMENTS_DIR"
git clone https://github.com/SWE-bench/SWE-bench.git "$SWEBENCH_EXPERIMENTS_DIR/SWE-bench"
git clone --depth 1 https://github.com/SWE-bench/swe-bench-tasks.git "$SWEBENCH_EXPERIMENTS_DIR/swe-bench-tasks"

python -m pip install datasets -e "$SWEBENCH_EXPERIMENTS_DIR/SWE-bench"

codex --version
docker info
swebench eval --help
```

See the [SWE-bench quickstart](https://www.swebench.com/SWE-bench/guides/quickstart/) and [CLI reference](https://www.swebench.com/SWE-bench/reference/cli/).

For Copilot runs, install and authenticate GitHub Copilot CLI separately. The installed version must support `--sandbox`, `--no-ask-user`, `--allow-tool`, `--disable-builtin-mcps`, `--excluded-tools`, and, when selected, `--model` and `--reasoning-effort`. Check `copilot --help` and the [Copilot CLI command reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference). Unsupported CLI options cause the assistant invocation to fail; check the Copilot log for details.

> [!WARNING]
> Copilot runs request local sandboxing and allow file edits and shell commands. Sandbox availability and restrictions depend on the host and Copilot configuration; an unsupported sandbox can fall back to unsandboxed execution. Built-in file tools enforce sandbox policy on a best-effort basis. Disabling built-in MCP servers and `web_fetch` does not prevent shell network access or other configured tools from accessing external content. The driver disables the inherited `COPILOT_ALLOW_ALL` environment setting for the Copilot subprocess, but saved approvals, configuration, and enterprise policies can still affect permissions. Use independently configured isolation and network controls if those restrictions are required. See [GitHub's local sandbox documentation](https://docs.github.com/en/copilot/concepts/security-governance-and-network-settings/about-cloud-and-local-sandboxes).

## Run the driver

Run these examples from the driver directory with the virtual environment active. In a new shell, set `SWEBENCH_EXPERIMENTS_DIR` again and reactivate the virtual environment with `source .venv/bin/activate`. The `--root` argument tells the driver where to look for both checkouts and where to write run artifacts.

Preview a randomly selected issue. This loads the dataset and prints the test-split size and selection without cloning a task workspace, calling Codex, or running Docker.

```bash
python run_swebench.py --root "$SWEBENCH_EXPERIMENTS_DIR" --dry-run
```

Generate and evaluate a patch for the selected issue. The driver handles one issue and uses one evaluation worker by default.

```bash
python run_swebench.py --root "$SWEBENCH_EXPERIMENTS_DIR" --run-id first-run
```

Select Copilot explicitly to generate a patch with its CLI:

```bash
python run_swebench.py --root "$SWEBENCH_EXPERIMENTS_DIR" \
  --assistant copilot --model MODEL-NAME --reasoning-effort high --skip-eval --run-id copilot-run
```

To select a random batch without replacement, set the number of issues with `--count` and optionally set the random seed with `--seed`. The default seed is `0`. The same seed and count reproduce the selection when dataset contents and ordering and Python sampling behavior are unchanged. Set `--count 0` to select all issues in dataset order; the seed has no effect in this mode. Alternatively, pass one or more exact instance IDs with `--ids`. Use `--skip-eval` to generate patches and predictions only. The driver still checks for both checkouts and all required executables in this mode.

```bash
python run_swebench.py --root "$SWEBENCH_EXPERIMENTS_DIR" \
  --seed 10 --count 3 --workers 2 --run-id batch-10
python run_swebench.py --root "$SWEBENCH_EXPERIMENTS_DIR" \
  --ids sympy__sympy-20590 --skip-eval --run-id sympy-patch
python run_swebench.py --help
```

## Command-line arguments

| Argument | Default | Behavior |
| --- | --- | --- |
| `--assistant {codex,copilot}` | `codex` | Selects the coding assistant and its executable. |
| `--count N` | `1` | Randomly selects `N` distinct issues, or selects all in dataset order when `N` is `0`. Must be nonnegative and no greater than the test-split size. |
| `--seed N` | `0` | Sets the integer seed for reproducible random sampling. Ignored when `--count` is `0`. |
| `--ids ID [ID ...]` | Select by count and seed | Selects exact instance IDs in the order given, omitting duplicates. Unknown IDs cause an error. Use this in place of `--seed` and `--count`. |
| `--root PATH` | `~/swebench-experiments` | Sets the output directory's parent and the base path for both checkouts. Pass the directory chosen during setup. |
| `--swebench-dir PATH` | `<root>/SWE-bench` | Points to the installed SWE-bench checkout. The driver runs evaluation from this directory. |
| `--task-repo PATH` | `<root>/swe-bench-tasks` | Points to the SWE-bench task repository used by the evaluator. |
| `--run-id ID` | `<assistant>-lite-YYYYMMDD-HHMMSS` (UTC) | Names the run directory and the evaluation run. Use letters, digits, dots, underscores, or hyphens. |
| `--workers N` | `1` | Sets the number of parallel evaluation workers. Must be positive. |
| `--model NAME` | Selected CLI default | Selects the model used for patch generation. Supported names depend on the assistant and account. |
| `--reasoning-effort LEVEL` | Selected CLI default | Codex accepts `minimal`, `low`, `medium`, `high`, and `xhigh`. Copilot accepts `low`, `medium`, `high`, `xhigh`, and `max`; availability can depend on the model. |
| `--skip-eval` | Off | Generates patches and predictions, then skips evaluation. The driver still checks for both checkouts and all required executables. |
| `--dry-run` | Off | Loads the dataset and prints the run ID and selected issues before checking prerequisites or creating workspaces. |
| `--overwrite` | Off | Allows reuse of a nonempty run directory and deletes and recreates the existing directories for the selected issues. |
| `--allow-network` | Off | Codex only. Enables network access inside the Codex workspace-write sandbox. The driver's own dataset download and Git clones run separately. This option is rejected for Copilot. |
| `-h`, `--help` | Off | Prints the available arguments and exits. |

## Run tests

With the virtual environment active and the requirements installed, run the tests from the driver directory:

```bash
python -m pytest -v
```

The tests use a stub dataset and do not require dataset downloads, Codex, Copilot, or Docker.

## Assistant adapters

The shared interface in `assistants/interface.py` describes how an adapter registers options and runs an assistant. The Codex and Copilot adapters own their CLI-specific commands and settings. The driver owns the shared checkout, prompt, patch extraction, and evaluation workflow. To add an assistant, implement the interface, register it in the driver, and add tests for its command and permissions.

## Find results

Each run writes to `$SWEBENCH_EXPERIMENTS_DIR/runs/<run-id>/` when you pass `--root` as shown above. When you omit `--run-id`, the driver generates a timestamped ID. Use a fresh ID to get a fresh evaluation. SWE-bench can reuse cached results when you repeat an ID, even if you regenerate patches with `--overwrite`. [SWE-bench CLI reference](https://www.swebench.com/SWE-bench/reference/cli/#swebench-eval-dataset)

| Path relative to the run directory | Contents |
| --- | --- |
| `generation_status.json` | Per-issue patch generation status and any errors |
| `run_metadata.json` | Run ID, assistant, supplied model and reasoning effort, and generation and evaluation durations |
| `predictions.jsonl` | Generated patches in SWE-bench prediction format |
| `<instance-id>/` | Repository checkout, issue, prompt, metadata, `codex.log` or `copilot.log`, and `model.patch` when generated |
| `evaluation.log` | SWE-bench command output when evaluation runs |

In run metadata, a `null` model or reasoning effort means no override was supplied; it does not identify the effective CLI default. The harness writes test results under `logs/evaluation/<run-id>/` inside the SWE-bench checkout. Check its `results.json` for the evaluation outcome. The driver can evaluate the patches it generated even if some issues failed during generation. It returns a nonzero exit code if any selected issue fails to produce a patch or if the evaluation command fails.
