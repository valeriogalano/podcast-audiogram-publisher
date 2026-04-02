import logging
import time
from datetime import date, datetime
from pathlib import Path

import requests

from .base import BasePlatform, Caption

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.facebook.com/v19.0"
_TOKEN_WARNING_DAYS = 7
_POLL_INTERVAL = 5
_POLL_MAX_ATTEMPTS = 24  # 2 minutes total


def _check_token_expiry(token_expiry: str) -> None:
    if not token_expiry:
        return
    try:
        expiry = date.fromisoformat(token_expiry)
    except ValueError:
        logger.warning("Instagram token_expiry is not a valid ISO date: %s", token_expiry)
        return
    days_left = (expiry - date.today()).days
    if days_left < 0:
        raise RuntimeError(
            f"Instagram access token expired on {token_expiry}. "
            "Renew it at https://developers.facebook.com/tools/explorer/"
        )
    if days_left <= _TOKEN_WARNING_DAYS:
        logger.warning(
            "Instagram access token expires in %d day(s) on %s. Renew it soon.",
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


def _post_with_retry(url: str, params: dict, max_retries: int = 3) -> dict:
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, params=params, timeout=60)
            _raise_for_error(resp)
            return resp.json()
        except RuntimeError:
            raise
        except Exception as exc:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning("Request attempt %d failed: %s. Retrying in %ds...", attempt + 1, exc, wait)
                time.sleep(wait)
            else:
                raise


class InstagramPlatform(BasePlatform):
    def is_configured(self) -> bool:
        return bool(
            self.config.get("access_token")
            and self.config.get("ig_user_id")
        )

    def publish(self, video_path: Path, caption: Caption) -> str:
        if not self.is_configured():
            raise RuntimeError(
                "Instagram access_token and ig_user_id must be set in config."
            )

        _check_token_expiry(self.config.get("token_expiry", ""))

        token = self.config["access_token"]
        user_id = self.config["ig_user_id"]
        caption_text = caption.body[:2200]

        # Step 1a: initiate resumable upload session
        logger.info("Initiating Instagram resumable upload for %s", video_path.name)
        init_resp = _post_with_retry(
            f"{_GRAPH_BASE}/{user_id}/media",
            {
                "upload_type": "resumable",
                "media_type": "REELS",
                "access_token": token,
            },
        )
        upload_url = init_resp.get("uri") or init_resp.get("video_url")
        if not upload_url:
            raise RuntimeError(f"Instagram did not return an upload URL: {init_resp}")

        # Step 1b: upload the binary file
        logger.info("Uploading video binary to Instagram...")
        file_size = video_path.stat().st_size
        with video_path.open("rb") as fh:
            upload_resp = requests.post(
                upload_url,
                headers={
                    "Authorization": f"OAuth {token}",
                    "offset": "0",
                    "file_size": str(file_size),
                },
                data=fh,
                timeout=300,
            )
        _raise_for_error(upload_resp)
        upload_data = upload_resp.json()
        fb_video_id = upload_data.get("h") or upload_data.get("fbupload_video_id")
        if not fb_video_id:
            raise RuntimeError(f"Instagram upload did not return a video ID: {upload_data}")

        # Step 1c: create the media container
        logger.info("Creating Instagram media container...")
        container_resp = _post_with_retry(
            f"{_GRAPH_BASE}/{user_id}/media",
            {
                "media_type": "REELS",
                "fbupload_video_id": fb_video_id,
                "caption": caption_text,
                "share_to_feed": "true",
                "access_token": token,
            },
        )
        container_id = container_resp.get("id")
        if not container_id:
            raise RuntimeError(f"Instagram did not return a container ID: {container_resp}")

        # Step 2: poll until container is ready
        logger.info("Waiting for Instagram media container %s to be ready...", container_id)
        for attempt in range(_POLL_MAX_ATTEMPTS):
            status_resp = requests.get(
                f"{_GRAPH_BASE}/{container_id}",
                params={"fields": "status_code", "access_token": token},
                timeout=30,
            )
            _raise_for_error(status_resp)
            status = status_resp.json().get("status_code")
            if status == "FINISHED":
                break
            if status == "ERROR":
                raise RuntimeError("Instagram media container processing failed.")
            logger.debug("Container status: %s (attempt %d/%d)", status, attempt + 1, _POLL_MAX_ATTEMPTS)
            time.sleep(_POLL_INTERVAL)
        else:
            raise RuntimeError("Instagram media container did not become ready in time.")

        # Step 3: publish
        logger.info("Publishing Instagram Reel...")
        publish_resp = _post_with_retry(
            f"{_GRAPH_BASE}/{user_id}/media_publish",
            {"creation_id": container_id, "access_token": token},
        )
        post_id = publish_resp.get("id")
        url = f"https://www.instagram.com/p/{post_id}/" if post_id else f"post:{post_id}"
        logger.info("Instagram publish complete: %s", url)
        return url
