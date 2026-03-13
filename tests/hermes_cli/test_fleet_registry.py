"""Tests for the Hermes Fleet registry."""

from __future__ import annotations

from hermes_cli.fleet_registry import FleetRegistry


class TestFleetRegistry:
    def test_registry_bootstraps_schema(self, tmp_path):
        db_path = tmp_path / "fleet.db"
        registry = FleetRegistry(db_path)

        assert db_path.exists()
        assert registry.list_machines() == []
        assert registry.list_agents() == []

    def test_upsert_machine_and_list(self, tmp_path):
        registry = FleetRegistry(tmp_path / "fleet.db")

        registry.upsert_machine(
            machine_id="local",
            name="Local MacBook",
            host="127.0.0.1",
            tags=["local", "mac"],
        )

        machines = registry.list_machines()
        assert len(machines) == 1
        assert machines[0]["machine_id"] == "local"
        assert machines[0]["name"] == "Local MacBook"
        assert machines[0]["host"] == "127.0.0.1"
        assert machines[0]["tags"] == ["local", "mac"]

    def test_upsert_agent_and_list(self, tmp_path):
        registry = FleetRegistry(tmp_path / "fleet.db")
        registry.upsert_machine(machine_id="local", name="Local", host="127.0.0.1")

        registry.upsert_agent(
            agent_id="agent_1",
            machine_id="local",
            name="planner",
            role="planner",
            status="idle",
            provider="openrouter",
            model="anthropic/claude-opus-4.6",
            endpoint_profile="frontier-opus",
            task_summary="Planning fleet architecture",
            session_name="hermes-planner",
        )

        agents = registry.list_agents()
        assert len(agents) == 1
        assert agents[0]["agent_id"] == "agent_1"
        assert agents[0]["machine_id"] == "local"
        assert agents[0]["role"] == "planner"
        assert agents[0]["status"] == "idle"
        assert agents[0]["endpoint_profile"] == "frontier-opus"

    def test_upsert_agent_replaces_existing_row(self, tmp_path):
        registry = FleetRegistry(tmp_path / "fleet.db")
        registry.upsert_machine(machine_id="local", name="Local", host="127.0.0.1")
        registry.upsert_agent(agent_id="agent_1", machine_id="local", status="idle")
        registry.upsert_agent(agent_id="agent_1", machine_id="local", status="busy", task_summary="Implementing")

        agents = registry.list_agents()
        assert len(agents) == 1
        assert agents[0]["status"] == "busy"
        assert agents[0]["task_summary"] == "Implementing"

    def test_summary_counts_agents_by_status(self, tmp_path):
        registry = FleetRegistry(tmp_path / "fleet.db")
        registry.upsert_machine(machine_id="local", name="Local", host="127.0.0.1")
        registry.upsert_agent(agent_id="agent_1", machine_id="local", status="idle")
        registry.upsert_agent(agent_id="agent_2", machine_id="local", status="busy")
        registry.upsert_agent(agent_id="agent_3", machine_id="local", status="blocked")

        summary = registry.get_summary()
        assert summary["total_agents"] == 3
        assert summary["by_status"]["idle"] == 1
        assert summary["by_status"]["busy"] == 1
        assert summary["by_status"]["blocked"] == 1

    def test_enqueue_assignment_and_list(self, tmp_path):
        registry = FleetRegistry(tmp_path / "fleet.db")
        assignment = registry.enqueue_assignment(
            task_summary="Implement the worker loop",
            requested_role="coder",
            requested_profile="local-mac-qwen",
            source="user",
        )

        assignments = registry.list_assignments()
        assert len(assignments) == 1
        assert assignments[0]["assignment_id"] == assignment["assignment_id"]
        assert assignments[0]["task_summary"] == "Implement the worker loop"
        assert assignments[0]["requested_role"] == "coder"
        assert assignments[0]["requested_profile"] == "local-mac-qwen"
        assert assignments[0]["status"] == "queued"
        assert assignments[0]["source"] == "user"

    def test_summary_counts_assignments_by_status(self, tmp_path):
        registry = FleetRegistry(tmp_path / "fleet.db")
        queued = registry.enqueue_assignment(task_summary="Task 1")
        second = registry.enqueue_assignment(task_summary="Task 2")
        registry.update_assignment(second["assignment_id"], status="running")

        summary = registry.get_summary()
        assert summary["total_assignments"] == 2
        assert summary["assignments_by_status"]["queued"] == 1
        assert summary["assignments_by_status"]["running"] == 1
