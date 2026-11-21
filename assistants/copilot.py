"""GitHub Copilot CLI adapter."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from .interface import CommandRunner


class CopilotAssistant:
    name = "copilot"
    display_name = "Copilot"
    executable = "copilot"
    prediction_name = "copilot-cli"
    run_prefix = "copilot-lite-"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--model", help="Optional Copilot model name (uses CLI default otherwise)")
        parser.add_argument("--reasoning-effort", choices=["low", "medium", "high", "xhigh", "max"],
                            help="Optional Copilot reasoning effort override")

    def __init__(self, args: argparse.Namespace) -> None:
        self.model = args.model
        self.reasoning_effort = args.reasoning_effort

    def run(self, workspace: Path, prompt: str, issue_dir: Path,
            command: CommandRunner) -> None:
        args = ["copilot", "--no-ask-user", "--sandbox", "--allow-tool=write,shell",
            "--disable-builtin-mcps", "--excluded-tools=web_fetch", "--output-format=json"]
        if self.model:
            args += ["--model", self.model]
        if self.reasoning_effort:
            args += ["--reasoning-effort", self.reasoning_effort]
        # Do not let an inherited bypass setting grant blanket permissions or trust the checkout.
        env = os.environ.copy()
        env["COPILOT_ALLOW_ALL"] = "false"
        result = command(args, cwd=workspace, stdin=prompt, log=issue_dir / "copilot.log",
                 json_log=issue_dir / "copilot.jsonl", check=False, env=env)
        if result.returncode:
            raise RuntimeError(f"Copilot failed with exit code {result.returncode}; see copilot.log")