"""
test_agent.py - Smoke tests for SocialAgent core logic.
No real API calls — all external dependencies are mocked via DI.
"""

import pytest
from unittest.mock import MagicMock, patch

from social_agent.agent import SocialAgent
from social_agent.types import PostingError, ConfigError
from social_agent.config import load_config


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_loads_valid_config(self, minimal_config):
        cfg = load_config(str(minimal_config))
        assert cfg["llm"]["model"] == "gemini-2.5-flash"
        assert len(cfg["topics"]) == 1
        assert len(cfg["formats"]) == 1

    def test_raises_config_error_for_missing_file(self, tmp_path):
        from social_agent.types import ConfigError
        with pytest.raises(ConfigError, match="Không tìm thấy config"):
            load_config(str(tmp_path / "nonexistent.yaml"))

    def test_raises_config_error_for_invalid_yaml(self, tmp_path):
        bad = tmp_path / "config.yaml"
        bad.write_text(": invalid: yaml: [", encoding="utf-8")
        with pytest.raises(ConfigError, match="không hợp lệ"):
            load_config(str(bad))


# ---------------------------------------------------------------------------
# SocialAgent init via DI
# ---------------------------------------------------------------------------

class TestSocialAgentInit:
    def test_init_with_mocked_deps(self, minimal_config, mock_fb_api, mock_li_api,
                                   mock_generator, mock_audit):
        agent = SocialAgent(
            config_path=str(minimal_config),
            fb_api=mock_fb_api,
            li_api=mock_li_api,
            generator=mock_generator,
            audit=mock_audit,
        )
        assert "test_page" in agent._targets
        assert "ai_vietnam" in agent._topics
        assert "thought_leadership" in agent._formats

    def test_targets_indexed_by_id(self, minimal_config, mock_fb_api, mock_li_api,
                                   mock_generator, mock_audit):
        agent = SocialAgent(
            config_path=str(minimal_config),
            fb_api=mock_fb_api,
            li_api=mock_li_api,
            generator=mock_generator,
            audit=mock_audit,
        )
        target = agent._targets["test_page"]
        assert target["type"] == "page"
        assert target["target_id"] == "123456789"


# ---------------------------------------------------------------------------
# post_now — happy path
# ---------------------------------------------------------------------------

class TestPostNow:
    def _make_agent(self, minimal_config, mock_fb_api, mock_li_api,
                    mock_generator, mock_audit):
        return SocialAgent(
            config_path=str(minimal_config),
            fb_api=mock_fb_api,
            li_api=mock_li_api,
            generator=mock_generator,
            audit=mock_audit,
        )

    def test_post_now_returns_post_url(self, minimal_config, mock_fb_api,
                                       mock_li_api, mock_generator, mock_audit):
        agent = self._make_agent(minimal_config, mock_fb_api, mock_li_api,
                                 mock_generator, mock_audit)
        with patch("social_agent.agent.generate_image", return_value=None):
            result = agent.post_now(
                target_id="test_page",
                topic_id="ai_vietnam",
                format_id="thought_leadership",
                image_path=None,
            )
        assert result.get("post_url") == "https://www.facebook.com/123_456"
        assert "content" in result

    def test_post_now_calls_fb_api(self, minimal_config, mock_fb_api,
                                   mock_li_api, mock_generator, mock_audit):
        agent = self._make_agent(minimal_config, mock_fb_api, mock_li_api,
                                 mock_generator, mock_audit)
        with patch("social_agent.agent.generate_image", return_value=None):
            agent.post_now(
                target_id="test_page",
                topic_id="ai_vietnam",
                format_id="thought_leadership",
                image_path=None,
            )
        mock_fb_api.post_to_page.assert_called_once()

    def test_post_now_raises_for_unknown_target(self, minimal_config, mock_fb_api,
                                                mock_li_api, mock_generator, mock_audit):
        agent = self._make_agent(minimal_config, mock_fb_api, mock_li_api,
                                 mock_generator, mock_audit)
        with pytest.raises(ValueError, match="Target không tồn tại"):
            agent.post_now(target_id="nonexistent_target")

    def test_post_now_logs_audit(self, minimal_config, mock_fb_api,
                                 mock_li_api, mock_generator, mock_audit):
        agent = self._make_agent(minimal_config, mock_fb_api, mock_li_api,
                                 mock_generator, mock_audit)
        with patch("social_agent.agent.generate_image", return_value=None):
            agent.post_now(
                target_id="test_page",
                topic_id="ai_vietnam",
                format_id="thought_leadership",
            )
        mock_audit.log_post.assert_called_once()
        call_kwargs = mock_audit.log_post.call_args
        assert call_kwargs.kwargs.get("success") is True or call_kwargs.args[5] is True


# ---------------------------------------------------------------------------
# _dispatch_post — PostingError for unknown type
# ---------------------------------------------------------------------------

class TestDispatchPost:
    def test_raises_posting_error_for_unknown_type(self, minimal_config,
                                                    mock_fb_api, mock_li_api,
                                                    mock_generator, mock_audit):
        agent = SocialAgent(
            config_path=str(minimal_config),
            fb_api=mock_fb_api,
            li_api=mock_li_api,
            generator=mock_generator,
            audit=mock_audit,
        )
        with pytest.raises(PostingError, match="Target type không hỗ trợ"):
            agent._dispatch_post(
                target={"type": "tiktok", "id": "t1"},
                text="test",
                image_path=None,
            )


# ---------------------------------------------------------------------------
# preview
# ---------------------------------------------------------------------------

class TestPreview:
    def test_preview_returns_string(self, minimal_config, mock_fb_api,
                                    mock_li_api, mock_generator, mock_audit):
        agent = SocialAgent(
            config_path=str(minimal_config),
            fb_api=mock_fb_api,
            li_api=mock_li_api,
            generator=mock_generator,
            audit=mock_audit,
        )
        result = agent.preview("ai_vietnam", "thought_leadership", platform="facebook")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_preview_all_platforms_returns_both(self, minimal_config, mock_fb_api,
                                                 mock_li_api, mock_generator, mock_audit):
        agent = SocialAgent(
            config_path=str(minimal_config),
            fb_api=mock_fb_api,
            li_api=mock_li_api,
            generator=mock_generator,
            audit=mock_audit,
        )
        result = agent.preview_all_platforms("ai_vietnam", "thought_leadership")
        assert "facebook" in result
        assert "linkedin" in result
        assert "raw" in result


# ---------------------------------------------------------------------------
# get_stats / get_history delegate to audit
# ---------------------------------------------------------------------------

class TestStats:
    def test_get_stats_delegates_to_audit(self, minimal_config, mock_fb_api,
                                          mock_li_api, mock_generator, mock_audit):
        agent = SocialAgent(
            config_path=str(minimal_config),
            fb_api=mock_fb_api,
            li_api=mock_li_api,
            generator=mock_generator,
            audit=mock_audit,
        )
        stats = agent.get_stats()
        mock_audit.stats.assert_called_once()
        assert stats["total"] == 0

    def test_get_history_delegates_to_audit(self, minimal_config, mock_fb_api,
                                            mock_li_api, mock_generator, mock_audit):
        agent = SocialAgent(
            config_path=str(minimal_config),
            fb_api=mock_fb_api,
            li_api=mock_li_api,
            generator=mock_generator,
            audit=mock_audit,
        )
        history = agent.get_history(limit=5)
        mock_audit.read_history.assert_called_once_with(limit=5)
        assert history == []
