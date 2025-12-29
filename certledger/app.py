from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timedelta

from PySide6 import QtWidgets

from .logging_setup import setup_logging
from .settings_store import load_settings, save_settings
from .paths import ensure_dirs
from . import db
from . import emailer


class CertLedgerWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.logger = setup_logging()
        ensure_dirs()
        db.init_db()

        self.setWindowTitle("CertLedger")
        self.resize(1100, 700)

        self.stack = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.stack)

        self.home = HomePage(self)
        self.people = PeoplePage(self)
        self.certs = CertsPage(self)
        self.create_person = CreatePersonPage(self)
        self.create_cert = CreateCertPage(self)
        self.logs = LogsPage(self)
        self.settings = SettingsPage(self)

        for w in [self.home, self.certs, self.people, self.create_person, self.create_cert, self.logs, self.settings]:
            self.stack.addWidget(w)

        self.show_home()

        # Startup mailbox scan (safe: emailer should skip if not configured)
        try:
            matched, processed = emailer.scan_inbox_and_apply_signatures(self.logger)
            if processed:
                QtWidgets.QMessageBox.information(
                    self, "Mailbox scan", f"Processed {processed} emails, matched {matched}."
                )
        except Exception as e:
            self.logger.exception("Startup mailbox scan failed.")
            QtWidgets.QMessageBox.warning(self, "Mailbox scan failed", str(e))

    def show_home(self):
        self.stack.setCurrentWidget(self.home)

    def show_people(self):
        self.people.refresh()
        self.stack.setCurrentWidget(self.people)

    def show_certs(self):
        self.certs.refresh()
        self.stack.setCurrentWidget(self.certs)

    def show_create_person(self):
        self.create_person.reset_form()
        self.stack.setCurrentWidget(self.create_person)

    def show_create_cert(self):
        self.create_cert.reset_form()
        self.stack.setCurrentWidget(self.create_cert)

    def show_logs(self):
        self.logs.refresh()
        self.stack.setCurrentWidget(self.logs)

    def show_settings(self):
        self.settings.load_into_form()
        self.stack.setCurrentWidget(self.settings)


class HomePage(QtWidgets.QWidget):
    def __init__(self, main: CertLedgerWindow):
        super().__init__()
        self.main = main
        layout = QtWidgets.QVBoxLayout(self)

        btn_certs = QtWidgets.QPushButton("Existing certificates")
        btn_people = QtWidgets.QPushButton("Person list")
        btn_new_cert = QtWidgets.QPushButton("Create certificate")
        btn_new_person = QtWidgets.QPushButton("Create person")
        btn_logs = QtWidgets.QPushButton("View logs")
        btn_settings = QtWidgets.QPushButton("Settings")

        btn_certs.clicked.connect(main.show_certs)
        btn_people.clicked.connect(main.show_people)
        btn_new_cert.clicked.connect(main.show_create_cert)
        btn_new_person.clicked.connect(main.show_create_person)
        btn_logs.clicked.connect(main.show_logs)
        btn_settings.clicked.connect(main.show_settings)

        for b in [btn_certs, btn_people, btn_new_cert, btn_new_person, btn_logs, btn_settings]:
            b.setMinimumHeight(40)
            layout.addWidget(b)

        layout.addStretch(1)


