"""
sqlite_store.py - SQLite-backed storage cho ReviewQueue và AuditLogger
======================================================================
Thay thế flat JSONL files để có:
  - O(log n) reads/writes thay vì O(n) chép toàn bộ file
  - ACID transactions - không bị corrupt khi crash giữa chừng
  - SQL aggregates cho stats() - không cần đọc hết file
  - Dùng sqlite3 stdlib, không cần thêm dependency
  - Cross-platform: các Path được normalize đúng trên cả 3 OS

Schema:
  posts     - audit log (append-only)
  queue     - review queue (mutable status)
"""

import hashlib
import json
import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from social_agent.utils.paths import get_db_path as _default_db_path

logger = logging.getLogger("social_agent.storage")


def _connect(db_path: Path) -> sqlite3.Connection:
    """Mở connection với WAL mode (tốt hơn cho concurrent read/write)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ============================================================
# Schema migration
# ============================================================

_SCHEMA_VERSION = 2

def _content_hash(content: str) -> str:
    """SHA-256 rút gọn của toàn bộ nội dung — dùng để phát hiện trùng lặp chính xác."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:24]


def _init_schema(conn: sqlite3.Connection):
    """Tạo tables + migrate schema nếu cần. Safe to call nhiều lần."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        );

        CREATE TABLE IF NOT EXISTS posts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT NOT NULL,
            target_id       TEXT NOT NULL,
            target_type     TEXT NOT NULL,
            topic_id        TEXT NOT NULL,
            format_id       TEXT NOT NULL,
            content_preview TEXT,
            content_hash    TEXT,
            success         INTEGER NOT NULL DEFAULT 0,
            post_id         TEXT,
            post_url        TEXT,
            error           TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_posts_target  ON posts(target_id);
        CREATE INDEX IF NOT EXISTS idx_posts_success ON posts(success);
        CREATE INDEX IF NOT EXISTS idx_posts_time    ON posts(timestamp);
        CREATE INDEX IF NOT EXISTS idx_posts_hash    ON posts(content_hash);

        CREATE TABLE IF NOT EXISTS queue (
            id              TEXT PRIMARY KEY,
            created_at      TEXT NOT NULL,
            reviewed_at     TEXT,
            target_id       TEXT NOT NULL,
            topic_id        TEXT NOT NULL,
            format_id       TEXT NOT NULL,
            platform        TEXT NOT NULL,
            content         TEXT NOT NULL,
            image_path      TEXT,
            brief_summary   TEXT,
            status          TEXT NOT NULL DEFAULT 'pending',
            rejection_reason TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status);

        CREATE TABLE IF NOT EXISTS writing_memory (
            profile_id      TEXT NOT NULL,
            topic_id        TEXT NOT NULL,
            approved_samples TEXT,    -- JSON array: [{title, body, cta}]
            learned_rules   TEXT,     -- JSON array: ["Không dùng từ X", "Luôn có Y"]
            voice_notes     TEXT,     -- Ghi chú riêng cho profile
            updated_at      TEXT,
            PRIMARY KEY (profile_id, topic_id)
        );
    """)

    # Schema migration v1 → v2: thêm content_hash column nếu chưa có
    existing = {row[1] for row in conn.execute("PRAGMA table_info(posts)").fetchall()}
    if "content_hash" not in existing:
        conn.execute("ALTER TABLE posts ADD COLUMN content_hash TEXT")
        logger.info("Schema migrated: added content_hash column")

    if "rejection_reason" not in {row[1] for row in conn.execute("PRAGMA table_info(queue)").fetchall()}:
        conn.execute("ALTER TABLE queue ADD COLUMN rejection_reason TEXT")
        logger.info("Schema migrated: added rejection_reason column to queue")

    conn.execute("INSERT OR IGNORE INTO schema_version VALUES (?)", (_SCHEMA_VERSION,))
    conn.commit()


# ============================================================
# JSONL Migration helper — chạy 1 lần khi upgrade
# ============================================================

