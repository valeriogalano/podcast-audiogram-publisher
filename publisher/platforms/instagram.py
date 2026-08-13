"""Instagram Reels publishing via the Instagram API with Instagram Login.

Deliberately *not* the Facebook Login flavour of the API: that one requires the
account to be linked to a Facebook Page and its token can only be renewed by
hand in the Access Token Debugger. With Instagram Login a professional account
is enough, and the long-lived token can be refreshed programmatically — see
``refresh_access_token``.

The trade-off: **this flavour has no upload endpoint**. `upload_type=resumable`
is Facebook-Login only; here Meta downloads the video from a public URL, so the
file must already be hosted somewhere reachable (see ``video_url_template``).
Verified the hard way on 2026-08-11: sending the video as a resumable upload
answers `error 100: The parameter video_url is required`.
"""
import logging
import re
import time
from datetime import date, timedelta
from pathlib import Path

import requests

from .base import BasePlatform, Caption

logger = logging.getLogger(__name__)

# graph.instagram.com does not report the served version in a response header,
# so this cannot be probed the way graph.facebook.com can. v23.0 is the version
# Meta documents for the Instagram Login flow.
_GRAPH_BASE = "https://graph.instagram.com/v23.0"
# The token refresh endpoint is unversioned.
_REFRESH_URL = "https://graph.instagram.com/refresh_access_token"

_TOKEN_WARNING_DAYS = 7
_POLL_INTERVAL = 5
_POLL_MAX_ATTEMPTS = 24  # 2 minutes total
_CAPTION_MAX_CHARS = 2200


def _check_token_expiry(token_expiry: str) -> None:
    if not token_expiry:
        return
    try:
        # str(): YAML deserializza una data non quotata in datetime.date, e
        # fromisoformat su un date solleva TypeError, non ValueError.
        expiry = date.fromisoformat(str(token_expiry))
    except ValueError:
        logger.warning("Instagram token_expiry is not a valid ISO date: %s", token_expiry)
        return
    days_left = (expiry - date.today()).days
    if days_left < 0:
        raise RuntimeError(
            f"Instagram access token expired on {token_expiry}. "
            "Refresh it with: python -m publisher --refresh-instagram-token"
        )
    if days_left <= _TOKEN_WARNING_DAYS:
        logger.warning(
            "Instagram access token expires in %d day(s) on %s. Refresh it soon.",
            days_left,
            token_expiry,
        )


def _raise_for_error(response: requests.Response) -> None:
    try:
        data = response.json()
    except Exception:
        response.raise_for_status()
        return
    if "error" in data:
        err = data["error"]
        raise RuntimeError(f"Instagram API error {err.get('code')}: {err.get('message')}")
    response.raise_for_status()


def _request_with_retry(method: str, url: str, max_retries: int = 3, **kwargs) -> dict:
    for attempt in range(max_retries):
        try:
            resp = requests.request(method, url, timeout=60, **kwargs)
            _raise_for_error(resp)
            return resp.json()
        except RuntimeError:
            # An API-level error is an answer, not a hiccup: retrying will not
            # change a bad token or a rejected video.
            raise
        except Exception as exc:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning("Request attempt %d failed: %s. Retrying in %ds...", attempt + 1, exc, wait)
                time.sleep(wait)
            else:
                raise


def refresh_access_token(access_token: str) -> tuple[str, date]:
    """Exchange a long-lived token for a fresh one, valid another 60 days.

    Returns the new token and its expiry date. Meta requires the token to be at
    least 24 hours old and not yet expired, so this cannot rescue a token that
    was already left to die.
    """
    data = _request_with_retry(
        "GET",
        _REFRESH_URL,
        params={"grant_type": "ig_refresh_token", "access_token": access_token},
    )
    new_token = data.get("access_token")
    if not new_token:
        raise RuntimeError(f"Instagram refresh did not return a token: {data}")
    # Senza expires_in la scadenza calcolata sarebbe oggi: _check_token_expiry
    # bloccherebbe la pubblicazione il giorno dopo, con un token ancora valido e
    # un messaggio d'errore che accusa il token. Meglio fallire subito e qui.
    expires_in = data.get("expires_in")
    if expires_in is None:
        raise RuntimeError(f"Instagram refresh did not return expires_in: {data}")
    return new_token, date.today() + timedelta(seconds=int(expires_in))


