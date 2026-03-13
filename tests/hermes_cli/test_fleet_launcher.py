"""Tests for fleet launcher with profile-based env injection."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hermes_cli.fleet_launcher import FleetLauncher


SAMPLE_CONFIG = {
    "fleet": {
        "model_profiles": {
            "local-mac-qwen": {
                "provider": "custom",
                "base_url": "http://127.0.0.1:11434/v1",
                "api_key": "ollama",
                "model": "qwen3:8b",
                "machine": "local",
                "tags": ["local", "ollama", "general"],
            },
            "frontier-opus": {
                "provider": "openrouter",
                "model": "anthropic/claude-opus-4.6",
            },
        }
    }
}


@pytest.fixture
def mock_launcher(tmp_path):
    """Create a launcher with mocked tmux and config."""
    from hermes_cli.fleet_registry import FleetRegistry

    db_path = tmp_path / "fleet.db"
    registry = FleetRegistry(db_path=db_path)
    launcher = FleetLauncher(registry=registry)

    # Mock tmux calls
    launcher._run_tmux = MagicMock(
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    )

    return launcher


# ── Basic spawn ──────────────────────────────────────────────────────────

@patch("hermes_cli.fleet_launcher.load_config", return_value=SAMPLE_CONFIG)
def test_spawn_without_profile(mock_config, mock_launcher):
    agent = mock_launcher.spawn_agent(name="test", role="worker")
    assert agent["agent_id"].startswith("agent_")
    assert agent["role"] == "worker"
    assert agent["provider"] == ""
    assert agent["model"] == ""
    assert agent["endpoint_profile"] == ""

    # tmux called with no env prefix
    call_args = mock_launcher._run_tmux.call_args[0][0]
    cmd_str = call_args[-1]  # last arg is the command
    assert "export" not in cmd_str


# ── Profile injection ────────────────────────────────────────────────────

@patch("hermes_cli.fleet_launcher.load_config", return_value=SAMPLE_CONFIG)
def test_spawn_with_custom_profile(mock_config, mock_launcher):
    agent = mock_launcher.spawn_agent(
        name="local-coder",
        role="coder",
        profile="local-mac-qwen",
    )
    assert agent["provider"] == "custom"
    assert agent["model"] == "qwen3:8b"
    assert agent["endpoint_profile"] == "local-mac-qwen"

    # tmux command should include env exports
    call_args = mock_launcher._run_tmux.call_args[0][0]
    cmd_str = call_args[-1]
    assert "export" in cmd_str
    assert "OPENAI_BASE_URL=" in cmd_str
    assert "127.0.0.1:11434" in cmd_str
    assert "OPENAI_API_KEY=" in cmd_str
    assert "HERMES_MODEL=" in cmd_str
    assert "qwen3:8b" in cmd_str


@patch("hermes_cli.fleet_launcher.load_config", return_value=SAMPLE_CONFIG)
def test_spawn_with_cloud_profile(mock_config, mock_launcher):
    agent = mock_launcher.spawn_agent(
        name="planner",
        role="planner",
        profile="frontier-opus",
    )
    assert agent["provider"] == "openrouter"
    assert agent["model"] == "anthropic/claude-opus-4.6"
    assert agent["endpoint_profile"] == "frontier-opus"

    # Should have HERMES_MODEL but not OPENAI_BASE_URL (cloud provider)
    call_args = mock_launcher._run_tmux.call_args[0][0]
    cmd_str = call_args[-1]
    assert "export" in cmd_str
    assert "HERMES_MODEL=" in cmd_str
    # openrouter is default, so no HERMES_INFERENCE_PROVIDER needed
    # No OPENAI_BASE_URL for cloud profiles
    assert "OPENAI_BASE_URL" not in cmd_str


# ── Error cases ──────────────────────────────────────────────────────────

@patch("hermes_cli.fleet_launcher.load_config", return_value=SAMPLE_CONFIG)
def test_spawn_unknown_profile_raises(mock_config, mock_launcher):
    with pytest.raises(ValueError, match="not found"):
        mock_launcher.spawn_agent(name="test", profile="nonexistent-profile")


@patch("hermes_cli.fleet_launcher.load_config", return_value={"fleet": {}})
def test_spawn_empty_profiles_raises(mock_config, mock_launcher):
    with pytest.raises(ValueError, match="not found"):
        mock_launcher.spawn_agent(name="test", profile="anything")


# ── Env prefix building ─────────────────────────────────────────────────

def test_build_env_prefix_empty(mock_launcher):
    assert mock_launcher._build_env_prefix({}) == ""


def test_build_env_prefix_single():
    launcher = FleetLauncher.__new__(FleetLauncher)
    prefix = launcher._build_env_prefix({"FOO": "bar"})
    assert prefix == "export FOO=bar && "


def test_build_env_prefix_multiple_sorted():
    launcher = FleetLauncher.__new__(FleetLauncher)
    prefix = launcher._build_env_prefix({"ZZZ": "last", "AAA": "first"})
    assert prefix.startswith("export AAA=first ZZZ=last")


def test_build_env_prefix_quotes_special_chars():
    launcher = FleetLauncher.__new__(FleetLauncher)
    prefix = launcher._build_env_prefix({"KEY": "value with spaces"})
    assert "value with spaces" in prefix
    # Should be shell-quoted
    assert "'" in prefix or '"' in prefix


# ── Stop and logs still work ─────────────────────────────────────────────

@patch("hermes_cli.fleet_launcher.load_config", return_value=SAMPLE_CONFIG)
def test_stop_agent(mock_config, mock_launcher):
    agent = mock_launcher.spawn_agent(name="stopper", role="worker")
    mock_launcher._run_tmux.reset_mock()
    mock_launcher.stop_agent(agent["agent_id"])
    # tmux kill-session should have been called
    call_args = mock_launcher._run_tmux.call_args[0][0]
    assert "kill-session" in call_args


@patch("hermes_cli.fleet_launcher.load_config", return_value=SAMPLE_CONFIG)
def test_get_logs(mock_config, mock_launcher):
    mock_launcher._run_tmux.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="some log output\n", stderr=""
    )
    agent = mock_launcher.spawn_agent(name="logger", role="worker")
    mock_launcher._run_tmux.reset_mock()
    mock_launcher._run_tmux.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="captured logs here\n", stderr=""
    )
    logs = mock_launcher.get_logs(agent["agent_id"])
    assert "captured logs here" in logs
