"""
conftest.py - Shared fixtures for Social Agent tests.
"""

import pytest
import yaml
from pathlib import Path
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Minimal valid config dict (no file I/O, no real tokens)
# ---------------------------------------------------------------------------

MINIMAL_CONFIG = {
    "llm": {
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "temperature": 0.8,
        "max_tokens": 4096,
    },
    "topics": [
        {
            "id": "ai_vietnam",
            "name": "AI tại Việt Nam",
            "description": "Xu hướng AI tại Việt Nam",
            "keywords": ["AI", "automation"],
        }
    ],
    "formats": [
        {
            "id": "thought_leadership",
            "name": "Thought Leadership",
            "max_chars": 500,
        }
    ],
    "targets": [
        {
            "id": "test_page",
            "name": "Test Page",
            "type": "page",
            "target_id": "123456789",
            "access_token": "TEST_TOKEN",
            "schedule": "0 8 * * *",
            "topics": ["ai_vietnam"],
            "formats": ["thought_leadership"],
            "enabled": True,
        }
    ],
    "cross_post_groups": [],
    "logging": {"log_dir": "/tmp/social_agent_test_logs", "level": "WARNING"},
}


@pytest.fixture
def minimal_config(tmp_path) -> Path:
    """Write MINIMAL_CONFIG to a temp config.yaml and return its path."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(MINIMAL_CONFIG, allow_unicode=True), encoding="utf-8")
    return config_file


@pytest.fixture
def mock_fb_api():
    """FacebookAPI mock that returns a successful post result."""
    api = MagicMock()
    api.post_to_page.return_value = {
        "post_id": "123_456",
        "post_url": "https://www.facebook.com/123_456",
    }
    api.post_to_group.return_value = {
        "post_id": "789_012",
        "post_url": "https://www.facebook.com/789_012",
    }
    api.validate_token.return_value = {"valid": True, "name": "Test Page"}
    return api


@pytest.fixture
def mock_li_api():
    """LinkedInAPI mock that returns a successful post result."""
    api = MagicMock()
    api.post_to_profile.return_value = {
        "post_id": "urn:li:share:123",
        "post_url": "https://www.linkedin.com/feed/update/urn:li:share:123",
    }
    api.validate_token.return_value = {"valid": True}
    return api


@pytest.fixture
def mock_generator():
    """ContentGenerator mock that returns a valid content dict."""
    gen = MagicMock()
    gen.api_key = "FAKE_GEMINI_KEY"
    gen.list_topics.return_value = MINIMAL_CONFIG["topics"]
    gen.generate.return_value = {
        "title": "Test Title AI",
        "body": "Nội dung test về AI tại Việt Nam.",
        "key_points": ["Point 1", "Point 2"],
        "cta": "Liên hệ FastDX ngay!",
        "hashtags": ["#AI", "#FastDX"],
    }
    return gen


@pytest.fixture
def mock_audit():
    """AuditLoggerDB mock that swallows writes and returns empty history."""
    audit = MagicMock()
    audit.read_history.return_value = []
    audit.stats.return_value = {"total": 0, "success": 0, "failed": 0, "by_target": {}, "by_topic": {}}
    audit.is_duplicate.return_value = False
    audit.recently_posted_combo.return_value = False
    return audit
