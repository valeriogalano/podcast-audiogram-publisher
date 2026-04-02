from pathlib import Path

import yaml

DEFAULTS = {
    "input_dir": "./output",
    "state_file": "./published.json",
    "youtube": {
        "enabled": False,
        "client_secrets": "./secrets/youtube_client_secrets.json",
        "token": "./secrets/youtube_token.json",
        "privacy": "private",
        "category_id": 22,
        "default_tags": ["podcast", "shorts"],
    },
    "instagram": {
        "enabled": False,
        "access_token": "",
        "ig_user_id": "",
        "token_expiry": "",
    },
    "tiktok": {
        "enabled": False,
        "client_key": "",
        "client_secret": "",
        "access_token": "",
        "refresh_token": "",
        "privacy_level": "SELF_ONLY",
    },
    "telegram": {
        "enabled": False,
        "api_id": 0,
        "api_hash": "",
        "session": "./secrets/telegram.session",
        "peer": "me",
        "period": 86400,
        "privacy": "all",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str | Path = "./config.yaml") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}. "
            f"Copy config.yaml.example to config.yaml and fill in your values."
        )
    with config_path.open() as f:
        user_config = yaml.safe_load(f) or {}
    return _deep_merge(DEFAULTS, user_config)