class PeoplePage(QtWidgets.QWidget):
    def __init__(self, main: CertLedgerWindow):
        super().__init__()
        self.main = main
        layout = QtWidgets.QVBoxLayout(self)

        top = QtWidgets.QHBoxLayout()
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search name / gov id / person id / nationality")
        self.search.textChanged.connect(self.refresh)

        btn_edit = QtWidgets.QPushButton("Edit selected")
        btn_edit.clicked.connect(self.edit_selected)

        btn_back = QtWidgets.QPushButton("Back")
        btn_back.clicked.connect(main.show_home)

        top.addWidget(self.search)
        top.addWidget(btn_edit)
        top.addWidget(btn_back)
        layout.addLayout(top)

        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Display name", "Gov ID", "Person ID", "Nationality"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.cellDoubleClicked.connect(lambda r, c: self.edit_row(r))
        layout.addWidget(self.table)

    def refresh(self):
        q = self.search.text().strip().lower()
        con = db.connect()
        rows = con.execute("SELECT * FROM people ORDER BY person_id DESC").fetchall()
        con.close()

        filtered = []
        for r in rows:
            display = (r["call_name"] or r["official_name"]).strip()
            nat = (r["nationality"] or "").strip()
            hay = f"{display} {r['official_name']} {r['gov_id_number']} {r['person_id']} {nat}".lower()
            if not q or q in hay:
                filtered.append((display, r["gov_id_number"], r["person_id"], nat))

        self.table.setRowCount(len(filtered))
        for i, (d, gov, pid, nat) in enumerate(filtered):
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(d))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(gov))
            self.table.setItem(i, 2, QtWidgets.QTableWidgetItem(pid))
            self.table.setItem(i, 3, QtWidgets.QTableWidgetItem(nat))

        self.table.resizeColumnsToContents()

    def _selected_person_id(self) -> str | None:
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return None
        row = sel[0].row()
        return self.table.item(row, 2).text()

    def edit_selected(self):
        pid = self._selected_person_id()
        if not pid:
            QtWidgets.QMessageBox.warning(self, "No selection", "Select a person first.")
            return
        dlg = EditPersonDialog(self.main, pid)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self.refresh()

    def edit_row(self, row: int):
        pid = self.table.item(row, 2).text()
        dlg = EditPersonDialog(self.main, pid)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self.refresh()


