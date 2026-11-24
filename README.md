# SWE-bench Experiments Driver

Run and evaluate coding assistants on SWE-bench Lite issues.

SWE-bench measures how well coding agents resolve real GitHub issues from open-source projects. For each issue, an agent starts from a specified repository revision and submits a patch. The benchmark runs tests to check whether the patch fixes the issue and preserves existing behavior. SWE-bench Lite is a curated subset of 300 issues designed to reduce evaluation cost. [Official SWE-bench homepage](https://www.swebench.com/)

`run_swebench.py` runs Codex CLI or GitHub Copilot CLI on issues from the SWE-bench Lite test split. It checks out each issue's base commit, saves the assistant's changes as a patch, and evaluates the generated patches with the SWE-bench Docker harness. Codex remains the default assistant.

For the work reported in this repo, the recorded experiments use a 100-issue subset of SWE-bench Lite because of limits in time, disk space and available coding assistant credits.

## Recorded experiments

The three runs below selected the same 100 SWE-bench Lite issues with seed `42`. Resolution rates use all 100 selected issues.
Both GPT-6.1-Terra runs produced patches for 99 issues and omitted `sphinx-doc__sphinx-8474` from evaluation.
The [workflow description](docs/swebench-workflow.md) traces patch generation and Docker evaluation. The [experiment notes](docs/swebench-notes.md) contain the run commands, logs, metadata, and examples of resolved and unresolved cases.

| Run | Model | Reasoning effort | Resolved / selected |
| --- | --- | --- | --- |
| [`codex-100`](docs/artifacts/codex-100-results.json) | `gpt-6.2-sol` | `medium` | 74 / 100 (74%) |
| [`codex-100-6.1-terra`](docs/artifacts/codex-100-62-terra-results.json) | `gpt-6.1-terra` | `medium` | 68 / 100 (68%) |
| [`copilot-100`](docs/artifacts/copilot-100-results.json) | `gpt-6.1-terra` | `medium` | 69 / 100 (69%)|

| Run | Patch generation | Docker evaluation | Total elapsed | Cloned workspaces |
| --- | ---: | ---: | ---: | ---: |
| `codex-100` | 45 min | 62 min | 1 hr 47 min | ~28 GB |
| `codex-100-6.1-terra` | 29 min | 62 min | 1 hr 31 min | ~28 GB |
| `copilot-100` | 44 min | 60 min | 1 hr 44 min | ~29 GB |

The Docker evaluation images took up about **71 GB** for the shared set of 100 images. Both GPT-6.1-Terra runs used the same 99 images. Together, the cloned workspaces and shared images occupied about **157 GB**, excluding Docker build cache, logs, and other artifacts. See the [storage estimates](docs/swebench-notes.md#estimated-disk-storage) for the measurement details.

## Analyze generation tokens and estimated costs

The [token usage notebook](notebooks/coding-assistant-tokens.ipynb) reports input and output tokens, cache reads and writes, and how many generation attempts had usable token data. It includes usage from failed attempts when available. Cost estimates use the checked-in [vendor rate snapshot](notebooks/coding-assistant-token-rates.json).

### Recorded token usage

| Run ID | Model | Attempts counted | Coverage | Total input | Cached input reads | Cache writes | Output |
| --- | --- | --- | --- | --- | --- | --- | --- |
| codex-100 | gpt-6.2-sol | 100/100 | Complete | 42,760,124 | 38,936,192 | 0 | 282,735 |
| codex-100-6.1-terra | gpt-6.1-terra | 100/100 | Complete | 25,878,714 | 24,342,784 | 0 | 150,684 |
| copilot-100 | gpt-6.1-terra | 100/100 | Complete | 51,152,386 | 48,583,842 | 2,563,075 | 465,774 |

### Standard token rates (USD per million)

OpenAI API Standard short-context pricing (30-minute cache writes) and GitHub Copilot default-tier pricing.

| Assistant | Model | Ordinary input | Cache reads | Cache writes | Output | Source |
| --- | --- | --- | --- | --- | --- | --- |
| codex | gpt-6.2-sol | $2.0 | $0.1 | $2.5 | $10.0 | [Vendor pricing](https://developers.openai.com/api/docs/models/gpt-6.2-sol) |
| codex | gpt-6.1-terra | $1.0 | $0.05 | $1.25 | $5.0 | [Vendor pricing](https://developers.openai.com/api/docs/models/gpt-6.1-terra) |
| copilot | gpt-6.1-terra | $1.0 | $0.05 | $1.25 | $5.0 | [Vendor pricing](https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing) |

### Estimated generation costs (USD)

These estimates apply the notebook’s checked-in rates to recorded usage. Average Cost divides the total by all 100 selected test cases per run. Actual charges depend on context tiers, cache retention, and plan billing.

| Run ID | Model | Coverage | Ordinary input | Cache reads | Cache writes | Output | Total | Average Cost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| codex-100 | gpt-6.2-sol | Complete | $7.6479 | $3.8936 | $0.0000 | $2.8274 | $14.3688 | $0.1437 |
| codex-100-6.1-terra | gpt-6.1-terra | Complete | $1.5359 | $1.2171 | $0.0000 | $0.7534 | $3.5065 | $0.0351 |
| copilot-100 | gpt-6.1-terra | Complete | $0.0055 | $2.4292 | $3.2038 | $2.3289 | $7.9674 | $0.0797 |

### Reproduce the analysis

1. Install the notebook kernel in the repository's local environment with `.venv/bin/python -m pip install ipykernel`.
2. Open the notebook in VS Code and select `.venv/bin/python` as its kernel.
3. Set `DATA_ROOT` to the directory passed to `--root` and set `RUN_IDS` to the runs you want to analyze. Run all cells.

Each run needs `run_metadata.json` with an explicit model, `generation_status.json`, and the per-issue `codex.jsonl` or `copilot.jsonl` logs under `DATA_ROOT / "runs" / run_id`. Use `--model` when generating patches for a run you plan to analyze. The checked-in experiment artifacts contain evaluation results and examples. The notebook reads the full generation logs from your experiment directory.

## Setup

Install Python 3.10 or later, Git, Docker, and the authenticated CLI for the assistant you select. Docker must be installed and running because the SWE-bench evaluator executes test environments in containers. See the [SWE-bench Docker setup guide](https://www.swebench.com/SWE-bench/guides/docker_setup/) and the [GitHub Copilot CLI setup guide](https://docs.github.com/en/copilot/how-tos/copilot-cli/cli-getting-started).

The driver retrieves the SWE-bench Lite test dataset from Hugging Face. Create a Hugging Face access token with read access to gated repositories, then set it in each shell where you run the driver:

```bash
export HF_TOKEN="hf_your_access_token"
```

Do not commit the token or add it to repository configuration. Replace `hf_your_access_token` with a token created in the Hugging Face account that has accepted the required SWE-bench dataset terms.

From the driver directory, create and activate a local virtual environment, then install the packages captured from the workspace environment:

```bash
git clone https://github.com/jimthompson5802/swebench-experiments-driver.git

cd swebench-experiments-driver

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The requirements file captures the test environment, including pytest. The driver also needs the `datasets` package and the SWE-bench CLI, which are installed separately below.

Set `SWEBENCH_EXPERIMENTS_DIR` to an absolute path of your choice for the checkouts and run artifacts. If you already have the checkouts elsewhere, pass their locations with `--swebench-dir` and `--task-repo` when running the driver.

```bash
SWEBENCH_EXPERIMENTS_DIR="/path/to/swebench-experiments"
mkdir -p "$SWEBENCH_EXPERIMENTS_DIR"
git clone https://github.com/SWE-bench/SWE-bench.git "$SWEBENCH_EXPERIMENTS_DIR/SWE-bench"
git clone --depth 1 https://github.com/SWE-bench/swe-bench-tasks.git "$SWEBENCH_EXPERIMENTS_DIR/swe-bench-tasks"

cd "$SWEBENCH_EXPERIMENTS_DIR/SWE-bench"
uv venv
source .venv/bin/activate
uv pip install -e .
uv pip install datasets

swebench eval --help
```

Run the driver with this environment active so it can import `datasets` and find the `swebench` executable on `PATH`. The [test setup](#run-tests) uses a separate environment inside this repository.

See the [SWE-bench quickstart](https://www.swebench.com/SWE-bench/guides/quickstart/) and [CLI reference](https://www.swebench.com/SWE-bench/reference/cli/).

For Copilot runs, install and authenticate GitHub Copilot CLI separately. The installed version must support `--sandbox`, `--no-ask-user`, `--allow-tool`, `--disable-builtin-mcps`, `--excluded-tools`, and `--output-format=json`. Model and reasoning overrides also require `--model` and `--reasoning-effort`. Check `copilot --help` and the [Copilot CLI command reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference). The per-issue Copilot log records errors from unsupported options.

> [!WARNING]
> Copilot runs request local sandboxing and allow file edits and shell commands. Sandbox availability and restrictions depend on the host and Copilot configuration; an unsupported sandbox can fall back to unsandboxed execution. Built-in file tools enforce sandbox policy on a best-effort basis. Disabling built-in MCP servers and `web_fetch` does not prevent shell network access or other configured tools from accessing external content. The driver disables the inherited `COPILOT_ALLOW_ALL` environment setting for the Copilot subprocess, but saved approvals, configuration, and enterprise policies can still affect permissions. Use independently configured isolation and network controls if those restrictions are required. See [GitHub's local sandbox documentation](https://docs.github.com/en/copilot/concepts/security-governance-and-network-settings/about-cloud-and-local-sandboxes).

## Run the driver

Run these examples from the driver directory. In a new shell, set `HF_TOKEN` and `SWEBENCH_EXPERIMENTS_DIR` again and activate the SWE-bench environment. Pass `--root` to use the configured directory for both checkouts and run artifacts.

```bash
source "$SWEBENCH_EXPERIMENTS_DIR/SWE-bench/.venv/bin/activate"
```

Preview a randomly selected issue. This loads the dataset and prints the test-split size and selection without cloning a task workspace, calling Codex, or running Docker.

```bash
python run_swebench.py --root "$SWEBENCH_EXPERIMENTS_DIR" --dry-run
```

Generate and evaluate a patch with Codex, the default assistant. Generation and evaluation each use one worker by default.

```bash
python run_swebench.py --root "$SWEBENCH_EXPERIMENTS_DIR" --run-id first-run
```

Select Copilot explicitly to generate a patch with its CLI.

```bash
python run_swebench.py --root "$SWEBENCH_EXPERIMENTS_DIR" \
  --assistant copilot --model MODEL-NAME --reasoning-effort high --skip-eval --run-id copilot-run
```

To select a random batch without replacement, set `--count` and optionally set `--seed`. The same seed and count reproduce the selection with the same dataset order and Python sampling behavior. Set `--count 0` to select all issues in dataset order or pass exact instance IDs with `--ids`.

Use `--skip-eval` to generate patches and predictions only. The driver still checks for both checkouts and for Git, the selected assistant CLI, `swebench`, and Docker. To evaluate saved predictions, use `--skip-generation` with the same root and run ID.

```bash
python run_swebench.py --root "$SWEBENCH_EXPERIMENTS_DIR" \
  --ids sympy__sympy-20590 --skip-eval --run-id sympy-patch
python run_swebench.py --root "$SWEBENCH_EXPERIMENTS_DIR" \
  --skip-generation --run-id sympy-patch
```

The second command reads `<root>/runs/sympy-patch/predictions.jsonl` and refreshes `evaluation.log`.
It preserves the saved predictions and `run_metadata.json` and only needs the two checkouts, `swebench`, and Docker.

```bash
python run_swebench.py --root "$SWEBENCH_EXPERIMENTS_DIR" \
  --assistant codex --run-id codex-10 --model gpt-6.2-sol --reasoning-effort medium \
  --seed 42 --count 10 --generation-workers 4 --evaluation-workers 4

python run_swebench.py --root "$SWEBENCH_EXPERIMENTS_DIR" \
  --assistant codex --run-id codex-10-6.1-terra --model gpt-6.1-terra --reasoning-effort medium \
  --seed 42 --count 10 --generation-workers 4 --evaluation-workers 4

python run_swebench.py --root "$SWEBENCH_EXPERIMENTS_DIR" \
  --assistant copilot --run-id copilot-10 --model gpt-6.1-terra --reasoning-effort medium \
  --seed 42 --count 10 --generation-workers 4 --evaluation-workers 4

python run_swebench.py --help
python run_swebench.py --assistant copilot --help
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
| `--generation-workers N` | `1` | Sets the number of patch-generation instances to run in parallel. Must be positive. |
| `--evaluation-workers N` | `1` | Sets the number of parallel SWE-bench evaluation workers. Must be positive. |
| `--workers N` | `1` | Deprecated compatibility alias for `--evaluation-workers`. |
| `--model NAME` | Selected CLI default | Selects the model used for patch generation. Supported names depend on the assistant and account. |
| `--reasoning-effort LEVEL` | Selected CLI default | Codex accepts `minimal`, `low`, `medium`, `high`, and `xhigh`. Copilot accepts `low`, `medium`, `high`, `xhigh`, and `max`; availability can depend on the model. |
| `--skip-generation` | Off | Evaluates saved predictions for an existing `--run-id`. Incompatible with `--skip-eval`, `--dry-run`, and `--overwrite`. |
| `--skip-eval` | Off | Generates patches and predictions, then skips evaluation. The driver still checks for both checkouts and all required executables. |
| `--dry-run` | Off | Loads the dataset and prints the run ID and selected issues before checking prerequisites or creating workspaces. |
| `--overwrite` | Off | Allows reuse of a nonempty run directory and deletes and recreates the existing directories for the selected issues. |
| `--allow-network` | Off | Codex only. Enables network access inside the Codex workspace-write sandbox. The driver's own dataset download and Git clones run separately. This option is rejected for Copilot. |
| `-h`, `--help` | Off | Prints the available arguments and exits. |

## Run tests

From the driver directory, use Python 3.10 or later to create a local test environment and install the pinned test dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -v
```

The tests use a stub dataset and do not require dataset downloads, Codex, Copilot, or Docker.

## Assistant adapters

The shared interface in `assistants/interface.py` describes how an adapter registers
options and runs an assistant. The Codex and Copilot adapters own their CLI-specific
commands and settings. The driver owns the shared checkout, prompt, patch extraction,
and evaluation workflow.

The driver builds the prompt from the issue description and saves a copy as
`prompt.txt`. It sends the same prompt through stdin. Codex reads stdin using the
trailing `-`; Copilot reads piped stdin without a prompt argument. JSON output changes
only stdout formatting, not prompt delivery. To add an assistant, implement the
interface, register it in the driver, and add tests for its command and permissions.

## Find results

Each run writes to `$SWEBENCH_EXPERIMENTS_DIR/runs/<run-id>/` when you pass `--root` as shown above. When you omit `--run-id`, the driver generates a timestamped ID. Use a fresh ID to get a fresh evaluation. SWE-bench can reuse cached results when you repeat an ID, even if you regenerate patches with `--overwrite`. [SWE-bench CLI reference](https://www.swebench.com/SWE-bench/reference/cli/#swebench-eval-dataset)

| Path relative to the run directory | Contents |
| --- | --- |
| `generation_status.json` | Per-issue patch generation status and any errors |
| `run_metadata.json` | Run ID, assistant, supplied model and reasoning effort, and generation and evaluation durations |
| `predictions.jsonl` | Generated patches in SWE-bench prediction format |
| `<instance-id>/` | Repository checkout, issue, prompt, metadata, readable `codex.log` or `copilot.log`, raw `codex.jsonl` or `copilot.jsonl`, and `model.patch` when generated |
| `evaluation.log` | SWE-bench command output when evaluation runs |

Both Codex and Copilot output JSONL event streams. Their event schemas and token usage
fields are provider-specific. The raw per-issue files preserve the original stdout
stream for later processing, including partial output from failed assistant runs.

In run metadata, a `null` model or reasoning effort means no override was supplied; it does not identify the effective CLI default. The harness writes test results under `logs/evaluation/<run-id>/` inside the SWE-bench checkout. Check its `results.json` for the evaluation outcome. The driver can evaluate the patches it generated even if some issues failed during generation. It returns a nonzero exit code if any selected issue fails to produce a patch or if the evaluation command fails.
