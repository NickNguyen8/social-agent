"""
research/agent.py - Research Agent cho Social Agent
====================================================
Fetch nội dung từ URLs, Facebook Pages, LinkedIn Companies,
tóm tắt bằng Gemini, trả về ResearchBrief để dùng trong content generation.

Luồng:
  sources (URLs / FB pages / LI companies)
    → Fetchers (song song)
    → BriefSummarizer (Gemini call #1)
    → ResearchBrief dict
    → ContentGenerator.generate_from_brief() (Gemini call #2)
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger("social_agent.research")

# Giới hạn text trả về từ mỗi source (tránh vượt context window)
MAX_CHARS_PER_SOURCE = 3000
# Tổng max chars gửi vào BriefSummarizer
MAX_TOTAL_CHARS = 12000


# ============================================================
# ResearchBrief type
# ============================================================

def _make_brief(topic_description: str) -> dict:
    return {
        "topic_description": topic_description,
        "sources_fetched": [],
        "sources_failed": [],
        "web_excerpts": [],      # [{"url", "title", "excerpt"}]
        "facebook_posts": [],    # [{"page_id", "text", "created_time"}]
        "linkedin_posts": [],    # [{"company", "text"}]
        "summary": "",
        "errors": [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================
# Helpers
# ============================================================

def _strip_html(html: str) -> str:
    """Loại bỏ HTML tags, trả về plain text."""
    html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<(br|p|div|li|h[1-6])[^>]*>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    html = html.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">") \
               .replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"')
    html = re.sub(r"\n{3,}", "\n\n", html)
    html = re.sub(r" {2,}", " ", html)
    return html.strip()


def _truncate(text: str, max_chars: int = MAX_CHARS_PER_SOURCE) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n… [truncated {len(text) - max_chars} chars]"


# ============================================================
# WebFetcher
# ============================================================

class WebFetcher:
    """Fetch nội dung từ URL bất kỳ (blog, news, landing page)."""

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (compatible; SocialResearchAgent/1.0)",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "vi,en;q=0.9",
    }

    def fetch(self, url: str, timeout: int = 15) -> dict:
        result = {"url": url, "title": "", "excerpt": "", "error": None}

        # Security: chỉ cho phép http/https — chặn file://, ftp://...
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            result["error"] = f"URL scheme không hợp lệ: {parsed.scheme!r} (chỉ http/https)"
            logger.warning(f"WebFetcher bị chặn URL scheme: {url}")
            return result

        try:
            resp = requests.get(url, headers=self.HEADERS, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
            html = resp.text

            title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            result["title"] = _strip_html(title_match.group(1)).strip() if title_match else url

            for tag in ("article", "main", "body"):
                m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", html, re.IGNORECASE | re.DOTALL)
                if m:
                    text = _strip_html(m.group(1))
                    if len(text) > 200:
                        result["excerpt"] = _truncate(text)
                        break

            if not result["excerpt"]:
                result["excerpt"] = _truncate(_strip_html(html))

            logger.debug(f"WebFetcher OK: {url} ({len(result['excerpt'])} chars)")

        except requests.Timeout:
            result["error"] = f"Timeout sau {timeout}s"
            logger.warning(f"WebFetcher timeout: {url}")
        except requests.RequestException as e:
            result["error"] = str(e)
            logger.warning(f"WebFetcher error {url}: {e}")

        return result


# ============================================================
# FacebookPageFetcher
# ============================================================

class FacebookPageFetcher:
    """Fetch bài đăng gần nhất từ Facebook Page qua Graph API."""

    BASE_URL = "https://graph.facebook.com/v20.0"

    def __init__(self, access_token: str):
        self.access_token = access_token

    def fetch(self, page_id_or_name: str, limit: int = 5) -> dict:
        result = {"page_id": page_id_or_name, "posts": [], "error": None}
        try:
            url = f"{self.BASE_URL}/{page_id_or_name}/posts"
            params = {
                "access_token": self.access_token,
                "fields": "message,created_time,story",
                "limit": limit,
            }
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()

            if "error" in data:
                code = data["error"].get("code", 0)
                msg = data["error"].get("message", "Unknown")
                result["error"] = f"FB API error {code}: {msg}"
                logger.warning(f"FacebookPageFetcher [{page_id_or_name}]: {result['error']}")
                return result

            posts = data.get("data", [])
            for p in posts:
                text = p.get("message") or p.get("story") or ""
                if text:
                    result["posts"].append({
                        "page_id": page_id_or_name,
                        "text": _truncate(text, 800),
                        "created_time": p.get("created_time", ""),
                    })

            logger.debug(f"FacebookPageFetcher [{page_id_or_name}]: {len(result['posts'])} posts")

        except requests.RequestException as e:
            result["error"] = str(e)
            logger.warning(f"FacebookPageFetcher [{page_id_or_name}] network error: {e}")

        return result


# ============================================================
# LinkedInPublicFetcher
# ============================================================

class LinkedInPublicFetcher:
    """Fetch bài đăng từ LinkedIn Company Page qua LinkedIn API."""

    BASE_URL = "https://api.linkedin.com/v2"

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token

    def fetch(self, company_id_or_name: str, limit: int = 5) -> dict:
        result = {"company": company_id_or_name, "posts": [], "error": None}

        if not self.access_token:
            result["error"] = "Chưa cấu hình LinkedIn access token"
            logger.info(f"LinkedInPublicFetcher [{company_id_or_name}]: no token configured")
            return result

        try:
            org_urn = company_id_or_name
            if not company_id_or_name.startswith("urn:"):
                org_urn = self._resolve_org_urn(company_id_or_name)
                if not org_urn:
                    result["error"] = f"Không tìm thấy company: {company_id_or_name}"
                    return result

            url = f"{self.BASE_URL}/ugcPosts"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "LinkedIn-Version": "202401",
            }
            params = {
                "q": "authors",
                "authors": f"List({org_urn})",
                "count": limit,
            }
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            data = resp.json()

            if resp.status_code != 200:
                result["error"] = data.get("message", f"HTTP {resp.status_code}")
                logger.warning(f"LinkedInPublicFetcher [{company_id_or_name}]: {result['error']}")
                return result

            for item in data.get("elements", []):
                content = item.get("specificContent", {})
                share = content.get("com.linkedin.ugc.ShareContent", {})
                commentary = share.get("shareCommentary", {}).get("text", "")
                if commentary:
                    result["posts"].append({
                        "company": company_id_or_name,
                        "text": _truncate(commentary, 800),
                    })

            logger.debug(f"LinkedInPublicFetcher [{company_id_or_name}]: {len(result['posts'])} posts")

        except requests.RequestException as e:
            result["error"] = str(e)
            logger.warning(f"LinkedInPublicFetcher [{company_id_or_name}] network error: {e}")

        return result

    def _resolve_org_urn(self, vanity_name: str) -> Optional[str]:
        try:
            url = f"{self.BASE_URL}/organizations"
            headers = {"Authorization": f"Bearer {self.access_token}"}
            params = {"q": "vanityName", "vanityName": vanity_name}
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            data = resp.json()
            elements = data.get("elements", [])
            if elements:
                org_id = elements[0].get("id")
                return f"urn:li:organization:{org_id}" if org_id else None
        except Exception:
            pass
        return None


# ============================================================
# BriefSummarizer
# ============================================================

class BriefSummarizer:
    """
    Gọi Gemini để tóm tắt tất cả nguồn thành 1 brief súc tích.
    Đây là Gemini call #1 trong luồng research.
    """

    SUMMARIZE_PROMPT = """Bạn là Research Assistant của FastDX — công ty tư vấn DX & AI tại Việt Nam.

