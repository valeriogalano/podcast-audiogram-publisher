import asyncio
import logging
from pathlib import Path

from .base import BasePlatform, Caption

logger = logging.getLogger(__name__)


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
        from telethon.tl.types import (
            DocumentAttributeVideo,
            InputMediaUploadedDocument,
            InputPrivacyValueAllowAll,
            InputPrivacyValueAllowContacts,
            InputPrivacyValueAllowCloseFriends,
        )

        _PRIVACY_MAP = {
            "all": InputPrivacyValueAllowAll,
            "contacts": InputPrivacyValueAllowContacts,
            "close_friends": InputPrivacyValueAllowCloseFriends,
        }

        api_id = int(self.config["api_id"])
        api_hash = self.config["api_hash"]
        session_path = self.config.get("session", "./secrets/telegram.session")
        peers = self.config.get("peers") or [self.config.get("peer", "me")]
        period = int(self.config.get("period", 86400))
        privacy_key = self.config.get("privacy", "all")
        privacy_class = _PRIVACY_MAP.get(privacy_key, InputPrivacyValueAllowAll)
        caption_text = caption.body

        results = []
        logger.info("Connecting to Telegram...")
        async with TelegramClient(session_path, api_id, api_hash) as client:
            logger.info("Uploading video to Telegram: %s", video_path.name)
            uploaded = await client.upload_file(str(video_path))
            media = InputMediaUploadedDocument(
                file=uploaded,
                mime_type="video/mp4",
                attributes=[DocumentAttributeVideo(duration=0, w=0, h=0, supports_streaming=True)],
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

        return ", ".join(results)
