"""SQLite-backed runtime registry for Hermes Fleet."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
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

    def get_summary(self) -> dict[str, Any]:
        agents = self.list_agents()
        counts = Counter(agent.get("status") or "unknown" for agent in agents)
        return {
            "total_agents": len(agents),
            "total_machines": len(self.list_machines()),
            "by_status": dict(counts),
        }
