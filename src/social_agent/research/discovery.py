"""
research/discovery.py - Dynamic Source Discovery cho Social Agent
=================================================================
Thay thế static URL lists trong config.yaml bằng hệ thống tự động:

1. GeminiSearchDiscovery  — dùng Gemini Search Grounding để tìm URLs mới nhất theo topic
2. FBPageDiscovery        — dùng Gemini để suggest FB page IDs, validate qua Graph API
3. SourceRegistry (SQLite) — lưu lại sources đã discover, score theo success rate, tự grow

Flow:
  topic_keywords
    → GeminiSearchDiscovery.find_urls()      (Gemini + Google Search grounding)
    → FBPageDiscovery.find_pages()           (Gemini suggest → FB Graph API validate)
    → SourceRegistry.merge_and_score()      (dedup, persist, return ranked sources)
    → ResearchAgent.research()              (fetch + summarize như cũ)

Config.yaml research.urls/fb_pages chỉ còn là OPTIONAL SEED, không phải nguồn chính.
"""

import json
import logging
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger("social_agent.research.discovery")


# ============================================================
# Source Registry — SQLite-backed, grows over time
# ============================================================

_REGISTRY_SCHEMA = """
CREATE TABLE IF NOT EXISTS discovered_sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id        TEXT    NOT NULL,
    source_type     TEXT    NOT NULL,   -- 'web_url' | 'fb_page' | 'fb_group'
    identifier      TEXT    NOT NULL,   -- URL hoặc FB page ID/username
    display_name    TEXT,               -- Tên hiển thị
    discovered_at   TEXT    NOT NULL,
    last_used_at    TEXT,
    success_count   INTEGER NOT NULL DEFAULT 0,
    fail_count      INTEGER NOT NULL DEFAULT 0,
    is_active       INTEGER NOT NULL DEFAULT 1,
    UNIQUE(topic_id, source_type, identifier)
);
CREATE INDEX IF NOT EXISTS idx_sources_topic   ON discovered_sources(topic_id);
CREATE INDEX IF NOT EXISTS idx_sources_active  ON discovered_sources(is_active);
CREATE INDEX IF NOT EXISTS idx_sources_score   ON discovered_sources(success_count, fail_count);
"""


class SourceRegistry:
    """
    SQLite-backed registry của tất cả discovered sources.
    Tự động dedup, track success/fail, và rank theo score.
    """

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            from social_agent.utils.paths import get_db_path
            db_path = get_db_path()
        self._db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ensure_schema(self):
        with self._connect() as conn:
            conn.executescript(_REGISTRY_SCHEMA)
            conn.commit()

    def upsert(self, topic_id: str, source_type: str, identifier: str,
               display_name: str = "") -> None:
        """Thêm source mới hoặc update display_name nếu đã có."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO discovered_sources
                    (topic_id, source_type, identifier, display_name, discovered_at, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(topic_id, source_type, identifier)
                DO UPDATE SET
                    display_name = COALESCE(excluded.display_name, display_name),
                    is_active = 1
            """, (topic_id, source_type, identifier.strip(), display_name, now))

    def mark_success(self, topic_id: str, source_type: str, identifier: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("""
                UPDATE discovered_sources
                SET success_count = success_count + 1, last_used_at = ?
                WHERE topic_id=? AND source_type=? AND identifier=?
            """, (now, topic_id, source_type, identifier))

    def mark_fail(self, topic_id: str, source_type: str, identifier: str):
        with self._connect() as conn:
            # Sau 3 lần fail liên tiếp → tự động deactivate
            conn.execute("""
                UPDATE discovered_sources
                SET fail_count = fail_count + 1,
                    is_active = CASE WHEN fail_count + 1 >= 3 THEN 0 ELSE 1 END
                WHERE topic_id=? AND source_type=? AND identifier=?
            """, (topic_id, source_type, identifier))

    def get_ranked(self, topic_id: str, source_type: str,
                   limit: int = 8) -> list[dict]:
        """
        Trả về sources active, ranked theo score = success_count - fail_count.
        Sources mới (chưa dùng) được ưu tiên ngang với success_count=1.
        """
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT identifier, display_name, success_count, fail_count
                FROM discovered_sources
                WHERE topic_id=? AND source_type=? AND is_active=1
                ORDER BY (success_count - fail_count) DESC,
                         discovered_at DESC
                LIMIT ?
            """, (topic_id, source_type, limit)).fetchall()
        return [dict(r) for r in rows]

    def count(self, topic_id: str, source_type: str) -> int:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT COUNT(*) FROM discovered_sources
                WHERE topic_id=? AND source_type=? AND is_active=1
            """, (topic_id, source_type)).fetchone()
        return row[0] if row else 0

    def get_all_for_topic(self, topic_id: str) -> dict:
        """Trả về tất cả active sources cho 1 topic, grouped by type."""
        result = {"web_url": [], "fb_page": [], "fb_group": []}
        for src_type in result:
            result[src_type] = [
                r["identifier"] for r in self.get_ranked(topic_id, src_type)
            ]
        return result