class CertsPage(QtWidgets.QWidget):
    def __init__(self, main: CertLedgerWindow):
        super().__init__()
        self.main = main
        layout = QtWidgets.QVBoxLayout(self)

        top = QtWidgets.QHBoxLayout()
        btn_back = QtWidgets.QPushButton("Back")
        btn_back.clicked.connect(main.show_home)

        btn_check = QtWidgets.QPushButton("Check mailbox now")
        btn_check.clicked.connect(self.check_mailbox_now)

        top.addWidget(btn_back)
        top.addStretch(1)
        top.addWidget(btn_check)
        layout.addLayout(top)

        self.table = QtWidgets.QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Cert #", "Type", "Receiver", "Giver", "Issued", "Valid until", "Valid?", "Status"
        ])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table)

        bottom = QtWidgets.QHBoxLayout()

        self.btn_open_pdf = QtWidgets.QPushButton("Open PDF")
        self.btn_open_pdf.clicked.connect(self.open_pdf)

        self.btn_manual_sign = QtWidgets.QPushButton("Mark as signed (manual)")
        self.btn_manual_sign.clicked.connect(self.manual_sign)

        bottom.addWidget(self.btn_open_pdf)
        bottom.addWidget(self.btn_manual_sign)
        bottom.addStretch(1)
        layout.addLayout(bottom)

    def refresh(self):
        con = db.connect()
        rows = con.execute("""
        SELECT c.*,
               pr.official_name AS r_off, pr.call_name AS r_call,
               pg.official_name AS g_off, pg.call_name AS g_call
          FROM certificates c
          JOIN people pr ON pr.person_id = c.receiver_person_id
          JOIN people pg ON pg.person_id = c.giver_person_id
         ORDER BY c.cert_number DESC
        """).fetchall()
        con.close()

        now = datetime.utcnow()
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            receiver = (r["r_call"] or r["r_off"]).strip()
            giver = (r["g_call"] or r["g_off"]).strip()
            issued = r["issued_at"]
            valid_until = r["valid_until"]

            try:
                vu = datetime.fromisoformat(valid_until.replace("Z", ""))
                valid = now <= vu
            except Exception:
                valid = False

            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(r["cert_number"]))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(r["cert_type"]))
            self.table.setItem(i, 2, QtWidgets.QTableWidgetItem(receiver))
            self.table.setItem(i, 3, QtWidgets.QTableWidgetItem(giver))
            self.table.setItem(i, 4, QtWidgets.QTableWidgetItem(issued))
            self.table.setItem(i, 5, QtWidgets.QTableWidgetItem(valid_until))
            self.table.setItem(i, 6, QtWidgets.QTableWidgetItem("VALID" if valid else "EXPIRED"))
            self.table.setItem(i, 7, QtWidgets.QTableWidgetItem(r["status"]))

        self.table.resizeColumnsToContents()

    def selected_cert_number(self) -> str | None:
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return None
        row = sel[0].row()
        return self.table.item(row, 0).text()

    def open_pdf(self):
        cert = self.selected_cert_number()
        if not cert:
            QtWidgets.QMessageBox.warning(self, "No selection", "Select a certificate first.")
            return
        pdf_path = ensure_dirs()["pdfs"] / f"{cert}.pdf"
        if not pdf_path.exists():
            QtWidgets.QMessageBox.warning(self, "No PDF", f"Missing: {pdf_path}")
            return
        os.startfile(str(pdf_path))  # Windows only

    def manual_sign(self):
        cert = self.selected_cert_number()
        if not cert:
            QtWidgets.QMessageBox.warning(self, "No selection", "Select a certificate first.")
            return

        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm manual signing",
            f"Manually mark certificate {cert} as SIGNED?\n\nThis will be logged.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        try:
            con = db.connect()
            con.execute(
                "UPDATE certificates SET status='SIGNED', signed_at=? WHERE cert_number=?",
                (db.now_iso(), cert),
            )
            con.commit()
            con.close()

            db.log_audit("MANUAL_SIGN", "CERT", cert, "OK", "Certificate manually marked as signed.")
            QtWidgets.QMessageBox.information(self, "Done", f"{cert} marked as SIGNED.")
            self.refresh()
        except Exception as e:
            self.main.logger.exception("Manual sign failed.")
            db.log_audit("MANUAL_SIGN", "CERT", cert, "ERROR", str(e))
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

    def check_mailbox_now(self):
        try:
            matched, processed = emailer.scan_inbox_and_apply_signatures(self.main.logger)
            QtWidgets.QMessageBox.information(self, "Mailbox scan", f"Processed {processed} emails, matched {matched}.")
            self.refresh()
        except Exception as e:
            self.main.logger.exception("Mailbox scan failed.")
            QtWidgets.QMessageBox.warning(self, "Mailbox scan failed", str(e))


class LogsPage(QtWidgets.QWidget):
    def __init__(self, main: CertLedgerWindow):
        super().__init__()
        self.main = main
        layout = QtWidgets.QVBoxLayout(self)

        top = QtWidgets.QHBoxLayout()
        btn_back = QtWidgets.QPushButton("Back")
        btn_back.clicked.connect(main.show_home)
        top.addWidget(btn_back)
        top.addStretch(1)
        layout.addLayout(top)

        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Timestamp", "Action", "Entity", "Result", "Message"])
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

    def refresh(self):
        con = db.connect()
        rows = con.execute(
            "SELECT ts, action, entity_type, entity_id, result, message "
            "FROM audit_log ORDER BY ts DESC LIMIT 2000"
        ).fetchall()
        con.close()

        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(r["ts"]))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(r["action"]))
            self.table.setItem(i, 2, QtWidgets.QTableWidgetItem(f"{r['entity_type']} {r['entity_id']}"))
            self.table.setItem(i, 3, QtWidgets.QTableWidgetItem(r["result"]))
            self.table.setItem(i, 4, QtWidgets.QTableWidgetItem(r["message"]))

        self.table.resizeColumnsToContents()


