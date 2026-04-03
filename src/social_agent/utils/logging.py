"""
logger_setup.py - Cấu hình logging toàn bộ agent
Console logger dùng Rich (màu sắc, icon), file logger rotating, JSONL audit log
"""

import json
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler

# Console toàn cục để dùng trong toàn bộ project
console = Console()


def setup_logging(log_dir: str = "logs", level: str = "INFO") -> logging.Logger:
    """
    Khởi tạo logging: Rich console + rotating file.
    Gọi một lần duy nhất khi khởi động agent.
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    log_level = getattr(logging, level.upper(), logging.INFO)

    # Root logger
    logger = logging.getLogger("fb_agent")
    logger.setLevel(log_level)

    # Tránh duplicate handlers nếu gọi lại
    if logger.handlers:
        return logger

    # --- Console handler dùng Rich ---
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        markup=True,
        rich_tracebacks=True,
    )
    rich_handler.setLevel(log_level)
    logger.addHandler(rich_handler)

    # --- File handler rotating ---
    log_file = Path(log_dir) / "app.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger


class AuditLogger:
    """
    Ghi audit log dạng JSONL (mỗi dòng = 1 post attempt).
    Dùng để thống kê và debug sau này.
    """

    def __init__(self, log_dir: str = "logs"):
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        self.log_path = Path(log_dir) / "posts.jsonl"

    def log_post(
        self,
        target_id: str,
        target_type: str,
        topic_id: str,
        format_id: str,
        content_preview: str,
        success: bool,
        post_id: Optional[str] = None,
        post_url: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Ghi một entry vào JSONL audit log."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "target_id": target_id,
            "target_type": target_type,
            "topic_id": topic_id,
            "format_id": format_id,
            "content_preview": content_preview[:100] + "..." if len(content_preview) > 100 else content_preview,
            "success": success,
            "post_id": post_id,
            "post_url": post_url,
            "error": error,
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read_history(self, limit: int = 50) -> list:
        """Đọc lịch sử post gần nhất."""
        if not self.log_path.exists():
            return []
        lines = self.log_path.read_text(encoding="utf-8").strip().split("\n")
        lines = [l for l in lines if l.strip()]
        entries = []
        for line in lines:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries[-limit:]

    def stats(self) -> dict:
        """Thống kê tổng hợp từ audit log."""
        history = self.read_history(limit=10000)
        total = len(history)
        success = sum(1 for e in history if e.get("success"))
        failed = total - success
        by_target = {}
        by_topic = {}
        for entry in history:
            t = entry.get("target_id", "unknown")
            by_target[t] = by_target.get(t, 0) + 1
            tp = entry.get("topic_id", "unknown")
            by_topic[tp] = by_topic.get(tp, 0) + 1
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "by_target": by_target,
            "by_topic": by_topic,
        }
