"""Fleet model profiles: named endpoint configurations for multi-provider routing.

A model profile maps a friendly name (e.g. "local-mac-qwen") to a concrete
provider, base_url, api_key, and model.  Profiles are defined in config.yaml
under fleet.model_profiles and resolved at spawn time to inject the right
environment into a managed agent.

Example config.yaml entry:

    fleet:
      model_profiles:
        local-mac-qwen:
          provider: custom
          base_url: http://127.0.0.1:11434/v1
          api_key: ollama
          model: qwen3:8b
          machine: local
          tags: [local, ollama, general]
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Optional


def list_model_profiles(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all configured model profiles as a sorted list of dicts."""
    profiles = config.get("fleet", {}).get("model_profiles", {}) or {}
    result: list[dict[str, Any]] = []
    for name in sorted(profiles):
        profile = profiles.get(name)
        if isinstance(profile, dict):
            result.append({"name": name, **profile})
    return result


def get_model_profile(config: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Return a single named profile or None."""
    profile = (config.get("fleet", {}).get("model_profiles", {}) or {}).get(name)
    if not isinstance(profile, dict):
        return None
    return {"name": name, **profile}


def resolve_profile_runtime(
    config: dict[str, Any],
    profile_name: str,
) -> dict[str, Any] | None:
    """Resolve a named profile to a runtime-ready provider dict.

    Returns a dict with keys matching runtime_provider.resolve_runtime_provider()
    output: provider, api_mode, base_url, api_key, model, source.

    Returns None if the profile doesn't exist.
    """
    profile = get_model_profile(config, profile_name)
    if profile is None:
        return None

    provider = profile.get("provider", "custom")
    base_url = profile.get("base_url", "")
    api_key = profile.get("api_key", "")
    model = profile.get("model", "")

    return {
        "provider": provider,
        "api_mode": "chat_completions",
        "base_url": base_url.rstrip("/") if base_url else "",
        "api_key": api_key,
        "model": model,
        "source": f"fleet-profile:{profile_name}",
        "profile_name": profile_name,
        "machine": profile.get("machine", ""),
        "tags": profile.get("tags", []),
    }


def profile_to_env(
    config: dict[str, Any],
    profile_name: str,
) -> dict[str, str] | None:
    """Resolve a profile to environment variables for a spawned agent.

    Returns a dict of env var name -> value, or None if profile not found.
    The env vars are what run_agent.py / runtime_provider.py read at startup.
    """
    runtime = resolve_profile_runtime(config, profile_name)
    if runtime is None:
        return None

    env: dict[str, str] = {}

    if runtime["base_url"]:
        env["OPENAI_BASE_URL"] = runtime["base_url"]

    if runtime["api_key"]:
        env["OPENAI_API_KEY"] = runtime["api_key"]

    if runtime["model"]:
        env["HERMES_MODEL"] = runtime["model"]

    # For custom endpoints, set provider to "custom" so runtime_provider
    # routes through the OpenAI-compatible path (not OpenRouter/Nous/etc.)
    provider = runtime["provider"]
    if provider and provider != "openrouter":
        env["HERMES_INFERENCE_PROVIDER"] = provider

    return env


def check_profile_health(
    config: dict[str, Any],
    profile_name: str,
    timeout: float = 3.0,
) -> dict[str, Any]:
    """Check whether a profile's endpoint is reachable and lists the expected model.

    Returns {healthy: bool, reachable: bool, model_available: bool, models: [], error: str}.
    """
    profile = get_model_profile(config, profile_name)
    if profile is None:
        return {
            "healthy": False,
            "reachable": False,
            "model_available": False,
            "models": [],
            "error": f"Profile '{profile_name}' not found in config",
        }

    base_url = (profile.get("base_url") or "").rstrip("/")
    api_key = profile.get("api_key", "")
    expected_model = profile.get("model", "")
    provider = profile.get("provider", "")

    # For non-custom providers (openrouter, nous, etc.), we can't easily
    # health-check without real credentials flowing.  Mark as healthy-assumed.
    if provider not in ("custom", "ollama", ""):
        return {
            "healthy": True,
            "reachable": True,
            "model_available": True,
            "models": [],
            "error": "",
            "note": f"Cloud provider '{provider}' — health assumed, not probed",
        }

    if not base_url:
        return {
            "healthy": False,
            "reachable": False,
            "model_available": False,
            "models": [],
            "error": "No base_url configured",
        }

    # Probe /models endpoint
    url = f"{base_url}/models"
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        models = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
        model_available = expected_model in models if expected_model else True
        return {
            "healthy": model_available,
            "reachable": True,
            "model_available": model_available,
            "models": models,
            "error": "" if model_available else f"Model '{expected_model}' not found in endpoint",
        }
    except Exception as exc:
        return {
            "healthy": False,
            "reachable": False,
            "model_available": False,
            "models": [],
            "error": str(exc),
        }
