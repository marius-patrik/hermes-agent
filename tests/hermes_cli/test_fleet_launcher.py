"""Tests for tmux-backed fleet launcher helpers."""

from __future__ import annotations

import os
from unittest.mock import patch

from hermes_cli.fleet_launcher import FleetLauncher
from hermes_cli.fleet_registry import FleetRegistry


class TestFleetLauncher:
    def test_spawn_agent_starts_tmux_and_registers_agent(self, tmp_path):
        with patch.dict(os.environ, {"HERMES_HOME": str(tmp_path)}):
            launcher = FleetLauncher(registry=FleetRegistry(tmp_path / "fleet" / "fleet.db"))

            calls = []

            def fake_run(cmd, check=True, capture_output=True, text=True):
                calls.append(cmd)
                class Result:
                    stdout = ""
                return Result()

            with patch("hermes_cli.fleet_launcher.subprocess.run", side_effect=fake_run):
                agent = launcher.spawn_agent(name="planner", role="planner", cwd="/tmp/project")

            assert calls
            assert calls[0][:4] == ["tmux", "new-session", "-d", "-s"]
            assert agent["name"] == "planner"
            assert agent["role"] == "planner"
            assert agent["machine_id"] == "local"
            assert agent["session_name"].startswith("hermes-planner-")

            agents = launcher.registry.list_agents()
            assert len(agents) == 1
            assert agents[0]["agent_id"] == agent["agent_id"]
            assert agents[0]["status"] == "idle"

    def test_stop_agent_kills_tmux_and_marks_agent_dead(self, tmp_path):
        with patch.dict(os.environ, {"HERMES_HOME": str(tmp_path)}):
            launcher = FleetLauncher(registry=FleetRegistry(tmp_path / "fleet" / "fleet.db"))
            launcher.registry.upsert_machine(machine_id="local", name="Local", host="127.0.0.1")
            launcher.registry.upsert_agent(
                agent_id="agent_1",
                machine_id="local",
                name="planner",
                role="planner",
                status="idle",
                session_name="hermes-planner-1234",
            )

            calls = []

            def fake_run(cmd, check=True, capture_output=True, text=True):
                calls.append(cmd)
                class Result:
                    stdout = ""
                return Result()

            with patch("hermes_cli.fleet_launcher.subprocess.run", side_effect=fake_run):
                launcher.stop_agent("agent_1")

            assert calls == [["tmux", "kill-session", "-t", "hermes-planner-1234"]]
            agent = launcher.registry.get_agent("agent_1")
            assert agent is not None
            assert agent["status"] == "dead"

    def test_get_logs_uses_tmux_capture_pane(self, tmp_path):
        with patch.dict(os.environ, {"HERMES_HOME": str(tmp_path)}):
            launcher = FleetLauncher(registry=FleetRegistry(tmp_path / "fleet" / "fleet.db"))
            launcher.registry.upsert_machine(machine_id="local", name="Local", host="127.0.0.1")
            launcher.registry.upsert_agent(
                agent_id="agent_1",
                machine_id="local",
                name="planner",
                role="planner",
                status="idle",
                session_name="hermes-planner-1234",
            )

            def fake_run(cmd, check=True, capture_output=True, text=True):
                class Result:
                    stdout = "hello\nworld\n"
                return Result()

            with patch("hermes_cli.fleet_launcher.subprocess.run", side_effect=fake_run) as mocked:
                logs = launcher.get_logs("agent_1", lines=50)

            mocked.assert_called_once_with(
                ["tmux", "capture-pane", "-pt", "hermes-planner-1234", "-S", "-50"],
                check=True,
                capture_output=True,
                text=True,
            )
            assert logs == "hello\nworld\n"
