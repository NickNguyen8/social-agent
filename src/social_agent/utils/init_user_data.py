"""
init_user_data.py - First-run setup cho Social Agent
=====================================================
Lần đầu chạy app, copy config.yaml template và .env.example vào user data dir
để người dùng có thể edit mà không cần biết source code ở đâu.

Gọi từ: agent.py, desktop/main.py, web/server.py
"""

import logging
import shutil
from pathlib import Path

from social_agent.utils.paths import get_data_dir, get_config_path, get_env_path

logger = logging.getLogger("social_agent.init")

# Root của repo / bundle — thư mục chứa config.yaml template
# src/social_agent/utils/init_user_data.py → parents[3] = social-agent/ (project root)
_PACKAGE_ROOT = Path(__file__).resolve().parents[3]  # social-agent/


def ensure_user_data_dir() -> dict:
    """
    Đảm bảo user data directory có đủ files cần thiết.
    Chỉ copy nếu file chưa tồn tại — không bao giờ overwrite.

    Trả về dict mô tả những gì đã được tạo:
      {"config": Path | None, "env_example": Path | None, "data_dir": Path}
    """
    data_dir = get_data_dir()
    created = {"config": None, "env_example": None, "data_dir": data_dir}

    # 1. config.yaml — copy template nếu chưa có
    config_dest = data_dir / "config.yaml"
    if not config_dest.exists():
        config_template = _PACKAGE_ROOT / "config.yaml"
        if config_template.exists():
            shutil.copy2(config_template, config_dest)
            logger.info(f"First run: copied config.yaml → {config_dest}")
            created["config"] = config_dest
        else:
            logger.warning(f"config.yaml template không tìm thấy tại {config_template}")

    # 2. .env.example — copy để user biết cần điền gì
    env_example_dest = data_dir / ".env.example"
    if not env_example_dest.exists():
        env_example_src = _PACKAGE_ROOT / ".env.example"
        if env_example_src.exists():
            shutil.copy2(env_example_src, env_example_dest)
            logger.info(f"First run: copied .env.example → {env_example_dest}")
            created["env_example"] = env_example_dest

    # 3. Thông báo nếu .env chưa tồn tại
    env_path = get_env_path()
    if not env_path.exists():
        logger.warning(
            f".env không tìm thấy. Tạo file tại: {data_dir / '.env'}\n"
            f"Tham khảo: {env_example_dest}"
        )

    return created