# ============================================================
# GeminiSearchDiscovery — tìm URLs mới nhất qua Gemini Search
# ============================================================

class GeminiSearchDiscovery:
    """
    Dùng Gemini với Google Search Grounding để tìm URLs mới nhất cho 1 topic.
    Mỗi lần gọi trả về 5-8 bài viết/trang mới nhất — không cần hardcode.

    Không dùng thêm API key nào — chỉ dùng Gemini API key đã có.
    """

    # Model hỗ trợ search grounding — gemini-2.5-flash có Google Search tool
    SEARCH_MODEL = "gemini-2.5-flash"

    DISCOVER_PROMPT = """Tìm kiếm và liệt kê các nguồn thông tin WEB mới nhất (trong 7 ngày gần đây) về chủ đề:

**{topic_name}**

Mô tả: {topic_description}
Từ khóa tìm kiếm: {keywords}

Yêu cầu:
- Ưu tiên nguồn tiếng Việt hoặc đề cập đến Việt Nam / Đông Nam Á
- Ưu tiên: blog kỹ thuật, báo cáo, case study, tin tức chuyên ngành
- Tránh: trang thương mại thuần túy, landing page, trang không có nội dung thực chất
- Chỉ liệt kê URLs thực tế có thể truy cập được

Trả về JSON (KHÔNG có text khác):
{{
  "urls": [
    {{"url": "https://...", "title": "Tên trang/bài", "reason": "Lý do chọn"}},
    ...
  ],
  "search_summary": "Tóm tắt ngắn về điều bạn tìm thấy"
}}

Liệt kê tối đa 8 URLs chất lượng nhất."""

    def __init__(self, gemini_api_key: str):
        self.api_key = gemini_api_key

    def discover(self, topic_id: str, topic_name: str, topic_description: str,
                 keywords: list[str], registry: SourceRegistry,
                 max_urls: int = 8) -> list[str]:
        """
        Tìm và lưu URLs mới vào registry. Trả về list URLs để dùng ngay.
        """
        prompt = self.DISCOVER_PROMPT.format(
            topic_name=topic_name,
            topic_description=topic_description,
            keywords=", ".join(keywords[:8]),
        )

        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.SEARCH_MODEL}:generateContent"
            )
            headers = {"x-goog-api-key": self.api_key}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "tools": [{"google_search": {}}],  # Enable Google Search grounding
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 2048,
                },
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            raw = data["candidates"][0]["content"]["parts"][0]["text"]
            discovered = self._parse_urls(raw)

            # Lưu vào registry
            saved = []
            for item in discovered[:max_urls]:
                u = item.get("url", "").strip()
                if u and u.startswith("http"):
                    registry.upsert(topic_id, "web_url", u, item.get("title", ""))
                    saved.append(u)

            logger.info(f"[GeminiSearch] topic={topic_id}: found {len(saved)} URLs")
            return saved

        except Exception as e:
            logger.warning(f"[GeminiSearch] Gemini search grounding failed: {e}")
            return []

    def _parse_urls(self, raw: str) -> list[dict]:
        cleaned = raw.strip()
        # Thử extract JSON block
        m = re.search(r"```json\s*(.*?)\s*```", cleaned, re.DOTALL)
        if m:
            cleaned = m.group(1)
        else:
            m = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if m:
                cleaned = m.group(0)
        try:
            result = json.loads(cleaned)
            return result.get("urls", [])
        except (json.JSONDecodeError, Exception):
            # Fallback: extract URLs trực tiếp từ text
            return [
                {"url": u, "title": ""}
                for u in re.findall(r"https?://[^\s\"'<>]+", raw)
                if "facebook.com" not in u  # FB URLs xử lý riêng
            ]


