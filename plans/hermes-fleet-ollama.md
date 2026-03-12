# Hermes Fleet + Orchestrator + Ollama — Implementation Plan

## Goal

Add a top-level multi-agent control plane to Hermes with:
- `hermes fleet` as the umbrella command
- a live TUI overview of all active Hermes agents across machines
- a first-class orchestrator agent that can spawn and manage worker agents
- explicit model/provider routing so agents can switch between OpenRouter, Nous, Codex, direct API-key providers, and multiple local/custom OpenAI-compatible endpoints
- Ollama deployed on both the MacBook and the Ubuntu homeserver so Hermes can selectively use local models

## Core Product Decisions

1. Command name: `hermes fleet`
   - `hermes fleet` opens the TUI
   - `hermes fleet ps` prints a table
   - `hermes fleet spawn`, `attach`, `logs`, `stop`, `doctor` manage agents
   - optional aliases later: `hermes top`, `hermes ps`

2. Source of truth split:
   - GitHub shared repo is for durable config, templates, plans, and artifacts
   - live agent state is local runtime state on each machine, not in GitHub

3. Orchestrator model:
   - orchestrator is a special Hermes agent, not a hard dependency
   - user-spawned agents and orchestrator-spawned agents both register in the same fleet registry
   - if orchestrator dies, workers continue running

4. Ollama integration:
   - use Hermes' existing OpenAI-compatible custom endpoint path
   - do not hard-code Ollama as a one-off hack
   - instead add endpoint/model profiles so we can route to multiple custom endpoints cleanly

5. Model routing policy:
   - planning/research/default hard problems => strongest frontier model available
   - implementation/repetitive concrete edits => cheaper faster model or strong local coder if suitable
   - local Ollama models should be selectable manually and by orchestrator policy

## Current Codebase Constraints / Reuse

### Already present and reusable

- `hermes_cli/main.py`
  - central argparse command registry
  - easy place to add `fleet` subcommand
- `hermes_cli/status.py`, `hermes_cli/doctor.py`
  - command implementation style to mirror
- `hermes_cli/curses_ui.py`
  - existing curses patterns we can reuse for initial fleet TUI
- `tools/process_registry.py`
  - existing background process tracking ideas, but session-scoped and in-memory
  - useful for log buffering patterns, not enough for multi-machine fleet state
- `tools/delegate_tool.py`
  - already supports child-agent spawning and provider/model override inheritance
- `run_agent.py`
  - already carries provider routing preferences and model config into child agents
- `hermes_cli/models.py`
  - already supports `provider:model` runtime switching
- `hermes_cli/runtime_provider.py`
  - already resolves OpenRouter / Nous / Codex / API-key providers / custom endpoint runtime credentials
- `agent/auxiliary_client.py`
  - already supports custom OpenAI-compatible endpoints via `OPENAI_BASE_URL`

### Missing

- persistent fleet registry
- machine inventory
- cross-machine discovery
- tmux-backed managed agent launcher
- orchestrator control plane
- multiple named custom endpoint profiles (needed for local vs server Ollama)
- policy engine for task -> model/profile selection
- Ollama deployment/bootstrap tooling

## High-Level Architecture

### 1. Fleet runtime registry

Each machine keeps local runtime state under `~/.hermes/fleet/`:

```text
~/.hermes/fleet/
  fleet.db
  agents/
    {agent_id}/
      meta.json
      heartbeat.json
      events.ndjson
      stdout.log
      stderr.log
      task.json
```

`fleet.db` tables:
- `machines`
- `agents`
- `heartbeats`
- `events`
- `assignments`
- `model_profiles_cache` (optional derived cache)

Minimum `agents` fields:
- `agent_id`
- `machine_id`
- `name`
- `role` (`user`, `worker`, `planner`, `reviewer`, `orchestrator`)
- `source` (`user`, `orchestrator`, `system`)
- `parent_agent_id`
- `root_run_id`
- `status` (`starting`, `idle`, `busy`, `blocked`, `stopping`, `dead`)
- `provider`
- `model`
- `endpoint_profile`
- `cwd`
- `session_type`
- `session_name`
- `pid`
- `task_summary`
- `started_at`
- `updated_at`
- `heartbeat_at`

