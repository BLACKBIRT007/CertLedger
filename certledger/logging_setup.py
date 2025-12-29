from __future__ import annotations
import logging
from datetime import datetime
from .paths import ensure_dirs

def setup_logging() -> logging.Logger:
    dirs = ensure_dirs()
    logs_dir = dirs["logs"]

    logger = logging.getLogger("certledger")
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers if called twice.
    if logger.handlers:
        return logger

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    # Rolling-ish main log
    file_handler = logging.FileHandler(logs_dir / "app.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    # Session log
    session_name = datetime.now().strftime("%Y-%m-%d_session.log")
    session_handler = logging.FileHandler(logs_dir / session_name, encoding="utf-8")
    session_handler.setFormatter(fmt)
    logger.addHandler(session_handler)

    # Console (VS Code terminal)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    return logger
