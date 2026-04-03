"""
paths.py - Cross-platform path resolution cho Social Agent
===========================================================
Dùng platformdirs để resolve đúng user data directory theo OS:

  macOS:   ~/Library/Application Support/social-agent/
  Windows: C:\\Users\\<user>\\AppData\\Roaming\\social-agent\\
  Linux:   ~/.local/share/social-agent/

Cấu trúc thư mục sau khi cài đặt:
  <data_dir>/
  ├── config.yaml        ← global settings (model, etc)
  ├── .env               ← secrets
  ├── social_agent.db    ← SQLite database (audit log, review queue, registry)
  ├── profiles/          ← individual .yaml files per account
  ├── topics/            ← individual .yaml files per topic
  └── logs/
      └── app.log

Cách dùng:
    from social_agent.utils.paths import get_data_dir, get_log_dir, get_db_path, get_config_path
"""

import os
import sys
from pathlib import Path

APP_NAME = "social-agent"
APP_AUTHOR = "social-agent"


def _try_platformdirs() -> bool:
    try:
        import platformdirs  # noqa: F401
        return True
    except ImportError:
        return False


def get_data_dir() -> Path:
    """
    User data directory theo OS. Tất cả runtime data (db, logs, config) lưu tại đây.

    macOS:   ~/Library/Application Support/social-agent/
    Windows: %APPDATA%\\social-agent\\
    Linux:   ~/.local/share/social-agent/
    """
    if _try_platformdirs():
        from platformdirs import user_data_dir
        p = Path(user_data_dir(APP_NAME, APP_AUTHOR))
    else:
        p = Path.cwd() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_log_dir() -> Path:
    """
    Log directory. Override via env var SOCIAL_AGENT_LOG_DIR (hữu ích cho Docker/VPS).

    Default: <data_dir>/logs/
    """
    env_override = os.environ.get("SOCIAL_AGENT_LOG_DIR")
    if env_override:
        p = Path(env_override)
    else:
        p = get_data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_db_path() -> Path:
    """
    SQLite database path. Override via env var SOCIAL_AGENT_DB_PATH.

    Default: <data_dir>/social_agent.db
    Tách riêng khỏi logs để dễ backup và migrate lên cloud sau này.
    """
    env_override = os.environ.get("SOCIAL_AGENT_DB_PATH")
    if env_override:
        return Path(env_override)
    return get_data_dir() / "social_agent.db"


def get_config_path(filename: str = "config.yaml") -> Path:
    """
    Tìm config.yaml theo thứ tự ưu tiên:
    1. SOCIAL_AGENT_CONFIG env var
    2. Thư mục hiện tại (CWD) — developer / CLI dùng trực tiếp
    3. <data_dir>/config.yaml — installed app
    4. Thư mục chứa file này (bundled PyInstaller app)

    Trả về Path đến file (có thể chưa tồn tại nếu chưa setup lần đầu).
    """
    env_override = os.environ.get("SOCIAL_AGENT_CONFIG")
    if env_override:
        return Path(env_override)

    candidates = [
        Path.cwd() / filename,
        get_data_dir() / filename,
        Path(__file__).parent / filename,
    ]
    for p in candidates:
        if p.exists():
            return p

    # Default: data_dir (nơi first-run sẽ copy template vào)
    return get_data_dir() / filename


def get_profiles_dir() -> Path:
    """Thư mục chứa các profile đơn lẻ (*.yaml)."""
    p = get_data_dir() / "profiles"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_topics_dir() -> Path:
    """Thư mục chứa định nghĩa topic (*.yaml)."""
    p = get_data_dir() / "topics"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_env_path() -> Path:
    """
    .env file path. Override via env var SOCIAL_AGENT_ENV_PATH.

    Default: <data_dir>/.env
    """
    env_override = os.environ.get("SOCIAL_AGENT_ENV_PATH")
    if env_override:
        return Path(env_override)

    candidates = [
        Path.cwd() / ".env",
        get_data_dir() / ".env",
    ]
    for p in candidates:
        if p.exists():
            return p

    return get_data_dir() / ".env"


def get_chrome_profile_default() -> Path:
    """Default Chrome user data directory theo OS."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    elif sys.platform == "win32":
        appdata = os.environ.get("LOCALAPPDATA", "")
        return Path(appdata) / "Google" / "Chrome" / "User Data"
    else:
        return Path.home() / ".config" / "google-chrome"
