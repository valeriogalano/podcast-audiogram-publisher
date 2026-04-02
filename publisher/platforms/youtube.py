import logging
import time
from pathlib import Path

from .base import BasePlatform, Caption

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def _get_credentials(client_secrets: str, token_path: str):
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None
    token_file = Path(token_path)
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), _SCOPES)
        # If the stored token doesn't cover all required scopes, force re-auth
        if creds and not all(s in (creds.scopes or []) for s in _SCOPES):
            logger.info(
                "Token scopes have changed. Deleting %s and re-authorizing...", token_file
            )
            token_file.unlink()
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets, _SCOPES)
            creds = flow.run_local_server(port=0)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json())

    return creds


def _find_episode_video_url(youtube, episode_title: str) -> str | None:
    """Search the authenticated channel for a video whose title contains
    the episode title. Returns the full YouTube URL if found, else None."""
    try:
        response = youtube.search().list(
            part="snippet",
            q=episode_title,
            type="video",
            forMine=True,
            maxResults=5,
        ).execute()
        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            video_title = snippet.get("title", "")
            if episode_title.lower() in video_title.lower():
                video_id = item["id"]["videoId"]
                return f"https://www.youtube.com/watch?v={video_id}"
        logger.debug("No matching episode video found for query: %s", episode_title)
    except Exception as exc:
        logger.warning("Episode video search failed: %s", exc)
    return None


def _upload_with_retry(youtube, request, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.debug("Upload progress: %d%%", int(status.progress() * 100))
            return response
        except Exception as exc:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning("Upload attempt %d failed: %s. Retrying in %ds...", attempt + 1, exc, wait)
                time.sleep(wait)
            else:
                raise


class YouTubePlatform(BasePlatform):
    def is_configured(self) -> bool:
        return bool(
            self.config.get("client_secrets")
            and Path(self.config["client_secrets"]).exists()
        )

    def publish(self, video_path: Path, caption: Caption) -> str:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        if not self.is_configured():
            raise RuntimeError(
                f"YouTube client_secrets file not found: {self.config.get('client_secrets')}. "
                "Download it from Google Cloud Console."
            )

        creds = _get_credentials(
            self.config["client_secrets"],
            self.config["token"],
        )
        youtube = build("youtube", "v3", credentials=creds)

        title = (caption.soundbite_title or caption.title)[:100]
        tags = list(caption.tags) + list(self.config.get("default_tags", []))

        description = caption.body
        if caption.title:
            episode_url = _find_episode_video_url(youtube, caption.title)
            if episode_url:
                logger.info("Found episode video: %s", episode_url)
                description = f"Guarda l'episodio completo: {episode_url}\n\n{description}"

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": str(self.config.get("category_id", 22)),
            },
            "status": {
                "privacyStatus": self.config.get("privacy", "private"),
            },
        }

        media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        logger.info("Uploading to YouTube: %s", video_path.name)
        response = _upload_with_retry(youtube, request)
        video_id = response["id"]
        url = f"https://www.youtube.com/shorts/{video_id}"
        logger.info("YouTube upload complete: %s", url)
        return url