class InstagramPlatform(BasePlatform):
    def is_configured(self) -> bool:
        # ig_user_id is optional: it is resolved from the token when missing.
        return bool(self.config.get("access_token"))

    def _user_id(self, token: str) -> str:
        configured = self.config.get("ig_user_id")
        if configured:
            return str(configured)
        data = _request_with_retry(
            "GET",
            f"{_GRAPH_BASE}/me",
            params={"fields": "user_id,username", "access_token": token},
        )
        user_id = data.get("user_id") or data.get("id")
        if not user_id:
            raise RuntimeError(f"Could not resolve the Instagram user id from the token: {data}")
        logger.info("Resolved Instagram account @%s (id %s)", data.get("username", "?"), user_id)
        return str(user_id)

    def video_url_for(self, video_path: Path) -> str:
        """Public URL of *video_path*, built from video_url_template.

        Instagram Login has no upload endpoint: Meta fetches the file over HTTP
        at publish time, so the video must already be reachable publicly.
        """
        template = self.config.get("video_url_template", "")
        if not template:
            raise RuntimeError(
                "Instagram needs video_url_template in config: the API with Instagram Login "
                "does not accept file uploads, it downloads the video from a public URL. "
                "Example: https://github.com/<owner>/<repo>/releases/download/podcast-ep{episode}/{filename}"
            )
        fields = {"filename": video_path.name}
        if "{episode}" in template:
            match = re.match(r"ep(\d+)_", video_path.name)
            if not match:
                raise RuntimeError(
                    f"video_url_template uses {{episode}} but the episode number could not be "
                    f"read from the file name '{video_path.name}' (expected a leading 'ep<N>_')."
                )
            fields["episode"] = match.group(1)
        return template.format(**fields)

    def publish(self, video_path: Path, caption: Caption) -> str:
        if not self.is_configured():
            raise RuntimeError("Instagram access_token must be set in config.")

        _check_token_expiry(self.config.get("token_expiry", ""))

        token = self.config["access_token"]
        user_id = self._user_id(token)
        caption_text = caption.body[:_CAPTION_MAX_CHARS]
        video_url = self.video_url_for(video_path)

        # Step 1: create the container. Meta downloads the video itself, so a
        # 200 here only means the URL was accepted, not that the video is good.
        logger.info("Creating Instagram Reels container from %s", video_url)
        container = _request_with_retry(
            "POST",
            f"{_GRAPH_BASE}/{user_id}/media",
            params={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption_text,
                "access_token": token,
            },
        )
        container_id = container.get("id")
        if not container_id:
            raise RuntimeError(f"Instagram did not return a container id: {container}")

        # Step 2: wait for Instagram to download and transcode the video.
        logger.info("Waiting for Instagram container %s to be ready...", container_id)
        for attempt in range(_POLL_MAX_ATTEMPTS):
            status = _request_with_retry(
                "GET",
                f"{_GRAPH_BASE}/{container_id}",
                params={"fields": "status_code,status", "access_token": token},
            )
            status_code = status.get("status_code")
            if status_code == "FINISHED":
                break
            if status_code == "ERROR":
                raise RuntimeError(
                    f"Instagram media container processing failed: {status.get('status', 'no detail')}"
                )
            logger.debug("Container status: %s (attempt %d/%d)", status_code, attempt + 1, _POLL_MAX_ATTEMPTS)
            time.sleep(_POLL_INTERVAL)
        else:
            raise RuntimeError("Instagram media container did not become ready in time.")

        # Step 3: publish.
        logger.info("Publishing Instagram Reel...")
        published = _request_with_retry(
            "POST",
            f"{_GRAPH_BASE}/{user_id}/media_publish",
            params={"creation_id": container_id, "access_token": token},
        )
        media_id = published.get("id")
        if not media_id:
            raise RuntimeError(f"Instagram did not return a media id: {published}")

        permalink = self._permalink(media_id, token)
        logger.info("Instagram publish complete: %s", permalink)
        return permalink

    def _permalink(self, media_id: str, token: str) -> str:
        """Best-effort permalink; the media id alone is useless in a log."""
        try:
            data = _request_with_retry(
                "GET",
                f"{_GRAPH_BASE}/{media_id}",
                params={"fields": "permalink", "access_token": token},
            )
            return data.get("permalink") or f"media:{media_id}"
        except Exception as exc:
            logger.warning("Could not fetch the permalink for media %s: %s", media_id, exc)
            return f"media:{media_id}"
