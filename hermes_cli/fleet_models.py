"""Helpers for fleet model profiles."""

from __future__ import annotations

from typing import Any


def list_model_profiles(config: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = config.get("fleet", {}).get("model_profiles", {}) or {}
    result: list[dict[str, Any]] = []
    for name in sorted(profiles):
        profile = profiles.get(name)
        if isinstance(profile, dict):
            result.append({"name": name, **profile})
    return result


def get_model_profile(config: dict[str, Any], name: str) -> dict[str, Any] | None:
    profile = (config.get("fleet", {}).get("model_profiles", {}) or {}).get(name)
    if not isinstance(profile, dict):
        return None
    return {"name": name, **profile}
