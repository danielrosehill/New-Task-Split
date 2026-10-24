"""Paths and config shared by the hook and ntsctl. Standard library only."""
import json
import os
from pathlib import Path

HOME = Path(os.environ.get("NEW_TASK_SPLIT_HOME")
            or Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "new-task-split")
STATE = Path(os.environ.get("NEW_TASK_SPLIT_STATE") or Path.home() / ".cache" / "new-task-split")
VENV = HOME / "venv"
MODEL_DIR = HOME / "model"
CONFIG = HOME / "config.json"

DEFAULT_REPO = "danielrosehill/Agent-Task-Break-Detector-ModernBERT"
DEFAULTS = {"enabled": False, "mode": "split", "model_repo": DEFAULT_REPO, "model_revision": None, "threshold": None}


def load() -> dict:
    try:
        return {**DEFAULTS, **json.loads(CONFIG.read_text())}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(cfg: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2) + "\n")
    tmp.replace(CONFIG)
