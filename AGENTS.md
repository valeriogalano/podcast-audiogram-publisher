# AGENTS.md — Audiogram Publisher

> Vibe coding project: this file is committed to the repository and is part of the project.
> `CLAUDE.md` points here — edit only this file, so there is never a second copy to keep in sync.

## Purpose

Python CLI tool that publishes audiograms to social platforms. It reads the output directory
of the companion project
[podcast-audiogram-generator](https://github.com/valeriogalano/podcast-audiogram-generator),
auto-detects the `.mp4` and `.txt` files for each soundbite, and publishes to the configured
platforms.

## Language

**English** — commit messages, PR titles and bodies, code comments, docstrings and
documentation, matching the existing README and history. Conversation with the maintainer
stays in Italian.

This matters because the sibling repositories differ: `podcast-audiogram-generator` is also
English, while the orchestrator `podcast-audiogram-automation` is in Italian. Check the target
repository before writing a commit — do not carry a convention across from another repo.

## Stack

- **Language**: Python 3.10+
- **Dependencies**: `requirements.txt`
- **Tests**: pytest
- **Docker**: none
- **Virtual environment**: `.venv/`

## Directory structure

```
publisher/          # Main package
  platforms/        # One module per platform (youtube, instagram, tiktok, telegram,
                    #   mastodon, linkedin). Instagram uses the Instagram Login API
                    #   (graph.instagram.com), NOT the Facebook Login flavour: no
                    #   Facebook Page needed and the token refreshes from code.
  cli.py            # CLI entry point (argparse)
  config.py         # config.yaml loading
  detector.py       # Soundbite/episode auto-detection
  state.py          # published.json tracking
tests/              # pytest unit tests
config.yaml         # Runtime config (gitignored — use config.yaml.example)
secrets/            # Credentials (gitignored)
```

## Commands

```bash
# Activate the venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the tests
.venv/bin/pytest tests/ -v

# Run the publisher
python -m publisher
python -m publisher --dry-run
python -m publisher --limit 3

# Refresh the long-lived Instagram token (prints JSON on stdout, publishes nothing)
python -m publisher --refresh-instagram-token
```

## CI lives in another repository

There is no `.github/workflows/` here. The GitHub Actions workflows for this project are
maintained in **`podcast-audiogram-automation`** (the repo formerly named
`markxvi-workflows`). When investigating a publishing failure or looking for run logs, go there — searching this repository for a workflow file will turn up nothing and
waste a pass.

## Conventions

- One class per platform in `publisher/platforms/`, all inheriting from `base.py`
- Configuration centralised in `config.yaml` (never hardcoded)
- Credentials always in `secrets/` or `config.yaml` (both gitignored)
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`

## Sensitive files

The following are gitignored and **must never be committed**:
- `config.yaml` (credentials and tokens)
- `secrets/` (OAuth tokens, session files)
- `*.session` (Telethon sessions)
