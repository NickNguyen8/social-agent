"""
agent.py - Orchestrator chính của Social Agent (Facebook + LinkedIn)
=====================================================================
Pipeline: generate content (1 lần) -> render cho từng platform -> post -> audit log
Cross-post mode: 1 lệnh đăng lên nhiều platform với content từ cùng 1 LLM call
Research mode: fetch sources → summarize → generate → post (auto khi topic có research config)
Review mode: target có review_mode: true → lưu queue chờ duyệt thay vì đăng ngay
"""

import logging
import os
import random
from typing import Optional, List

from dotenv import load_dotenv

from social_agent.config import load_config
from social_agent.content.generator import ContentGenerator
from social_agent.content.formats import FormatRenderer
from social_agent.content.images import generate_image
from social_agent.platforms.facebook import FacebookAPI
from social_agent.platforms.linkedin import LinkedInAPI
from social_agent.platforms.profile import ProfileCheckpointError, ProfilePoster
from social_agent.storage.sqlite import ReviewQueueDB, AuditLoggerDB, WritingMemoryDB, migrate_from_jsonl
from social_agent.types import PLATFORM_MAP, PostingError
from social_agent.utils.logging import setup_logging
from social_agent.utils.paths import get_config_path, get_log_dir, get_profiles_dir, get_topics_dir
from social_agent.utils.init_user_data import ensure_user_data_dir

from pathlib import Path

load_dotenv()
logger = logging.getLogger("social_agent")


class ReviewQueue:
    """
    DEPRECATED: dùng ReviewQueueDB (SQLite) thay thế.
    Giữ lại alias để backward compatibility.
    """
    def __new__(cls, **_):
        logger.warning("ReviewQueue đã deprecated. Dùng ReviewQueueDB (SQLite).")
        return ReviewQueueDB()


