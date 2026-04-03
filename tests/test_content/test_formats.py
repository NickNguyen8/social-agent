"""
test_formats.py - Tests for FormatRenderer (no LLM calls, pure rendering logic).
"""

import pytest
from social_agent.content.formats import FormatRenderer, _normalize_hashtags


class TestNormalizeHashtags:
    def test_adds_hash_prefix(self):
        result = _normalize_hashtags(["AI", "FastDX"])
        assert result == "#AI #FastDX"

    def test_strips_existing_hash(self):
        result = _normalize_hashtags(["#AI", "#FastDX"])
        assert result == "#AI #FastDX"

    def test_removes_spaces_in_tag(self):
        result = _normalize_hashtags(["Digital Transformation"])
        assert "#DigitalTransformation" in result

    def test_limits_count(self):
        tags = ["a", "b", "c", "d", "e", "f", "g"]
        result = _normalize_hashtags(tags, count=5)
        assert result.count("#") == 5

    def test_handles_string_input(self):
        result = _normalize_hashtags("#AI #FastDX")
        assert "#AI" in result
        assert "#FastDX" in result

    def test_empty_list(self):
        assert _normalize_hashtags([]) == ""


class TestFormatRenderer:
    """FormatRenderer.render() with a minimal format_config dict."""

    FORMAT_CFG = {"id": "thought_leadership", "name": "Thought Leadership", "max_chars": 500}

    def setup_method(self):
        self.renderer = FormatRenderer()
        self.content = {
            "title": "Test Title AI",
            "body": "Nội dung test về AI.",
            "key_points": ["Điểm 1", "Điểm 2"],
            "cta": "Liên hệ FastDX!",
            "hashtags": ["#AI", "#FastDX"],
        }

    def test_render_thought_leadership_facebook(self):
        result = self.renderer.render(
            "thought_leadership", self.content, self.FORMAT_CFG, platform="facebook"
        )
        assert isinstance(result, str)
        assert len(result) > 10
        assert "#AI" in result or "#FastDX" in result

    def test_render_thought_leadership_linkedin(self):
        result = self.renderer.render(
            "thought_leadership", self.content, self.FORMAT_CFG, platform="linkedin"
        )
        assert isinstance(result, str)
        assert len(result) > 10

    def test_render_quick_insight_facebook(self):
        content = {
            "hook": "AI đang thay đổi mọi thứ",
            "body": "Trong 5 năm qua...",
            "key_points": ["Insight 1", "Insight 2"],
            "cta": "Share nếu đồng ý!",
            "hashtags": ["#AI"],
        }
        cfg = {"id": "quick_insight", "name": "Quick Insight", "max_chars": 280}
        result = self.renderer.render("quick_insight", content, cfg, platform="facebook")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_story_post_facebook(self):
        content = {
            "opening_hook": "Năm 2020, tôi gặp một doanh nghiệp...",
            "body": "Họ đang dùng Excel để quản lý 500 nhân viên.",
            "lesson": "Bài học: bắt đầu từ nỗi đau thực sự.",
            "cta": "Bạn đang gặp vấn đề gì?",
            "hashtags": ["#DX", "#FastDX"],
        }
        cfg = {"id": "story_post", "name": "Story Post", "max_chars": 450}
        result = self.renderer.render("story_post", content, cfg, platform="facebook")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_engagement_post_facebook(self):
        content = {
            "question": "Bạn dùng AI hay chưa?",
            "body": "Theo khảo sát mới nhất...",
            "key_points": ["Option A", "Option B"],
            "cta": "Comment bên dưới!",
            "hashtags": ["#AI", "#Poll"],
        }
        cfg = {"id": "engagement_post", "name": "Engagement Post", "max_chars": 400}
        result = self.renderer.render("engagement_post", content, cfg, platform="facebook")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_title_not_duplicated_at_start(self):
        """Nếu body bắt đầu bằng title → renderer phải strip title khỏi body."""
        content = {
            "title": "Test Title",
            "body": "Test Title\nNội dung thực sự ở đây.",
            "key_points": [],
            "cta": "CTA",
            "hashtags": [],
        }
        result = self.renderer.render(
            "thought_leadership", content, self.FORMAT_CFG, platform="facebook"
        )
        # Title should not appear twice
        assert result.count("Test Title") <= 1
