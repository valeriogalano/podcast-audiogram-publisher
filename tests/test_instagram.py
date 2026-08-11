"""Tests for InstagramPlatform (Instagram API with Instagram Login)."""
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from publisher.platforms.base import Caption
from publisher.platforms.instagram import (
    InstagramPlatform,
    _check_token_expiry,
    refresh_access_token,
)


def _caption(**kwargs):
    defaults = dict(
        title="Episode Title",
        soundbite_title="SB1",
        body="Ascolta questo pezzo!",
        tags=["podcast"],
    )
    defaults.update(kwargs)
    return Caption(**defaults)


class TestCheckTokenExpiry:
    def test_accepts_iso_string(self):
        _check_token_expiry((date.today() + timedelta(days=30)).isoformat())

    def test_accepts_date_object(self):
        # YAML deserializza una data non quotata in datetime.date: prima
        # sollevava TypeError, che nessuno intercettava.
        _check_token_expiry(date.today() + timedelta(days=30))

    def test_raises_when_expired(self):
        with pytest.raises(RuntimeError, match="expired"):
            _check_token_expiry((date.today() - timedelta(days=1)).isoformat())

    def test_raises_when_expired_as_date_object(self):
        with pytest.raises(RuntimeError, match="expired"):
            _check_token_expiry(date.today() - timedelta(days=1))

    def test_empty_value_is_skipped(self):
        _check_token_expiry("")

    def test_garbage_only_warns(self, caplog):
        _check_token_expiry("non-una-data")
        assert "not a valid ISO date" in caplog.text


class TestIsConfigured:
    def test_token_alone_is_enough(self):
        # ig_user_id is optional by design: it is resolved from the token.
        assert InstagramPlatform({"access_token": "tok"}).is_configured() is True

    def test_missing_token(self):
        assert InstagramPlatform({"ig_user_id": "42"}).is_configured() is False


class TestRefreshAccessToken:
    def test_returns_token_and_expiry(self):
        with patch(
            "publisher.platforms.instagram._request_with_retry",
            return_value={"access_token": "new-tok", "expires_in": 5184000},
        ):
            token, expiry = refresh_access_token("old-tok")
        assert token == "new-tok"
        assert expiry == date.today() + timedelta(days=60)

    def test_raises_without_token_in_response(self):
        with patch("publisher.platforms.instagram._request_with_retry", return_value={}):
            with pytest.raises(RuntimeError, match="did not return a token"):
                refresh_access_token("old-tok")


class TestUserIdResolution:
    def test_configured_id_wins_and_skips_the_call(self):
        platform = InstagramPlatform({"access_token": "tok", "ig_user_id": 42})
        with patch("publisher.platforms.instagram._request_with_retry") as request:
            assert platform._user_id("tok") == "42"
        request.assert_not_called()

    def test_resolved_from_token_when_missing(self):
        platform = InstagramPlatform({"access_token": "tok"})
        with patch(
            "publisher.platforms.instagram._request_with_retry",
            return_value={"user_id": 1784100, "username": "valeriogalano"},
        ):
            assert platform._user_id("tok") == "1784100"

    def test_raises_when_unresolvable(self):
        platform = InstagramPlatform({"access_token": "tok"})
        with patch("publisher.platforms.instagram._request_with_retry", return_value={}):
            with pytest.raises(RuntimeError, match="Could not resolve"):
                platform._user_id("tok")


