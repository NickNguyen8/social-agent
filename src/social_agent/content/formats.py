import re
from typing import Union

WEBSITE = "https://fastdx.dev"


def _strip_markdown(text: str) -> str:
    """
    Xóa markdown formatting khỏi plain-text post (Facebook không render markdown).
    - **bold** / __bold__ → bold
    - *italic* / _italic_ → italic
    - ### Heading → Heading
    - `code` → code
    """
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'`(.+?)`', r'\1', text)
    return text


def _strip_link(text: str) -> str:
    """Xóa URL fastdx.dev nếu LLM tự nhúng vào CTA/body."""
    import re
    return re.sub(r'\s*https?://\S*fastdx\S*', '', text).strip()


def _strip_leading_duplicate(body: str, header: str) -> str:
    """
    Strip dòng đầu của body chỉ khi khớp chính xác với header.
    Dùng 40 ký tự đầu để so sánh — tránh xóa nhầm khi body chỉ bắt đầu
    bằng vài từ giống nhau.
    """
    if not header or not body:
        return body
    header_key = header.strip().upper()[:40]
    lines = body.splitlines()
    # Chỉ xóa tối đa 2 dòng đầu trống + 1 dòng trùng header
    cleaned = 0
    while lines and cleaned < 3:
        first = lines[0].strip()
        if not first:
            lines.pop(0)
            cleaned += 1
        elif first.upper()[:40] == header_key:
            lines.pop(0)
            cleaned += 1
            break
        else:
            break
    return "\n".join(lines).strip()


def _normalize_hashtags(tags: Union[list, str], count: int = 5) -> str:
    """Chuẩn hóa hashtag: đảm bảo có #, không có space, giới hạn số lượng."""
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.replace(",", " ").split() if t.strip()]
    normalized = []
    for tag in tags[:count]:
        tag = tag.strip().lstrip("#").replace(" ", "")
        if tag:
            normalized.append(f"#{tag}")
    return " ".join(normalized)