class CreatePersonPage(QtWidgets.QWidget):
    def __init__(self, main: CertLedgerWindow):
        super().__init__()
        self.main = main
        layout = QtWidgets.QFormLayout(self)

        self.gov = QtWidgets.QLineEdit()
        self.dob = QtWidgets.QLineEdit()
        self.official = QtWidgets.QLineEdit()
        self.call = QtWidgets.QLineEdit()
        self.nick = QtWidgets.QLineEdit()
        self.email = QtWidgets.QLineEdit()
        self.nationality = QtWidgets.QLineEdit()

        layout.addRow("Gov ID number*", self.gov)
        layout.addRow("Date of birth (YYYY-MM-DD)*", self.dob)
        layout.addRow("Official name*", self.official)
        layout.addRow("Call name", self.call)
        layout.addRow("Nickname", self.nick)
        layout.addRow("Email", self.email)
        layout.addRow("Nationality", self.nationality)

        btns = QtWidgets.QHBoxLayout()
        btn_save = QtWidgets.QPushButton("Save person")
        btn_back = QtWidgets.QPushButton("Back")
        btn_save.clicked.connect(self.save)
        btn_back.clicked.connect(main.show_home)
        btns.addWidget(btn_save)
        btns.addWidget(btn_back)
        layout.addRow(btns)

    def reset_form(self):
        for w in [self.gov, self.dob, self.official, self.call, self.nick, self.email, self.nationality]:
            w.setText("")

    def save(self):
        if not self.gov.text().strip() or not self.dob.text().strip() or not self.official.text().strip():
            QtWidgets.QMessageBox.warning(self, "Missing fields", "Gov ID, DOB, and Official name are required.")
            return

        pid = db.next_person_id()
        now = db.now_iso()
        person = {
            "person_id": pid,
            "gov_id_number": self.gov.text().strip(),
            "date_of_birth": self.dob.text().strip(),
            "official_name": self.official.text().strip(),
            "call_name": self.call.text().strip() or None,
            "nickname": self.nick.text().strip() or None,
            "email": self.email.text().strip() or None,
            "nationality": self.nationality.text().strip() or None,
            "created_at": now,
            "updated_at": now,
        }

        try:
            db.upsert_person(person)
            db.log_audit("CREATE_PERSON", "PERSON", pid, "OK", "Person created.")
            QtWidgets.QMessageBox.information(self, "Saved", f"Created {pid}")
            self.main.show_people()
        except Exception as e:
            self.main.logger.exception("Create person failed.")
            db.log_audit("CREATE_PERSON", "PERSON", pid, "ERROR", str(e))
            QtWidgets.QMessageBox.critical(self, "Error", str(e))


