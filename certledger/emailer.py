from __future__ import annotations

import hashlib
import imaplib
import smtplib
import email
from email.message import EmailMessage
from email.header import decode_header
from email.utils import parseaddr
from typing import Optional, Tuple

import keyring

from .settings_store import load_settings, save_settings
from . import db

SERVICE_NAME = "CertLedger"


def _normalize_email(addr: str) -> str:
    return (addr or "").strip().lower()


def _ensure_windows_keyring(logger=None) -> None:
    # Only attempt to force WinVault backend if it exists.
    try:
        from keyring.backends import Windows
        keyring.set_keyring(Windows.WinVaultKeyring())
        if logger:
            logger.info(f"Keyring backend forced: {keyring.get_keyring()}")
    except Exception as e:
        if logger:
            logger.info(f"Keyring backend not forced (ok): {e}")


def set_app_password(system_email: str, app_password: str) -> None:
    system_email = _normalize_email(system_email)
    keyring.set_password(SERVICE_NAME, system_email, app_password)


def get_app_password(system_email: str) -> Optional[str]:
    system_email = _normalize_email(system_email)
    return keyring.get_password(SERVICE_NAME, system_email)


def send_signature_request(to_email: str, cert_number: str, sign_code: str, cert_summary: str, logger=None) -> None:
    s = load_settings()
    system_email = _normalize_email(s.system_email)

    _ensure_windows_keyring(logger)

    pwd = get_app_password(system_email) if system_email else None
    if not system_email:
        raise RuntimeError("System email not set in Settings.")
    if not pwd:
        raise RuntimeError(
            f"App password not found in keyring for {system_email}. "
            "Go to Settings -> Set/Change app password."
        )

    msg = EmailMessage()
    msg["From"] = system_email
    msg["To"] = to_email
    msg["Subject"] = f"SIGN REQUEST: {cert_number}"

    body = (
        "INSTRUCTIONS (IMPORTANT)\n"
        "1) Send a NEW email (do not reply).\n"
        f"2) Subject must be exactly: {cert_number}\n"
        f"3) Email body must contain ONLY this code (no extra text): {sign_code}\n\n"
        "Certificate summary:\n"
        f"{cert_summary}\n"
    )
    msg.set_content(body)

    with smtplib.SMTP(s.smtp_host, s.smtp_port) as smtp:
        smtp.starttls()
        smtp.login(system_email, pwd)
        smtp.send_message(msg)


def _decode_mime_header(value: str) -> str:
    parts = decode_header(value)
    out = ""
    for text, enc in parts:
        if isinstance(text, bytes):
            out += text.decode(enc or "utf-8", errors="replace")
        else:
            out += text
    return out


def _extract_text_plain(message: email.message.Message) -> str:
    if message.is_multipart():
        for part in message.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", "")).lower()
            if ctype == "text/plain" and "attachment" not in disp:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        return ""
    payload = message.get_payload(decode=True) or b""
    charset = message.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def _norm_body(body: str) -> str:
    return body.replace("\r\n", "\n").strip()


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _store_evidence(
    con,
    cert_number: str | None,
    subject: str,
    from_email: str,
    body: str,
    message_id: str | None,
    matched: int,
    notes: str,
) -> None:
    con.execute(
        "INSERT INTO email_evidence(cert_number, received_at, from_email, subject, body_hash, message_id, matched, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (cert_number, db.now_iso(), from_email, subject, _hash_text(body), message_id, matched, notes),
    )


def scan_inbox_and_apply_signatures(logger) -> Tuple[int, int]:
    db.init_db()

    s = load_settings()
    system_email = _normalize_email(s.system_email)

    _ensure_windows_keyring(logger)

    pwd = get_app_password(system_email) if system_email else None

    # Do NOT error if not configured; just skip.
    if not system_email or not pwd:
        logger.info(
            f"Mailbox scan skipped. system_email='{system_email}' pwd_present={bool(pwd)} backend={keyring.get_keyring()}"
        )
        return 0, 0

    matched = 0
    processed = 0

    con = db.connect()
    try:
        with imaplib.IMAP4_SSL(s.imap_host, s.imap_port) as imap:
            imap.login(system_email, pwd)
            imap.select(s.imap_folder)

            start_uid = int(s.last_imap_uid) + 1
            typ, data = imap.uid("search", None, f"UID {start_uid}:*")
            if typ != "OK":
                raise RuntimeError("IMAP search failed.")

            uids = data[0].split() if data and data[0] else []

            for uid_b in uids:
                uid = int(uid_b.decode("ascii"))
                typ, msg_data = imap.uid("fetch", uid_b, "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue

                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                from_email = _normalize_email(parseaddr(msg.get("From", ""))[1])
                subject = _decode_mime_header(msg.get("Subject", "")).strip()
                message_id = msg.get("Message-ID", None)

                body = _extract_text_plain(msg)
                body_n = _norm_body(body)

                processed += 1
                s.last_imap_uid = max(int(s.last_imap_uid), uid)

                cert_row = con.execute(
                    "SELECT * FROM certificates WHERE cert_number = ? AND status = 'SIGN_REQUESTED'",
                    (subject,),
                ).fetchone()

                if not cert_row:
                    _store_evidence(
                        con, None, subject, from_email, body_n, message_id, 0,
                        "No matching cert in SIGN_REQUESTED with subject=cert_number.",
                    )
                    con.commit()
                    continue

                cert_number = cert_row["cert_number"]

                if s.require_from_match:
                    recv = con.execute(
                        "SELECT email FROM people WHERE person_id = ?",
                        (cert_row["receiver_person_id"],),
                    ).fetchone()
                    give = con.execute(
                        "SELECT email FROM people WHERE person_id = ?",
                        (cert_row["giver_person_id"],),
                    ).fetchone()

                    allowed = set()
                    if recv and recv["email"]:
                        allowed.add(_normalize_email(recv["email"]))
                    if give and give["email"]:
                        allowed.add(_normalize_email(give["email"]))

                    if not allowed:
                        _store_evidence(
                            con, cert_number, subject, from_email, body_n, message_id, 0,
                            "From-match enabled but receiver/giver have no email on file.",
                        )
                        con.commit()
                        continue

                    if from_email not in allowed:
                        _store_evidence(
                            con, cert_number, subject, from_email, body_n, message_id, 0,
                            "From-address did not match receiver/giver email on file.",
                        )
                        con.commit()
                        continue

                sign_code = (cert_row["sign_code"] or "").strip()
                if not sign_code or body_n != sign_code:
                    _store_evidence(
                        con, cert_number, subject, from_email, body_n, message_id, 0,
                        "Body did not exactly equal sign_code.",
                    )
                    con.commit()
                    continue

                con.execute(
                    "UPDATE certificates SET status='SIGNED', signed_at=? WHERE cert_number=?",
                    (db.now_iso(), cert_number),
                )
                _store_evidence(
                    con, cert_number, subject, from_email, body_n, message_id, 1,
                    "Signature matched and certificate signed.",
                )
                con.commit()

                db.log_audit("CONFIRM_SIGN", "CERT", cert_number, "OK", f"Signed via email from {from_email}.")
                matched += 1
                logger.info(f"SIGNED: {cert_number} via {from_email}")

            imap.logout()

    finally:
        con.close()

    save_settings(s)
    return matched, processed
