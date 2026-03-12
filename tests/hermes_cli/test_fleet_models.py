"""Tests for fleet model profile helpers."""

from __future__ import annotations

from hermes_cli.fleet_models import get_model_profile, list_model_profiles


class TestListModelProfiles:
    def test_returns_empty_list_when_no_profiles_configured(self):
        assert list_model_profiles({"fleet": {"model_profiles": {}}}) == []

    def test_returns_sorted_profile_entries(self):
        config = {
            "fleet": {
                "model_profiles": {
                    "server-ollama": {
                        "provider": "custom",
                        "model": "qwen3:14b",
                        "base_url": "http://dekstop:11434/v1",
                    },
                    "frontier-opus": {
                        "provider": "openrouter",
                        "model": "anthropic/claude-opus-4.6",
                    },
                }
            }
        }

        profiles = list_model_profiles(config)
        assert [p["name"] for p in profiles] == ["frontier-opus", "server-ollama"]
        assert profiles[0]["provider"] == "openrouter"
        assert profiles[1]["base_url"] == "http://dekstop:11434/v1"


class TestGetModelProfile:
    def test_returns_profile_with_name_field(self):
        config = {
            "fleet": {
                "model_profiles": {
                    "local-qwen": {
                        "provider": "custom",
                        "model": "qwen3:8b",
                        "base_url": "http://127.0.0.1:11434/v1",
                    }
                }
            }
        }

        profile = get_model_profile(config, "local-qwen")
        assert profile == {
            "name": "local-qwen",
            "provider": "custom",
            "model": "qwen3:8b",
            "base_url": "http://127.0.0.1:11434/v1",
        }

    def test_missing_profile_returns_none(self):
        assert get_model_profile({"fleet": {"model_profiles": {}}}, "missing") is None
