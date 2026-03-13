"""Tests for fleet orchestrator lifecycle commands."""

from __future__ import annotations

from argparse import Namespace
from unittest.mock import MagicMock

from hermes_cli import fleet as fleet_mod


def test_orch_status_reports_not_running(capsys):
    registry = MagicMock()
    registry.list_agents.return_value = []

    original = fleet_mod.FleetRegistry
    fleet_mod.FleetRegistry = lambda: registry
    try:
        fleet_mod.fleet_command(Namespace(fleet_command="orch", orch_command="status"))
    finally:
        fleet_mod.FleetRegistry = original

    out = capsys.readouterr().out
    assert "Orchestrator: not running" in out


def test_orch_start_spawns_orchestrator(capsys):
    launcher = MagicMock()
    launcher.spawn_agent.return_value = {
        "agent_id": "agent_orch123",
        "session_name": "hermes-orchestrator-1234",
        "provider": "openrouter",
        "model": "anthropic/claude-opus-4.6",
        "endpoint_profile": "frontier-opus",
    }

    original = fleet_mod.FleetLauncher
    fleet_mod.FleetLauncher = lambda: launcher
    try:
        fleet_mod.fleet_command(
            Namespace(
                fleet_command="orch",
                orch_command="start",
                profile="frontier-opus",
                machine="local",
                cwd="/tmp/project",
                command=None,
                name=None,
            )
        )
    finally:
        fleet_mod.FleetLauncher = original

    launcher.spawn_agent.assert_called_once_with(
        name="orchestrator",
        role="orchestrator",
        profile="frontier-opus",
        machine_id="local",
        cwd="/tmp/project",
        command=None,
    )
    out = capsys.readouterr().out
    assert "Started orchestrator agent_orch123" in out


def test_orch_status_reports_running_agent(capsys):
    registry = MagicMock()
    registry.list_agents.return_value = [
        {
            "agent_id": "agent_orch123",
            "name": "orchestrator",
            "role": "orchestrator",
            "status": "idle",
            "machine_id": "local",
            "endpoint_profile": "frontier-opus",
            "session_name": "hermes-orchestrator-1234",
        }
    ]

    original = fleet_mod.FleetRegistry
    fleet_mod.FleetRegistry = lambda: registry
    try:
        fleet_mod.fleet_command(Namespace(fleet_command="orch", orch_command="status"))
    finally:
        fleet_mod.FleetRegistry = original

    out = capsys.readouterr().out
    assert "Orchestrator: running" in out
    assert "agent_orch123" in out
    assert "frontier-opus" in out


def test_orch_stop_stops_running_orchestrator(capsys):
    registry = MagicMock()
    registry.list_agents.return_value = [
        {
            "agent_id": "agent_orch123",
            "name": "orchestrator",
            "role": "orchestrator",
            "status": "idle",
            "machine_id": "local",
            "endpoint_profile": "frontier-opus",
            "session_name": "hermes-orchestrator-1234",
        }
    ]
    launcher = MagicMock()

    original_registry = fleet_mod.FleetRegistry
    original_launcher = fleet_mod.FleetLauncher
    fleet_mod.FleetRegistry = lambda: registry
    fleet_mod.FleetLauncher = lambda: launcher
    try:
        fleet_mod.fleet_command(Namespace(fleet_command="orch", orch_command="stop"))
    finally:
        fleet_mod.FleetRegistry = original_registry
        fleet_mod.FleetLauncher = original_launcher

    launcher.stop_agent.assert_called_once_with("agent_orch123")
    out = capsys.readouterr().out
    assert "Stopped orchestrator agent_orch123" in out


def test_orch_stop_reports_not_running(capsys):
    registry = MagicMock()
    registry.list_agents.return_value = []

    original = fleet_mod.FleetRegistry
    fleet_mod.FleetRegistry = lambda: registry
    try:
        fleet_mod.fleet_command(Namespace(fleet_command="orch", orch_command="stop"))
    finally:
        fleet_mod.FleetRegistry = original

    out = capsys.readouterr().out
    assert "Orchestrator: not running" in out
