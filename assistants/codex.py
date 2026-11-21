"""Codex CLI adapter."""
from __future__ import annotations

import argparse
from pathlib import Path

from .interface import CommandRunner


class CodexAssistant:
    name = "codex"
    display_name = "Codex"
    executable = "codex"
    prediction_name = "codex-cli"
    run_prefix = "codex-lite-"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--model", help="Optional Codex model name (uses CLI default otherwise)")
        parser.add_argument("--reasoning-effort", choices=["minimal", "low", "medium", "high", "xhigh"],
                            help="Optional Codex model_reasoning_effort override")
        parser.add_argument("--allow-network", action="store_true",
                            help="Allow Codex workspace-write network access (off by default)")

    def __init__(self, args: argparse.Namespace) -> None:
        self.model = args.model
        self.reasoning_effort = args.reasoning_effort
        self.allow_network = args.allow_network

    def run(self, workspace: Path, prompt: str, issue_dir: Path,
            command: CommandRunner) -> None:
        args = ["codex", "exec", "--sandbox", "workspace-write", "--cd", str(workspace)]
        if self.model:
            args += ["--model", self.model]
        if self.reasoning_effort:
            args += ["-c", f'model_reasoning_effort="{self.reasoning_effort}"']
        if self.allow_network:
            args += ["-c", "sandbox_workspace_write.network_access=true"]
        args += ["-"]
        result = command(args, cwd=workspace, stdin=prompt, log=issue_dir / "codex.log", check=False)
        if result.returncode:
            raise RuntimeError(f"Codex failed with exit code {result.returncode}; see codex.log")