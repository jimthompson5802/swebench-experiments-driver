"""Contract between the benchmark driver and a coding assistant."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Protocol


class CommandRunner(Protocol):
    def __call__(self, args: list[str], *, cwd: Path | None = None,
                 stdin: str | None = None, log: Path | None = None,
                 json_log: Path | None = None,
                 check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]: ...


class Assistant(Protocol):
    """An assistant edits the workspace and raises on invocation failure."""

    name: str
    display_name: str
    executable: str
    prediction_name: str
    run_prefix: str
    model: str | None
    reasoning_effort: str | None

    def run(self, workspace: Path, prompt: str, issue_dir: Path,
            command: CommandRunner) -> None: ...


class AssistantFactory(Protocol):
    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser) -> None: ...

    def __call__(self, args: argparse.Namespace) -> Assistant: ...