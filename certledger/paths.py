from __future__ import annotations
from pathlib import Path
import sys

def app_root() -> Path:
    # When frozen with PyInstaller, sys.executable points to the exe location.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]

def ensure_dirs() -> dict[str, Path]:
    root = app_root()
    data = root / "data"
    pdfs = data / "pdfs"
    logs = root / "logs"
    data.mkdir(exist_ok=True)
    pdfs.mkdir(exist_ok=True)
    logs.mkdir(exist_ok=True)
    return {"root": root, "data": data, "pdfs": pdfs, "logs": logs}

def db_path() -> Path:
    return ensure_dirs()["data"] / "certs.sqlite3"

def settings_path() -> Path:
    return app_root() / "settings.json"
