
# CertLedger

**Local Certificate Registry & Verification System**

---

## Table of Contents

1. Overview
2. What CertLedger Is (and Is Not)
3. Core Concepts
4. System Requirements
5. Installation & First Run
6. Application Structure
7. Getting Started (Typical Workflow)
8. Managing People
9. Creating Certificates
10. Certificate Validity & Expiration
11. Signing Certificates
12. Manual Overrides
13. PDF Handling
14. Email System (Gmail)
15. Logs & Auditing
16. Desktop Shortcut (One-Click Start)
17. Data Storage & Portability
18. Security Model
19. Common Mistakes & Troubleshooting
20. Design Philosophy

---

## 1. Overview

CertLedger is a **local, offline-first certificate registry** designed to:

- Generate and manage certificate numbers
- Track who issued and received certificates
- Track validity and expiration
- Verify signatures via **email confirmation**
- Store and open certificate PDFs
- Maintain a **complete audit log**
- Avoid document generation, cloud hosting, or external services

CertLedger is meant for **administrative control and traceability**, not document design.

---

## 2. What CertLedger Is (and Is Not)

### CertLedger IS:

- A local certificate **database**
- A numbering authority
- A validation tracker (valid / expired)
- An email-based signing verifier
- An audit log system

### CertLedger IS NOT:

- A PDF generator
- A cloud service
- A Word / Office integration
- A blockchain
- A public-facing verification portal

The PDF is created externally. CertLedger only ensures that:

> “What’s in the database matches the real document.”

---

## 3. Core Concepts

### Certificates

Each certificate has:

- A **unique certificate number**
- A type (free text)
- Issue date
- Expiration date
- Receiver (person)
- Giver (person)
- Status:
  - `ISSUED`
  - `SIGN_REQUESTED`
  - `SIGNED`
- Optional linked PDF

### People

People are stored once and reused.
Each person has:

- Internal Person ID
- Government ID number
- Date of birth
- Official name
- Call name (preferred display name)
- Nickname
- Email
- Nationality

### Audit Log

Every important action is logged:

- Create
- Edit
- Manual overrides
- Email actions
- Errors

Nothing silently changes.

---

## 4. System Requirements

- Windows 10 or newer
- Python 3.11+
- Internet access **only** for sending/receiving email
- A dedicated Gmail account (recommended)

---

## 5. Installation & First Run

### Folder Structure

CertLedger runs entirely from one folder:


Certificate_database/

├─ main.py

├─ certledger/

├─ data/

│  ├─ certs.sqlite3

│  └─ pdfs/

├─ logs/

├─ settings.json

├─ venv/



### First Run

Always start using the virtual environment:

```powershell
.\venv\Scripts\python.exe .\main.py
```




## On First Run

- Database is created automatically
- Folder structure is created automatically

---

## 6. Application Structure (UI)

### Home Screen

Buttons available:

- Existing certificates
- Person list
- Create certificate
- Create person
- View logs
- Settings

Navigation is explicit and simple.

---

## 7. Getting Started (Typical Workflow)

1. Configure email settings
2. Create people (receivers / givers)
3. Create a certificate → get a number
4. Insert the number into a PDF you create
5. Import the PDF
6. Request or apply signing
7. Monitor validity and logs

---

## 8. Managing People

### Create Person

**Path:** Home → Create person

**Required fields:**

- Gov ID number
- Date of birth (YYYY-MM-DD)
- Official name

**Optional fields:**

- Call name (used in UI)
- Nickname
- Email (recommended)
- Nationality

Each person receives:

- A generated Person ID (e.g. `P-000012`)

---

### Edit Person

**Path:** Home → Person list

Steps:

1. Double-click a person
2. Edit fields
3. Save

All changes are logged.

---

## 9. Creating Certificates

**Path:** Home → Create certificate

You enter:

- Certificate type
- Receiver
- Giver
- Validity duration (days)
- Which name variant appears on the certificate

