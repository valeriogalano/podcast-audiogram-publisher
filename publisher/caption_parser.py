import re
from pathlib import Path

from .platforms.base import Caption


def parse_caption_file(path: Path) -> Caption:
    return parse_caption_text(path.read_text(encoding="utf-8"))


def parse_caption_text(text: str) -> Caption:
    body = text.strip()

    # Split into non-empty paragraphs (separated by blank lines)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]

    title = paragraphs[0] if len(paragraphs) > 0 else ""
    soundbite_title = paragraphs[1] if len(paragraphs) > 1 else ""

    # Extract hashtags from the last line of the full text
    last_line = body.splitlines()[-1].strip() if body else ""
    tags = re.findall(r"#([\w-]+)", last_line)

    # Extract episode URL — look for a URL preceded by a "listen" keyword
    episode_url = None
    url_pattern = re.compile(r"https?://\S+")
    for line in body.splitlines():
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
