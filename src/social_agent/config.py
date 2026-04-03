"""
config.py - Config loading and env-var resolution for Social Agent.
"""

import os
import re
from pathlib import Path

import yaml
from social_agent.types import ConfigError


def _resolve_env_vars(obj):
    """Đệ quy thay thế ${ENV_VAR} trong config bằng giá trị từ environment."""
    if isinstance(obj, str):
        return re.sub(
            r"\$\{([^}]+)\}",
            lambda m: os.environ.get(m.group(1), m.group(0)),
            obj,
        )
    elif isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_env_vars(i) for i in obj]
    return obj


def load_config(path: str) -> dict:
    """Load và resolve env vars trong config.yaml.

    Raises:
        ConfigError: Nếu file không tồn tại hoặc YAML không hợp lệ.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Không tìm thấy config: {path}")
    try:
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"config.yaml không hợp lệ: {e}") from e
    if not isinstance(raw, dict):
        raise ConfigError(f"config.yaml phải là một YAML mapping, nhận được: {type(raw).__name__}")
    return _resolve_env_vars(raw)
