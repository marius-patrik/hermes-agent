"""Tests for Hermes Fleet CLI wiring and config defaults."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

from hermes_cli.config import DEFAULT_CONFIG, ensure_hermes_home, load_config
from hermes_cli import main as main_mod


class TestFleetConfigDefaults:
    def test_default_config_includes_fleet_section(self):
        assert "fleet" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["fleet"]["enabled"] is True
        assert DEFAULT_CONFIG["fleet"]["default_command"] == "fleet"
        assert DEFAULT_CONFIG["fleet"]["machines"] == []
        assert DEFAULT_CONFIG["fleet"]["model_profiles"] == {}

    def test_load_config_includes_fleet_defaults(self, tmp_path):
        with patch.dict(os.environ, {"HERMES_HOME": str(tmp_path)}):
            config = load_config()
            assert config["fleet"]["enabled"] is True
            assert config["fleet"]["default_command"] == "fleet"
            assert config["fleet"]["machines"] == []
            assert config["fleet"]["model_profiles"] == {}

    def test_ensure_hermes_home_creates_fleet_subdir(self, tmp_path):
        with patch.dict(os.environ, {"HERMES_HOME": str(tmp_path)}):
            ensure_hermes_home()
            assert (tmp_path / "fleet").is_dir()


class TestFleetCliWiring:
    def test_cmd_fleet_delegates_to_fleet_module(self):
        called = {}

        def fake_fleet_command(args):
            called["action"] = getattr(args, "fleet_command", None)

        with patch("hermes_cli.fleet.fleet_command", side_effect=fake_fleet_command):
            args = type("Args", (), {"fleet_command": "ps"})()
            main_mod.cmd_fleet(args)

        assert called == {"action": "ps"}

    def test_main_dispatches_fleet_subcommand(self):
        called = {}

        def fake_fleet_command(args):
            called["command"] = args.command
            called["fleet_command"] = args.fleet_command

        argv = ["hermes", "fleet", "ps"]
        with patch.object(sys, "argv", argv), patch("hermes_cli.fleet.fleet_command", side_effect=fake_fleet_command):
            main_mod.main()

        assert called == {"command": "fleet", "fleet_command": "ps"}

    def test_main_dispatches_nested_fleet_ollama_status_subcommand(self):
        called = {}

        def fake_fleet_command(args):
            called["command"] = args.command
            called["fleet_command"] = args.fleet_command
            called["ollama_command"] = getattr(args, "ollama_command", None)

        argv = ["hermes", "fleet", "ollama", "status"]
        with patch.object(sys, "argv", argv), patch("hermes_cli.fleet.fleet_command", side_effect=fake_fleet_command):
            main_mod.main()

        assert called == {
            "command": "fleet",
            "fleet_command": "ollama",
            "ollama_command": "status",
        }

    def test_main_dispatches_fleet_spawn_with_arguments(self):
        called = {}

        def fake_fleet_command(args):
            called["fleet_command"] = args.fleet_command
            called["name"] = args.name
            called["role"] = args.role
            called["profile"] = args.profile
            called["cwd"] = args.cwd

        argv = ["hermes", "fleet", "spawn", "--name", "planner", "--role", "planner", "--profile", "frontier-opus", "--cwd", "/tmp/project"]
        with patch.object(sys, "argv", argv), patch("hermes_cli.fleet.fleet_command", side_effect=fake_fleet_command):
            main_mod.main()

        assert called == {
            "fleet_command": "spawn",
            "name": "planner",
            "role": "planner",
            "profile": "frontier-opus",
            "cwd": "/tmp/project",
        }