def migrate_from_jsonl(log_dir: str, db_path: Optional[Path] = None) -> dict:
    """
    Import dữ liệu từ legacy JSONL files vào SQLite (chỉ chạy 1 lần).
    Trả về {'posts': n, 'queue': n} số records đã import.
    """
    log_path = Path(log_dir)
    posts_jsonl = log_path / "posts.jsonl"
    queue_jsonl = log_path / "review_queue.jsonl"
    counts = {"posts": 0, "queue": 0}

    with _connect(db_path or _default_db_path()) as conn:
        _init_schema(conn)

        # Migrate posts
        if posts_jsonl.exists():
            for line in posts_jsonl.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    conn.execute("""
                        INSERT OR IGNORE INTO posts
                        (timestamp, target_id, target_type, topic_id, format_id,
                         content_preview, success, post_id, post_url, error)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                    """, (
                        e.get("timestamp", datetime.now().isoformat()),
                        e.get("target_id", ""),
                        e.get("target_type", ""),
                        e.get("topic_id", ""),
                        e.get("format_id", ""),
                        e.get("content_preview", "")[:100],
                        1 if e.get("success") else 0,
                        e.get("post_id"),
                        e.get("post_url"),
                        e.get("error"),
                    ))
                    counts["posts"] += 1
                except (json.JSONDecodeError, Exception):
                    continue
            conn.commit()
            # Rename cũ để bảo toàn
            posts_jsonl.rename(posts_jsonl.with_suffix(".jsonl.bak"))
            logger.info(f"Migrated {counts['posts']} posts from JSONL")

        # Migrate queue
        if queue_jsonl.exists():
            for line in queue_jsonl.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    conn.execute("""
                        INSERT OR IGNORE INTO queue
                        (id, created_at, reviewed_at, target_id, topic_id, format_id,
                         platform, content, image_path, brief_summary, status)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        e.get("id", uuid.uuid4().hex[:8]),
                        e.get("created_at", datetime.now().isoformat()),
                        e.get("reviewed_at"),
                        e.get("target_id", ""),
                        e.get("topic_id", ""),
                        e.get("format_id", ""),
                        e.get("platform", "facebook"),
                        e.get("content", ""),
                        e.get("image_path"),
                        e.get("brief_summary", ""),
                        e.get("status", "pending"),
                    ))
                    counts["queue"] += 1
                except (json.JSONDecodeError, Exception):
                    continue
            conn.commit()
            queue_jsonl.rename(queue_jsonl.with_suffix(".jsonl.bak"))
            logger.info(f"Migrated {counts['queue']} queue entries from JSONL")

    return counts


# ============================================================
# ReviewQueueDB — thay thế ReviewQueue (JSONL-based)
# ============================================================

class ReviewQueueDB:
    """
    Review queue backed by SQLite.
    Drop-in replacement cho ReviewQueue cũ (JSONL).
    P1: O(log n) reads/writes thay vì O(n) của JSONL.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or _default_db_path()
        with _connect(self._db_path) as conn:
            _init_schema(conn)

    def enqueue(
        self,
        target_id: str,
        topic_id: str,
        format_id: str,
        content: str,
        platform: str,
        image_path: Optional[str] = None,
        brief_summary: str = "",
    ) -> str:
        entry_id = uuid.uuid4().hex[:8]
        with _connect(self._db_path) as conn:
            conn.execute("""
                INSERT INTO queue
                (id, created_at, target_id, topic_id, format_id,
                 platform, content, image_path, brief_summary, status)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                entry_id,
                datetime.now().isoformat(),
                target_id, topic_id, format_id,
                platform, content, image_path, brief_summary,
                "pending",
            ))
        return entry_id

    def list_pending(self) -> list:
        with _connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM queue WHERE status='pending' ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, entry_id: str) -> Optional[dict]:
        with _connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM queue WHERE id=?", (entry_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_status(self, entry_id: str, status: str, reason: Optional[str] = None) -> bool:
        with _connect(self._db_path) as conn:
            result = conn.execute(
                "UPDATE queue SET status=?, reviewed_at=?, rejection_reason=? WHERE id=?",
                (status, datetime.now().isoformat(), reason, entry_id),
            )
        return result.rowcount > 0


# ============================================================
# AuditLoggerDB — thay thế AuditLogger (JSONL-based)
# ============================================================

class AuditLoggerDB:
    """
    Audit logger backed by SQLite.
    Drop-in replacement cho AuditLogger cũ (JSONL).
    P1: stats() dùng SQL COUNT/GROUP BY thay vì đọc toàn bộ file.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or _default_db_path()
        with _connect(self._db_path) as conn:
            _init_schema(conn)

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
        chash = _content_hash(content_preview)
        preview = (
            content_preview[:500] + "..."
            if len(content_preview) > 500
            else content_preview
        )
        with _connect(self._db_path) as conn:
            conn.execute("""
                INSERT INTO posts
                (timestamp, target_id, target_type, topic_id, format_id,
                 content_preview, content_hash, success, post_id, post_url, error)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                datetime.now().isoformat(),
                target_id, target_type, topic_id, format_id,
                preview, chash, 1 if success else 0,
                post_id, post_url, error,
            ))

    def recently_posted_combo(self, target_id: str, topic_id: str, format_id: str,
                               within_hours: int = 48) -> bool:
        """True nếu cùng (target, topic, format) đã post thành công trong N giờ qua.
        Dùng để skip generate sớm — trước khi tốn Gemini call.
        """
        with _connect(self._db_path) as conn:
            row = conn.execute(
                """SELECT 1 FROM posts
                   WHERE target_id=? AND topic_id=? AND format_id=? AND success=1
                   AND timestamp >= datetime('now', ? || ' hours')
                   LIMIT 1""",
                (target_id, topic_id, format_id, f"-{within_hours}"),
            ).fetchone()
        return row is not None

    def is_duplicate(self, content: str, target_id: str) -> bool:
        """True nếu content (theo SHA-256 hash) đã từng post thành công lên target này."""
        chash = _content_hash(content)
        with _connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM posts WHERE content_hash=? AND target_id=? AND success=1 LIMIT 1",
                (chash, target_id),
            ).fetchone()
        return row is not None

    def read_history(self, limit: int = 50) -> list:
        """Đọc lịch sử post gần nhất."""
        with _connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM posts ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        result = [dict(r) for r in rows]
        # Normalize: success về bool thay vì int (backward compat)
        for r in result:
            r["success"] = bool(r["success"])
        return result

    def stats(self) -> dict:
        """
        P1 Performance: SQL aggregates thay vì đọc 10000 rows.
        Trả về dict với total, success, failed, by_target, by_topic.
        """
        with _connect(self._db_path) as conn:
            totals = conn.execute(
                "SELECT COUNT(*) as total, SUM(success) as ok FROM posts"
            ).fetchone()
            by_target_rows = conn.execute(
                "SELECT target_id, COUNT(*) as n FROM posts GROUP BY target_id ORDER BY n DESC"
            ).fetchall()
            by_topic_rows = conn.execute(
                "SELECT topic_id, COUNT(*) as n FROM posts GROUP BY topic_id ORDER BY n DESC"
            ).fetchall()

        total = totals["total"] or 0
        success = int(totals["ok"] or 0)
        return {
            "total": total,
            "success": success,
            "failed": total - success,
            "by_target": {r["target_id"]: r["n"] for r in by_target_rows},
            "by_topic": {r["topic_id"]: r["n"] for r in by_topic_rows},
        }

# ============================================================
# WritingMemoryDB - Pillar 2 Learning Loop
# ============================================================

class WritingMemoryDB:
    """Lưu trữ memory về các bài đã approve/reject để improve prompt content generation."""
    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or _default_db_path()
        with _connect(self._db_path) as conn:
            _init_schema(conn)

    def get(self, profile_id: str, topic_id: str) -> dict:
        with _connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM writing_memory WHERE profile_id=? AND topic_id=?",
                (profile_id, topic_id)
            ).fetchone()
        if not row:
            return {"approved_samples": [], "learned_rules": [], "voice_notes": ""}
        
        result = dict(row)
        result["approved_samples"] = json.loads(result["approved_samples"] or "[]")
        result["learned_rules"] = json.loads(result["learned_rules"] or "[]")
        return result

    def add_sample(self, profile_id: str, topic_id: str, sample: dict, max_samples: int = 5):
        """Lưu bài đã approve làm example. Lấy top 5 cái gần nhất."""
        mem = self.get(profile_id, topic_id)
        samples = [sample] + mem.get("approved_samples", [])
        # Dedup: skip nếu body y hệt
        seen = set()
        unique = []
        for s in samples:
            body = s.get("body", "")
            if body not in seen:
                unique.append(s)
                seen.add(body)
        
        unique = unique[:max_samples]
        
        with _connect(self._db_path) as conn:
            conn.execute("""
                INSERT INTO writing_memory (profile_id, topic_id, approved_samples, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(profile_id, topic_id) DO UPDATE SET
                    approved_samples = excluded.approved_samples,
                    updated_at = excluded.updated_at
            """, (profile_id, topic_id, json.dumps(unique), datetime.now().isoformat()))

    def add_rule(self, profile_id: str, topic_id: str, rule: str):
        """Append rule mới rút ra từ rejection feedback."""
        mem = self.get(profile_id, topic_id)
        rules = mem.get("learned_rules", [])
        if rule and rule not in rules:
            rules.append(rule)
        
        with _connect(self._db_path) as conn:
            conn.execute("""
                INSERT INTO writing_memory (profile_id, topic_id, learned_rules, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(profile_id, topic_id) DO UPDATE SET
                    learned_rules = excluded.learned_rules,
                    updated_at = excluded.updated_at
            """, (profile_id, topic_id, json.dumps(rules), datetime.now().isoformat()))