### 2. Managed launcher

A fleet-managed agent is started through a wrapper instead of directly invoking `hermes`.

Wrapper responsibilities:
- allocate `agent_id`
- create agent runtime dir
- start a tmux session for the agent
- write metadata to registry
- write heartbeat periodically
- mirror stdout/stderr to logs
- detect exit and mark dead/stopped

### 3. Machine discovery

Machine inventory should live in config, not code.

Primary config location:
- `~/.hermes/config.yaml`

Shared durable config (optional, synced through GitHub workspace):
- `~/hermes-shared/fleet/machines.yaml`
- `~/hermes-shared/fleet/model-profiles.yaml`
- `~/hermes-shared/fleet/policies.yaml`

The local CLI aggregates:
- local machine state directly
- remote machine state via SSH-over-Tailscale commands

### 4. Orchestrator

The orchestrator is a long-running fleet-managed Hermes agent with special responsibilities:
- inventory active agents
- maintain task queue
- spawn workers by role/template
- choose provider/model/profile per assignment
- avoid duplicated work
- restart or replace failed helper agents according to policy

Important: the orchestrator should call the same managed launcher and registry APIs as users. No special hidden path.

## Model / Provider Routing Design

## Existing behavior we should preserve

Today Hermes already supports:
- switching providers at runtime with `provider:model`
- custom OpenAI-compatible endpoint via `OPENAI_BASE_URL`
- provider/model override for delegated subagents
- per-task auxiliary provider overrides

That means the answer to “should Hermes be able to switch to any model from any provider any time?” is effectively:
- yes for existing provider classes
- yes for one custom endpoint today
- not clean enough yet for multiple custom endpoints like “Mac Ollama” vs “server Ollama”

## New concept: endpoint profiles

Add named endpoint profiles so multiple custom endpoints can coexist.

Example config shape:

```yaml
fleet:
  model_profiles:
    frontier-opus:
      provider: openrouter
      model: anthropic/claude-opus-4.6

    frontier-openai:
      provider: openrouter
      model: openai/gpt-5.4-pro

    local-mac-qwen:
      provider: custom
      base_url: http://127.0.0.1:11434/v1
      api_key: ollama
      model: qwen3:8b
      machine: local
      tags: [local, ollama, general]

    server-ollama-general:
      provider: custom
      base_url: http://100.x.y.z:11434/v1
      api_key: ollama
      model: qwen3:14b
      machine: dekstop
      tags: [remote, ollama, general]

    server-ollama-coder:
      provider: custom
      base_url: http://100.x.y.z:11434/v1
      api_key: ollama
      model: qwen2.5-coder:14b
      machine: dekstop
      tags: [remote, ollama, coding]
```

Routing precedence for fleet-managed agents:
1. explicit spawn/delegate args
2. orchestrator task policy result
3. profile defaults
4. existing provider:model runtime config fallback

## Policy engine

Introduce simple task classes first:
- `planning`
- `research`
- `coding`
- `review`
- `ops`
- `background`

Initial default policy:
- planning/research/review => best frontier profile available (`frontier-opus` first, then strong OpenAI, then strong local if explicitly allowed)
- coding => cheaper but strong coding profile (`frontier-openai-codex` or `server-ollama-coder` depending policy)
- repetitive concrete implementation => cheaper/faster profile
- local fallback => any healthy Ollama profile when network/frontier provider unavailable or policy prefers local

Do not make this “AI magic” yet. Start rule-based and observable.

## Ollama Deployment Plan

## Machine targets

1. MacBook (local)
   - install Ollama app / binary
   - ensure service is running
   - pull at least one default model
   - expose only on localhost by default

