"""Tests for fleet Ollama helpers."""

from __future__ import annotations

import json
from unittest.mock import patch

from hermes_cli.fleet_ollama import get_ollama_status


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = json.dumps(payload).encode()

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestGetOllamaStatus:
    def test_reports_healthy_server_and_models(self):
        payload = {
            "models": [
                {"name": "qwen3:8b"},
                {"name": "qwen2.5-coder:7b"},
            ]
        }
        with patch("hermes_cli.fleet_ollama.urllib.request.urlopen", return_value=_FakeResponse(payload)):
            status = get_ollama_status("http://127.0.0.1:11434")

        assert status["healthy"] is True
        assert status["base_url"] == "http://127.0.0.1:11434"
        assert status["models"] == ["qwen3:8b", "qwen2.5-coder:7b"]
        assert status["error"] == ""

    def test_reports_unhealthy_server_when_request_fails(self):
        with patch("hermes_cli.fleet_ollama.urllib.request.urlopen", side_effect=OSError("connection refused")):
            status = get_ollama_status("http://127.0.0.1:11434")

        assert status["healthy"] is False
        assert status["models"] == []
        assert "connection refused" in status["error"]
