"""Unit tests for the pure helpers in the Telegram platform."""
from publisher.platforms.base import Caption
from publisher.state import PublishState
from publisher.platforms.telegram import (
    STORY_MAX_DURATION,
    DEFAULT_LINK_TEXT,
    _use_story,
    _build_message_caption,
    _is_peer_published,
    _mark_peer_published,
    _peer_state_platform,
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


def _caption(**kwargs) -> Caption:
    defaults = dict(
        title="Episode 150: The title",
        soundbite_title="A soundbite line",
        body="full body with the TRANSCRIPT_MARKER inside",
        tags=["podcast", "python"],
        episode_url="https://example.com/ep150",
    )
    defaults.update(kwargs)
    return Caption(**defaults)


class TestBuildMessageCaption:
    def test_excludes_the_transcript_body(self):
        result = _build_message_caption(_caption())
        assert "TRANSCRIPT_MARKER" not in result

    def test_includes_title_soundbite_and_hashtags(self):
        result = _build_message_caption(_caption())
        assert "Episode 150: The title" in result
        assert "A soundbite line" in result
        assert "#podcast" in result
        assert "#python" in result

    def test_link_is_a_clickable_anchor(self):
        result = _build_message_caption(_caption(), link_text="Listen now")
        assert '<a href="https://example.com/ep150">Listen now</a>' in result

    def test_uses_default_link_text(self):
        result = _build_message_caption(_caption())
        assert DEFAULT_LINK_TEXT in result

    def test_html_special_chars_are_escaped(self):
        result = _build_message_caption(_caption(soundbite_title="A & B <tag>"))
        assert "A &amp; B &lt;tag&gt;" in result
        assert "<tag>" not in result

    def test_missing_url_omits_the_link(self):
        result = _build_message_caption(_caption(episode_url=None))
        assert "<a href" not in result
        assert "Episode 150: The title" in result

    def test_missing_tags_omits_hashtags(self):
        result = _build_message_caption(_caption(tags=[]))
        assert "#" not in result


class TestPeerState:
    def test_peer_state_platform_includes_peer(self):
        assert _peer_state_platform("telegram", "@channel") == "telegram:peer:@channel"

    def test_peer_state_is_separate_from_platform_state(self, tmp_path):
        state = PublishState(tmp_path / "published.json")
        key = "ep150/sb1"

        _mark_peer_published(state, key, "telegram", "me")

        assert _is_peer_published(state, key, "telegram", "me") is True
        assert _is_peer_published(state, key, "telegram", "@other") is False
        assert state.is_published("telegram", key) is False
