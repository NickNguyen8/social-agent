"""
dotenv_writer.py - Tự động cập nhật giá trị trong file .env
Dùng để lưu token mới sau khi refresh mà không cần chỉnh sửa tay.
"""

import re
from pathlib import Path


def update_env_file(updates: dict, env_path: str | Path = ".env") -> list[str]:
    """
    Cập nhật các key trong .env với giá trị mới.
    - Nếu key đã tồn tại: ghi đè giá trị cũ.
    - Nếu key chưa có: thêm vào cuối file.
    Trả về danh sách các key đã được cập nhật/thêm mới.
    """
    env_path = Path(env_path)
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []

    remaining = dict(updates)  # keys chưa được ghi đè
    new_lines = []

    for line in lines:
        matched = False
        for key in list(remaining.keys()):
            # Match KEY=... hoặc # KEY=... (commented out)
            if re.match(rf"^#?\s*{re.escape(key)}\s*=", line):
                new_lines.append(f"{key}={remaining.pop(key)}")
                matched = True
                break
        if not matched:
            new_lines.append(line)

    # Thêm các key chưa có vào cuối
    if remaining:
        new_lines.append("")
        new_lines.append("# === Auto-refreshed tokens ===")
        for key, val in remaining.items():
            new_lines.append(f"{key}={val}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return list(updates.keys())
