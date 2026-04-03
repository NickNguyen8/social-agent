"""
apps/desktop/bridge.py — Python API exposed to JS via pywebview.
JS gọi: await window.pywebview.api.get_stats({})

Tất cả methods ở đây phải mirror với apps/web/server.py endpoints
để apps/ui/app.js có thể dùng được trên cả 2 môi trường.

NOTE: Dữ liệu trả về được thiết kế để sau này có thể sync lên cloud server
(các field như target_id, topic_id, timestamp đã chuẩn hóa).
"""

from __future__ import annotations

import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = str(ROOT / "config.yaml")

logger = logging.getLogger("desktop.bridge")


def _agent():
    """Lazy-load SocialAgent để tránh import chậm lúc startup."""
    from social_agent.agent import SocialAgent
    return SocialAgent(config_path=CONFIG_PATH)


class Bridge:
    """Các method này được expose thẳng vào JS window.pywebview.api.*"""

    # ── Read-only ──────────────────────────────────────────────────────────

    def get_stats(self, _args=None) -> dict:
        """Thống kê tổng hợp từ audit log."""
        return _agent().get_stats()

    def get_history(self, args: dict = None) -> list:
        """Lịch sử đăng bài gần nhất."""
        limit = (args or {}).get("limit", 20)
        return _agent().get_history(limit=limit)

    def list_targets(self, _args=None) -> list:
        """Danh sách targets đã cấu hình."""
        agent = _agent()
        return [
            {"id": k, "name": v.get("name", k), "type": v.get("type"), "enabled": v.get("enabled", True)}
            for k, v in agent._targets.items()
        ]

    def list_topics(self, _args=None) -> list:
        """Danh sách topics đã cấu hình."""
        agent = _agent()
        return [
            {"id": k, "name": v.get("name", k)}
            for k, v in agent._topics.items()
        ]

    def preview(self, args: dict) -> str:
        """Generate + render nội dung, trả về string (không đăng)."""
        topic_id = args.get("topic_id")
        format_id = args.get("format_id")
        platform = args.get("platform", "facebook")
        return _agent().preview(topic_id, format_id, platform=platform)

    # ── Actions ────────────────────────────────────────────────────────────

    def post_now(self, args: dict) -> dict:
        """Đăng bài ngay lập tức."""
        return _agent().post_now(
            target_id=args["target_id"],
            topic_id=args.get("topic_id"),
            format_id=args.get("format_id"),
            no_image=args.get("no_image", False),
        )
