import logging
import time
from pathlib import Path

from .base import BasePlatform, Caption

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 2   # seconds between media-processing polls
_POLL_TIMEOUT = 60   # seconds before giving up


class MastodonPlatform(BasePlatform):
    def is_configured(self) -> bool:
        return bool(
            self.config.get("instance_url")
            and self.config.get("access_token")
        )

    def publish(self, video_path: Path, caption: Caption) -> str:
        if not self.is_configured():
            raise RuntimeError(
                "Mastodon instance_url and access_token must be set in config. "
                "Generate a token at <your-instance>/settings/applications"
            )

        from mastodon import Mastodon

        instance_url = self.config["instance_url"]
        access_token = self.config["access_token"]
        visibility = self.config.get("visibility", "public")

        mastodon = Mastodon(access_token=access_token, api_base_url=instance_url)

        logger.info("Uploading video to Mastodon: %s", video_path.name)
        media = mastodon.media_post(
            str(video_path),
            mime_type="video/mp4",
            description=caption.body,
        )

        # Wait for server-side processing
        deadline = time.monotonic() + _POLL_TIMEOUT
        while media.get("url") is None:
            if time.monotonic() > deadline:
                raise RuntimeError("Mastodon media processing timed out after %ds" % _POLL_TIMEOUT)
            time.sleep(_POLL_INTERVAL)
            media = mastodon.media(media["id"])
            logger.debug("Mastodon media status: %s", media.get("url"))

        status_text = caption.body
        if caption.tags:
            tags_str = " ".join(f"#{t.lstrip('#')}" for t in caption.tags)
            status_text = f"{status_text}\n\n{tags_str}"

        logger.info("Posting Mastodon status (visibility=%s)...", visibility)
        post = mastodon.status_post(
            status=status_text,
            media_ids=[media],
            visibility=visibility,
        )

        url = post.get("url", post.get("id", "unknown"))
        logger.info("Mastodon post published: %s", url)
        return str(url)
