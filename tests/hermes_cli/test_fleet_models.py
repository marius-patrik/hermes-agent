"""Tests for fleet model profile resolution, env injection, and health checks."""

from __future__ import annotations

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

import pytest

from hermes_cli.fleet_models import (
    check_profile_health,
    get_model_profile,
    list_model_profiles,
    profile_to_env,
    resolve_profile_runtime,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

SAMPLE_CONFIG = {
    "fleet": {
        "model_profiles": {
            "local-mac-qwen": {
                "provider": "custom",
                "base_url": "http://127.0.0.1:11434/v1",
                "api_key": "ollama",
                "model": "qwen3:8b",
                "machine": "local",
                "tags": ["local", "ollama", "general"],
            },
            "frontier-opus": {
                "provider": "openrouter",
                "model": "anthropic/claude-opus-4.6",
            },
            "server-ollama-coder": {
                "provider": "custom",
                "base_url": "http://100.1.2.3:11434/v1",
                "api_key": "ollama",
                "model": "qwen2.5-coder:14b",
                "machine": "dekstop",
                "tags": ["remote", "ollama", "coding"],
            },
        }
    }
}

EMPTY_CONFIG: dict = {}
NO_PROFILES_CONFIG: dict = {"fleet": {}}


# ── list_model_profiles ──────────────────────────────────────────────────

def test_list_profiles_returns_sorted():
    profiles = list_model_profiles(SAMPLE_CONFIG)
    names = [p["name"] for p in profiles]
    assert names == ["frontier-opus", "local-mac-qwen", "server-ollama-coder"]


def test_list_profiles_empty_config():
    assert list_model_profiles(EMPTY_CONFIG) == []
    assert list_model_profiles(NO_PROFILES_CONFIG) == []


# ── get_model_profile ────────────────────────────────────────────────────

def test_get_profile_found():
    profile = get_model_profile(SAMPLE_CONFIG, "local-mac-qwen")
    assert profile is not None
    assert profile["name"] == "local-mac-qwen"
    assert profile["model"] == "qwen3:8b"
    assert profile["base_url"] == "http://127.0.0.1:11434/v1"


def test_get_profile_not_found():
    assert get_model_profile(SAMPLE_CONFIG, "nonexistent") is None
    assert get_model_profile(EMPTY_CONFIG, "anything") is None


# ── resolve_profile_runtime ──────────────────────────────────────────────

def test_resolve_runtime_custom_profile():
    runtime = resolve_profile_runtime(SAMPLE_CONFIG, "local-mac-qwen")
    assert runtime is not None
    assert runtime["provider"] == "custom"
    assert runtime["base_url"] == "http://127.0.0.1:11434/v1"
    assert runtime["api_key"] == "ollama"
    assert runtime["model"] == "qwen3:8b"
    assert runtime["api_mode"] == "chat_completions"
    assert runtime["source"] == "fleet-profile:local-mac-qwen"
    assert runtime["machine"] == "local"
    assert "local" in runtime["tags"]


def test_resolve_runtime_cloud_profile():
    runtime = resolve_profile_runtime(SAMPLE_CONFIG, "frontier-opus")
    assert runtime is not None
    assert runtime["provider"] == "openrouter"
    assert runtime["model"] == "anthropic/claude-opus-4.6"
    assert runtime["base_url"] == ""  # no custom base_url for cloud


def test_resolve_runtime_not_found():
    assert resolve_profile_runtime(SAMPLE_CONFIG, "nope") is None


def test_resolve_runtime_strips_trailing_slash():
    config = {
        "fleet": {
            "model_profiles": {
                "test": {
                    "provider": "custom",
                    "base_url": "http://localhost:8080/v1/",
                    "model": "test-model",
                }
            }
        }
    }
    runtime = resolve_profile_runtime(config, "test")
    assert runtime["base_url"] == "http://localhost:8080/v1"


# ── profile_to_env ──────────────────────────────────────────────────────

def test_env_custom_profile():
    env = profile_to_env(SAMPLE_CONFIG, "local-mac-qwen")
    assert env is not None
    assert env["OPENAI_BASE_URL"] == "http://127.0.0.1:11434/v1"
    assert env["OPENAI_API_KEY"] == "ollama"
    assert env["HERMES_MODEL"] == "qwen3:8b"
    assert env["HERMES_INFERENCE_PROVIDER"] == "custom"


def test_env_cloud_profile():
    env = profile_to_env(SAMPLE_CONFIG, "frontier-opus")
    assert env is not None
    assert "OPENAI_BASE_URL" not in env  # no custom base_url
    assert env["HERMES_MODEL"] == "anthropic/claude-opus-4.6"
    # openrouter is the default provider — no need to set env var
    assert "HERMES_INFERENCE_PROVIDER" not in env


def test_env_not_found():
    assert profile_to_env(SAMPLE_CONFIG, "nonexistent") is None


# ── check_profile_health ────────────────────────────────────────────────

def test_health_not_found():
    result = check_profile_health(EMPTY_CONFIG, "nope")
    assert result["healthy"] is False
    assert "not found" in result["error"]


def test_health_cloud_provider_assumed():
    result = check_profile_health(SAMPLE_CONFIG, "frontier-opus")
    assert result["healthy"] is True
    assert "assumed" in result.get("note", "")


def test_health_no_base_url():
    config = {
        "fleet": {
            "model_profiles": {
                "broken": {"provider": "custom", "model": "test"}
            }
        }
    }
    result = check_profile_health(config, "broken")
    assert result["healthy"] is False
    assert "No base_url" in result["error"]


def test_health_unreachable():
    config = {
        "fleet": {
            "model_profiles": {
                "unreachable": {
                    "provider": "custom",
                    "base_url": "http://127.0.0.1:19999/v1",
                    "model": "test",
                }
            }
        }
    }
    result = check_profile_health(config, "unreachable", timeout=0.5)
    assert result["healthy"] is False
    assert result["reachable"] is False


# ── Live health check against a mock server ──────────────────────────────

class _MockModelsHandler(BaseHTTPRequestHandler):
    """Responds to GET /models with a fake OpenAI-compatible model list."""

    def do_GET(self):
        if self.path == "/models":
            body = json.dumps({
                "data": [
                    {"id": "qwen3:8b", "object": "model"},
                    {"id": "llama3:8b", "object": "model"},
                ]
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # silence logs


@pytest.fixture
def mock_models_server():
    """Start a temporary HTTP server that mimics /models."""
    server = HTTPServer(("127.0.0.1", 0), _MockModelsHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def test_health_model_available(mock_models_server):
    config = {
        "fleet": {
            "model_profiles": {
                "test": {
                    "provider": "custom",
                    "base_url": mock_models_server,
                    "model": "qwen3:8b",
                }
            }
        }
    }
    result = check_profile_health(config, "test")
    assert result["healthy"] is True
    assert result["reachable"] is True
    assert result["model_available"] is True
    assert "qwen3:8b" in result["models"]


def test_health_model_not_available(mock_models_server):
    config = {
        "fleet": {
            "model_profiles": {
                "test": {
                    "provider": "custom",
                    "base_url": mock_models_server,
                    "model": "nonexistent-model",
                }
            }
        }
    }
    result = check_profile_health(config, "test")
    assert result["healthy"] is False
    assert result["reachable"] is True
    assert result["model_available"] is False
    assert "not found" in result["error"]
