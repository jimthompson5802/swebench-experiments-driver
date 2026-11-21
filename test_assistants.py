import argparse
import subprocess

import pytest

from assistants.codex import CodexAssistant
from assistants.copilot import CopilotAssistant


@pytest.mark.parametrize("adapter,options,expected", [
    (CodexAssistant, [], ["codex", "exec", "--sandbox", "workspace-write", "--cd", "WORKSPACE", "-"]),
    (CodexAssistant, ["--model", "m", "--reasoning-effort", "high", "--allow-network"],
     ["codex", "exec", "--sandbox", "workspace-write", "--cd", "WORKSPACE", "--model", "m",
      "-c", 'model_reasoning_effort="high"', "-c", "sandbox_workspace_write.network_access=true", "-"]),
    (CopilotAssistant, [], ["copilot", "--no-ask-user", "--sandbox", "--allow-tool=write,shell",
                            "--disable-builtin-mcps", "--excluded-tools=web_fetch"]),
    (CopilotAssistant, ["--model", "m", "--reasoning-effort", "max"],
     ["copilot", "--no-ask-user", "--sandbox", "--allow-tool=write,shell",
      "--disable-builtin-mcps", "--excluded-tools=web_fetch", "--model", "m", "--reasoning-effort", "max"]),
])
def test_adapter_invocation(tmp_path, monkeypatch, adapter, options, expected):
    monkeypatch.setenv("COPILOT_ALLOW_ALL", "true")
    monkeypatch.setenv("TEST_PASSTHROUGH", "preserved")
    parser = argparse.ArgumentParser()
    adapter.add_arguments(parser)
    assistant = adapter(parser.parse_args(options))
    workspace = tmp_path / "repo"
    calls = []

    def command(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="")

    assistant.run(workspace, "issue prompt", tmp_path, command)
    expected = [str(workspace) if item == "WORKSPACE" else item for item in expected]
    args, kwargs = calls[0]
    assert args == expected
    if assistant.name == "copilot":
        env = kwargs.pop("env")
        assert env["COPILOT_ALLOW_ALL"] == "false"
        assert env["TEST_PASSTHROUGH"] == "preserved"
    assert kwargs == {"cwd": workspace, "stdin": "issue prompt",
                      "log": tmp_path / f"{assistant.name}.log", "check": False}


@pytest.mark.parametrize("adapter", [CodexAssistant, CopilotAssistant])
def test_adapter_nonzero_exit(tmp_path, adapter):
    parser = argparse.ArgumentParser()
    adapter.add_arguments(parser)
    assistant = adapter(parser.parse_args([]))

    def command(args, **kwargs):
        return subprocess.CompletedProcess(args, 42, stdout="failure")

    with pytest.raises(RuntimeError, match=rf"{assistant.display_name} failed with exit code 42; see {assistant.name}\.log"):
        assistant.run(tmp_path / "repo", "prompt", tmp_path, command)