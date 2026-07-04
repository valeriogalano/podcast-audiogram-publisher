import re
from pathlib import Path

from .platforms.base import Caption


HASHTAG_LINE_PATTERN = re.compile(r"^#[\w-]+(?:\s+#[\w-]+)*$")
HASHTAG_PATTERN = re.compile(r"#([\w-]+)")


def parse_caption_file(path: Path) -> Caption:
    return parse_caption_text(path.read_text(encoding="utf-8"))


def _extract_tags(lines: list[str]) -> list[str]:
    for line in lines:
        candidate = line.strip()
        if HASHTAG_LINE_PATTERN.fullmatch(candidate):
            return HASHTAG_PATTERN.findall(candidate)
    return []


def parse_caption_text(text: str) -> Caption:
    body = text.strip()
    lines = body.splitlines()

    # Split into non-empty paragraphs (separated by blank lines)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]

    title = paragraphs[0] if len(paragraphs) > 0 else ""
    soundbite_title = paragraphs[1] if len(paragraphs) > 1 else ""

    # Hashtags live on their own line; the transcript may follow them.
    tags = _extract_tags(lines)

    # Extract episode URL — look for a URL preceded by a "listen" keyword
    episode_url = None
    url_pattern = re.compile(r"https?://\S+")
    for line in lines:
        if re.search(r"\bascolta\b|\blisten\b|\bscopri\b", line, re.IGNORECASE):
            match = url_pattern.search(line)
            if match:
                episode_url = match.group(0).rstrip(".")
                break

    return Caption(
        title=title,
        soundbite_title=soundbite_title,
        body=body,
        tags=tags,
        episode_url=episode_url,
    )