Nhiệm vụ: Phân tích và tóm tắt các nguồn dưới đây thành một "Research Brief" súc tích bằng tiếng Việt, phục vụ việc viết bài đăng social media về chủ đề: **{topic_description}**

---
{sources_block}
---

Yêu cầu tóm tắt:
- Tổng hợp các thông tin quan trọng, số liệu, insight nổi bật từ các nguồn
- Xác định góc nhìn khác biệt hoặc mâu thuẫn giữa các nguồn (nếu có)
- Đề xuất 2-3 góc tiếp cận nội dung phù hợp với brand FastDX (tư vấn DX/AI thực chiến)
- Tổng hợp ngắn gọn: không quá 500 từ
- Trả về JSON:

{{
  "key_insights": ["Insight 1", "Insight 2", "Insight 3"],
  "notable_stats": ["Số liệu/thực tế đáng chú ý 1", "..."],
  "content_angles": ["Góc tiếp cận 1", "Góc tiếp cận 2", "Góc tiếp cận 3"],
  "summary": "Tóm tắt tổng hợp 3-5 câu súc tích nhất về chủ đề",
  "source_quality": "high|medium|low"
}}"""

    def __init__(self, gemini_api_key: str, model: str = "gemini-2.5-flash"):
        self.api_key = gemini_api_key
        self.model = model

    def summarize(self, topic_description: str, brief: dict) -> dict:
        sources_block = self._build_sources_block(brief)

        if not sources_block.strip():
            logger.warning("BriefSummarizer: không có nguồn nào để tóm tắt")
            return {
                "key_insights": [],
                "notable_stats": [],
                "content_angles": [],
                "summary": topic_description,
                "source_quality": "low",
            }

        prompt = self.SUMMARIZE_PROMPT.format(
            topic_description=topic_description,
            sources_block=sources_block,
        )

        try:
            # Security: API key in header, NOT in URL
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.model}:generateContent"
            )
            headers = {"x-goog-api-key": self.api_key}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 2048,
                    "thinkingConfig": {"thinkingBudget": 0},
                },
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"]

            cleaned = raw.strip()
            m = re.search(r"```json\s*(.*?)\s*```", cleaned, re.DOTALL)
            if m:
                cleaned = m.group(1)
            else:
                m = re.search(r"\{.*\}", cleaned, re.DOTALL)
                if m:
                    cleaned = m.group(0)

            result = json.loads(cleaned)
            logger.info(f"BriefSummarizer OK: {len(result.get('key_insights', []))} insights")
            return result

        except Exception as e:
            logger.error(f"BriefSummarizer error: {e}")
            return {
                "key_insights": [],
                "notable_stats": [],
                "content_angles": [],
                "summary": topic_description,
                "source_quality": "low",
                "error": str(e),
            }

    def _build_sources_block(self, brief: dict) -> str:
        parts = []
        total_chars = 0

        for item in brief.get("web_excerpts", []):
            if total_chars >= MAX_TOTAL_CHARS:
                break
            chunk = f"### Web: {item['title']}\nURL: {item['url']}\n\n{item['excerpt']}"
            parts.append(chunk)
            total_chars += len(chunk)

        for post in brief.get("facebook_posts", []):
            if total_chars >= MAX_TOTAL_CHARS:
                break
            chunk = f"### Facebook ({post['page_id']}) — {post.get('created_time', '')}\n{post['text']}"
            parts.append(chunk)
            total_chars += len(chunk)

        for post in brief.get("linkedin_posts", []):
            if total_chars >= MAX_TOTAL_CHARS:
                break
            chunk = f"### LinkedIn ({post['company']})\n{post['text']}"
            parts.append(chunk)
            total_chars += len(chunk)

        return "\n\n---\n\n".join(parts)


# ============================================================
# ResearchAgent
# ============================================================

class ResearchAgent:
    """
    Agent điều phối toàn bộ quy trình nghiên cứu:
    1. Fetch song song từ tất cả nguồn
    2. Tóm tắt bằng BriefSummarizer
    3. Trả về ResearchBrief
    """

    def __init__(
        self,
        gemini_api_key: str,
        fb_access_token: Optional[str] = None,
        li_access_token: Optional[str] = None,
        gemini_model: str = "gemini-2.5-flash",
        max_workers: int = 5,
    ):
        self.web_fetcher = WebFetcher()
        self.fb_fetcher = FacebookPageFetcher(fb_access_token) if fb_access_token else None
        self.li_fetcher = LinkedInPublicFetcher(li_access_token)
        self.summarizer = BriefSummarizer(gemini_api_key, model=gemini_model)
        self.max_workers = max_workers

    def research(
        self,
        topic_description: str,
        urls: Optional[list] = None,
        fb_pages: Optional[list] = None,
        linkedin_companies: Optional[list] = None,
        summarize: bool = True,
    ) -> dict:
        brief = _make_brief(topic_description)
        urls = urls or []
        fb_pages = fb_pages or []
        linkedin_companies = linkedin_companies or []

        if not any([urls, fb_pages, linkedin_companies]):
            logger.warning("ResearchAgent: không có nguồn nào được cung cấp")
            brief["errors"].append("Không có nguồn nào được cung cấp")
            brief["summary"] = topic_description
            return brief

        logger.info(
            f"ResearchAgent: {len(urls)} URLs, {len(fb_pages)} FB pages, "
            f"{len(linkedin_companies)} LinkedIn companies"
        )

        futures = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for url in urls:
                f = executor.submit(self.web_fetcher.fetch, url)
                futures[f] = ("web", url)

            if self.fb_fetcher:
                for page in fb_pages:
                    f = executor.submit(self.fb_fetcher.fetch, page)
                    futures[f] = ("facebook", page)
            else:
                for page in fb_pages:
                    brief["sources_failed"].append(f"fb:{page}")
                    brief["errors"].append(f"Facebook fetcher chưa cấu hình (cần access token): {page}")

            for company in linkedin_companies:
                f = executor.submit(self.li_fetcher.fetch, company)
                futures[f] = ("linkedin", company)

            for future in as_completed(futures):
                source_type, source_id = futures[future]
                try:
                    result = future.result()
                    self._merge_result(brief, source_type, source_id, result)
                except Exception as e:
                    brief["sources_failed"].append(f"{source_type}:{source_id}")
                    brief["errors"].append(f"{source_type}:{source_id} — {e}")
                    logger.error(f"ResearchAgent fetch error [{source_type}:{source_id}]: {e}")

        logger.info(
            f"ResearchAgent fetch done: {len(brief['sources_fetched'])} OK, "
            f"{len(brief['sources_failed'])} failed"
        )

        if summarize:
            summary_result = self.summarizer.summarize(topic_description, brief)
            brief["summary"] = summary_result.get("summary", topic_description)
            brief["key_insights"] = summary_result.get("key_insights", [])
            brief["notable_stats"] = summary_result.get("notable_stats", [])
            brief["content_angles"] = summary_result.get("content_angles", [])
            brief["source_quality"] = summary_result.get("source_quality", "medium")

        return brief

    def _merge_result(self, brief: dict, source_type: str, source_id: str, result: dict):
        error = result.get("error")
        if error:
            brief["sources_failed"].append(f"{source_type}:{source_id}")
            brief["errors"].append(f"{source_type}:{source_id} — {error}")
            return

        brief["sources_fetched"].append(f"{source_type}:{source_id}")

        if source_type == "web":
            if result.get("excerpt"):
                brief["web_excerpts"].append({
                    "url": result["url"],
                    "title": result["title"],
                    "excerpt": result["excerpt"],
                })

        elif source_type == "facebook":
            for post in result.get("posts", []):
                brief["facebook_posts"].append(post)

        elif source_type == "linkedin":
            for post in result.get("posts", []):
                brief["linkedin_posts"].append(post)
