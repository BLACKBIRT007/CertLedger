from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Optional
from .paths import db_path


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(db_path(), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON;")
    con.execute("PRAGMA journal_mode = WAL;")
    con.execute("PRAGMA busy_timeout = 30000;")
    return con



def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def init_db() -> None:
    con = connect()
    cur = con.cursor()

    # Core tables (desired schema)
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS people (
        person_id TEXT PRIMARY KEY,
        gov_id_number TEXT NOT NULL,
        date_of_birth TEXT NOT NULL,
        official_name TEXT NOT NULL,
        call_name TEXT,
        nickname TEXT,
        email TEXT,
        nationality TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS certificates (
        cert_number TEXT PRIMARY KEY,
        cert_type TEXT NOT NULL,
        issued_at TEXT NOT NULL,
        receiver_person_id TEXT NOT NULL,
        giver_person_id TEXT NOT NULL,
        receiver_name_used TEXT NOT NULL,
        giver_name_used TEXT NOT NULL,
        valid_until TEXT NOT NULL,
        status TEXT NOT NULL,
        sign_code TEXT,
        sign_requested_at TEXT,
        signed_at TEXT,
        pdf_relpath TEXT,
        FOREIGN KEY(receiver_person_id) REFERENCES people(person_id),
        FOREIGN KEY(giver_person_id) REFERENCES people(person_id)
    );

    -- Evidence must be able to store unmatched emails too (cert_number nullable, no FK)
    CREATE TABLE IF NOT EXISTS email_evidence (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cert_number TEXT,
        received_at TEXT NOT NULL,
        from_email TEXT NOT NULL,
        subject TEXT NOT NULL,
        body_hash TEXT NOT NULL,
        message_id TEXT,
        matched INTEGER NOT NULL,
        notes TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        actor TEXT NOT NULL,
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        before_json TEXT,
        after_json TEXT,
        result TEXT NOT NULL,
        message TEXT NOT NULL
    );
    """)
    con.commit()

    # Self-heal older DBs: add nationality if missing
    cols = [r[1] for r in con.execute("PRAGMA table_info(people)").fetchall()]
    if "nationality" not in cols:
        con.execute("ALTER TABLE people ADD COLUMN nationality TEXT;")
        con.commit()

    # Self-heal older email_evidence schemas that had FK constraints
    fk_list = con.execute("PRAGMA foreign_key_list(email_evidence)").fetchall()
    if fk_list:
        _migrate_email_evidence_remove_fk(con)

    con.close()


def _migrate_email_evidence_remove_fk(con: sqlite3.Connection) -> None:
    # Rename old table
    con.execute("ALTER TABLE email_evidence RENAME TO email_evidence_old;")

    # Create new table without FK and with nullable cert_number
    con.execute("""
    CREATE TABLE email_evidence (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cert_number TEXT,
        received_at TEXT NOT NULL,
        from_email TEXT NOT NULL,
        subject TEXT NOT NULL,
        body_hash TEXT NOT NULL,
        message_id TEXT,
        matched INTEGER NOT NULL,
        notes TEXT NOT NULL
    );
    """)

    # Copy what we can. Older schema may have had cert_number + subject. Keep both if present.
    old_cols = [r[1] for r in con.execute("PRAGMA table_info(email_evidence_old)").fetchall()]
    has_subject = "subject" in old_cols

    if has_subject:
        con.execute("""
        INSERT INTO email_evidence(id, cert_number, received_at, from_email, subject, body_hash, message_id, matched, notes)
        SELECT id, cert_number, received_at, from_email, subject, body_hash, message_id, matched, notes
        FROM email_evidence_old;
        """)
    else:
        # If old table didn't have subject, use cert_number as subject fallback
        con.execute("""
        INSERT INTO email_evidence(id, cert_number, received_at, from_email, subject, body_hash, message_id, matched, notes)
        SELECT id, cert_number, received_at, from_email, cert_number, body_hash, message_id, matched, notes
        FROM email_evidence_old;
        """)

    con.execute("DROP TABLE email_evidence_old;")
    con.commit()


def log_audit(
    action: str,
    entity_type: str,
    entity_id: str,
    result: str,
    message: str,
    actor: str = "system",
    before_json: Optional[str] = None,
    after_json: Optional[str] = None,
) -> None:
    con = connect()
    con.execute(
        "INSERT INTO audit_log(ts, actor, action, entity_type, entity_id, before_json, after_json, result, message) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (now_iso(), actor, action, entity_type, entity_id, before_json, after_json, result, message),
    )
    con.commit()
    con.close()


def next_person_id() -> str:
    con = connect()
    row = con.execute("SELECT person_id FROM people ORDER BY person_id DESC LIMIT 1").fetchone()
    con.close()
    if not row:
        return "P-000001"
    n = int(row["person_id"].split("-")[1]) + 1
    return f"P-{n:06d}"


def next_cert_number(year: int) -> str:
    prefix = f"C-{year}-"
    con = connect()
    row = con.execute(
        "SELECT cert_number FROM certificates WHERE cert_number LIKE ? ORDER BY cert_number DESC LIMIT 1",
        (prefix + "%",),
    ).fetchone()
    con.close()
    if not row:
        return f"{prefix}000001"
    n = int(row["cert_number"].split("-")[2]) + 1
    return f"{prefix}{n:06d}"


def upsert_person(person: dict[str, Any]) -> None:
    con = connect()
    con.execute(
        """
        INSERT INTO people(person_id, gov_id_number, date_of_birth, official_name, call_name, nickname, email, nationality, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(person_id) DO UPDATE SET
            gov_id_number=excluded.gov_id_number,
            date_of_birth=excluded.date_of_birth,
            official_name=excluded.official_name,
            call_name=excluded.call_name,
            nickname=excluded.nickname,
            email=excluded.email,
            nationality=excluded.nationality,
            updated_at=excluded.updated_at
        """,
        (
            person["person_id"],
            person["gov_id_number"],
            person["date_of_birth"],
            person["official_name"],
            person.get("call_name"),
            person.get("nickname"),
            person.get("email"),
            person.get("nationality"),
            person["created_at"],
            person["updated_at"],
        ),
    )
    con.commit()
    con.close()


def create_certificate(cert: dict[str, Any]) -> None:
    con = connect()
    con.execute(
        """
        INSERT INTO certificates(cert_number, cert_type, issued_at, receiver_person_id, giver_person_id,
                                 receiver_name_used, giver_name_used, valid_until, status,
                                 sign_code, sign_requested_at, signed_at, pdf_relpath)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cert["cert_number"],
            cert["cert_type"],
            cert["issued_at"],
            cert["receiver_person_id"],
            cert["giver_person_id"],
            cert["receiver_name_used"],
            cert["giver_name_used"],
            cert["valid_until"],
            cert["status"],
            cert.get("sign_code"),
            cert.get("sign_requested_at"),
            cert.get("signed_at"),
            cert.get("pdf_relpath"),
        ),
    )
    con.commit()
    con.close()