class TestVideoUrl:
    def test_builds_the_url_from_the_template(self):
        platform = InstagramPlatform({
            "access_token": "tok",
            "video_url_template": "https://example.com/rel/podcast-ep{episode}/{filename}",
        })
        url = platform.video_url_for(Path("/tmp/ep150_sb1_nosubs_vertical.mp4"))
        assert url == "https://example.com/rel/podcast-ep150/ep150_sb1_nosubs_vertical.mp4"

    def test_template_without_episode_placeholder(self):
        platform = InstagramPlatform({
            "access_token": "tok",
            "video_url_template": "https://cdn.example.com/{filename}",
        })
        assert platform.video_url_for(Path("/tmp/sb.mp4")) == "https://cdn.example.com/sb.mp4"

    def test_missing_template_explains_why(self):
        platform = InstagramPlatform({"access_token": "tok"})
        with pytest.raises(RuntimeError, match="video_url_template"):
            platform.video_url_for(Path("/tmp/sb.mp4"))

    def test_unparsable_episode_is_reported(self):
        platform = InstagramPlatform({
            "access_token": "tok",
            "video_url_template": "https://example.com/{episode}/{filename}",
        })
        with pytest.raises(RuntimeError, match="episode number"):
            platform.video_url_for(Path("/tmp/soundbite.mp4"))


class TestPublish:
    def test_raises_without_token(self, tmp_path):
        video = tmp_path / "sb.mp4"
        video.write_bytes(b"x")
        with pytest.raises(RuntimeError, match="access_token"):
            InstagramPlatform({}).publish(video, _caption())

    def test_publishes_and_returns_the_permalink(self, tmp_path):
        video = tmp_path / "ep150_sb1.mp4"
        video.write_bytes(b"fake-video")
        platform = InstagramPlatform({
            "access_token": "tok",
            "ig_user_id": "42",
            "video_url_template": "https://example.com/ep{episode}/{filename}",
        })
        seen = {}

        def fake_request(method, url, **kwargs):
            if url.endswith("/42/media"):
                seen["params"] = kwargs["params"]
                return {"id": "container-1"}
            if url.endswith("/container-1"):
                return {"status_code": "FINISHED"}
            if url.endswith("/42/media_publish"):
                return {"id": "media-9"}
            if url.endswith("/media-9"):
                return {"permalink": "https://www.instagram.com/reel/abc/"}
            raise AssertionError(f"unexpected call: {url}")

        with patch("publisher.platforms.instagram._request_with_retry", side_effect=fake_request):
            result = platform.publish(video, _caption())

        assert result == "https://www.instagram.com/reel/abc/"
        # Meta scarica il video: mandiamo un URL, mai il file.
        assert seen["params"]["video_url"] == "https://example.com/ep150/ep150_sb1.mp4"
        assert "upload_type" not in seen["params"]

    def test_raises_when_container_processing_fails(self, tmp_path):
        video = tmp_path / "ep150_sb1.mp4"
        video.write_bytes(b"x")
        platform = InstagramPlatform({
            "access_token": "tok",
            "ig_user_id": "42",
            "video_url_template": "https://example.com/{filename}",
        })

        def fake_request(method, url, **kwargs):
            if url.endswith("/42/media"):
                return {"id": "container-1"}
            if url.endswith("/container-1"):
                return {"status_code": "ERROR", "status": "video too long"}
            raise AssertionError(f"unexpected call: {url}")

        with patch("publisher.platforms.instagram._request_with_retry", side_effect=fake_request):
            with pytest.raises(RuntimeError, match="video too long"):
                platform.publish(video, _caption())

    def test_caption_is_truncated_to_the_api_limit(self, tmp_path):
        video = tmp_path / "ep150_sb1.mp4"
        video.write_bytes(b"x")
        platform = InstagramPlatform({
            "access_token": "tok",
            "ig_user_id": "42",
            "video_url_template": "https://example.com/{filename}",
        })
        seen = {}

        def fake_request(method, url, **kwargs):
            if url.endswith("/42/media"):
                seen["caption"] = kwargs["params"]["caption"]
                return {"id": "c"}
            if url.endswith("/c"):
                return {"status_code": "FINISHED"}
            if url.endswith("/42/media_publish"):
                return {"id": "m"}
            return {"permalink": "https://www.instagram.com/reel/x/"}

        with patch("publisher.platforms.instagram._request_with_retry", side_effect=fake_request):
            platform.publish(video, _caption(body="a" * 3000))

        assert len(seen["caption"]) == 2200
