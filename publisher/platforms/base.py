from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Caption:
    title: str
    soundbite_title: str
    body: str
    tags: list[str] = field(default_factory=list)
    episode_url: str | None = None


class BasePlatform(ABC):
    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def publish(self, video_path: Path, caption: Caption) -> str:
        """Upload and publish the video. Returns a URL or ID for the published post."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if all required config keys are present and valid."""
