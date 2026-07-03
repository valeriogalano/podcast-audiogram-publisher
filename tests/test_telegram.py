"""Unit tests for the pure decision helpers in the Telegram platform."""
from publisher.platforms.telegram import (
    STORY_MAX_DURATION,
    MESSAGE_CAPTION_LIMIT,
    _use_story,
    _truncate_caption,
)


class TestUseStory:
    def test_short_video_uses_story(self):
        assert _use_story(30.0) is True

    def test_exactly_at_limit_uses_story(self):
        assert _use_story(60.0) is True

    def test_over_limit_uses_message(self):
        assert _use_story(60.5) is False
        assert _use_story(71.0) is False

    def test_unknown_duration_falls_back_to_story(self):
        # 0.0 means ffprobe failed -> preserve previous default (story)
        assert _use_story(0.0) is True

    def test_custom_max_duration(self):
        assert _use_story(90.0, max_duration=120) is True
        assert _use_story(130.0, max_duration=120) is False

    def test_default_limit_is_sixty(self):
        assert STORY_MAX_DURATION == 60


class TestTruncateCaption:
    def test_short_caption_is_unchanged(self):
        assert _truncate_caption("hello", limit=1024) == "hello"

    def test_caption_exactly_at_limit_is_unchanged(self):
        text = "x" * MESSAGE_CAPTION_LIMIT
        assert _truncate_caption(text) == text

    def test_long_caption_is_truncated_within_limit(self):
        text = "word " * 500  # 2500 chars
        result = _truncate_caption(text, limit=100)
        assert len(result) <= 100
        assert result.endswith("…")

    def test_truncation_cuts_on_word_boundary(self):
        text = "alpha beta gamma delta epsilon"
        result = _truncate_caption(text, limit=14)
        # No partial word before the ellipsis
        assert result.endswith("…")
        assert "gam…" not in result
        assert result[:-1].strip().split(" ")[-1] in {"alpha", "beta"}

    def test_default_limit_is_1024(self):
        assert MESSAGE_CAPTION_LIMIT == 1024
