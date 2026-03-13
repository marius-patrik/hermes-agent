"""Tests for fleet delegate command / assignment queueing."""

from __future__ import annotations

from argparse import Namespace
from unittest.mock import MagicMock

from hermes_cli import fleet as fleet_mod


def test_delegate_enqueues_assignment(capsys):
    registry = MagicMock()
    registry.enqueue_assignment.return_value = {
        "assignment_id": "asgn_1234abcd",
        "task_summary": "Implement queue worker",
        "requested_role": "coder",
        "requested_profile": "local-mac-qwen",
        "status": "queued",
    }

    original = fleet_mod.FleetRegistry
    fleet_mod.FleetRegistry = lambda: registry
    try:
        fleet_mod.fleet_command(
            Namespace(
                fleet_command="delegate",
                task="Implement queue worker",
                role="coder",
                profile="local-mac-qwen",
            )
        )
    finally:
        fleet_mod.FleetRegistry = original

    registry.enqueue_assignment.assert_called_once_with(
        task_summary="Implement queue worker",
        requested_role="coder",
        requested_profile="local-mac-qwen",
        source="user",
    )
    out = capsys.readouterr().out
    assert "Queued assignment asgn_1234abcd" in out
    assert "coder" in out
    assert "local-mac-qwen" in out


def test_delegate_defaults_role_and_profile(capsys):
    registry = MagicMock()
    registry.enqueue_assignment.return_value = {
        "assignment_id": "asgn_default",
        "task_summary": "Review code",
        "requested_role": "worker",
        "requested_profile": "",
        "status": "queued",
    }

    original = fleet_mod.FleetRegistry
    fleet_mod.FleetRegistry = lambda: registry
    try:
        fleet_mod.fleet_command(
            Namespace(
                fleet_command="delegate",
                task="Review code",
                role="worker",
                profile="",
            )
        )
    finally:
        fleet_mod.FleetRegistry = original

    registry.enqueue_assignment.assert_called_once_with(
        task_summary="Review code",
        requested_role="worker",
        requested_profile="",
        source="user",
    )
    out = capsys.readouterr().out
    assert "Queued assignment asgn_default" in out