2. Ubuntu homeserver (remote / dekstop)
   - install Ollama service
   - enable/start systemd unit
   - bind to Tailscale-accessible interface or leave localhost + SSH tunnel depending policy
   - pull at least one general model and one coding model

## Initial model set

MacBook:
- `qwen3:8b` as safe general local model

Homeserver:
- `qwen3:14b` if RAM permits, otherwise `qwen3:8b`
- `qwen2.5-coder:14b` if RAM permits, otherwise `qwen2.5-coder:7b`

We should not hard-code giant models without checking memory first. The deploy script must inspect available RAM/disk and choose a tier.

## Connectivity

Preferred remote connectivity for Hermes -> server Ollama:
- Tailscale IP / MagicDNS over `http://<tailscale-host-or-ip>:11434/v1`

Alternative safer mode:
- keep server Ollama bound to localhost
- use fleet SSH tunnel/proxy when a local machine wants to hit it

For first implementation, support both, defaulting to localhost-only unless config explicitly enables network bind.

## Command Surface

### User-facing

- `hermes fleet`
  - open TUI
- `hermes fleet ps`
  - list agents
- `hermes fleet spawn ...`
  - spawn managed agent
- `hermes fleet attach <agent-id>`
  - attach tmux / tail logs
- `hermes fleet logs <agent-id>`
  - tail logs
- `hermes fleet stop <agent-id>`
- `hermes fleet restart <agent-id>`
- `hermes fleet doctor`
  - registry + heartbeat + tmux + machine health + model profile health
- `hermes fleet orch start|stop|status`
- `hermes fleet delegate ...`
  - enqueue/assign a task through orchestrator
- `hermes fleet models`
  - show available model profiles and health
- `hermes fleet ollama setup --machine local|dekstop|all`
  - install/configure Ollama
- `hermes fleet ollama pull --profile <profile>`
  - pull the profile’s model
- `hermes fleet ollama status`
  - show Ollama health on all machines

### Optional aliases later

- `hermes top` -> `hermes fleet`
- `hermes ps` -> `hermes fleet ps`

## TUI Layout

Top bar:
- orchestrator status
- machines online/offline
- total agents / busy / blocked / dead
- active model profiles

Left pane:
- machines
- local
- dekstop

Main pane:
- agents table
- columns: status, id, role, machine, provider/profile, task, session, age, heartbeat

Right pane:
- selected agent details
- prompt/task summary
- parent/children
- cwd
- provider/model/base_url profile
- log tail

Footer actions:
- `s` spawn
- `d` delegate
- `a` attach
- `l` logs
- `x` stop
- `r` restart
- `o` orchestrator toggle
- `m` model profiles
- `D` doctor

## Files to Create / Modify

### New files

- `hermes_cli/fleet.py`
  - top-level command handlers
- `hermes_cli/fleet_tui.py`
  - curses TUI implementation
- `hermes_cli/fleet_registry.py`
  - sqlite schema + registry API
- `hermes_cli/fleet_launcher.py`
  - tmux-backed managed launcher
- `hermes_cli/fleet_discovery.py`
  - local + remote machine aggregation
- `hermes_cli/fleet_models.py`
  - endpoint profile loading + routing policy helpers
- `hermes_cli/fleet_ollama.py`
  - install/status/pull helpers
- `tests/hermes_cli/test_fleet_registry.py`
- `tests/hermes_cli/test_fleet_models.py`
- `tests/hermes_cli/test_fleet_cli.py`
- `tests/hermes_cli/test_fleet_ollama.py`

### Modified files

- `hermes_cli/main.py`
  - add `fleet` subcommand and its nested subcommands
- `hermes_cli/config.py`
  - add `fleet` section defaults and helpers
- `hermes_cli/status.py`
  - add fleet/orchestrator/model-profile summary section
- `hermes_cli/doctor.py`
  - add fleet registry + tmux + ssh/ollama/model-profile checks
- `hermes_cli/models.py`
  - add awareness of named model profiles / custom endpoint profile selection
- `hermes_cli/runtime_provider.py`
  - resolve runtime credentials from named profiles, not only env/global provider
