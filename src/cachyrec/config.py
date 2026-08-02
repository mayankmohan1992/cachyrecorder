"""Configuration for CachyRecorder."""
import contextlib
import json
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("CACHYREC_HOME", Path.home() / ".local/share/cachyrecorder"))
FRAME_DIR = DATA_DIR / "frames"
DB_PATH = DATA_DIR / "index.db"
CONFIG_PATH = DATA_DIR / "config.json"
STATE_PATH = DATA_DIR / "state.json"

DEFAULTS = {
    "interval_sec": 5,
    "similarity_skip": 4,        # dhash hamming distance below this -> skip frame as duplicate
    "webp_quality": 55,
    "max_width": 1600,           # downscale stored frames
    "ocr_lang": "eng",
    "retention_days": 30,
    "pause_on_idle_sec": 180,    # back off when screen is unchanged this long (0=off)
    "exclude_title_keywords": ["Bitwarden", "KeePass", "Private Browsing", "1Password"],
    "paused": False,
}


def load():
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        with contextlib.suppress(Exception):
            cfg.update(json.loads(CONFIG_PATH.read_text()))
    return cfg


def save(cfg):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2))
    tmp.replace(CONFIG_PATH)


def set_paused(value: bool):
    cfg = load()
    cfg["paused"] = bool(value)
    save(cfg)
    return cfg