# ============================================================
# FBPageDiscovery — discover và validate Facebook pages
# ============================================================

class FBPageDiscovery:
    """
    Dùng Gemini để suggest Facebook pages/communities phù hợp với topic,
    sau đó validate từng page qua Facebook Graph API.
    Pages hợp lệ được lưu vào SourceRegistry để dùng lại.
    """

    SUGGEST_PROMPT = """Liệt kê các Facebook Page và Group cộng đồng Việt Nam liên quan đến chủ đề:

**{topic_name}**
Mô tả: {topic_description}
Từ khóa: {keywords}

Yêu cầu:
- Ưu tiên: cộng đồng kỹ thuật VN, group chuyên ngành, page của công ty/tổ chức thật
- Ưu tiên: group/page có nhiều thành viên hoặc followes, hoạt động tích cực
- Chỉ liệt kê page/group THẬT SỰ TỒN TẠI trên Facebook
- Dùng username/vanity name (phần sau facebook.com/) hoặc page ID số

Ví dụ format:
- "hanoiaiclub" → username của page AI Hà Nội
- "vndevs" → username của cộng đồng dev VN
- "1234567890" → page ID số

Trả về JSON:
{{
  "pages": [
    {{"id": "username_hoac_page_id", "name": "Tên page/group", "type": "page|group", "reason": "Lý do chọn"}},
    ...
  ]
}}

Liệt kê tối đa 10 pages/groups."""

    FB_GRAPH_BASE = "https://graph.facebook.com/v20.0"

    def __init__(self, gemini_api_key: str, fb_access_token: Optional[str] = None):
        self.gemini_api_key = gemini_api_key
        self.fb_token = fb_access_token

    def discover(self, topic_id: str, topic_name: str, topic_description: str,
                 keywords: list[str], registry: SourceRegistry,
                 max_pages: int = 8) -> list[str]:
        """
        Suggest + validate FB pages. Trả về list page IDs/usernames hợp lệ.
        """
        suggestions = self._suggest_pages(topic_name, topic_description, keywords)
        if not suggestions:
            logger.info(f"[FBPageDiscovery] No suggestions from Gemini for {topic_id}")
            return []

        validated = []
        for item in suggestions[:15]:  # Validate tối đa 15 suggestions
            page_id = item.get("id", "").strip()
            if not page_id:
                continue

            is_valid, display_name = self._validate_page(page_id)
            if is_valid:
                src_type = "fb_group" if item.get("type") == "group" else "fb_page"
                name = display_name or item.get("name", page_id)
                registry.upsert(topic_id, src_type, page_id, name)
                validated.append(page_id)
                logger.debug(f"[FBPageDiscovery] Validated: {page_id} ({name})")
            else:
                logger.debug(f"[FBPageDiscovery] Invalid/inaccessible: {page_id}")

            if len(validated) >= max_pages:
                break

        logger.info(f"[FBPageDiscovery] topic={topic_id}: {len(validated)}/{len(suggestions)} pages validated")
        return validated

    def _suggest_pages(self, topic_name: str, topic_description: str,
                       keywords: list[str]) -> list[dict]:
        prompt = self.SUGGEST_PROMPT.format(
            topic_name=topic_name,
            topic_description=topic_description,
            keywords=", ".join(keywords[:8]),
        )
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-2.5-flash:generateContent"
            )
            headers = {"x-goog-api-key": self.gemini_api_key}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 1024,
                    "thinkingConfig": {"thinkingBudget": 0},
                },
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            resp.raise_for_status()
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]

            cleaned = raw.strip()
            m = re.search(r"```json\s*(.*?)\s*```", cleaned, re.DOTALL)
            if m:
                cleaned = m.group(1)
            else:
                m = re.search(r"\{.*\}", cleaned, re.DOTALL)
                if m:
                    cleaned = m.group(0)

            return json.loads(cleaned).get("pages", [])
        except Exception as e:
            logger.warning(f"[FBPageDiscovery] Gemini suggest failed: {e}")
            return []

    def _validate_page(self, page_id_or_name: str) -> tuple[bool, str]:
        """
        Kiểm tra page/group có tồn tại và accessible qua token hiện tại không.
        Trả về (is_valid, display_name).
        """
        if not self.fb_token:
            # Không có token → không validate được nhưng vẫn giữ lại để thử sau
            return True, page_id_or_name

        try:
            url = f"{self.FB_GRAPH_BASE}/{page_id_or_name}"
            params = {
                "access_token": self.fb_token,
                "fields": "id,name,fan_count",
            }
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()

            if "error" in data:
                return False, ""

            name = data.get("name", page_id_or_name)
            return True, name

        except Exception:
            # Timeout hoặc network error → không loại bỏ, để retry sau
            return True, page_id_or_name