- `tools/delegate_tool.py`
  - accept endpoint/profile override cleanly for orchestrator-assigned subagents
- `run_agent.py`
  - surface endpoint profile metadata into agent state/logging if provided

## Implementation Order

### Phase 1 — Fleet foundations

1. Add `fleet` config defaults to `hermes_cli/config.py`
2. Create `hermes_cli/fleet_registry.py`
3. Create sqlite schema and CRUD helpers
4. Create tests for registry
5. Add `hermes fleet ps` and `hermes fleet doctor`
6. Add machine inventory loading from config

### Phase 2 — Managed launcher

7. Create `hermes_cli/fleet_launcher.py`
8. Implement tmux-based start/stop/log/attach
9. Write agent metadata + heartbeat files
10. Add `spawn`, `stop`, `restart`, `logs`, `attach`
11. Add doctor checks for stale tmux sessions / dead pids / stale heartbeats

### Phase 3 — TUI

12. Create `hermes_cli/fleet_tui.py`
13. Reuse curses patterns from `hermes_cli/curses_ui.py`
14. Add read-only table view first
15. Add action keys after list/detail views are stable

### Phase 4 — Model profiles

16. Add named `fleet.model_profiles` config support
17. Add resolver in `hermes_cli/fleet_models.py`
18. Extend `runtime_provider.py` to resolve from profile
19. Extend CLI and delegations to accept `--profile`
20. Add `hermes fleet models`
21. Add tests covering profile precedence and custom endpoints

### Phase 5 — Orchestrator

22. Add orchestrator role/template support in launcher
23. Add assignment queue tables to registry
24. Add `orch start|stop|status`
25. Add `delegate` command
26. Implement simple rule-based routing policy
27. Add parent/child agent tracking in registry

### Phase 6 — Ollama support

28. Create `hermes_cli/fleet_ollama.py`
29. Implement local machine Ollama detection/install/start/status
30. Implement remote machine install/status via SSH commands
31. Implement RAM-aware default model selection
32. Add `hermes fleet ollama setup/status/pull`
33. Add model-profile templates for local and remote Ollama
34. Add doctor checks for Ollama reachability and `/v1/models` compatibility

## Testing

### Unit

- registry schema + inserts + transitions
- model profile loading and precedence
- provider/profile resolution
- CLI parser for `fleet` subcommands
- doctor output when tmux missing / profile unhealthy / Ollama unreachable

### Integration

- spawn a managed agent in tmux and detect heartbeat
- restart stopped agent
- resolve custom endpoint profile against a mock OpenAI-compatible server
- local Ollama compatibility probe using `/v1/models` and `/v1/chat/completions`

### Manual smoke test

- MacBook:
  - `hermes fleet ollama setup --machine local`
  - `hermes fleet models`
  - `hermes fleet spawn --role planner --profile frontier-opus`
  - `hermes fleet spawn --role coder --profile local-mac-qwen`
  - `hermes fleet`
- Homeserver:
  - `hermes fleet ollama setup --machine dekstop`
  - `hermes fleet ollama status`
  - `hermes fleet spawn --machine dekstop --role coder --profile server-ollama-coder`

## Practical Notes

- The current codebase is Python, so the first in-tree implementation should also be Python for integration speed.
- The user prefers Go for reusable scripting/skills to reduce model usage. That is a good fit for later standalone operational helpers, but the first fleet integration should land directly in Hermes' Python CLI.
- If we later want a persistent high-performance sidecar/daemon, that can become a separate Go helper process; do not introduce that complexity in v1.

## Immediate Next Steps

1. Finish local Ollama setup and validate `/v1` compatibility.
2. Add `fleet` config scaffolding and registry implementation.
3. Add named model profiles so local/server Ollama can coexist cleanly.
4. Add `hermes fleet ps` + `doctor` before the full TUI.
5. Add managed launcher + tmux integration.
6. Add orchestrator after the fleet substrate is stable.