You receive:

- A generated certificate number (e.g. `C-2025-000001`)

You must manually place this number into your PDF.

CertLedger does **not** modify documents.

---

## 10. Certificate Validity & Expiration

- Each certificate has `valid_until`
- Validity is calculated using the system clock

In the certificate list:

- **VALID** = green
- **EXPIRED** = red

Expiration dates can be manually edited (logged).

---

## 11. Signing Certificates (Email-Based)

### Purpose

Email signing proves that the receiver confirms the certificate.

### How It Works

1. Certificate is created
2. Click **Request signature email**
3. Receiver gets instructions:
   - Send a **new email**
   - Subject = certificate number
   - Body = signing code only
4. CertLedger scans the inbox
5. If everything matches → status becomes **SIGNED**

### Security Checks

- Optional: sender email must match receiver/giver
- Body must exactly match signing code
- Subject must exactly match certificate number

---

## 12. Manual Overrides

### Manual Signing

**Path:** Existing certificates → Mark as signed (manual)

Used when:

- Email is impossible
- Legacy certificates
- Administrative override

This action is:

- Explicit
- Confirmed
- Fully logged

---

## 13. PDF Handling

### Importing PDFs

**Path:** Existing certificates → Import PDF

Steps:

1. Select a certificate
2. Choose a PDF file

Result:

- File is renamed to:
  <CERT_NUMBER>.pdf
- Stored in:
  data/pdfs/

  ---

  ### Opening PDFs

  Steps:


  1. Select certificate
  2. Click **Open PDF**

  Opens in the system default PDF viewer.

  ### Emailing PDFs

  After import, you may choose to:

  - Send the PDF to the receiver

  Rules:

  - Email uses the system email
  - Attachment is the imported PDF

  ---

  ## 14. Email System (Gmail)

  ### Why Gmail

  - Reliable SMTP + IMAP
  - App passwords
  - No hosting required

  ### Setup Steps

  1. Create a dedicated Gmail account
  2. Enable 2FA
  3. Create an **App Password**
  4. In CertLedger:

  - Settings → set system email
  - Set app password (stored securely via Windows Keyring)

  Passwords are **never stored in plaintext**.

  ---

  ## 15. Logs & Auditing

  ### In-App Logs

  **Path:** Home → View logs

  Displays:

  - Timestamp
  - Action
  - Entity
  - Result
  - Message

  ---

  ### File Logs

  Stored in:
- logs/


Used for:

- Audits
- Troubleshooting
- Compliance

---

## 16. Desktop Shortcut (One-Click Start)

### Recommended Method (No Console Window)

Create a Windows shortcut pointing to:
`<project>`\venv\Scripts\pythonw.exe `<project>`\main.py

Set **Start in** to the project folder.

Name the shortcut: CertLedger



Double-click → app starts.

---

## 17. Data Storage & Portability

Everything is local:

- Database: `data/certs.sqlite3`
- PDFs: `data/pdfs/`
- Logs: `logs/`
- Settings: `settings.json`

### To migrate:

1. Copy the entire project folder
2. Open on another Windows machine
3. Run

No installer required.

---

## 18. Security Model

- Local-first
- No cloud dependencies
- No auto-deletions
- Explicit user actions
- Email verification is additive, not exclusive
- Manual overrides are logged, not hidden

This system favors **traceability over automation**.

---

## 19. Common Mistakes & Troubleshooting

### App won’t start

- You’re using global Python instead of the venv

### Email not working

- Wrong app password
- IMAP disabled in Gmail
- System email mismatch

### PDF won’t open

- File not named exactly as certificate number
- File not in `data/pdfs/`

### “Expired” looks wrong

- Check system date/time

---

## 20. Design Philosophy

CertLedger is intentionally:

- Simple
- Explicit
- Local
- Auditable

It assumes:

> “If something matters, it must be visible and logged.”

No magic.
No hidden automation.
No cloud dependency.

---

**End of README**