# ============================================================
# DynamicSourceResolver — điểm tập trung cho cả hệ thống
# ============================================================

class DynamicSourceResolver:
    """
    Tập hợp tất cả discovery strategies và trả về sources cho ResearchAgent.

    Thay thế việc đọc static URLs từ config.yaml.
    Mỗi topic run → discover + update registry → return ranked sources.

    Usage:
        resolver = DynamicSourceResolver(gemini_api_key, fb_token)
        sources = resolver.resolve(topic_id, topic_cfg)
        # sources = {"urls": [...], "fb_pages": [...]}
        brief = research_agent.research(topic_description, **sources)
    """

    # Số nguồn tối đa trả về cho ResearchAgent mỗi lần
    MAX_WEB_URLS = 5
    MAX_FB_PAGES = 4

    # Chỉ re-discover khi registry có ít hơn ngưỡng này
    MIN_SOURCES_THRESHOLD = 3

    def __init__(
        self,
        gemini_api_key: str,
        fb_access_token: Optional[str] = None,
        registry: Optional[SourceRegistry] = None,
    ):
        self.gemini_api_key = gemini_api_key
        self.fb_token = fb_access_token
        self.registry = registry or SourceRegistry()
        self.web_discovery = GeminiSearchDiscovery(gemini_api_key)
        self.fb_discovery = FBPageDiscovery(gemini_api_key, fb_access_token)

    def resolve(
        self,
        topic_id: str,
        topic_cfg: dict,
        seed_urls: Optional[list] = None,
        seed_fb_pages: Optional[list] = None,
        force_discover: bool = False,
    ) -> dict:
        """
        Trả về {"urls": [...], "fb_pages": [...]} cho topic.

        Logic:
        1. Seed từ config (nếu có) vào registry
        2. Nếu registry thiếu nguồn (< MIN_SOURCES_THRESHOLD) → chạy discovery
        3. Trả về top-ranked sources từ registry
        """
        topic_name = topic_cfg.get("name", topic_id)
        topic_description = topic_cfg.get("description", "")
        keywords = topic_cfg.get("keywords", [])

        # Bước 1: Seed từ config → registry (lần đầu hoặc không tốn thêm call)
        for url in (seed_urls or []):
            if url and url.startswith("http"):
                self.registry.upsert(topic_id, "web_url", url, "")
        for page in (seed_fb_pages or []):
            if page:
                self.registry.upsert(topic_id, "fb_page", page, "")

        # Bước 2: Discovery nếu cần
        web_count = self.registry.count(topic_id, "web_url")
        fb_count = self.registry.count(topic_id, "fb_page") + \
                   self.registry.count(topic_id, "fb_group")

        if force_discover or web_count < self.MIN_SOURCES_THRESHOLD:
            logger.info(
                f"[DynamicSourceResolver] topic={topic_id}: "
                f"web={web_count} < {self.MIN_SOURCES_THRESHOLD} → running web discovery"
            )
            self.web_discovery.discover(
                topic_id, topic_name, topic_description, keywords, self.registry
            )

        if force_discover or fb_count < self.MIN_SOURCES_THRESHOLD:
            logger.info(
                f"[DynamicSourceResolver] topic={topic_id}: "
                f"fb={fb_count} < {self.MIN_SOURCES_THRESHOLD} → running FB page discovery"
            )
            self.fb_discovery.discover(
                topic_id, topic_name, topic_description, keywords, self.registry
            )

        # Bước 3: Trả về top-ranked sources
        web_sources = self.registry.get_ranked(topic_id, "web_url", self.MAX_WEB_URLS)
        fb_page_sources = self.registry.get_ranked(topic_id, "fb_page", self.MAX_FB_PAGES)
        fb_group_sources = self.registry.get_ranked(topic_id, "fb_group", 2)

        urls = [s["identifier"] for s in web_sources]
        fb_pages = [s["identifier"] for s in fb_page_sources + fb_group_sources]

        logger.info(
            f"[DynamicSourceResolver] topic={topic_id} resolved: "
            f"{len(urls)} URLs, {len(fb_pages)} FB pages/groups"
        )
        return {"urls": urls, "fb_pages": fb_pages, "linkedin_companies": []}

    def record_result(self, topic_id: str, sources_fetched: list, sources_failed: list):
        """
        Gọi sau khi ResearchAgent.research() xong để update scores trong registry.
        sources_fetched và sources_failed có format "type:identifier" (từ ResearchBrief).
        """
        for entry in sources_fetched:
            src_type, identifier = self._parse_entry(entry)
            if src_type and identifier:
                reg_type = "fb_page" if src_type == "facebook" else \
                           "fb_group" if src_type == "facebook_group" else "web_url"
                self.registry.mark_success(topic_id, reg_type, identifier)

        for entry in sources_failed:
            src_type, identifier = self._parse_entry(entry)
            if src_type and identifier:
                reg_type = "fb_page" if src_type == "facebook" else \
                           "fb_group" if src_type == "facebook_group" else "web_url"
                self.registry.mark_fail(topic_id, reg_type, identifier)

    def _parse_entry(self, entry: str) -> tuple[str, str]:
        """Parse "web:https://..." hoặc "facebook:page_id" thành (type, identifier)."""
        parts = entry.split(":", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return "", entry

    def get_registry_stats(self, topic_id: Optional[str] = None) -> dict:
        """Stats về registry để dùng trong CLI stats command."""
        with self.registry._connect() as conn:
            if topic_id:
                rows = conn.execute("""
                    SELECT source_type, COUNT(*) as total,
                           SUM(is_active) as active,
                           SUM(success_count) as hits
                    FROM discovered_sources
                    WHERE topic_id=?
                    GROUP BY source_type
                """, (topic_id,)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT topic_id, source_type, COUNT(*) as total,
                           SUM(is_active) as active
                    FROM discovered_sources
                    GROUP BY topic_id, source_type
                    ORDER BY topic_id
                """).fetchall()
        return [dict(r) for r in rows]
