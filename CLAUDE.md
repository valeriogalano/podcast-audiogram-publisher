# CLAUDE.md — Audiogram Publisher

> Vibe coding project: questo file è committato nel repo e fa parte del progetto.

## Scopo

CLI tool Python che pubblica videogrammi (audiogram) su piattaforme social.
Legge la cartella di output del progetto companion
[pensieriincodice-audiogram-generator](https://github.com/vgalano/podcast-audiogram-generator),
auto-rileva i file `.mp4` e `.txt` per ogni soundbite, e pubblica sulle
piattaforme configurate.

## Stack

- **Linguaggio**: Python 3.10+
- **Dipendenze**: `requirements.txt`
- **Test**: pytest
- **Docker**: nessuno
- **Ambienti virtuali**: `.venv/`

## Struttura directory

```
publisher/          # Package principale
  platforms/        # Un modulo per piattaforma (youtube, instagram, tiktok, telegram)
  cli.py            # Entry point CLI (argparse)
  config.py         # Caricamento config.yaml
  detector.py       # Auto-rilevamento soundbite/episodi
  state.py          # Tracking published.json
tests/              # Test pytest (unit)
config.yaml         # Config runtime (gitignored — usa config.yaml.example)
secrets/            # Credenziali (gitignored)
```

## Comandi

```bash
# Attiva venv
source .venv/bin/activate

# Installa dipendenze
pip install -r requirements.txt

# Esegui i test
.venv/bin/pytest tests/ -v

# Esegui il publisher
python -m publisher
python -m publisher --dry-run
python -m publisher --limit 3
```

## Convenzioni

- Una classe per piattaforma in `publisher/platforms/`, tutte ereditano da `base.py`
- Configurazione centralizzata in `config.yaml` (mai hardcoded)
- Credenziali sempre in `secrets/` o `config.yaml` (entrambi gitignored)
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`

## File sensibili

I seguenti file sono gitignored e **non vanno mai committati**:
- `config.yaml` (credenziali e token)
- `secrets/` (token OAuth, session files)
- `*.session` (sessioni Telethon)