"""Tests for MastodonPlatform."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from publisher.platforms.mastodon import MastodonPlatform
from publisher.platforms.base import Caption


def _caption(**kwargs):
    defaults = dict(title="Episode Title", soundbite_title="SB1", body="Listen to this!", tags=["podcast"])
    defaults.update(kwargs)
    return Caption(**defaults)


class TestMastodonIsConfigured:
    def test_both_required_fields_present(self):
        platform = MastodonPlatform({"instance_url": "https://mastodon.social", "access_token": "tok"})
        assert platform.is_configured() is True

    def test_missing_access_token(self):
        platform = MastodonPlatform({"instance_url": "https://mastodon.social"})
        assert platform.is_configured() is False

    def test_missing_instance_url(self):
        platform = MastodonPlatform({"access_token": "tok"})
        assert platform.is_configured() is False

    def test_empty_config(self):
        platform = MastodonPlatform({})
        assert platform.is_configured() is False


class TestMastodonPublish:
    def _make_platform(self, **extra):
        config = {"instance_url": "https://mastodon.social", "access_token": "tok", **extra}
        return MastodonPlatform(config)

    def test_raises_when_not_configured(self, tmp_path):
        platform = MastodonPlatform({})
        video = tmp_path / "video.mp4"
        video.touch()
        with pytest.raises(RuntimeError, match="instance_url and access_token"):
            platform.publish(video, _caption())

    def test_publish_returns_post_url(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake-video")
        platform = self._make_platform()

        mock_media = {"id": "123", "url": "https://mastodon.social/media/123"}
        mock_post = {"url": "https://mastodon.social/@user/99999", "id": "99999"}

        mock_mastodon = MagicMock()
        mock_mastodon.media_post.return_value = mock_media
        mock_mastodon.status_post.return_value = mock_post

        with patch("mastodon.Mastodon", return_value=mock_mastodon):
            result = platform.publish(video, _caption())

        assert result == "https://mastodon.social/@user/99999"
        mock_mastodon.media_post.assert_called_once()
        mock_mastodon.status_post.assert_called_once()

    def test_publish_polls_until_url_ready(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake-video")
        platform = self._make_platform()

        # First media response has no url, second has it
        media_pending = {"id": "123", "url": None}
        media_ready = {"id": "123", "url": "https://mastodon.social/media/123"}
        mock_post = {"url": "https://mastodon.social/@user/99999"}

        mock_mastodon = MagicMock()
        mock_mastodon.media_post.return_value = media_pending
        mock_mastodon.media.return_value = media_ready
        mock_mastodon.status_post.return_value = mock_post

        with patch("mastodon.Mastodon", return_value=mock_mastodon):
            with patch("publisher.platforms.mastodon.time.sleep"):
                result = platform.publish(video, _caption())

        mock_mastodon.media.assert_called_once_with("123")
        assert result == "https://mastodon.social/@user/99999"

    def test_publish_uses_default_visibility(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake-video")
        platform = self._make_platform()

        media = {"id": "1", "url": "https://mastodon.social/m/1"}
        mock_mastodon = MagicMock()
        mock_mastodon.media_post.return_value = media
        mock_mastodon.status_post.return_value = {"url": "https://example.com/1"}

        with patch("mastodon.Mastodon", return_value=mock_mastodon):
            platform.publish(video, _caption())

        _, kwargs = mock_mastodon.status_post.call_args
        assert kwargs.get("visibility") == "public"

    def test_publish_appends_tags_to_status(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake-video")
        platform = self._make_platform()

        media = {"id": "1", "url": "https://mastodon.social/m/1"}
        mock_mastodon = MagicMock()
        mock_mastodon.media_post.return_value = media
        mock_mastodon.status_post.return_value = {"url": "https://example.com/1"}

        caption = _caption(body="Listen!", tags=["podcast", "tech"])
        with patch("mastodon.Mastodon", return_value=mock_mastodon):
            platform.publish(video, caption)

        _, kwargs = mock_mastodon.status_post.call_args
        assert "#podcast" in kwargs["status"]
        assert "#tech" in kwargs["status"]
