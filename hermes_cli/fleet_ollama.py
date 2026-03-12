"""Helpers for inspecting Ollama endpoints used by Hermes Fleet."""

from __future__ import annotations

import json
import urllib.request
from typing import Any


def get_ollama_status(base_url: str = "http://127.0.0.1:11434") -> dict[str, Any]:
    api_base = base_url.rstrip("/")
    url = f"{api_base}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=5.0) as response:
            payload = json.loads(response.read().decode())
        models = [item.get("name", "") for item in payload.get("models", []) if item.get("name")]
        return {
            "healthy": True,
            "base_url": api_base,
            "models": models,
            "error": "",
        }
    except Exception as exc:
        return {
            "healthy": False,
            "base_url": api_base,
            "models": [],
            "error": str(exc),
        }
