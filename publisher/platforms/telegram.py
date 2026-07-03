import asyncio
import json
import logging
import subprocess
from pathlib import Path

from .base import BasePlatform, Caption

logger = logging.getLogger(__name__)

# Telegram Stories only accept videos up to 60 seconds. Longer videos are
# posted as a normal video message to the peer instead of a story.
STORY_MAX_DURATION = 60
# Telegram media caption limit (non-premium). Longer captions are truncated.
MESSAGE_CAPTION_LIMIT = 1024

_PRIVACY_MAP_LAZY: dict | None = None


def _probe_duration(video_path: Path) -> float:
    """Return the video duration in seconds via ffprobe (0.0 if unknown)."""
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json", str(video_path),
            ],
            capture_output=True, text=True, check=True,
        ).stdout
        return float(json.loads(out).get("format", {}).get("duration", 0.0))
    except (subprocess.CalledProcessError, ValueError, KeyError, FileNotFoundError) as exc:
        logger.warning("Could not probe video duration (%s); assuming it fits a story.", exc)
        return 0.0


def _use_story(duration: float, max_duration: float = STORY_MAX_DURATION) -> bool:
    """Stories are used only for videos within the duration limit.

    A duration of 0.0 means "unknown" (ffprobe failed): fall back to a story to
    preserve the previous default behavior.
    """
    return duration <= max_duration


def _truncate_caption(text: str, limit: int = MESSAGE_CAPTION_LIMIT) -> str:
    """Truncate a caption to fit Telegram's media caption limit.

    Cuts on a word boundary and appends an ellipsis, keeping the result within
    ``limit`` characters. Returns the text unchanged when it already fits.
    """
    if len(text) <= limit:
        return text
    truncated = text[:limit - 1].rstrip()
    space = truncated.rfind(" ")
    if space > 0:
        truncated = truncated[:space].rstrip()
    return truncated + "…"


def _privacy_map() -> dict:
    global _PRIVACY_MAP_LAZY
    if _PRIVACY_MAP_LAZY is None:
        from telethon.tl.types import (
            InputPrivacyValueAllowAll,
            InputPrivacyValueAllowContacts,
            InputPrivacyValueAllowCloseFriends,
        )
        _PRIVACY_MAP_LAZY = {
            "all": InputPrivacyValueAllowAll,
            "contacts": InputPrivacyValueAllowContacts,
            "close_friends": InputPrivacyValueAllowCloseFriends,
        }
    return _PRIVACY_MAP_LAZY


class TelegramPlatform(BasePlatform):
    def is_configured(self) -> bool:
        return bool(
            self.config.get("api_id")
            and self.config.get("api_hash")
        )

    def publish(self, video_path: Path, caption: Caption) -> str:
        if not self.is_configured():
            raise RuntimeError(
                "Telegram api_id and api_hash must be set in config. "
                "Get them at https://my.telegram.org/apps"
            )
        return asyncio.run(self._publish_async(video_path, caption))

    async def _publish_async(self, video_path: Path, caption: Caption) -> str:
        from telethon import TelegramClient
        from telethon.tl.functions.stories import SendStoryRequest
        from telethon.tl.types import DocumentAttributeVideo, InputMediaUploadedDocument

        api_id = int(self.config["api_id"])
        api_hash = self.config["api_hash"]
        session_path = self.config.get("session", "./secrets/telegram.session")
        peers = self.config.get("peers") or [self.config.get("peer", "me")]
        period = int(self.config.get("period", 86400))
        privacy_key = self.config.get("privacy", "all")
        privacy_map = _privacy_map()
        privacy_class = privacy_map.get(privacy_key, privacy_map["all"])
        caption_text = caption.body
        story_max = int(self.config.get("story_max_duration", STORY_MAX_DURATION))
        caption_limit = int(self.config.get("message_caption_limit", MESSAGE_CAPTION_LIMIT))

        duration = _probe_duration(video_path)

        results = []
        logger.info("Connecting to Telegram...")
        async with TelegramClient(session_path, api_id, api_hash) as client:
            if _use_story(duration, story_max):
                logger.info("Uploading video to Telegram: %s", video_path.name)
                uploaded = await client.upload_file(str(video_path))
                media = InputMediaUploadedDocument(
                    file=uploaded,
                    mime_type="video/mp4",
                    attributes=[DocumentAttributeVideo(
                        duration=int(round(duration)), w=0, h=0, supports_streaming=True,
                    )],
                )
                for peer in peers:
                    logger.info("Sending Telegram Story to peer '%s'...", peer)
                    await client(
                        SendStoryRequest(
                            peer=peer,
                            media=media,
                            privacy_rules=[privacy_class()],
                            caption=caption_text,
                            period=period,
                        )
                    )
                    results.append(f"telegram:story:{peer}")
                    logger.info("Telegram Story posted to '%s'.", peer)
            else:
                # Too long for a story (>60s): post a normal video message.
                logger.info(
                    "Video is %.1fs (> %ds): posting a normal video message instead of a story.",
                    duration, story_max,
                )
                media_caption = _truncate_caption(caption_text, caption_limit)
                for peer in peers:
                    logger.info("Sending Telegram video message to peer '%s'...", peer)
                    await client.send_file(
                        peer, str(video_path),
                        caption=media_caption,
                        supports_streaming=True,
                    )
                    results.append(f"telegram:message:{peer}")
                    logger.info("Telegram video message posted to '%s'.", peer)

        return ", ".join(results)
