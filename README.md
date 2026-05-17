# Swiss Invoice Compliance AI

> **Production-ready AI backend** for Swiss companies — upload invoice PDFs or images, extract all fields via OCR, validate against 12 Swiss legal rules (UID, IBAN, QR-bill, MWST), and export to Excel / SAP / Power BI.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green)](https://fastapi.tiangolo.com)
[![Tests](https://img.shields.io/badge/tests-86%20passed-brightgreen)](https://pytest.org)
[![SQLite](https://img.shields.io/badge/DB-SQLite%20%2F%20Postgres-lightblue)](https://www.sqlite.org)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

---

## Table of Contents

1. [What This Project Does](#what-this-project-does)
2. [Project Plan](#project-plan)
3. [Architecture](#architecture)
4. [Pipeline](#pipeline)
5. [Tech Stack & Libraries](#tech-stack--libraries)
6. [Compliance Rules](#compliance-rules)
7. [Supported Invoice Languages](#supported-invoice-languages)
8. [API Endpoints](#api-endpoints)
9. [Export Formats](#export-formats)
10. [Quick Start](#quick-start)
11. [Configuration](#configuration)
12. [OCR Setup](#ocr-setup)
13. [Running Tests](#running-tests)
14. [Switching to PostgreSQL](#switching-to-postgresql)
15. [Roadmap](#roadmap)
16. [Portfolio Talking Points](#portfolio-talking-points)

---

## What This Project Does

Swiss companies receive invoices in German, French, Italian, and English from hundreds of vendors. Manually checking each invoice for legal compliance (Swiss UID format, QR-bill reference, correct MWST rate) is slow and error-prone.

This system automates the entire process:

1. **Receive** — accept PDF or image invoice via REST API upload
2. **Extract** — run OCR to get raw text, then parse 15+ fields with multilingual regex
3. **Validate** — run 12 Swiss compliance rules, score each invoice PASS / WARNING / FAIL
4. **Store** — persist invoice, line items, and compliance results in SQLite (or Postgres)
5. **Export** — download Excel report, SAP-ready CSV, or Power BI JSON on demand

---

## Project Plan

The project was built in 8 structured phases:

| Phase | Deliverable | Status |
|---|---|---|
| 1 | Project structure, config, environment | ✅ Done |
| 2 | Database models — Invoice, LineItem, ComplianceResult | ✅ Done |
| 3 | Pluggable OCR layer (Tesseract / EasyOCR / Mock) | ✅ Done |
| 4 | Multilingual field extraction engine (15+ fields, 4 languages) | ✅ Done |
| 5 | Swiss compliance engine (12 rules) | ✅ Done |
| 6 | FastAPI routers — upload, list, detail, reprocess, delete | ✅ Done |
| 7 | Export service — Excel, SAP CSV, Power BI JSON | ✅ Done |
| 8 | Sample data, seed script, 86 unit + integration tests | ✅ Done |
| 9 | **v1.1** — Fraud/anomaly detection engine (8 rules, score 0-100) | ✅ Done |
| 10 | **v1.1** — 4 new compliance rules (tax gt total, suspicious amount, date order, payment terms) | ✅ Done |
| 11 | **v1.1** — 3 new DB tables: anomaly_flags, vendors, uploaded_files | ✅ Done |
| 12 | **v1.1** — `/invoices/{id}/anomalies` endpoint + 30 new tests | ✅ Done |

---

## Architecture

```
swiss-invoice-compliance/
│
├── app/
│   ├── main.py                  ← FastAPI app factory, CORS, router registration
│   ├── config.py                ← pydantic-settings: loads .env, auto-creates dirs
│   │
│   ├── models/
│   │   ├── database.py          ← SQLAlchemy engine (SQLite + Postgres-ready)
│   │   │                          SessionLocal, Base, get_db() dependency, init_db()
│   │   ├── invoice.py           ← ORM: Invoice, LineItem, ComplianceResult
│   │   │                          Enums: ProcessingStatus, ComplianceStatus, Language
│   │   │                          @property: overall_compliance_status (computed)
│   │   └── schemas.py           ← Pydantic v2 request/response schemas
│   │                              InvoiceOut, InvoiceSummary, ComplianceSummary
│   │
│   ├── services/
│   │   ├── ocr_service.py       ← Abstract BaseOCREngine (Strategy pattern)
│   │   │                          Implementations: Tesseract, EasyOCR, Mock
│   │   │                          Factory: get_ocr_engine() with fallback to mock
│   │   ├── field_extractor.py   ← 15 compiled regex patterns (DE/FR/IT/EN)
│   │   │                          extract_fields() → ExtractedFields dataclass
│   │   │                          Confidence scoring (0.0 – 1.0)
│   │   ├── compliance_engine.py ← 12 rule functions in ALL_RULES list
│   │   │                          run_compliance_checks() → List[RuleResult]
│   │   │                          summarise_compliance() → ComplianceStatus
│   │   └── export_service.py    ← ExportService: Excel (openpyxl), SAP CSV, Power BI JSON
│   │
│   ├── routers/
│   │   ├── invoices.py          ← POST /upload, GET /, GET /{id}, DELETE /{id}
│   │   │                          POST /{id}/reprocess, GET /{id}/raw
│   │   ├── compliance.py        ← GET /compliance/{id}, GET /compliance/stats/overview
│   │   ├── dashboard.py         ← GET /dashboard/stats, GET /dashboard/vendors
│   │   └── exports.py           ← GET /exports/excel, /sap-csv, /powerbi-json
│   │
│   └── utils/
│       └── file_handler.py      ← Upload validation (extension, MIME, size)
│                                   Safe filename generation with UUID prefix
│
├── tests/
│   ├── conftest.py              ← pytest fixtures: in-memory SQLite (StaticPool),
│   │                              engine patching before app import, TestClient
│   ├── test_field_extractor.py  ← 45 unit tests: regex patterns, amount parsing,
│   │                              date parsing, language detection, confidence
│   ├── test_compliance_engine.py← 30 unit tests: all 12 rules, edge cases
│   └── test_api.py              ← 19 integration tests: full HTTP request/response
│                                  upload→extract→comply→list→detail→delete
│
├── sample_data/
│   ├── invoices/
│   │   ├── sample_de_invoice.txt   ← German invoice (Tesag AG)
│   │   ├── sample_fr_invoice.txt   ← French invoice (Électricité Romande SA)
│   │   └── sample_noncompliant.txt ← Non-compliant invoice (missing UID, bad rate)
│   └── seed_db.py               ← Seeds DB from txt files for demo
│
├── uploads/                     ← Uploaded invoice files (auto-created, git-ignored)
├── exports/                     ← Generated export files (auto-created, git-ignored)
│
├── .env.example                 ← Configuration template
├── requirements.txt             ← All Python dependencies
├── pytest.ini                   ← Test discovery config
└── run.py                       ← Convenience launcher (--seed, --seed-only flags)
```

---

## Pipeline

Every uploaded invoice goes through a 5-stage pipeline automatically:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INVOICE PIPELINE                             │
│                                                                     │
│  ┌──────────┐    ┌──────────┐    ┌───────────┐    ┌─────────────┐  │
│  │  UPLOAD  │───▶│   OCR    │───▶│  EXTRACT  │───▶│  COMPLIANCE │  │
│  │          │    │          │    │           │    │             │  │
│  │ PDF/PNG  │    │Tesseract │    │ 15 fields │    │ 12 rules    │  │
│  │ JPG/TIFF │    │EasyOCR   │    │ DE/FR/IT  │    │ UID format  │  │
│  │ Validate │    │Mock      │    │ EN regex  │    │ IBAN check  │  │
│  │ extension│    │          │    │ Confidence│    │ QR-bill     │  │
│  │ MIME type│    │Raw text  │    │ scoring   │    │ MWST rate   │  │
│  └──────────┘    └──────────┘    └───────────┘    └─────────────┘  │
│                                                           │         │
│                                                           ▼         │
│  ┌──────────────────────────────────────────────┐  ┌───────────┐   │
│  │                  EXPORT                      │  │   STORE   │   │
│  │                                              │  │           │   │
│  │  📊 Excel  — 4 sheets, colour-coded status   │  │  SQLite   │   │
│  │  📋 SAP CSV — BAPI_INCOMINGINVOICE_CREATE    │◀─│  Invoice  │   │
│  │  📈 Power BI JSON — denormalised payload     │  │  LineItem │   │
│  │                                              │  │Compliance │   │
│  └──────────────────────────────────────────────┘  └───────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Stage-by-stage detail

| Stage | Input | Output | Key logic |
|---|---|---|---|
| **1. Upload** | PDF / PNG / JPG / TIFF | Saved file + DB record | Extension + MIME whitelist, UUID-prefixed filename, max 20 MB |
| **2. OCR** | File path | Raw text string | Strategy pattern — swap engines via `OCR_ENGINE` env var; mock engine for CI |
| **3. Extract** | Raw text | 15-field `ExtractedFields` object | 15 compiled regex patterns with DE/FR/IT/EN alternations; confidence = fields_found / total_fields |
| **4. Compliance** | ExtractedFields | List of 12 `RuleResult` objects | Each rule returns PASS / WARNING / FAIL + human-readable message; overall = worst result |
| **5. Store** | All above | Persisted DB rows | SQLAlchemy ORM; Invoice → LineItems (1:N) → ComplianceResults (1:N) |

---

## Tech Stack & Libraries

| Category | Library | Version | Why it was chosen |
|---|---|---|---|
| **Web framework** | [FastAPI](https://fastapi.tiangolo.com) | 0.110 | Auto OpenAPI docs, async-ready, Pydantic integration, dependency injection |
| **ASGI server** | [Uvicorn](https://www.uvicorn.org) | 0.29 | Production ASGI server; `--reload` for dev |
| **ORM** | [SQLAlchemy](https://www.sqlalchemy.org) | 2.0 | Declarative ORM, Postgres-ready, relationship loading, in-memory SQLite for tests |
| **Validation** | [Pydantic v2](https://docs.pydantic.dev) | 2.x | Fast schema validation, `from_attributes=True` for ORM serialisation |
| **Settings** | [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | 2.x | `.env` file loading, type-safe config |
| **OCR (primary)** | [pytesseract](https://github.com/madmaze/pytesseract) | 0.3 | Python wrapper for Tesseract; supports DE/FR/IT/EN language packs |
| **PDF → images** | [pdf2image](https://github.com/Belval/pdf2image) | 1.17 | Converts PDF pages to PIL images for Tesseract |
| **OCR (alternative)** | [EasyOCR](https://github.com/JaidedAI/EasyOCR) | 1.7 | Better multilingual accuracy; heavier install |
| **Image processing** | [Pillow](https://pillow.readthedocs.io) | 10.x | PIL image loading and preprocessing |
| **Excel export** | [openpyxl](https://openpyxl.readthedocs.io) | 3.1 | Write .xlsx with 4 sheets, colour fills, auto column widths |
| **Data processing** | [pandas](https://pandas.pydata.org) | 2.x | DataFrame operations for export service |
| **Logging** | [loguru](https://loguru.readthedocs.io) | 0.7 | Structured logging with file rotation, zero config |
| **Testing** | [pytest](https://pytest.org) | 8.x | Test discovery, fixtures, parametrize |
| **Test client** | [httpx](https://www.python-httpx.org) | 0.27 | Async-capable TestClient for FastAPI integration tests |
| **CORS** | FastAPI built-in | — | `CORSMiddleware` for browser clients and Power BI |
| **DB driver** | sqlite3 (stdlib) | — | Zero-install default; swap for psycopg2 for Postgres |

### Why these choices matter for interviews

- **FastAPI over Flask/Django**: async-first, automatic OpenAPI, native Pydantic — ideal for document processing APIs that need to handle concurrent uploads
- **SQLAlchemy 2.0 ORM**: clean separation between DB schema and API schema (Pydantic); one codebase runs on SQLite locally and Postgres in production with zero code changes
- **Strategy pattern for OCR**: `BaseOCREngine` ABC lets you swap Tesseract ↔ EasyOCR ↔ Mock via env var — critical for CI (no Tesseract binary needed) and for future cloud OCR (AWS Textract, Azure Form Recognizer)
- **StaticPool in tests**: SQLite in-memory without `StaticPool` creates a new DB per connection — each `create_all` and each query would see different databases. StaticPool forces a single shared connection, making in-memory testing reliable

---

## Compliance Rules

The engine evaluates 12 rules per invoice, each returning PASS / WARNING / FAIL:

| Rule ID | Category | Description | Swiss Legal Basis |
|---|---|---|---|
| `CH_INVNUM_PRESENT` | mandatory | Invoice number present | OR Art. 957a |
| `CH_VENDOR_PRESENT` | identity | Vendor name present | OR Art. 957a |
| `CH_DATE_PRESENT` | mandatory | Invoice date present | OR Art. 957a |
| `CH_DUEDATE_PRESENT` | mandatory | Due date present and after invoice date | OR Art. 957a |
| `CH_CURRENCY` | mandatory | Currency is CHF, EUR, or USD | MWSTG |
| `CH_TOTAL_PRESENT` | mandatory | Positive total amount present | OR Art. 957a |
| `CH_UID_FORMAT` | identity | Swiss UID in `CHE-xxx.xxx.xxx` format | MWSTG Art. 25 |
| `CH_IBAN_FORMAT` | payment | Swiss IBAN: CH prefix, exactly 21 characters | ISO 13616 |
| `CH_QR_FORMAT` | payment | QR-bill reference: 26–27 digits (SIX Group standard) | SIX QR-Rechnung |
| `CH_VAT_PRESENT` | tax | VAT / MWST number present | MWSTG Art. 25 |
| `CH_VAT_RATE` | tax | Rate is valid Swiss rate: 8.1%, 2.6%, 3.8%, or 0% | MWSTG Art. 25 |
| `CH_TAX_CALC` | tax | Tax amount is consistent with rate × net (±2% tolerance) | MWSTG |
| `CH_TAX_GT_TOTAL` | tax | Tax amount must not exceed total amount | Accounting |
| `CH_AMOUNT_SUSPICIOUS` | mandatory | Zero total or suspiciously round large amount | Best practice |
| `CH_DATE_ORDER` | mandatory | Invoice date must be on or before due date | OR Art. 957a |
| `CH_PAYMENT_TERMS` | mandatory | Payment terms present and not exceeding 365 days | Best practice |

### Compliance scoring

- **COMPLIANT** — all mandatory rules PASS
- **WARNING** — all mandatory rules PASS, at least one optional rule WARNING
- **NON_COMPLIANT** — at least one mandatory rule FAIL

---

## Fraud & Anomaly Detection (v1.1)

Every invoice is automatically analysed for fraud signals after compliance checking. An **anomaly score (0–100)** is computed from 8 rule-based detectors:

| Detector | Score | Severity | What it catches |
|---|---|---|---|
| `DUPLICATE_INVOICE_NUMBER` | 40 | critical | Same invoice number already in the DB |
| `SAME_IBAN_DIFFERENT_VENDOR` | 35 | critical | Payment redirection — IBAN already belongs to a different vendor |
| `INVOICE_DATE_FUTURE` | 35 | critical | Invoice date is in the future |
| `AMOUNT_MISMATCH` | 30 | high | Tax amount exceeds total amount (impossible accounting) |
| `AMOUNT_UNUSUALLY_HIGH` | 25 | high | Amount is > 3 standard deviations above vendor's historical average |
| `MISSING_VAT_UID` | 20 | medium | No VAT number or Swiss UID on invoice |
| `SUSPICIOUS_DUE_DATE` | 15 | medium | Due date is < 3 days or > 365 days after invoice date |
| `UNUSUAL_CURRENCY` | 10 | low | Currency is not CHF, EUR, or USD |

**Risk levels:** low (0–19) · medium (20–39) · high (40–69) · critical (70–100)

Each flag includes a `description` and a `recommended_action` for the AP team.

### Anomaly API

```
GET  /invoices/{id}/anomalies        → stored anomaly report + all flags
POST /invoices/{id}/anomalies/rerun  → re-run detection on existing invoice
```

Example response:
```json
{
  "invoice_id": 5,
  "anomaly_score": 75,
  "risk_level": "critical",
  "flags": [
    {
      "anomaly_type": "SAME_IBAN_DIFFERENT_VENDOR",
      "severity": "critical",
      "score_contribution": 35,
      "description": "IBAN CH56... already used by vendor 'LegitCo AG' (invoice #3).",
      "recommended_action": "Possible payment redirection fraud. Verify IBAN directly with vendor via phone — not email."
    },
    {
      "anomaly_type": "INVOICE_DATE_FUTURE",
      "severity": "critical",
      "score_contribution": 35,
      "description": "Invoice date 2026-08-15 is in the future (today: 2026-05-17).",
      "recommended_action": "Reject invoice. Request a corrected invoice with a valid date."
    }
  ]
}
```

---

## Supported Invoice Languages

Language is auto-detected per invoice from keyword density:

| Language | Keywords detected | Sample fields |
|---|---|---|
| 🇩🇪 German | Rechnung, MWST, Fälligkeit | Rechnungsnummer, Fälligkeitsdatum, Mehrwertsteuer |
| 🇫🇷 French | Facture, TVA, Échéance | Numéro de facture, Date d'échéance, TVA |
| 🇮🇹 Italian | Fattura, IVA, Scadenza | Numero fattura, Data scadenza, IVA |
| 🇬🇧 English | Invoice, VAT, Due date | Invoice Number, Due Date, VAT |

---

## API Endpoints

Base URL: `http://localhost:8000` — Interactive docs at `/docs`

### Invoices

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/invoices/upload` | Upload PDF/image → run full pipeline → return invoice + compliance |
| `GET` | `/invoices/` | List all invoices (paginated: `skip`, `limit`; filterable: `status`, `language`) |
| `GET` | `/invoices/{id}` | Full invoice detail with all compliance results |
| `GET` | `/invoices/{id}/raw` | Raw OCR text for debugging |
| `POST` | `/invoices/{id}/reprocess` | Re-run OCR + extraction + compliance on existing file |
| `DELETE` | `/invoices/{id}` | Delete invoice record and uploaded file |
| `GET` | `/invoices/{id}/anomalies` | Anomaly report with score and all fraud flags |
| `POST` | `/invoices/{id}/anomalies/rerun` | Re-run anomaly detection on existing invoice |

### Compliance

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/compliance/{id}` | Compliance summary + all 12 rule results for one invoice |
| `GET` | `/compliance/stats/overview` | Aggregate: total invoices, pass rate, most failed rules |

### Exports

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/exports/excel` | Download `.xlsx` report (4 sheets, colour-coded) |
| `GET` | `/exports/sap-csv` | Download SAP FI-compatible CSV |
| `GET` | `/exports/powerbi-json` | Download Power BI denormalised JSON |

### Dashboard

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/dashboard/stats` | KPI aggregates: counts, pass rates, amounts by currency |
| `GET` | `/dashboard/vendors` | Per-vendor invoice count and compliance rate |

---

## Export Formats

### Excel (.xlsx)
Four sheets generated with openpyxl:
- **Summary** — KPI table: total invoices, compliant count, pass rate, total CHF
- **Invoices** — one row per invoice with all extracted fields
- **Line Items** — all line items across all invoices
- **Compliance Results** — each rule result (pass/fail/warning) per invoice

Colour coding: 🟢 COMPLIANT (green fill) | 🟡 WARNING (amber) | 🔴 NON_COMPLIANT (red)

### SAP CSV
Semicolon-delimited. Column names map directly to `BAPI_INCOMINGINVOICE_CREATE` / MIRO fields:

```
COMPANY_CODE; DOC_TYPE; PSTNG_DATE; REF_DOC_NO; GROSS_AMOUNT; CURRENCY;
VAT_REG_NO; IBAN; SWISS_UID; QR_REFERENCE; VENDOR_NAME; COMPLIANCE_STATUS
```

### Power BI JSON
Denormalised payload — each record contains invoice + compliance + line items:

```json
{
  "metadata": { "schema_version": "1.0", "generated_at": "2025-01-15T10:30:00Z" },
  "invoices": [
    {
      "id": 1,
      "invoice_number": "RE-2024-0042",
      "vendor_name": "Tesag AG",
      "total_amount": 3444.45,
      "currency": "CHF",
      "compliance_status": "COMPLIANT",
      "compliance_results": [...],
      "line_items": [...]
    }
  ]
}
```

Connect via Power BI → **Get Data** → **Web** → paste `/exports/powerbi-json` URL.

---

## Quick Start

### 1. Clone and set up

```bash
git clone https://github.com/lari98/swiss-invoice-compliance.git
cd swiss-invoice-compliance

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — set OCR_ENGINE=mock to skip Tesseract installation for local testing
```

### 3. Seed sample data and start

```bash
python run.py --seed
```

Or step by step:
```bash
python sample_data/seed_db.py      # load 3 sample invoices
uvicorn app.main:app --reload --port 8000
```

### 4. Explore

- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health
- List invoices: http://localhost:8000/invoices/
- Download Excel: http://localhost:8000/exports/excel

---

## Configuration

Copy `.env.example` to `.env` and adjust:

```env
# Database — SQLite (default) or Postgres
DATABASE_URL=sqlite:///./swiss_invoices.db

# OCR engine: mock | tesseract | easyocr
OCR_ENGINE=mock

# Tesseract options (only needed if OCR_ENGINE=tesseract)
TESSERACT_LANGUAGES=deu+fra+ita+eng
# TESSERACT_CMD=C:/Program Files/Tesseract-OCR/tesseract.exe  # Windows

# File storage
UPLOAD_DIR=uploads
EXPORT_DIR=exports
MAX_UPLOAD_MB=20

# API
API_HOST=0.0.0.0
API_PORT=8000
```

---

## OCR Setup

### Option A: Mock (no install — ideal for testing and CI)
```env
OCR_ENGINE=mock
```
The mock engine returns deterministic fake text. All 86 tests run without Tesseract installed.

### Option B: Tesseract (recommended for real invoice images)
1. Install Tesseract: https://github.com/tesseract-ocr/tesseract
2. Install Poppler (for PDF→image conversion): https://poppler.freedesktop.org
3. Install language packs: `deu`, `fra`, `ita`, `eng`
4. Set in `.env`:
```env
OCR_ENGINE=tesseract
TESSERACT_LANGUAGES=deu+fra+ita+eng
```

### Option C: EasyOCR (better multilingual accuracy, larger install ~500 MB)
```bash
pip install easyocr
```
```env
OCR_ENGINE=easyocr
```

---

## Running Tests

```bash
# Run all 86 tests
pytest

# With coverage report
pytest --cov=app --cov-report=html

# Run only unit tests
pytest tests/test_field_extractor.py tests/test_compliance_engine.py -v

# Run only integration tests
pytest tests/test_api.py -v

# Run a specific test class
pytest tests/test_compliance_engine.py::TestUID -v
```

**Test structure:**

| File | Tests | What is covered |
|---|---|---|
| `test_field_extractor.py` | 45 | Regex patterns, amount/date parsing, language detection, confidence scoring |
| `test_compliance_engine.py` | 36 | All 16 compliance rules (12 original + 4 v1.1), edge cases, full pipeline run |
| `test_api.py` | 19 | Upload→extract→comply, list, detail, delete, reprocess, exports, dashboard |
| `test_anomaly_service.py` | 30 | All 8 anomaly detectors, score calculation, DB persistence, rerun idempotency |

All tests use an in-memory SQLite database with `StaticPool` (no file system side effects).

---

## Switching to PostgreSQL

No code changes needed — the ORM layer handles both dialects.

1. Update `.env`:
```env
DATABASE_URL=postgresql://user:password@localhost:5432/swiss_invoices
```

2. Install driver:
```bash
pip install psycopg2-binary
```

3. Restart the server — `init_db()` creates all tables automatically.

---

## Roadmap

Future improvements planned for v2.0:

| Feature | Description |
|---|---|
| **Cloud OCR** | Plug in AWS Textract or Azure Form Recognizer via the existing `BaseOCREngine` interface |
| **Async pipeline** | Move OCR processing to background task queue (Celery + Redis) for large batches |
| **Vendor master** | Link invoices to a vendor registry; flag unknown vendors |
| **Duplicate detection** | Flag invoices with same number + vendor + amount |
| **Email ingest** | IMAP listener to auto-process invoices from a dedicated inbox |
| **Frontend** | React dashboard consuming the `/dashboard` and `/compliance` endpoints |
| **Docker** | `Dockerfile` + `docker-compose.yml` with Tesseract and Postgres |
| **Auth** | JWT authentication on upload and export endpoints |

---

## Portfolio Talking Points

This project is designed to demonstrate production engineering skills to recruiters and hiring managers:

**Backend engineering**
- FastAPI with dependency injection, file upload validation, background pipeline, proper HTTP status codes (201, 404, 422, 500)
- Clean separation: routers → services → models — no business logic in route handlers

**Database design**
- SQLAlchemy 2.0 ORM with `Invoice → LineItem` and `Invoice → ComplianceResult` relationships
- Postgres-ready abstraction: swap `DATABASE_URL` env var, zero code changes
- Pydantic v2 schemas separate from ORM models (`from_attributes=True`)

**OCR & NLP**
- Pluggable OCR architecture using Strategy pattern (`BaseOCREngine` ABC)
- 15 compiled regex patterns with DE/FR/IT/EN multilingual alternations
- Negative lookaheads to avoid false matches (e.g. `(?![\s-]*Nr)` prevents UID capture from MWST-Nr lines)
- Confidence scoring per invoice

**Swiss domain expertise**
- UID format: `CHE-xxx.xxx.xxx` (MWSTG Art. 25)
- QR-Rechnung reference: 26–27 digit string (SIX Group standard)
- MWST rates: 8.1% (standard), 2.6% (accommodation), 3.8% (special), 0% (exempt)
- IBAN: CH prefix, exactly 21 characters (ISO 13616)

**Data integration**
- Excel export with colour-coded compliance status (openpyxl)
- SAP BAPI_INCOMINGINVOICE_CREATE field mapping for direct ERP import
- Power BI denormalised JSON with schema versioning

**Testing**
- 86 tests: 45 unit, 22 unit, 19 integration
- In-memory SQLite with `StaticPool` — no test database setup needed
- `engine` patching in `conftest.py` before app import — correct isolation pattern

**Software design**
- SOLID principles throughout: Single Responsibility (each service has one job), Open/Closed (add OCR engines without changing existing code), Dependency Inversion (routes depend on `get_db()` abstraction)
- No single-file scripts — clean module boundaries across 15+ files

**Relevant roles:** Finance automation, ERP integration, SAP consulting, accounting technology, Swiss RegTech, DACH insurance, document processing AI, backend Python engineering.

---

## License

MIT — free to use, modify, and include in your portfolio.
