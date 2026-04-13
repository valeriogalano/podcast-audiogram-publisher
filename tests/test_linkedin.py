"""Tests for LinkedInPlatform."""
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from publisher.platforms.linkedin import LinkedInPlatform
from publisher.platforms.base import Caption


def _caption(**kwargs):
    defaults = dict(title="Episode Title", soundbite_title="SB1", body="Listen to this!", tags=["podcast"])
    defaults.update(kwargs)
    return Caption(**defaults)


def _make_platform(**extra):
    config = {"access_token": "tok", "author": "urn:li:person:ABC123", **extra}
    return LinkedInPlatform(config)


class TestLinkedInIsConfigured:
    def test_both_required_fields_present(self):
        platform = LinkedInPlatform({"access_token": "tok", "author": "urn:li:person:ABC"})
        assert platform.is_configured() is True

    def test_missing_author(self):
        platform = LinkedInPlatform({"access_token": "tok"})
        assert platform.is_configured() is False

    def test_missing_access_token(self):
        platform = LinkedInPlatform({"author": "urn:li:person:ABC"})
        assert platform.is_configured() is False

    def test_empty_config(self):
        platform = LinkedInPlatform({})
        assert platform.is_configured() is False


class TestLinkedInPublish:
    def test_raises_when_not_configured(self, tmp_path):
        platform = LinkedInPlatform({})
        video = tmp_path / "video.mp4"
        video.touch()
        with pytest.raises(RuntimeError, match="access_token and author"):
            platform.publish(video, _caption())

    def _make_responses(self, video_urn="urn:li:video:VID1", post_id="POST1"):
        """Build mock requests.post / requests.put / requests.get return values."""
        # initializeUpload response
        init_resp = MagicMock()
        init_resp.raise_for_status = MagicMock()
        init_resp.json.return_value = {
            "value": {
                "video": video_urn,
                "uploadToken": "token123",
                "uploadInstructions": [
                    {"uploadUrl": "https://upload.example.com/chunk1", "firstByte": 0, "lastByte": 99}
                ],
            }
        }

        # PUT chunk response
        put_resp = MagicMock()
        put_resp.raise_for_status = MagicMock()
        put_resp.headers = {"ETag": '"etag-abc"'}

        # finalizeUpload response
        fin_resp = MagicMock()
        fin_resp.raise_for_status = MagicMock()
        fin_resp.json.return_value = {}

        # GET video status response — AVAILABLE
        status_resp = MagicMock()
        status_resp.raise_for_status = MagicMock()
        status_resp.json.return_value = {"status": "AVAILABLE"}

        # POST post response
        post_resp = MagicMock()
        post_resp.raise_for_status = MagicMock()
        post_resp.headers = {"x-restli-id": post_id}

        return init_resp, put_resp, fin_resp, status_resp, post_resp

    def test_publish_returns_post_id(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"x" * 100)
        platform = _make_platform()
        init_resp, put_resp, fin_resp, status_resp, post_resp = self._make_responses()

        with patch("publisher.platforms.linkedin.requests.post", side_effect=[init_resp, fin_resp, post_resp]) as mock_post, \
             patch("publisher.platforms.linkedin.requests.put", return_value=put_resp), \
             patch("publisher.platforms.linkedin.requests.get", return_value=status_resp):
            result = platform.publish(video, _caption())

        assert result == "linkedin:post:POST1"

    def test_publish_raises_on_processing_failed(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"x" * 100)
        platform = _make_platform()
        init_resp, put_resp, fin_resp, _, post_resp = self._make_responses()

        failed_status = MagicMock()
        failed_status.raise_for_status = MagicMock()
        failed_status.json.return_value = {"status": "PROCESSING_FAILED"}

        with patch("publisher.platforms.linkedin.requests.post", side_effect=[init_resp, fin_resp, post_resp]), \
             patch("publisher.platforms.linkedin.requests.put", return_value=put_resp), \
             patch("publisher.platforms.linkedin.requests.get", return_value=failed_status):
            with pytest.raises(RuntimeError, match="processing failed"):
                platform.publish(video, _caption())

    def test_publish_appends_tags(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"x" * 100)
        platform = _make_platform()
        init_resp, put_resp, fin_resp, status_resp, post_resp = self._make_responses()

        posted_bodies = []

        def capture_post(url, json=None, headers=None, timeout=None):
            posted_bodies.append((url, json))
            if "initializeUpload" in url:
                return init_resp
            if "finalizeUpload" in url:
                return fin_resp
            return post_resp

        caption = _caption(body="Listen!", tags=["podcast", "tech"])
        with patch("publisher.platforms.linkedin.requests.post", side_effect=capture_post), \
             patch("publisher.platforms.linkedin.requests.put", return_value=put_resp), \
             patch("publisher.platforms.linkedin.requests.get", return_value=status_resp):
            platform.publish(video, caption)

        # The last POST is the UGC post
        _, post_body = posted_bodies[-1]
        assert "#podcast" in post_body["commentary"]
        assert "#tech" in post_body["commentary"]