class CreateCertPage(QtWidgets.QWidget):
    def __init__(self, main: CertLedgerWindow):
        super().__init__()
        self.main = main
        layout = QtWidgets.QFormLayout(self)

        self.cert_type = QtWidgets.QLineEdit()
        self.receiver = QtWidgets.QComboBox()
        self.giver = QtWidgets.QComboBox()

        self.valid_days = QtWidgets.QSpinBox()
        self.valid_days.setRange(1, 3650)
        self.valid_days.setValue(365)

        self.receiver_name_used = QtWidgets.QComboBox()
        self.receiver_name_used.addItems(["official", "call", "nickname"])

        self.giver_name_used = QtWidgets.QComboBox()
        self.giver_name_used.addItems(["official", "call", "nickname"])

        layout.addRow("Certificate type*", self.cert_type)
        layout.addRow("Receiver*", self.receiver)
        layout.addRow("Giver*", self.giver)
        layout.addRow("Receiver name used", self.receiver_name_used)
        layout.addRow("Giver name used", self.giver_name_used)
        layout.addRow("Validity (days)*", self.valid_days)

        btns = QtWidgets.QHBoxLayout()
        btn_save = QtWidgets.QPushButton("Create certificate (generate number)")
        btn_req = QtWidgets.QPushButton("Request signature email")
        btn_back = QtWidgets.QPushButton("Back")

        btn_save.clicked.connect(self.create_only)
        btn_req.clicked.connect(self.create_and_request_signature)
        btn_back.clicked.connect(main.show_home)

        btns.addWidget(btn_save)
        btns.addWidget(btn_req)
        btns.addWidget(btn_back)
        layout.addRow(btns)

        self.last_created_cert = None

    def reset_form(self):
        self.cert_type.setText("")
        self.valid_days.setValue(365)
        self.last_created_cert = None
        self._load_people()

    def _load_people(self):
        con = db.connect()
        rows = con.execute(
            "SELECT person_id, official_name, call_name, gov_id_number FROM people ORDER BY person_id DESC"
        ).fetchall()
        con.close()

        self.receiver.clear()
        self.giver.clear()

        for r in rows:
            display = (r["call_name"] or r["official_name"]).strip()
            label = f"{display} | {r['gov_id_number']} | {r['person_id']}"
            self.receiver.addItem(label, r["person_id"])
            self.giver.addItem(label, r["person_id"])

    def _create_cert(self) -> str:
        if not self.cert_type.text().strip():
            raise RuntimeError("Certificate type is required.")
        if self.receiver.count() == 0:
            raise RuntimeError("No people exist yet. Create people first.")

        year = datetime.utcnow().year
        cert_number = db.next_cert_number(year)
        issued = db.now_iso()
        valid_until = (datetime.utcnow() + timedelta(days=int(self.valid_days.value()))).isoformat(timespec="seconds") + "Z"

        cert = {
            "cert_number": cert_number,
            "cert_type": self.cert_type.text().strip(),
            "issued_at": issued,
            "receiver_person_id": self.receiver.currentData(),
            "giver_person_id": self.giver.currentData(),
            "receiver_name_used": self.receiver_name_used.currentText(),
            "giver_name_used": self.giver_name_used.currentText(),
            "valid_until": valid_until,
            "status": "ISSUED",
            "pdf_relpath": None,
        }
        db.create_certificate(cert)
        db.log_audit("CREATE_CERT", "CERT", cert_number, "OK", "Certificate created.")
        self.last_created_cert = cert_number
        return cert_number

    def create_only(self):
        try:
            cert = self._create_cert()
            QtWidgets.QMessageBox.information(
                self, "Certificate created",
                f"Certificate number:\n{cert}\n\nPut this number in your PDF."
            )
            self.main.show_certs()
        except Exception as e:
            self.main.logger.exception("Create cert failed.")
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

    def create_and_request_signature(self):
        try:
            cert = self._create_cert()
            self._request_signature_for(cert)
            QtWidgets.QMessageBox.information(
                self, "Request sent",
                f"Created {cert} and sent signature request email."
            )
            self.main.show_certs()
        except Exception as e:
            self.main.logger.exception("Create+request failed.")
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

    def _request_signature_for(self, cert_number: str):
        sign_code = "S-" + secrets.token_hex(4).upper()

        con = db.connect()
        cert = con.execute("SELECT * FROM certificates WHERE cert_number=?", (cert_number,)).fetchone()
        recv = con.execute("SELECT * FROM people WHERE person_id=?", (cert["receiver_person_id"],)).fetchone()
        give = con.execute("SELECT * FROM people WHERE person_id=?", (cert["giver_person_id"],)).fetchone()
        con.close()

        if not recv["email"]:
            raise RuntimeError("Receiver has no email set. Add it in the person profile.")

        summary = (
            f"Cert: {cert_number}\n"
            f"Type: {cert['cert_type']}\n"
            f"Issued: {cert['issued_at']}\n"
            f"Valid until: {cert['valid_until']}\n"
            f"Receiver: {(recv['call_name'] or recv['official_name'])}\n"
            f"Giver: {(give['call_name'] or give['official_name'])}\n"
        )

        con = db.connect()
        con.execute(
            "UPDATE certificates SET status='SIGN_REQUESTED', sign_code=?, sign_requested_at=? WHERE cert_number=?",
            (sign_code, db.now_iso(), cert_number),
        )
        con.commit()
        con.close()

        # If your emailer signature doesn't accept logger, remove logger=self.main.logger
        emailer.send_signature_request(
            to_email=recv["email"],
            cert_number=cert_number,
            sign_code=sign_code,
            cert_summary=summary,
        )
        db.log_audit("SEND_SIGN_EMAIL", "CERT", cert_number, "OK", f"Sent to {recv['email']}")


