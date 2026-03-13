"""Hermes Fleet command handlers."""

from __future__ import annotations

from argparse import Namespace
from typing import Any

from hermes_cli.config import load_config
from hermes_cli.fleet_launcher import FleetLauncher
from hermes_cli.fleet_models import (
    check_profile_health,
    list_model_profiles,
    resolve_profile_runtime,
)
from hermes_cli.fleet_ollama import get_ollama_status
from hermes_cli.fleet_registry import FleetRegistry


def _print_agent_table(agents: list[dict[str, Any]]) -> None:
    if not agents:
        print("No fleet agents registered.")
        return

    print("STATUS   AGENT ID         MACHINE      ROLE       PROFILE              TASK")
    for agent in agents:
        status = (agent.get("status") or "-")[:8]
        agent_id = (agent.get("agent_id") or "-")[:16]
        machine = (agent.get("machine_id") or "-")[:12]
        role = (agent.get("role") or "-")[:10]
        profile = (agent.get("endpoint_profile") or "-")[:20]
        task = (agent.get("task_summary") or "")[:40]
        print(f"{status:<8} {agent_id:<16} {machine:<12} {role:<10} {profile:<20} {task}")


def _cmd_ps(_args: Namespace) -> None:
    registry = FleetRegistry()
    _print_agent_table(registry.list_agents())


def _cmd_doctor(_args: Namespace) -> None:
    config = load_config()
    registry = FleetRegistry()
    summary = registry.get_summary()

    print("Hermes Fleet Doctor")
    print(f"  Machines: {summary['total_machines']}")
    print(f"  Agents:   {summary['total_agents']}")
    for status, count in sorted(summary["by_status"].items()):
        print(f"  {status}: {count}")

    # Profile health checks
    profiles = list_model_profiles(config)
    if profiles:
        print()
        print("Model Profiles:")
        for profile in profiles:
            name = profile["name"]
            health = check_profile_health(config, name)
            status_str = "healthy" if health["healthy"] else "unhealthy"
            indicator = "✓" if health["healthy"] else "✗"
            provider = profile.get("provider", "?")
            model = profile.get("model", "?")
            line = f"  {indicator} {name}: {provider}:{model} [{status_str}]"
            if health.get("error"):
                line += f" — {health['error']}"
            if health.get("note"):
                line += f" ({health['note']})"
            print(line)


def _cmd_models(args: Namespace) -> None:
    config = load_config()
    profiles = list_model_profiles(config)
    if not profiles:
        print("No fleet model profiles configured.")
        print()
        print("Add profiles to ~/.hermes/config.yaml under fleet.model_profiles:")
        print()
        print("  fleet:")
        print("    model_profiles:")
        print("      local-mac-qwen:")
        print("        provider: custom")
        print("        base_url: http://127.0.0.1:11434/v1")
        print("        api_key: ollama")
        print("        model: qwen3:8b")
        return

    verbose = getattr(args, "verbose", False)

    print("Fleet model profiles:")
    print()
    for profile in profiles:
        name = profile["name"]
        provider = profile.get("provider", "")
        model = profile.get("model", "")
        base_url = profile.get("base_url", "")
        machine = profile.get("machine", "")
        tags = profile.get("tags", [])

        print(f"  {name}")
        print(f"    provider: {provider}")
        print(f"    model:    {model}")
        if base_url:
            print(f"    base_url: {base_url}")
        if machine:
            print(f"    machine:  {machine}")
        if tags:
            print(f"    tags:     {', '.join(str(t) for t in tags)}")

        if verbose:
            health = check_profile_health(config, name)
            status = "healthy" if health["healthy"] else "unhealthy"
            print(f"    health:   {status}")
            if health.get("models"):
                print(f"    endpoint models: {', '.join(health['models'])}")
            if health.get("error"):
                print(f"    error:    {health['error']}")

        print()


def _cmd_spawn(args: Namespace) -> None:
    launcher = FleetLauncher()
    agent = launcher.spawn_agent(
        name=getattr(args, "name", None),
        role=getattr(args, "role", "worker"),
        profile=getattr(args, "profile", ""),
        machine_id=getattr(args, "machine", "local"),
        cwd=getattr(args, "cwd", None),
        command=getattr(args, "command", None),
    )
    print(f"Spawned fleet agent {agent['agent_id']} in tmux session {agent['session_name']}")
    if agent.get("provider"):
        print(f"  Provider: {agent['provider']}")
    if agent.get("model"):
        print(f"  Model:    {agent['model']}")
    if agent.get("endpoint_profile"):
        print(f"  Profile:  {agent['endpoint_profile']}")



def _cmd_logs(args: Namespace) -> None:
    launcher = FleetLauncher()
    logs = launcher.get_logs(args.agent_id, lines=getattr(args, "lines", 200))
    print(logs, end="" if logs.endswith("\n") else "\n")



def _cmd_stop(args: Namespace) -> None:
    launcher = FleetLauncher()
    launcher.stop_agent(args.agent_id)
    print(f"Stopped fleet agent {args.agent_id}")



def _cmd_attach(args: Namespace) -> None:
    launcher = FleetLauncher()
    launcher.attach_agent(args.agent_id)



def _cmd_ollama(args: Namespace) -> None:
    ollama_command = getattr(args, "ollama_command", None) or "status"
    if ollama_command == "status":
        status = get_ollama_status()
        health = "healthy" if status["healthy"] else "unreachable"
        print(f"Local Ollama: {health}")
        print(f"  URL:    {status['base_url']}")
        if status["models"]:
            print(f"  Models: {', '.join(status['models'])}")
        if status["error"]:
            print(f"  Error:  {status['error']}")
        return
    print(f"Fleet Ollama subcommand '{ollama_command}' is planned but not implemented yet.")


def _cmd_stub(args: Namespace) -> None:
    sub = getattr(args, "fleet_command", "fleet")
    print(f"Fleet subcommand '{sub}' is planned but not implemented yet.")


def fleet_command(args: Namespace) -> None:
    command = getattr(args, "fleet_command", None) or "ps"
    if command == "ps":
        _cmd_ps(args)
        return
    if command == "doctor":
        _cmd_doctor(args)
        return
    if command == "models":
        _cmd_models(args)
        return
    if command == "spawn":
        _cmd_spawn(args)
        return
    if command == "logs":
        _cmd_logs(args)
        return
    if command == "stop":
        _cmd_stop(args)
        return
    if command == "attach":
        _cmd_attach(args)
        return
    if command == "ollama":
        _cmd_ollama(args)
        return
    _cmd_stub(args)
