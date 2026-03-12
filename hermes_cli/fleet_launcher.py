"""Local tmux-backed launcher for Hermes Fleet managed agents."""

from __future__ import annotations

import platform
import shlex
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from hermes_cli.config import get_project_root
from hermes_cli.fleet_registry import FleetRegistry


class FleetLauncher:
    def __init__(self, registry: FleetRegistry | None = None):
        self.registry = registry or FleetRegistry()

    def _run_tmux(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(args, check=True, capture_output=True, text=True)

    def _default_command(self, cwd: str | None = None) -> str:
        project_root = Path(get_project_root())
        target_cwd = Path(cwd).expanduser() if cwd else project_root
        python_bin = Path(sys.executable)
        return f"cd {shlex.quote(str(target_cwd))} && exec {shlex.quote(str(python_bin))} -m hermes_cli.main"

    def spawn_agent(
        self,
        *,
        name: str | None = None,
        role: str = "worker",
        profile: str = "",
        machine_id: str = "local",
        cwd: str | None = None,
        command: str | None = None,
    ) -> dict[str, Any]:
        agent_id = f"agent_{uuid.uuid4().hex[:12]}"
        base_name = (name or role or "agent").strip() or "agent"
        session_slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in base_name).strip("-") or "agent"
        session_name = f"hermes-{session_slug}-{agent_id[-4:]}"
        startup_command = command or self._default_command(cwd)

        self.registry.upsert_machine(
            machine_id=machine_id,
            name=platform.node() or machine_id,
            host="127.0.0.1" if machine_id == "local" else machine_id,
            tags=[machine_id],
            transport="local" if machine_id == "local" else "ssh",
            workspace=str(Path(cwd).expanduser()) if cwd else str(get_project_root()),
        )

        self._run_tmux(["tmux", "new-session", "-d", "-s", session_name, startup_command])

        agent = {
            "agent_id": agent_id,
            "machine_id": machine_id,
            "name": base_name,
            "role": role,
            "status": "idle",
            "provider": "",
            "model": "",
            "endpoint_profile": profile,
            "task_summary": f"Managed agent session ({role})",
            "session_name": session_name,
        }
        self.registry.upsert_agent(**agent)
        return agent

    def stop_agent(self, agent_id: str) -> None:
        agent = self.registry.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Unknown fleet agent: {agent_id}")
        self._run_tmux(["tmux", "kill-session", "-t", agent["session_name"]])
        self.registry.upsert_agent(**{**agent, "status": "dead"})

    def get_logs(self, agent_id: str, lines: int = 200) -> str:
        agent = self.registry.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Unknown fleet agent: {agent_id}")
        result = self._run_tmux(["tmux", "capture-pane", "-pt", agent["session_name"], "-S", f"-{lines}"])
        return result.stdout

    def attach_agent(self, agent_id: str) -> None:
        agent = self.registry.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Unknown fleet agent: {agent_id}")
        subprocess.run(["tmux", "attach-session", "-t", agent["session_name"]], check=True)