class SocialAgent:
    """
    Agent trung tâm điều phối toàn bộ quy trình đa platform.
    Hỗ trợ Facebook (Page, Group, Profile) và LinkedIn (Personal, Company).
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        fb_api: Optional[FacebookAPI] = None,
        li_api: Optional[LinkedInAPI] = None,
        generator: Optional[ContentGenerator] = None,
        audit: Optional[AuditLoggerDB] = None,
    ):
        """
        Khởi tạo SocialAgent.

        Args:
            config_path: Đường dẫn đến config.yaml.
            fb_api: Inject FacebookAPI instance (hữu ích khi test để mock).
            li_api: Inject LinkedInAPI instance (hữu ích khi test để mock).
            generator: Inject ContentGenerator instance (hữu ích khi test để mock).
            audit: Inject AuditLoggerDB instance (hữu ích khi test với in-memory DB).
        """
        ensure_user_data_dir()
        resolved_config_path = config_path or str(get_config_path())
        self.config = load_config(resolved_config_path)

        log_cfg = self.config.get("logging", {})
        log_dir = log_cfg.get("log_dir") or str(get_log_dir())

        setup_logging(
            log_dir=log_dir,
            level=log_cfg.get("level", "INFO"),
        )

        try:
            counts = migrate_from_jsonl(log_dir)
            if any(counts.values()):
                logger.info(f"JSONL -> SQLite migration: {counts}")
        except Exception as e:
            logger.debug(f"Migration skip (OK nếu đã migrate rồi): {e}")

        self.generator = generator or ContentGenerator(resolved_config_path)
        self.renderer = FormatRenderer()
        self.fb_api = fb_api or FacebookAPI()
        self.li_api = li_api or LinkedInAPI()
        self.audit = audit or AuditLoggerDB()
        self.writing_memory = WritingMemoryDB()
        self._log_dir = log_dir

        self._load_from_dirs()

    def _load_from_dirs(self):
        """Loading targets, topics, formats from individual YAML files in their respective folders."""
        import yaml
        from social_agent.config import _resolve_env_vars

        self._targets = {}
        p_dir = get_profiles_dir()
        # Fallback search if empty (during dev)
        if not any(p_dir.glob("*.yaml")):
            p_dir = Path("profiles")
            
        for f in p_dir.glob("*.yaml"):
            try:
                with open(f, encoding="utf-8") as f_in:
                    data = yaml.safe_load(f_in)
                    if data and "id" in data:
                        self._targets[data["id"]] = _resolve_env_vars(data)
            except Exception as e:
                logger.error(f"Lỗi load profile {f}: {e}")

        self._topics = {}
        t_dir = get_topics_dir()
        if not any(t_dir.glob("*.yaml")):
            t_dir = Path("topics")
            
        for f in t_dir.glob("*.yaml"):
            try:
                with open(f, encoding="utf-8") as f_in:
                    data = yaml.safe_load(f_in)
                    if data and "id" in data:
                        self._topics[data["id"]] = _resolve_env_vars(data)
            except Exception as e:
                logger.error(f"Lỗi load topic {f}: {e}")

        # Formats & Cross-post groups
        self._formats = {}
        for f in Path("formats").glob("*.yaml"):
            try:
                with open(f, encoding="utf-8") as f_in:
                    data = yaml.safe_load(f_in)
                    if data and "id" in data:
                        self._formats[data["id"]] = data
            except Exception: pass

        self._cross_groups = {}
        for f in Path("cross_post_groups").glob("*.yaml"):
            try:
                with open(f, encoding="utf-8") as f_in:
                    data = yaml.safe_load(f_in)
                    if data and "id" in data:
                        self._cross_groups[data["id"]] = data
            except Exception: pass

        logger.info(f"Loaded: {len(self._targets)} targets, {len(self._topics)} topics")

    def post_now(
        self,
        target_id: str,
        topic_id: Optional[str] = None,
        format_id: Optional[str] = None,
        image_path: Optional[str] = None,
        no_image: bool = False,
    ) -> dict:
        """
        Đăng bài ngay lập tức lên 1 target.
        Tự động dùng research flow nếu topic có block 'research' trong config.
        Nếu target có review_mode: true → lưu vào review queue thay vì đăng ngay.
        """
        target = self._targets.get(target_id)
        if not target:
            raise ValueError(f"Target không tồn tại: {target_id}")

        topic_id = topic_id or self._pick_fresh_topic(target_id, target)
        format_id = format_id or self._pick_fresh_format(target_id, target, topic_id)

        topic_cfg = self._topics.get(topic_id)
        if not topic_cfg:
            raise ValueError(f"Topic không tồn tại: {topic_id}")
        fmt = self._formats.get(format_id)
        if not fmt:
            raise ValueError(f"Format không tồn tại: {format_id}")

        research_cfg = topic_cfg.get("research")
        review_mode = target.get("review_mode", False)

        logger.info(
            f"[{target_id}] Post: topic={topic_id}, format={format_id}, "
            f"research={'yes' if research_cfg else 'no'}, review={review_mode}"
        )

        # Early combo check — tránh tốn Gemini call nếu cùng topic+format đã post gần đây
        if self.audit.recently_posted_combo(target_id, topic_id, format_id, within_hours=48):
            logger.warning(f"[{target_id}] Combo ({topic_id}, {format_id}) đã post trong 48h — bỏ qua.")
            return {"skipped": True, "reason": "recent_combo", "topic_id": topic_id, "format_id": format_id}

        recent_titles = self._recent_titles(target_id)

        try:
            if research_cfg and any([
                research_cfg.get("urls"),
                research_cfg.get("fb_pages"),
                research_cfg.get("linkedin_companies"),
            ]):
                content_dict, brief = self._generate_with_research(
                    topic_cfg, research_cfg, format_id, target,
                    recent_titles=recent_titles,
                )
            else:
                content_dict = self.generator.generate(
                    topic_id, format_id, recent_titles=recent_titles,
                    profile=target
                )
                brief = None

            platform = PLATFORM_MAP.get(target.get("type", "page"), "facebook")
            post_text = self.renderer.render(format_id, content_dict, fmt, platform=platform)
            logger.info(f"[{target_id}] Rendered ({platform}): {len(post_text)} ký tự")

            if image_path is None and not no_image:
                try:
                    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(generate_image, content_dict, self.generator.api_key)
                        try:
                            image_path = future.result(timeout=45)
                        except FuturesTimeout:
                            future.cancel()
                            logger.warning(f"[{target_id}] Image generation timeout (45s) — đăng không ảnh.")
                except Exception as e:
                    logger.warning(f"[{target_id}] Không tạo được ảnh, đăng không ảnh: {e}")

            # Dedup check: skip nếu content y hệt đã post thành công trên target này
            if self.audit.is_duplicate(post_text, target_id):
                logger.warning(f"[{target_id}] Duplicate content detected — bỏ qua.")
                return {"skipped": True, "reason": "duplicate", "content": post_text}

            if review_mode:
                review_queue = ReviewQueueDB()
                entry_id = review_queue.enqueue(
                    target_id=target_id,
                    topic_id=topic_id,
                    format_id=format_id,
                    content=post_text,
                    platform=platform,
                    image_path=image_path,
                    brief_summary=brief.get("summary", "") if brief else "",
                )
                logger.info(f"[{target_id}] Đã lưu vào review queue: {entry_id}")
                return {
                    "queued": True,
                    "review_id": entry_id,
                    "content": post_text,
                    "platform": platform,
                    "message": f"Đã lưu vào review queue (ID: {entry_id}). Dùng 'cli.py review' để duyệt.",
                }

            result = self._dispatch_post(target, post_text, image_path)

            self.audit.log_post(
                target_id=target_id,
                target_type=target["type"],
                topic_id=topic_id,
                format_id=format_id,
                content_preview=post_text,
                success=True,
                post_id=result.get("post_id"),
                post_url=result.get("post_url"),
            )
            logger.info(f"[{target_id}] Thành công: {result.get('post_url', '')}")
            return {**result, "content": post_text, "platform": platform}

        except ProfileCheckpointError as e:
            logger.error(f"[{target_id}] FB Checkpoint: {e}")
            self.audit.log_post(target_id, target.get("type"), topic_id, format_id,
                                "", False, error=f"CHECKPOINT: {e}")
            raise
        except Exception as e:
            logger.error(f"[{target_id}] Thất bại: {e}")
            self.audit.log_post(target_id, target.get("type", "unknown"), topic_id,
                                format_id, "", False, error=str(e))
            raise

    def _generate_with_research(
        self,
        topic_cfg: dict,
        research_cfg: dict,
        format_id: str,
        target: dict,
        recent_titles: list = None,
    ) -> tuple:
        from social_agent.research.agent import ResearchAgent
        from social_agent.research.discovery import DynamicSourceResolver

        topic_id = topic_cfg["id"]

        fb_token = os.environ.get("FASTDX_PAGE_TOKEN") or (
            target.get("access_token")
            if target.get("type") in ("page", "group") else None
        )
        li_token = os.environ.get("LINKEDIN_ACCESS_TOKEN") or (
            target.get("access_token")
            if target.get("type", "").startswith("linkedin") else None
        )

        # --- Dynamic source discovery ---
        resolver = DynamicSourceResolver(
            gemini_api_key=self.generator.api_key,
            fb_access_token=fb_token,
        )
        # Seed URLs/pages từ config (optional overrides)
        seed_urls = research_cfg.get("urls", [])
        seed_fb_pages = research_cfg.get("fb_pages", [])

        resolved = resolver.resolve(
            topic_id=topic_id,
            topic_cfg=topic_cfg,
            seed_urls=seed_urls,
            seed_fb_pages=seed_fb_pages,
        )

        # Fallback: nếu discovery không tìm được gì → dùng seed config
        if not resolved["urls"] and not resolved["fb_pages"]:
            logger.warning(f"[{topic_id}] Dynamic discovery empty, using config seeds")
            resolved = {
                "urls": seed_urls,
                "fb_pages": seed_fb_pages + research_cfg.get("linkedin_companies", []),
                "linkedin_companies": research_cfg.get("linkedin_companies", []),
            }

        # Nếu vẫn rỗng → fallback sang generate thường
        if not resolved["urls"] and not resolved["fb_pages"]:
            logger.warning(f"[{topic_id}] No sources available, fallback to standard generate")
            content_dict = self.generator.generate(
                topic_id, format_id, recent_titles=recent_titles, 
                profile=target
            )
            return content_dict, None

        research = ResearchAgent(
            gemini_api_key=self.generator.api_key,
            fb_access_token=fb_token,
            li_access_token=li_token,
        )

        try:
            brief = research.research(
                topic_description=topic_cfg.get("description", topic_cfg["name"]),
                urls=resolved["urls"],
                fb_pages=resolved["fb_pages"],
                linkedin_companies=resolved.get("linkedin_companies", []),
            )
        except Exception as e:
            logger.warning(f"[research] Thất bại, fallback sang generate thường: {e}")
            content_dict = self.generator.generate(
                topic_cfg["id"], format_id, recent_titles=recent_titles,
                profile=target
            )
            return content_dict, None

        # Cập nhật scores trong registry dựa trên kết quả fetch
        resolver.record_result(
            topic_id=topic_id,
            sources_fetched=brief.get("sources_fetched", []),
            sources_failed=brief.get("sources_failed", []),
        )

        if not brief.get("sources_fetched"):
            logger.warning("[research] Không có nguồn nào fetched, fallback sang generate thường")
            content_dict = self.generator.generate(
                topic_cfg["id"], format_id, recent_titles=recent_titles,
                profile=target
            )
            return content_dict, None

        content_dict = self.generator.generate_from_brief(
            brief, format_id, recent_titles=recent_titles, 
            profile=target
        )
        return content_dict, brief

    def cross_post(
        self,
        group_id: Optional[str] = None,
        target_ids: Optional[List] = None,
        topic_id: Optional[str] = None,
        format_id: Optional[str] = None,
        image_path: Optional[str] = None,
    ) -> dict:
        """Đăng cùng content lên nhiều platform - generate LLM chỉ 1 lần."""
        if group_id:
            group = self._cross_groups.get(group_id)
            if not group:
                raise ValueError(f"Cross-post group không tồn tại: {group_id}")
            target_ids = group.get("targets", [])
        elif not target_ids:
            raise ValueError("Phải cung cấp group_id hoặc target_ids")

        first_target = self._targets.get(target_ids[0], {})
        format_id = format_id or random.choice(
            first_target.get("formats", list(self._formats.keys()))
        )
        topic_id = topic_id or random.choice(
            first_target.get("topics", list(self._topics.keys()))
        )

        fmt = self._formats.get(format_id)
        if not fmt:
            raise ValueError(f"Format không tồn tại: {format_id}")

        logger.info(f"Cross-post: {target_ids} | topic={topic_id} | format={format_id}")

        content_dict = self.generator.generate(topic_id, format_id, profile=first_target)
        logger.info(f"Content generated, posting to {len(target_ids)} targets...")

        if image_path is None:
            try:
                image_path = generate_image(content_dict, self.generator.api_key)
            except Exception as e:
                logger.warning(f"Không tạo được ảnh, đăng không ảnh: {e}")

        results = {}
        for target_id in target_ids:
            target = self._targets.get(target_id)
            if not target:
                logger.warning(f"Target không tồn tại: {target_id}, bỏ qua")
                continue
            if not target.get("enabled", True):
                logger.info(f"[{target_id}] Bị tắt, bỏ qua")
                continue

            try:
                platform = PLATFORM_MAP.get(target.get("type", "page"), "facebook")
                post_text = self.renderer.render(format_id, content_dict, fmt, platform=platform)

                result = self._dispatch_post(target, post_text, image_path)
                self.audit.log_post(target_id, target["type"], topic_id, format_id,
                                    post_text, True, result.get("post_id"), result.get("post_url"))
                results[target_id] = {**result, "content": post_text, "platform": platform, "success": True}
                logger.info(f"[{target_id}] OK: {result.get('post_url', '')}")

            except Exception as e:
                logger.error(f"[{target_id}] Thất bại trong cross-post: {e}")
                self.audit.log_post(target_id, target.get("type", "unknown"), topic_id,
                                    format_id, "", False, error=str(e))
                results[target_id] = {"success": False, "error": str(e)}

        success_count = sum(1 for r in results.values() if r.get("success"))
        logger.info(f"Cross-post hoàn tất: {success_count}/{len(target_ids)} thành công")
        return results

    def preview(self, topic_id: str, format_id: str, platform: str = "facebook") -> str:
        fmt = self._formats.get(format_id)
        if not fmt:
            raise ValueError(f"Format không tồn tại: {format_id}")
        content_dict = self.generator.generate(topic_id, format_id)
        return self.renderer.render(format_id, content_dict, fmt, platform=platform)

    def preview_all_platforms(self, topic_id: str, format_id: str) -> dict:
        fmt = self._formats.get(format_id)
        if not fmt:
            raise ValueError(f"Format không tồn tại: {format_id}")
        content_dict = self.generator.generate(topic_id, format_id)
        return {
            "facebook": self.renderer.render(format_id, content_dict, fmt, platform="facebook"),
            "linkedin": self.renderer.render(format_id, content_dict, fmt, platform="linkedin"),
            "raw": content_dict,
        }

    def _recent_titles(self, target_id: str, limit: int = 5) -> list:
        """Lấy tiêu đề/hook của các bài đăng gần nhất để tránh lặp góc nhìn."""
        history = self.audit.read_history(limit=20)
        titles = []
        for e in history:
            if e.get("target_id") == target_id and e.get("success"):
                preview = e.get("content_preview", "")
                # Lấy dòng đầu tiên không rỗng làm title
                first_line = next((l.strip() for l in preview.splitlines() if l.strip()), "")
                if first_line:
                    titles.append(first_line[:100])
            if len(titles) >= limit:
                break
        return titles

    def _recent_combos(self, target_id: str, limit: int = 30) -> set:
        history = self.audit.read_history(limit=limit)
        return {
            (e["topic_id"], e["format_id"])
            for e in history
            if e.get("target_id") == target_id and e.get("success")
        }

    def _pick_fresh_topic(self, target_id: str, target: dict) -> str:
        candidates = target.get("topics", list(self._topics.keys()))
        used_topics = {t for t, _ in self._recent_combos(target_id)}
        fresh = [t for t in candidates if t not in used_topics]
        pool = fresh if fresh else candidates
        chosen = random.choice(pool)
        if not fresh:
            logger.info(f"[{target_id}] Tất cả topics đã dùng, bắt đầu lại vòng mới.")
        return chosen

    def _pick_fresh_format(self, target_id: str, target: dict, topic_id: str) -> str:
        candidates = target.get("formats", list(self._formats.keys()))
        used_formats = {f for t, f in self._recent_combos(target_id) if t == topic_id}
        fresh = [f for f in candidates if f not in used_formats]
        pool = fresh if fresh else candidates
        return random.choice(pool)

    def _dispatch_post(self, target: dict, text: str, image_path: Optional[str]) -> dict:
        """Phân phối post đến đúng handler dựa trên target type.

        Raises:
            PostingError: Nếu target type không hỗ trợ hoặc API call thất bại.
        """
        target_type = target.get("type", "page")

        try:
            if target_type == "page":
                return self.fb_api.post_to_page(
                    page_id=target["target_id"],
                    access_token=target["access_token"],
                    message=text,
                    image_path=image_path,
                )
            elif target_type == "group":
                return self.fb_api.post_to_group(
                    group_id=target["target_id"],
                    access_token=target["access_token"],
                    message=text,
                    image_path=image_path,
                )
            elif target_type == "profile":
                poster = ProfilePoster(
                    chrome_profile_path=target.get("chrome_profile", ""),
                    chrome_profile_dir=target.get("chrome_profile_dir", "Default"),
                    headless=False,
                )
                return poster.post_sync(text, image_path)
            elif target_type == "linkedin_profile":
                return self.li_api.post_to_profile(
                    access_token=target["access_token"],
                    text=text,
                    image_path=image_path,
                    visibility=target.get("visibility", "PUBLIC"),
                )
            elif target_type == "linkedin_company":
                return self.li_api.post_to_company(
                    access_token=target["access_token"],
                    company_id=target["company_id"],
                    text=text,
                    image_path=image_path,
                    visibility=target.get("visibility", "PUBLIC"),
                )
            else:
                raise PostingError(f"Target type không hỗ trợ: {target_type}")
        except PostingError:
            raise
        except ProfileCheckpointError:
            raise
        except Exception as e:
            raise PostingError(f"[{target.get('id', target_type)}] Dispatch thất bại: {e}") from e

    def validate(self) -> dict:
        results = {}
        for target_id, target in self._targets.items():
            target_type = target.get("type", "page")

            if target_type in ("page", "group"):
                token = target.get("access_token", "")
                if not token or token.startswith("${"):
                    results[target_id] = {"valid": False, "error": "Token chưa cấu hình"}
                else:
                    results[target_id] = self.fb_api.validate_token(token)

            elif target_type == "profile":
                from pathlib import Path
                path = Path(target.get("chrome_profile", ""))
                results[target_id] = (
                    {"valid": True, "note": "Chrome profile OK"}
                    if path.exists()
                    else {"valid": False, "error": f"Chrome profile không tồn tại: {path}"}
                )

            elif target_type in ("linkedin_profile", "linkedin_company"):
                token = target.get("access_token", "")
                if not token or token.startswith("${"):
                    results[target_id] = {"valid": False, "error": "LinkedIn token chưa cấu hình"}
                else:
                    results[target_id] = self.li_api.validate_token(token)

        return results

    def run_scheduled(self):
        """Khởi động APScheduler daemon."""
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger

        tz = self.config.get("scheduler", {}).get("timezone", "Asia/Ho_Chi_Minh")
        scheduler = BlockingScheduler(timezone=tz)
        enabled_count = 0

        for target_id, target in self._targets.items():
            if not target.get("enabled", True):
                continue
            schedule = target.get("schedule")
            if not schedule:
                continue

            def make_job(tid):
                def job():
                    try:
                        self.post_now(target_id=tid)
                    except Exception as e:
                        logger.error(f"[{tid}] Scheduled job thất bại: {e}")
                return job

            parts = schedule.split()
            trigger = CronTrigger(
                minute=parts[0], hour=parts[1], day=parts[2],
                month=parts[3], day_of_week=parts[4], timezone=tz,
            )
            scheduler.add_job(make_job(target_id), trigger=trigger, id=target_id)
            logger.info(f"[{target_id}] Lên lịch: {schedule}")
            enabled_count += 1

        if enabled_count == 0:
            logger.warning("Không có target nào được bật.")
            return

        # --- Weekly auto token refresh (Thứ 2 lúc 07:00) ---
        def _auto_refresh_tokens():
            try:
                self.refresh_fb_tokens()
            except Exception as e:
                logger.error(f"[token-refresh] Thất bại: {e}")

        scheduler.add_job(
            _auto_refresh_tokens,
            trigger=CronTrigger(day_of_week="mon", hour=7, minute=0, timezone=tz),
            id="__token_refresh__",
        )
        logger.info("[token-refresh] Lên lịch auto-refresh mỗi thứ 2 lúc 07:00")

        logger.info(f"Scheduler: {enabled_count} target(s). Ctrl+C để dừng.")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler đã dừng.")

    def refresh_fb_tokens(self) -> dict:
        """
        Gia hạn Facebook Page Tokens tự động từ credentials trong .env.
        Ghi tokens mới vào .env — không cần vào browser hay copy tay.
        """
        from social_agent.utils.dotenv_writer import update_env_file
        import re

        app_id = os.getenv("FB_APP_ID")
        app_secret = os.getenv("FB_APP_SECRET")
        user_token = os.getenv("FB_USER_TOKEN")

        if not all([app_id, app_secret, user_token]):
            missing = [k for k, v in {"FB_APP_ID": app_id, "FB_APP_SECRET": app_secret,
                                       "FB_USER_TOKEN": user_token}.items() if not v]
            raise ValueError(f"Thiếu credentials để auto-refresh: {', '.join(missing)}")

        result = self.fb_api.refresh_page_tokens(app_id, app_secret, user_token)

        # Build page_id → env_key mapping từ config
        page_id_to_env: dict[str, str] = {}
        for t in self.config.get("targets", []):
            raw_token = t.get("access_token", "")
            m = re.match(r"\$\{(\w+)\}", raw_token)
            if m:
                page_id_to_env[str(t.get("target_id", ""))] = m.group(1)

        updates: dict = {
            "FB_APP_ID": app_id,
            "FB_APP_SECRET": app_secret,
            "FB_USER_TOKEN": result["long_lived_user_token"],
        }
        for page in result["pages"]:
            env_key = page_id_to_env.get(page["id"])
            if env_key:
                updates[env_key] = page["token"]
            else:
                fallback = page["name"].upper().replace(" ", "_").replace("-", "_") + "_TOKEN"
                updates[fallback] = page["token"]

        update_env_file(updates)
        logger.info(f"[token-refresh] Đã gia hạn {len(result['pages'])} page token(s): "
                    + ", ".join(p["name"] for p in result["pages"]))
        return result

    def research_and_post(
        self,
        topic_description: str,
        target_id: str,
        format_id: Optional[str] = None,
        urls: Optional[List] = None,
        fb_pages: Optional[List] = None,
        linkedin_companies: Optional[List] = None,
        image_path: Optional[str] = None,
        dry_run: bool = False,
    ) -> dict:
        from social_agent.research.agent import ResearchAgent

        target = self._targets.get(target_id)
        if not target and not dry_run:
            raise ValueError(f"Target không tồn tại: {target_id}")

        format_id = format_id or random.choice(
            target.get("formats", list(self._formats.keys())) if target else list(self._formats.keys())
        )
        fmt = self._formats.get(format_id)
        if not fmt:
            raise ValueError(f"Format không tồn tại: {format_id}")

        fb_token = os.environ.get("FASTDX_PAGE_TOKEN") or (
            target.get("access_token") if target and target.get("type") in ("page", "group") else None
        )
        li_token = os.environ.get("LINKEDIN_ACCESS_TOKEN") or (
            target.get("access_token") if target and target.get("type", "").startswith("linkedin") else None
        )

        research = ResearchAgent(
            gemini_api_key=self.generator.api_key,
            fb_access_token=fb_token,
            li_access_token=li_token,
        )

        logger.info(f"[research_and_post] Fetching sources for: {topic_description[:60]}")
        brief = research.research(
            topic_description=topic_description,
            urls=urls,
            fb_pages=fb_pages,
            linkedin_companies=linkedin_companies,
        )

        logger.info(f"[research_and_post] Generating content: format={format_id}")
        content_dict = self.generator.generate_from_brief(brief, format_id)

        platform = PLATFORM_MAP.get(target.get("type", "page"), "facebook") if target else "facebook"
        post_text = self.renderer.render(format_id, content_dict, fmt, platform=platform)

        result = {
            "brief": brief,
            "content": post_text,
            "platform": platform,
            "format_id": format_id,
            "topic_description": topic_description,
        }

        if dry_run:
            logger.info(f"[research_and_post] Dry-run: {len(post_text)} ký tự")
            return result

        if image_path is None:
            try:
                image_path = generate_image(content_dict, self.generator.api_key)
            except Exception as e:
                logger.warning(f"[research_and_post] Không tạo được ảnh: {e}")

        # Tôn trọng review_mode: nếu target bật review → đưa vào queue thay vì đăng ngay
        review_mode = target.get("review_mode", False)
        topic_label = f"research:{topic_description[:40]}"

        if review_mode:
            review_queue = ReviewQueueDB()
            entry_id = review_queue.enqueue(
                target_id=target_id,
                topic_id=topic_label,
                format_id=format_id,
                content=post_text,
                platform=platform,
                image_path=image_path,
                brief_summary=brief.get("summary", ""),
            )
            logger.info(f"[research_and_post] review_mode=true → queued: {entry_id}")
            result.update({"queued": True, "review_id": entry_id})
            return result

        post_result = self._dispatch_post(target, post_text, image_path)

        self.audit.log_post(
            target_id=target_id,
            target_type=target["type"],
            topic_id=topic_label,
            format_id=format_id,
            content_preview=post_text,
            success=True,
            post_id=post_result.get("post_id"),
            post_url=post_result.get("post_url"),
        )

        result.update(post_result)
        logger.info(f"[research_and_post] OK: {post_result.get('post_url', '')}")
        return result

    def approve_review(self, entry_id: str) -> dict:
        queue = ReviewQueueDB()
        entry = queue.get(entry_id)
        if not entry:
            raise ValueError(f"Không tìm thấy review entry: {entry_id}")
        if entry["status"] != "pending":
            raise ValueError(f"Entry {entry_id} đã được xử lý: {entry['status']}")

        target_id = entry["target_id"]
        target = self._targets.get(target_id)
        if not target:
            raise ValueError(f"Target không tồn tại: {target_id}")

        post_text = entry["content"]
        image_path = entry.get("image_path")

        # Đăng bài thực tế
        result = self._dispatch_post(target, post_text, image_path)

        # Ghi log audit
        self.audit.log_post(
            target_id=target_id,
            target_type=target["type"],
            topic_id=entry["topic_id"],
            format_id=entry["format_id"],
            content_preview=post_text,
            success=True,
            post_id=result.get("post_id"),
            post_url=result.get("post_url"),
        )

        # --- Pillar 2 Learning: Record sample if approved ---
        try:
            self.writing_memory.add_sample(
                profile_id=target_id,
                topic_id=entry["topic_id"],
                sample={"title": entry.get("brief_summary", ""), "body": post_text}
            )
        except Exception as e:
            logger.warning(f"Không thể lưu writing memory: {e}")

        queue.update_status(entry_id, "approved")
        logger.info(f"[{target_id}] Review approved & posted: {result.get('post_url', '')}")
        return {**result, "content": post_text}

    def reject_review(self, entry_id: str, reason: Optional[str] = None) -> bool:
        queue = ReviewQueueDB()
        entry = queue.get(entry_id)
        if not entry:
            raise ValueError(f"Không tìm thấy review entry: {entry_id}")
            
        queue.update_status(entry_id, "rejected", reason=reason)
        logger.info(f"Review rejected: {entry_id} | reason: {reason}")
        
        # --- Pillar 2 Learning: Extract rule from reason ---
        if reason:
            try:
                self._learn_from_rejection(entry["target_id"], entry["topic_id"], reason)
            except Exception as e:
                logger.warning(f"Error learning from rejection: {e}")
                
        return True

    def _learn_from_rejection(self, profile_id: str, topic_id: str, reason: str):
        """Dùng Gemini để đúc kết 1 rule ngắn gọn súc tích từ feedback người dùng."""
        prompt = f"Người dùng đã từ chối bài viết social media vì lý do: '{reason}'.\n" \
                 f"Hãy đúc kết 1 quy tắc (rules) ngắn gọn, súc tích (1 dòng) " \
                 f"để lần sau AI không vi phạm nữa. Trả về text thuần."
        
        try:
            # Dùng generator để gọi Gemini
            rule = self.generator.generate_custom_prompt(prompt)
            if rule:
                self.writing_memory.add_rule(profile_id, topic_id, rule.strip())
                logger.info(f"Learned new rule for [{profile_id}]: {rule.strip()}")
        except Exception:
            # Fallback: dùng chính cái reason làm rule nếu Gemini fail
            self.writing_memory.add_rule(profile_id, topic_id, f"Tránh: {reason}")

    def list_review_queue(self) -> list:
        return ReviewQueueDB().list_pending()

    def get_stats(self) -> dict:
        return self.audit.stats()

    def get_history(self, limit: int = 20) -> list:
        return self.audit.read_history(limit=limit)


# Backward-compat alias
FacebookAgent = SocialAgent
