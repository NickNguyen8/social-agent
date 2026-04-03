"""
test_config.py - Tests for config loading and env-var resolution.
"""

import os
import pytest
import yaml

from social_agent.config import load_config, _resolve_env_vars
from social_agent.types import ConfigError


class TestResolveEnvVars:
    def test_replaces_env_var_in_string(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "secret123")
        result = _resolve_env_vars("${MY_TOKEN}")
        assert result == "secret123"

    def test_keeps_placeholder_when_var_missing(self):
        result = _resolve_env_vars("${NONEXISTENT_VAR_XYZ}")
        assert result == "${NONEXISTENT_VAR_XYZ}"

    def test_resolves_nested_dict(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "key-abc")
        obj = {"outer": {"token": "${API_KEY}"}}
        result = _resolve_env_vars(obj)
        assert result["outer"]["token"] == "key-abc"

    def test_resolves_list(self, monkeypatch):
        monkeypatch.setenv("TOKEN_A", "val_a")
        result = _resolve_env_vars(["${TOKEN_A}", "literal"])
        assert result == ["val_a", "literal"]

    def test_passthrough_non_string(self):
        assert _resolve_env_vars(42) == 42
        assert _resolve_env_vars(True) is True
        assert _resolve_env_vars(None) is None


class TestLoadConfig:
    def test_valid_config_loads(self, minimal_config):
        cfg = load_config(str(minimal_config))
        assert "llm" in cfg
        assert "topics" in cfg
        assert "targets" in cfg

    def test_missing_file_raises_config_error(self, tmp_path):
        with pytest.raises(ConfigError, match="Không tìm thấy config"):
            load_config(str(tmp_path / "missing.yaml"))

    def test_invalid_yaml_raises_config_error(self, tmp_path):
        bad = tmp_path / "config.yaml"
        bad.write_text(": invalid: [bad yaml", encoding="utf-8")
        with pytest.raises(ConfigError, match="không hợp lệ"):
            load_config(str(bad))

    def test_non_mapping_yaml_raises_config_error(self, tmp_path):
        non_mapping = tmp_path / "config.yaml"
        non_mapping.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="YAML mapping"):
            load_config(str(non_mapping))

    def test_env_vars_resolved_in_tokens(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_PAGE_TOKEN", "page_token_value")
        cfg_data = {
            "llm": {"provider": "gemini", "model": "gemini-2.5-flash",
                    "temperature": 0.8, "max_tokens": 4096},
            "topics": [],
            "formats": [],
            "targets": [{"id": "p", "access_token": "${TEST_PAGE_TOKEN}"}],
            "cross_post_groups": [],
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(cfg_data), encoding="utf-8")
        cfg = load_config(str(config_file))
        assert cfg["targets"][0]["access_token"] == "page_token_value"
