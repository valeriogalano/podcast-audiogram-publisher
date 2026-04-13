import argparse
import logging
import logging.handlers
import sys
from pathlib import Path

from .caption_parser import parse_caption_file
from .config import load_config
from .detector import detect_assets, scan_output_dir, soundbite_key
from .platforms.base import Caption
from .platforms.youtube import YouTubePlatform
from .platforms.instagram import InstagramPlatform
from .platforms.tiktok import TikTokPlatform
from .platforms.telegram import TelegramPlatform
from .platforms.mastodon import MastodonPlatform
from .platforms.linkedin import LinkedInPlatform
from .state import PublishState

PLATFORM_REGISTRY = {
    "youtube": YouTubePlatform,
    "instagram": InstagramPlatform,
    "tiktok": TikTokPlatform,
    "telegram": TelegramPlatform,
    "mastodon": MastodonPlatform,
    "linkedin": LinkedInPlatform,
}


def _get_enabled_platforms(config: dict, override: list[str] | None) -> list[str]:
    if override:
        return [p.strip().lower() for p in override]
    return [name for name in PLATFORM_REGISTRY if config.get(name, {}).get("enabled")]


def _publish_assets(assets, platform_names, config, logger, dry_run, state=None, key=None):
    """Publish *assets* to *platform_names*. Returns exit code (0 = all ok)."""
    if assets.caption_file:
        caption = parse_caption_file(assets.caption_file)
    else:
        logger.warning("No caption file found in %s; using empty caption.", assets.folder)
        caption = Caption(title="", soundbite_title="", body="")

    if dry_run:
        logger.info("[DRY-RUN] Would publish:")
        logger.info("  Video:    %s", assets.video_vertical)
        logger.info("  Title:    %s", caption.title)
        logger.info("  Tags:     %s", caption.tags)
        logger.info("  Platforms: %s", platform_names)
        return 0

    exit_code = 0
    for name in platform_names:
        if name not in PLATFORM_REGISTRY:
            logger.warning("Unknown platform '%s', skipping.", name)
            continue
        if state and key and state.is_published(name, key):
            logger.info("[%s] Already published, skipping.", name)
            continue
        platform_config = config.get(name, {})
        platform = PLATFORM_REGISTRY[name](platform_config)
        if not platform.is_configured():
            logger.error("Platform '%s' is not properly configured, skipping.", name)
            exit_code = 1
            continue
        try:
            result = platform.publish(assets.video_vertical, caption)
            logger.info("[%s] Published: %s", name, result)
            if state and key:
                state.mark_published(name, key)
        except Exception as exc:
            logger.error("[%s] Publish failed: %s", name, exc)
            exit_code = 1
    return exit_code


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m publisher",
        description="Publish audiogram videos to social media platforms.",
    )
    parser.add_argument(
        "input",
        metavar="INPUT",
        nargs="?",
        help=(
            "Path to a soundbite folder (e.g. output/ep142/sb1/) or episode folder "
            "(e.g. output/ep142/). If omitted, the most recent unpublished soundbite "
            "from input_dir (config) is picked automatically."
        ),
    )
    parser.add_argument(
        "--state-file",
        default=None,
        metavar="PATH",
        help="JSON file that tracks published soundbites (default: state_file in config).",
    )
    parser.add_argument(
        "--config",
        default="./config.yaml",
        metavar="PATH",
        help="YAML config file (default: ./config.yaml)",
    )
    parser.add_argument(
        "--platforms",
        default=None,
        metavar="LIST",
        help="Comma-separated list of platforms to publish to (overrides config)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        metavar="N",
        help="Maximum number of audiograms to publish in auto mode (default: 1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be published without uploading",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        metavar="LEVEL",
        help="Log level: DEBUG | INFO | WARNING | ERROR (default: INFO)",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        metavar="PATH",
        help="Write logs to this file (rotates daily, keeps 7 days). If omitted, logs go to stderr only.",
    )
    args = parser.parse_args(argv)

    log_format = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    log_level = getattr(logging, args.log_level)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if args.log_file:
        file_handler = logging.handlers.TimedRotatingFileHandler(
            args.log_file,
            when="midnight",
            backupCount=7,
            encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter(log_format))
        handlers.append(file_handler)
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=handlers,
    )
    logger = logging.getLogger("publisher")

    try:
        config = load_config(args.config)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    platform_names = _get_enabled_platforms(
        config, args.platforms.split(",") if args.platforms else None
    )
    if not platform_names:
        logger.error("No platforms enabled. Check your config or use --platforms.")
        sys.exit(1)

    state_path = Path(args.state_file or config.get("state_file", "./published.json"))
    state = PublishState(state_path)
    output_dir = Path(config.get("input_dir", "./output")).resolve()

    # ------------------------------------------------------------------ auto mode
    if args.input is None:
        try:
            all_soundbites = scan_output_dir(output_dir)
        except NotADirectoryError as exc:
            logger.error("%s", exc)
            sys.exit(1)

        if not all_soundbites:
            logger.info("No soundbites found in %s.", output_dir)
            sys.exit(0)

        # Find unpublished soundbites up to the configured limit
        targets = []
        for assets in all_soundbites:
            if len(targets) >= args.limit:
                break
            key = soundbite_key(output_dir, assets)
            pending = [p for p in platform_names if not state.is_published(p, key)]
            if pending:
                targets.append((assets, key, pending))

        if not targets:
            logger.info("All soundbites have been published. Nothing to do.")
            sys.exit(0)

        exit_code = 0
        for assets, key, pending_platforms in targets:
            logger.info("Next unpublished soundbite: %s (pending: %s)", key, pending_platforms)
            exit_code |= _publish_assets(
                assets, pending_platforms, config, logger, args.dry_run, state=state, key=key
            )
        sys.exit(exit_code)

    # ---------------------------------------------------------------- manual mode
    try:
        all_assets = detect_assets(args.input)
    except (FileNotFoundError, NotADirectoryError) as exc:
        logger.error("%s", exc)
        sys.exit(1)

    logger.info("Found %d soundbite(s) to publish.", len(all_assets))

    exit_code = 0
    for assets in all_assets:
        logger.info("--- Processing: %s ---", assets.folder)
        try:
            key = soundbite_key(output_dir, assets)
        except ValueError:
            key = None
            logger.debug("Soundbite %s is outside input_dir; state will not be tracked.", assets.folder)
        exit_code |= _publish_assets(assets, platform_names, config, logger, args.dry_run, state=state, key=key)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
