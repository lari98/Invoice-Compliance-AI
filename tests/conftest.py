"""
pytest configuration.

Key fix: StaticPool forces SQLAlchemy to reuse ONE SQLite in-memory
connection for the entire test. Without it every new connection gets
its own blank in-memory DB, so tables created in the fixture are
invisible to the app's DB calls.
"""
import os
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["OCR_ENGINE"]   = "mock"
os.environ["UPLOAD_DIR"]   = "/tmp/test_uploads"
os.environ["EXPORT_DIR"]   = "/tmp/test_exports"

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool          # ← the critical fix
from fastapi.testclient import TestClient

# ── Build test engine (single shared connection) ──────────────────────────────
_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,                        # all calls share ONE connection
)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

# ── Patch the app's engine BEFORE importing app modules ───────────────────────
import app.models.database as _db_module
_db_module.engine       = _engine
_db_module.SessionLocal = _Session

from app.main import app
from app.models.database import Base, get_db


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def db():
    """Fresh schema per test."""
    from app.models import invoice  # noqa — registers models
    Base.metadata.create_all(bind=_engine)
    session = _Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


@pytest.fixture(scope="function")
def client(db):
    """TestClient whose get_db dependency returns the test session."""
    def _override():          # generator override — matches FastAPI's expectation
        yield db
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Sample invoice texts ──────────────────────────────────────────────────────

SAMPLE_DE = """\
RECHNUNG
Rechnungsnummer: INV-2024-001247
Rechnungsdatum: 15.03.2024
Fälligkeitsdatum: 15.04.2024
Lieferant: Mustermann AG
Schweiz
UID: CHE-123.456.789
MWST-Nr.: CHE-123.456.789 MWST
IBAN: CH56 0483 5012 3456 7800 9
Zwischensumme CHF: 3'450.00
MWST 8.1%: 279.45
Gesamtbetrag CHF: 3'729.45
Zahlungsbedingungen: 30 Tage netto
QR-Referenz: 21 00000 00003 13947 14300 09017
"""

SAMPLE_FR = """\
FACTURE
Numéro de facture: FAC-2024-00892
Date de facture: 20.03.2024
Date d'échéance: 20.04.2024
Fournisseur: Services Numériques Sàrl
Genève, Suisse
IDE: CHE-987.654.321 TVA
IBAN: CH93 0076 2011 6238 5295 7
Montant total CHF: 5'091.51
TVA 8.1%: 381.51
Conditions de paiement: 30 jours net
"""

SAMPLE_BAD = """\
INVOICE
Invoice Number: INV-EN-2024-0055
Invoice Date: 22.03.2024
Vendor: TechSolutions Ltd. London UK
Total: GBP 3840.00
VAT 20%: GBP 640.00
"""