class SettingsPage(QtWidgets.QWidget):
    def __init__(self, main: CertLedgerWindow):
        super().__init__()
        self.main = main
        layout = QtWidgets.QFormLayout(self)

        self.system_email = QtWidgets.QLineEdit()
        self.require_from_match = QtWidgets.QCheckBox("Require From-address match (receiver or giver)")
        self.require_from_match.setChecked(True)

        self.smtp_host = QtWidgets.QLineEdit()
        self.smtp_port = QtWidgets.QSpinBox()
        self.smtp_port.setRange(1, 65535)

        self.imap_host = QtWidgets.QLineEdit()
        self.imap_port = QtWidgets.QSpinBox()
        self.imap_port.setRange(1, 65535)

        layout.addRow("System email (Gmail)", self.system_email)
        layout.addRow(self.require_from_match)
        layout.addRow("SMTP host", self.smtp_host)
        layout.addRow("SMTP port", self.smtp_port)
        layout.addRow("IMAP host", self.imap_host)
        layout.addRow("IMAP port", self.imap_port)

        btns = QtWidgets.QHBoxLayout()
        btn_save = QtWidgets.QPushButton("Save settings")
        btn_set_pwd = QtWidgets.QPushButton("Set/Change app password")
        btn_test_scan = QtWidgets.QPushButton("Check mailbox now")
        btn_back = QtWidgets.QPushButton("Back")

        btn_save.clicked.connect(self.save_from_form)
        btn_set_pwd.clicked.connect(self.set_password_prompt)
        btn_test_scan.clicked.connect(self.scan_now)
        btn_back.clicked.connect(main.show_home)

        btns.addWidget(btn_save)
        btns.addWidget(btn_set_pwd)
        btns.addWidget(btn_test_scan)
        btns.addWidget(btn_back)
        layout.addRow(btns)

    def load_into_form(self):
        s = load_settings()
        self.system_email.setText(s.system_email)
        self.require_from_match.setChecked(bool(s.require_from_match))
        self.smtp_host.setText(s.smtp_host)
        self.smtp_port.setValue(int(s.smtp_port))
        self.imap_host.setText(s.imap_host)
        self.imap_port.setValue(int(s.imap_port))

    def save_from_form(self):
        s = load_settings()
        s.system_email = self.system_email.text().strip()
        s.require_from_match = bool(self.require_from_match.isChecked())
        s.smtp_host = self.smtp_host.text().strip()
        s.smtp_port = int(self.smtp_port.value())
        s.imap_host = self.imap_host.text().strip()
        s.imap_port = int(self.imap_port.value())
        save_settings(s)
        db.log_audit("UPDATE_SETTINGS", "SETTINGS", "settings.json", "OK", "Settings updated.")
        QtWidgets.QMessageBox.information(self, "Saved", "Settings saved.")

    def set_password_prompt(self):
        email_addr = self.system_email.text().strip()
        if not email_addr:
            QtWidgets.QMessageBox.warning(self, "Missing email", "Set System email first, then set app password.")
            return

        pwd, ok = QtWidgets.QInputDialog.getText(
            self,
            "App password",
            "Enter Gmail app password:",
            QtWidgets.QLineEdit.Password,
        )
        if ok and pwd.strip():
            emailer.set_app_password(email_addr, pwd.strip())
            db.log_audit("SET_EMAIL_PASSWORD", "SETTINGS", email_addr, "OK", "Stored app password in keyring.")
            QtWidgets.QMessageBox.information(self, "Stored", "App password stored in Windows Credential Manager.")

    def scan_now(self):
        try:
            matched, processed = emailer.scan_inbox_and_apply_signatures(self.main.logger)
            QtWidgets.QMessageBox.information(self, "Mailbox scan", f"Processed {processed} emails, matched {matched}.")
        except Exception as e:
            self.main.logger.exception("Mailbox scan failed.")
            QtWidgets.QMessageBox.warning(self, "Mailbox scan failed", str(e))