class FormatRenderer:
    """
    Render content dict thành string cho từng platform.
    Dùng: renderer.render(format_id, content, format_config, platform="facebook")
    """

    # Giới hạn thực tế để tránh bị cắt trong feed (không phải hard limit của platform)
    _MAX_LEN = {"facebook": 1500, "linkedin": 1300}

    def render(
        self,
        format_id: str,
        content: dict,
        format_config: dict = None,
        platform: str = "facebook",
    ) -> str:
        """
        Render content theo format và platform.
        platform: str = "facebook" # "facebook" or "linkedin"
        """
        hashtag_count = 5
        if format_config:
            hashtag_count = format_config.get("hashtag_count", 5)

        if platform == "linkedin":
            renderer = getattr(self, f"_linkedin_{format_id}", self._linkedin_generic)
        else:
            renderer = getattr(self, f"_facebook_{format_id}", self._facebook_generic)

        text = renderer(content, hashtag_count)

        max_len = self._MAX_LEN.get(platform, 1500)
        if len(text) > max_len:
            import logging
            logging.getLogger("social_agent.content").warning(
                f"Post quá dài ({len(text)} ký tự > {max_len}). Truncating body."
            )
            text = self._truncate(text, max_len)

        return text

    def _truncate(self, text: str, max_len: int) -> str:
        """Cắt body để giữ hashtags + URL ở cuối, không bị mất."""
        lines = text.splitlines()
        # Tách phần cuối: hashtags + URL (thường là 3 dòng cuối)
        tail_lines = []
        body_lines = list(lines)
        for _ in range(min(3, len(lines))):
            last = body_lines[-1].strip()
            if last.startswith("#") or last.startswith("http") or last == "":
                tail_lines.insert(0, body_lines.pop())
            else:
                break
        tail = "\n".join(tail_lines)
        budget = max_len - len(tail) - 4  # 4 = "…\n\n"
        body = "\n".join(body_lines)
        if len(body) > budget:
            body = body[:budget].rsplit(" ", 1)[0] + "…"
        return (body + "\n\n" + tail).strip()

    # ================================================================
    # FACEBOOK RENDERERS
    # ================================================================

    def _facebook_thought_leadership(self, content: dict, hashtag_count: int) -> str:
        title = content.get("title", "").strip()
        body = _strip_markdown(_strip_leading_duplicate(_strip_link(content.get("body", "").strip()), title))
        hashtags = _normalize_hashtags(content.get("hashtags", []), hashtag_count)
        parts = []
        if title:
            parts.append(title)
            parts.append("")
            parts.append("")
        if body:
            parts.append(body)
        parts.append("")
        parts.append(WEBSITE)
        if hashtags:
            parts.append("")
            parts.append(hashtags)
        return "\n".join(parts).strip()

    def _facebook_quick_insight(self, content: dict, hashtag_count: int) -> str:
        hook = content.get("hook", "").strip()
        body = _strip_markdown(_strip_leading_duplicate(_strip_link(content.get("body", "").strip()), hook))
        cta = _strip_link(content.get("cta", "").strip())
        hashtags = _normalize_hashtags(content.get("hashtags", []), hashtag_count)
        parts = []
        if hook:
            parts.append(hook)
        if body:
            parts.append("")
            parts.append(body)
        if cta:
            parts.append("")
            parts.append(f"👉 {cta}")
        parts.append(WEBSITE)
        if hashtags:
            parts.append("")
            parts.append(hashtags)
        return "\n".join(parts).strip()

    def _facebook_story_post(self, content: dict, hashtag_count: int) -> str:
        opening = content.get("opening_hook", "").strip()
        body = _strip_markdown(_strip_leading_duplicate(_strip_link(content.get("body", "").strip()), opening))
        lesson = _strip_markdown(content.get("lesson", "").strip())
        cta = _strip_link(content.get("cta", "").strip())
        hashtags = _normalize_hashtags(content.get("hashtags", []), hashtag_count)
        parts = []
        if opening:
            parts.append(opening)
        if body:
            parts.append("")
            parts.append(body)
        if lesson:
            parts.append("")
            parts.append(f"💡 {lesson}")
        if cta:
            parts.append("")
            parts.append(cta)
        parts.append(WEBSITE)
        if hashtags:
            parts.append("")
            parts.append(hashtags)
        return "\n".join(parts).strip()

    def _facebook_engagement_post(self, content: dict, hashtag_count: int) -> str:
        question = content.get("question", "").strip()
        body = _strip_markdown(_strip_leading_duplicate(_strip_link(content.get("body", "").strip()), question))
        bullets = content.get("key_points", [])
        cta = _strip_link(content.get("cta", "").strip())
        hashtags = _normalize_hashtags(content.get("hashtags", []), hashtag_count)
        parts = []
        if question:
            parts.append(question)
        if body:
            parts.append("")
            parts.append(body)
        if bullets:
            parts.append("")
            for i, bullet in enumerate(bullets[:3], 1):
                parts.append(f"{'①②③'[i-1]} {bullet.strip()}")
        if cta:
            parts.append("")
            parts.append(cta)
        parts.append(WEBSITE)
        if hashtags:
            parts.append("")
            parts.append(hashtags)
        return "\n".join(parts).strip()

    def _facebook_generic(self, content: dict, hashtag_count: int) -> str:
        hashtags = _normalize_hashtags(content.get("hashtags", []), hashtag_count)
        parts = [str(v) for k, v in content.items()
                 if v and k not in ("hashtags", "linkedin_body")]
        result = "\n\n".join(parts)
        if hashtags:
            result += f"\n\n{hashtags}"
        return result.strip()

    # ================================================================
    # LINKEDIN RENDERERS
    # Không emoji quá nhiều, tone chuyên nghiệp, dùng linkedin_body
    # Best practice: 700-1300 ký tự, 3-5 hashtag
    # ================================================================

    def _linkedin_thought_leadership(self, content: dict, hashtag_count: int) -> str:
        title = content.get("title", "").strip()
        body = (content.get("linkedin_body") or content.get("body", "")).strip()
        key_points = content.get("key_points", [])
        cta = _strip_link(content.get("cta", "").strip())
        hashtags = _normalize_hashtags(content.get("hashtags", []), min(hashtag_count, 5))
        parts = []
        if title:
            parts.append(title)
            parts.append("")
        if body:
            parts.append(body)
        if key_points:
            parts.append("")
            for point in key_points[:3]:
                parts.append(f"- {point.strip()}")
        if cta:
            parts.append("")
            parts.append(cta)
        if hashtags:
            parts.append("")
            parts.append(hashtags)
        return "\n".join(parts).strip()

    def _linkedin_quick_insight(self, content: dict, hashtag_count: int) -> str:
        hook = content.get("hook", "").strip()
        body = (content.get("linkedin_body") or content.get("body", "")).strip()
        cta = _strip_link(content.get("cta", "").strip())
        hashtags = _normalize_hashtags(content.get("hashtags", []), min(hashtag_count, 5))
        parts = []
        if hook:
            parts.append(hook)
            parts.append("")
        if body:
            parts.append(body)
        if cta:
            parts.append("")
            parts.append(cta)
        if hashtags:
            parts.append("")
            parts.append(hashtags)
        return "\n".join(parts).strip()

    def _linkedin_story_post(self, content: dict, hashtag_count: int) -> str:
        opening = content.get("opening_hook", "").strip()
        body = (content.get("linkedin_body") or content.get("body", "")).strip()
        lesson = content.get("lesson", "").strip()
        cta = _strip_link(content.get("cta", "").strip())
        hashtags = _normalize_hashtags(content.get("hashtags", []), min(hashtag_count, 5))
        parts = []
        if opening:
            parts.append(opening)
            parts.append("")
        if body:
            parts.append(body)
        if lesson:
            parts.append("")
            parts.append(f"Bài học: {lesson}")
        if cta:
            parts.append("")
            parts.append(cta)
        if hashtags:
            parts.append("")
            parts.append(hashtags)
        return "\n".join(parts).strip()

    def _linkedin_engagement_post(self, content: dict, hashtag_count: int) -> str:
        question = content.get("question", "").strip()
        body = (content.get("linkedin_body") or content.get("body", "")).strip()
        key_points = content.get("key_points", [])
        cta = _strip_link(content.get("cta", "").strip())
        hashtags = _normalize_hashtags(content.get("hashtags", []), min(hashtag_count, 5))
        parts = []
        if question:
            parts.append(question)
            parts.append("")
        if body:
            parts.append(body)
        if key_points:
            parts.append("")
            for point in key_points[:3]:
                parts.append(f"- {point.strip()}")
        if cta:
            parts.append("")
            parts.append(cta)
        if hashtags:
            parts.append("")
            parts.append(hashtags)
        return "\n".join(parts).strip()

    def _linkedin_generic(self, content: dict, hashtag_count: int) -> str:
        body = (content.get("linkedin_body") or content.get("body", "")).strip()
        hashtags = _normalize_hashtags(content.get("hashtags", []), min(hashtag_count, 5))
        result = body
        if hashtags:
            result += f"\n\n{hashtags}"
        return result.strip()
