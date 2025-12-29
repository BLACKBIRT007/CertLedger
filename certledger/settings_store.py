from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

from .paths import settings_path


@dataclass
class Settings:
    # Email account (username)
    system_email: str = ""

    # Gmail defaults
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_folder: str = "INBOX"

    # Last processed IMAP UID
    last_imap_uid: int = 0

    # Security rules
    require_from_match: bool = True


def load_settings() -> Settings:
    path: Path = settings_path()
    if not path.exists():
        s = Settings()
        save_settings(s)
        return s

    data = json.loads(path.read_text(encoding="utf-8"))
    # Ignore unknown fields if you previously had different settings.json keys
    valid_keys = set(Settings.__dataclass_fields__.keys())
    filtered = {k: v for k, v in data.items() if k in valid_keys}
    return Settings(**filtered)


def save_settings(s: Settings) -> None:
    path: Path = settings_path()
    path.write_text(json.dumps(asdict(s), indent=2), encoding="utf-8")