class EditPersonDialog(QtWidgets.QDialog):
    def __init__(self, main: CertLedgerWindow, person_id: str):
        super().__init__(main)
        self.main = main
        self.person_id = person_id
        self.setWindowTitle(f"Edit Person {person_id}")
        self.resize(520, 340)

        form = QtWidgets.QFormLayout(self)

        self.gov = QtWidgets.QLineEdit()
        self.dob = QtWidgets.QLineEdit()
        self.official = QtWidgets.QLineEdit()
        self.call = QtWidgets.QLineEdit()
        self.nick = QtWidgets.QLineEdit()
        self.email = QtWidgets.QLineEdit()
        self.nationality = QtWidgets.QLineEdit()

        form.addRow("Gov ID number*", self.gov)
        form.addRow("Date of birth (YYYY-MM-DD)*", self.dob)
        form.addRow("Official name*", self.official)
        form.addRow("Call name", self.call)
        form.addRow("Nickname", self.nick)
        form.addRow("Email", self.email)
        form.addRow("Nationality", self.nationality)

        btns = QtWidgets.QHBoxLayout()
        btn_save = QtWidgets.QPushButton("Save changes")
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_save.clicked.connect(self.save)
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_save)
        btns.addWidget(btn_cancel)
        form.addRow(btns)

        self._load()

    def _load(self):
        con = db.connect()
        row = con.execute("SELECT * FROM people WHERE person_id=?", (self.person_id,)).fetchone()
        con.close()
        if not row:
            QtWidgets.QMessageBox.critical(self, "Error", "Person not found.")
            self.reject()
            return

        self.before = dict(row)
        self.gov.setText(row["gov_id_number"])
        self.dob.setText(row["date_of_birth"])
        self.official.setText(row["official_name"])
        self.call.setText(row["call_name"] or "")
        self.nick.setText(row["nickname"] or "")
        self.email.setText(row["email"] or "")
        self.nationality.setText(row["nationality"] or "")

    def save(self):
        if not self.gov.text().strip() or not self.dob.text().strip() or not self.official.text().strip():
            QtWidgets.QMessageBox.warning(self, "Missing fields", "Gov ID, DOB, and Official name are required.")
            return

        now = db.now_iso()
        after = {
            "person_id": self.person_id,
            "gov_id_number": self.gov.text().strip(),
            "date_of_birth": self.dob.text().strip(),
            "official_name": self.official.text().strip(),
            "call_name": self.call.text().strip() or None,
            "nickname": self.nick.text().strip() or None,
            "email": self.email.text().strip() or None,
            "nationality": self.nationality.text().strip() or None,
            "created_at": self.before["created_at"],
            "updated_at": now,
        }

        try:
            db.upsert_person(after)
            db.log_audit(
                action="EDIT_PERSON",
                entity_type="PERSON",
                entity_id=self.person_id,
                result="OK",
                message="Person edited.",
                before_json=json.dumps(self.before, ensure_ascii=False),
                after_json=json.dumps(after, ensure_ascii=False),
            )
            self.accept()
        except Exception as e:
            self.main.logger.exception("Edit person failed.")
            db.log_audit("EDIT_PERSON", "PERSON", self.person_id, "ERROR", str(e))
            QtWidgets.QMessageBox.critical(self, "Error", str(e))
