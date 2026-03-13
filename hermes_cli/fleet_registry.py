"""SQLite-backed runtime registry for Hermes Fleet."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_cli.config import ensure_hermes_home, get_hermes_home


DEFAULT_MACHINE_FIELDS = {
    "name": "",
    "host": "",
    "tags": [],
    "transport": "local",
    "workspace": "",
    "last_seen": None,
}

DEFAULT_AGENT_FIELDS = {
    "machine_id": "",
    "name": "",
    "role": "worker",
    "status": "idle",
    "provider": "",
    "model": "",
    "endpoint_profile": "",
    "task_summary": "",
    "session_name": "",
}

DEFAULT_ASSIGNMENT_FIELDS = {
    "task_summary": "",
    "requested_role": "worker",
    "requested_profile": "",
    "status": "queued",
    "source": "user",
    "assigned_agent_id": "",
    "created_at": None,
    "updated_at": None,
}


class FleetRegistry:
    """Small SQLite helper for Hermes Fleet runtime state."""

    def __init__(self, db_path: str | Path | None = None):
        ensure_hermes_home()
        self.db_path = Path(db_path) if db_path else get_hermes_home() / "fleet" / "fleet.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS machines (
                    machine_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    host TEXT NOT NULL DEFAULT '',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    transport TEXT NOT NULL DEFAULT 'local',
                    workspace TEXT NOT NULL DEFAULT '',
                    last_seen TEXT
                );

                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    machine_id TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT 'worker',
                    status TEXT NOT NULL DEFAULT 'idle',
                    provider TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    endpoint_profile TEXT NOT NULL DEFAULT '',
                    task_summary TEXT NOT NULL DEFAULT '',
                    session_name TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(machine_id) REFERENCES machines(machine_id)
                );

                CREATE TABLE IF NOT EXISTS assignments (
                    assignment_id TEXT PRIMARY KEY,
                    task_summary TEXT NOT NULL DEFAULT '',
                    requested_role TEXT NOT NULL DEFAULT 'worker',
                    requested_profile TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'queued',
                    source TEXT NOT NULL DEFAULT 'user',
                    assigned_agent_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT,
                    updated_at TEXT
                );
                """
            )

    def upsert_machine(self, machine_id: str, **fields: Any) -> None:
        data = {**DEFAULT_MACHINE_FIELDS, **fields}
        tags_json = json.dumps(list(data.get("tags") or []))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO machines (machine_id, name, host, tags_json, transport, workspace, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(machine_id) DO UPDATE SET
                    name=excluded.name,
                    host=excluded.host,
                    tags_json=excluded.tags_json,
                    transport=excluded.transport,
                    workspace=excluded.workspace,
                    last_seen=excluded.last_seen
                """,
                (
                    machine_id,
                    data["name"],
                    data["host"],
                    tags_json,
                    data["transport"],
                    data["workspace"],
                    data["last_seen"],
                ),
            )

    def list_machines(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT machine_id, name, host, tags_json, transport, workspace, last_seen FROM machines ORDER BY machine_id"
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["tags"] = json.loads(item.pop("tags_json") or "[]")
            result.append(item)
        return result

    def upsert_agent(self, agent_id: str, **fields: Any) -> None:
        data = {**DEFAULT_AGENT_FIELDS, **fields}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agents (
                    agent_id, machine_id, name, role, status, provider, model,
                    endpoint_profile, task_summary, session_name
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    machine_id=excluded.machine_id,
                    name=excluded.name,
                    role=excluded.role,
                    status=excluded.status,
                    provider=excluded.provider,
                    model=excluded.model,
                    endpoint_profile=excluded.endpoint_profile,
                    task_summary=excluded.task_summary,
                    session_name=excluded.session_name
                """,
                (
                    agent_id,
                    data["machine_id"],
                    data["name"],
                    data["role"],
                    data["status"],
                    data["provider"],
                    data["model"],
                    data["endpoint_profile"],
                    data["task_summary"],
                    data["session_name"],
                ),
            )

    def list_agents(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT agent_id, machine_id, name, role, status, provider, model,
                       endpoint_profile, task_summary, session_name
                FROM agents
                ORDER BY agent_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT agent_id, machine_id, name, role, status, provider, model,
                       endpoint_profile, task_summary, session_name
                FROM agents
                WHERE agent_id = ?
                """,
                (agent_id,),
            ).fetchone()
        return dict(row) if row else None

    def enqueue_assignment(self, **fields: Any) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        assignment_id = f"asgn_{uuid.uuid4().hex[:10]}"
        data = {**DEFAULT_ASSIGNMENT_FIELDS, **fields}
        data["created_at"] = data.get("created_at") or now
        data["updated_at"] = data.get("updated_at") or now
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO assignments (
                    assignment_id, task_summary, requested_role, requested_profile,
                    status, source, assigned_agent_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assignment_id,
                    data["task_summary"],
                    data["requested_role"],
                    data["requested_profile"],
                    data["status"],
                    data["source"],
                    data["assigned_agent_id"],
                    data["created_at"],
                    data["updated_at"],
                ),
            )
        return {"assignment_id": assignment_id, **data}

    def update_assignment(self, assignment_id: str, **fields: Any) -> None:
        current = self.get_assignment(assignment_id)
        if not current:
            raise ValueError(f"Unknown fleet assignment: {assignment_id}")
        data = {**current, **fields, "updated_at": datetime.now(timezone.utc).isoformat()}
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE assignments
                SET task_summary = ?, requested_role = ?, requested_profile = ?,
                    status = ?, source = ?, assigned_agent_id = ?, created_at = ?, updated_at = ?
                WHERE assignment_id = ?
                """,
                (
                    data["task_summary"],
                    data["requested_role"],
                    data["requested_profile"],
                    data["status"],
                    data["source"],
                    data["assigned_agent_id"],
                    data["created_at"],
                    data["updated_at"],
                    assignment_id,
                ),
            )

    def list_assignments(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT assignment_id, task_summary, requested_role, requested_profile,
                       status, source, assigned_agent_id, created_at, updated_at
                FROM assignments
                ORDER BY created_at, assignment_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_assignment(self, assignment_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT assignment_id, task_summary, requested_role, requested_profile,
                       status, source, assigned_agent_id, created_at, updated_at
                FROM assignments
                WHERE assignment_id = ?
                """,
                (assignment_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_summary(self) -> dict[str, Any]:
        agents = self.list_agents()
        assignments = self.list_assignments()
        counts = Counter(agent.get("status") or "unknown" for agent in agents)
        assignment_counts = Counter(item.get("status") or "unknown" for item in assignments)
        return {
            "total_agents": len(agents),
            "total_machines": len(self.list_machines()),
            "by_status": dict(counts),
            "total_assignments": len(assignments),
            "assignments_by_status": dict(assignment_counts),
        }
