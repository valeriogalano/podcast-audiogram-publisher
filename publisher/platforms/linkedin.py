import logging
import math
import time
from pathlib import Path

import requests

from .base import BasePlatform, Caption

logger = logging.getLogger(__name__)

_API_BASE = "https://api.linkedin.com"
_CHUNK_SIZE = 4 * 1024 * 1024   # 4 MB per chunk (LinkedIn minimum)
_POLL_INTERVAL = 3               # seconds between video-status polls
_POLL_TIMEOUT = 120              # seconds before giving up


class LinkedInPlatform(BasePlatform):
    def is_configured(self) -> bool:
        return bool(
            self.config.get("access_token")
            and self.config.get("author")
        )

    def publish(self, video_path: Path, caption: Caption) -> str:
        if not self.is_configured():
            raise RuntimeError(
                "LinkedIn access_token and author must be set in config. "
                "Generate a token with scopes w_member_social and r_liteprofile."
            )

        access_token = self.config["access_token"]
        author = self.config["author"]
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "LinkedIn-Version": "202504",
            "X-Restli-Protocol-Version": "2.0.0",
        }

        file_size = video_path.stat().st_size
        num_parts = max(1, math.ceil(file_size / _CHUNK_SIZE))

        # Step 1: Initialize upload
        logger.info("Initializing LinkedIn video upload: %s", video_path.name)
        init_body = {
            "initializeUploadRequest": {
                "owner": author,
                "fileSizeBytes": file_size,
                "uploadCaptions": False,
                "uploadThumbnail": False,
            }
        }
        resp = requests.post(
            f"{_API_BASE}/rest/videos?action=initializeUpload",
            json=init_body,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        init_data = resp.json().get("value", {})
        upload_urls = init_data.get("uploadInstructions", [])
        video_urn = init_data.get("video")
        if not video_urn or not upload_urls:
            raise RuntimeError(f"LinkedIn initializeUpload returned unexpected data: {init_data}")

        # Step 2: Upload chunks
        etags = []
        with video_path.open("rb") as fh:
            for instruction in upload_urls:
                upload_url = instruction["uploadUrl"]
                first_byte = instruction["firstByte"]
                last_byte = instruction["lastByte"]
                chunk_size = last_byte - first_byte + 1
                chunk = fh.read(chunk_size)
                logger.debug(
                    "Uploading chunk bytes %d-%d (%d bytes)...",
                    first_byte, last_byte, len(chunk),
                )
                put_resp = requests.put(
                    upload_url,
                    data=chunk,
                    headers={"Content-Type": "application/octet-stream"},
                    timeout=120,
                )
                put_resp.raise_for_status()
                etags.append(put_resp.headers.get("ETag", ""))

        # Step 3: Finalize upload
        logger.info("Finalizing LinkedIn video upload...")
        finalize_body = {
            "finalizeUploadRequest": {
                "video": video_urn,
                "uploadToken": init_data.get("uploadToken", ""),
                "uploadedPartIds": etags,
            }
        }
        fin_resp = requests.post(
            f"{_API_BASE}/rest/videos?action=finalizeUpload",
            json=finalize_body,
            headers=headers,
            timeout=30,
        )
        fin_resp.raise_for_status()

        # Step 4: Poll until video is available
        video_id = video_urn.split(":")[-1]
        deadline = time.monotonic() + _POLL_TIMEOUT
        while True:
            if time.monotonic() > deadline:
                raise RuntimeError("LinkedIn video processing timed out after %ds" % _POLL_TIMEOUT)
            status_resp = requests.get(
                f"{_API_BASE}/rest/videos/{video_id}",
                headers=headers,
                timeout=30,
            )
            status_resp.raise_for_status()
            status = status_resp.json().get("status")
            logger.debug("LinkedIn video status: %s", status)
            if status == "AVAILABLE":
                break
            if status == "PROCESSING_FAILED":
                raise RuntimeError("LinkedIn video processing failed.")
            time.sleep(_POLL_INTERVAL)

        # Step 5: Create the post
        logger.info("Creating LinkedIn post...")
        post_text = caption.body
        if caption.tags:
            tags_str = " ".join(f"#{t.lstrip('#')}" for t in caption.tags)
            post_text = f"{post_text}\n\n{tags_str}"

        post_body = {
            "author": author,
            "commentary": post_text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "content": {
                "media": {
                    "title": caption.title or caption.soundbite_title,
                    "id": video_urn,
                }
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        post_resp = requests.post(
            f"{_API_BASE}/rest/posts",
            json=post_body,
            headers=headers,
            timeout=30,
        )
        post_resp.raise_for_status()
        post_id = post_resp.headers.get("x-restli-id", post_resp.headers.get("X-RestLi-Id", "unknown"))
        logger.info("LinkedIn post published: %s", post_id)
        return f"linkedin:post:{post_id}"
