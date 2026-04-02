import logging
import math
import time
from pathlib import Path

import requests

from .base import BasePlatform, Caption

logger = logging.getLogger(__name__)

_API_BASE = "https://open.tiktokapis.com/v2"
_CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB
_POLL_INTERVAL = 5
_POLL_MAX_ATTEMPTS = 24


def _refresh_token(config: dict) -> str:
    resp = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        data={
            "client_key": config["client_key"],
            "client_secret": config["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": config["refresh_token"],
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"TikTok token refresh failed: {data}")
    return data["access_token"]


def _raise_for_error(data: dict) -> None:
    error = data.get("error")
    if error and error.get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok API error {error.get('code')}: {error.get('message')}")


def _post_json_with_retry(url: str, token: str, body: dict, max_retries: int = 3) -> dict:
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
                json=body,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            _raise_for_error(data)
            return data
        except RuntimeError:
            raise
        except Exception as exc:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning("TikTok request attempt %d failed: %s. Retrying in %ds...", attempt + 1, exc, wait)
                time.sleep(wait)
            else:
                raise


class TikTokPlatform(BasePlatform):
    def is_configured(self) -> bool:
        return bool(
            self.config.get("client_key")
            and self.config.get("client_secret")
            and self.config.get("access_token")
        )

    def publish(self, video_path: Path, caption: Caption) -> str:
        if not self.is_configured():
            raise RuntimeError(
                "TikTok client_key, client_secret, and access_token must be set in config."
            )

        token = self.config["access_token"]
        file_size = video_path.stat().st_size
        chunk_count = max(1, math.ceil(file_size / _CHUNK_SIZE))
        chunk_size = math.ceil(file_size / chunk_count)
        title = caption.title[:150]

        # Step 1: initialize upload
        logger.info("Initializing TikTok upload for %s", video_path.name)
        init_body = {
            "post_info": {
                "title": title,
                "privacy_level": self.config.get("privacy_level", "SELF_ONLY"),
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": chunk_size,
                "total_chunk_count": chunk_count,
            },
        }

        try:
            init_data = _post_json_with_retry(
                f"{_API_BASE}/post/publish/video/init/", token, init_body
            )
        except RuntimeError as exc:
            if "scope" in str(exc).lower() or "permission" in str(exc).lower():
                raise RuntimeError(
                    "TikTok video.publish scope is not approved for this account. "
                    "Apply at https://developers.tiktok.com/"
                ) from exc
            raise

        publish_id = init_data["data"]["publish_id"]
        upload_url = init_data["data"]["upload_url"]

        # Step 2: upload chunks
        logger.info("Uploading %d chunk(s) to TikTok...", chunk_count)
        with video_path.open("rb") as fh:
            for chunk_idx in range(chunk_count):
                chunk = fh.read(chunk_size)
                start = chunk_idx * chunk_size
                end = start + len(chunk) - 1
                for attempt in range(3):
                    try:
                        resp = requests.put(
                            upload_url,
                            headers={
                                "Content-Range": f"bytes {start}-{end}/{file_size}",
                                "Content-Type": "video/mp4",
                            },
                            data=chunk,
                            timeout=300,
                        )
                        resp.raise_for_status()
                        break
                    except Exception as exc:
                        if attempt < 2:
                            time.sleep(2 ** attempt)
                        else:
                            raise
                logger.debug("Uploaded chunk %d/%d", chunk_idx + 1, chunk_count)

        # Step 3: poll for publish status
        logger.info("Waiting for TikTok publish status (id: %s)...", publish_id)
        for attempt in range(_POLL_MAX_ATTEMPTS):
            status_data = _post_json_with_retry(
                f"{_API_BASE}/post/publish/status/fetch/",
                token,
                {"publish_id": publish_id},
            )
            status = status_data.get("data", {}).get("status")
            if status == "PUBLISH_COMPLETE":
                break
            if status in ("FAILED", "SPAM_RISK_TOO_MANY_POSTS", "SPAM_RISK_USER_BANNED_FROM_POSTING"):
                raise RuntimeError(f"TikTok publish failed with status: {status}")
            logger.debug("TikTok status: %s (attempt %d/%d)", status, attempt + 1, _POLL_MAX_ATTEMPTS)
            time.sleep(_POLL_INTERVAL)
        else:
            raise RuntimeError("TikTok publish did not complete in time.")

        result = f"tiktok:publish_id:{publish_id}"
        logger.info("TikTok publish complete: %s", result)
        return result
