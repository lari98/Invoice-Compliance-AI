"""
Unit tests for the anomaly detection service (v1.1).
All tests use an in-memory SQLite DB via the shared conftest fixtures.
"""
import pytest
from datetime import date, timedelta

from app.services.anomaly_service import (
    run_anomaly_detection,
    _dup_invoice_number,
    _same_iban_diff_vendor,
    _invoice_date_future,
    _amount_mismatch,
    _missing_vat_uid,
    _suspicious_due_date,
    _unusual_currency,
)
from app.services.field_extractor import ExtractionResult as ExtractedFields
from app.models.invoice import Invoice, ProcessingStatus


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fields(**kwargs) -> ExtractedFields:
    defaults = dict(
        invoice_number="INV-001", vendor_name="Acme AG",
        total_amount=1500.0, tax_amount=121.5, tax_rate_percent=8.1,
        currency="CHF", iban="CH9300762011623852957",
        swiss_uid="CHE-123.456.789", vat_number="CHE-123.456.789",
        invoice_date="2024-01-10", due_date="2024-02-10",
        payment_terms="30 days net",
    )
    defaults.update(kwargs)
    return ExtractedFields(**defaults)


def _invoice(db, **kwargs) -> Invoice:
    defaults = dict(
        original_filename="test.pdf", file_path="/tmp/test.pdf",
        file_type="pdf", status=ProcessingStatus.COMPLETED,
        invoice_number="INV-001", vendor_name="Acme AG",
        total_amount=1500.0, currency="CHF",
    )
    defaults.update(kwargs)
    inv = Invoice(**defaults)
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


# ── Duplicate invoice number ──────────────────────────────────────────────────

class TestDuplicateInvoiceNumber:
    def test_no_duplicate(self, db):
        inv = _invoice(db, invoice_number="INV-UNIQUE-999")
        fields = _fields(invoice_number="INV-UNIQUE-999")
        assert _dup_invoice_number(inv, fields, db) is None

    def test_duplicate_detected(self, db):
        _invoice(db, invoice_number="INV-DUP-001")
        inv2 = _invoice(db, invoice_number="INV-DUP-001")
        fields = _fields(invoice_number="INV-DUP-001")
        flag = _dup_invoice_number(inv2, fields, db)
        assert flag is not None
        assert flag.anomaly_type == "DUPLICATE_INVOICE_NUMBER"
        assert flag.score_contribution == 40

    def test_no_number_skipped(self, db):
        inv = _invoice(db)
        fields = _fields(invoice_number=None)
        assert _dup_invoice_number(inv, fields, db) is None


# ── Same IBAN, different vendor ───────────────────────────────────────────────

class TestSameIBANDifferentVendor:
    def test_clean(self, db):
        inv = _invoice(db, vendor_name="Acme AG", iban="CH9300762011623852957")
        fields = _fields(vendor_name="Acme AG", iban="CH9300762011623852957")
        assert _same_iban_diff_vendor(inv, fields, db) is None

    def test_conflict(self, db):
        _invoice(db, vendor_name="LegitCo AG", iban="CH5604835012345678009")
        inv2 = _invoice(db, vendor_name="FraudCo GmbH", iban="CH5604835012345678009")
        fields = _fields(vendor_name="FraudCo GmbH", iban="CH5604835012345678009")
        flag = _same_iban_diff_vendor(inv2, fields, db)
        assert flag is not None
        assert flag.anomaly_type == "SAME_IBAN_DIFFERENT_VENDOR"
        assert flag.score_contribution == 35

    def test_no_iban_skipped(self, db):
        inv = _invoice(db)
        fields = _fields(iban=None)
        assert _same_iban_diff_vendor(inv, fields, db) is None


# ── Invoice date in the future ────────────────────────────────────────────────

class TestInvoiceDateFuture:
    def test_past_date_ok(self, db):
        inv = _invoice(db)
        fields = _fields(invoice_date="2020-06-01")
        assert _invoice_date_future(inv, fields, db) is None

    def test_future_date_flagged(self, db):
        inv = _invoice(db)
        future = (date.today() + timedelta(days=30)).isoformat()
        fields = _fields(invoice_date=future)
        flag = _invoice_date_future(inv, fields, db)
        assert flag is not None
        assert flag.anomaly_type == "INVOICE_DATE_FUTURE"
        assert flag.score_contribution == 35

    def test_no_date_skipped(self, db):
        inv = _invoice(db)
        assert _invoice_date_future(inv, _fields(invoice_date=None), db) is None


# ── Amount mismatch ───────────────────────────────────────────────────────────

class TestAmountMismatch:
    def test_valid_amounts(self, db):
        inv = _invoice(db)
        fields = _fields(tax_amount=121.5, total_amount=1500.0)
        assert _amount_mismatch(inv, fields, db) is None

    def test_tax_gt_total_flagged(self, db):
        inv = _invoice(db)
        fields = _fields(tax_amount=2000.0, total_amount=1500.0)
        flag = _amount_mismatch(inv, fields, db)
        assert flag is not None
        assert flag.anomaly_type == "AMOUNT_MISMATCH"
        assert flag.score_contribution == 30

    def test_missing_amounts_skipped(self, db):
        inv = _invoice(db)
        assert _amount_mismatch(inv, _fields(tax_amount=None), db) is None


# ── Missing VAT/UID ───────────────────────────────────────────────────────────

class TestMissingVatUid:
    def test_uid_present_ok(self, db):
        inv = _invoice(db)
        fields = _fields(swiss_uid="CHE-123.456.789", vat_number=None)
        assert _missing_vat_uid(inv, fields, db) is None

    def test_vat_present_ok(self, db):
        inv = _invoice(db)
        fields = _fields(swiss_uid=None, vat_number="CHE-111.222.333")
        assert _missing_vat_uid(inv, fields, db) is None

    def test_both_missing_flagged(self, db):
        inv = _invoice(db)
        fields = _fields(swiss_uid=None, vat_number=None)
        flag = _missing_vat_uid(inv, fields, db)
        assert flag is not None
        assert flag.anomaly_type == "MISSING_VAT_UID"
        assert flag.score_contribution == 20


# ── Suspicious due date ───────────────────────────────────────────────────────

class TestSuspiciousDueDate:
    def test_normal_30_days_ok(self, db):
        inv = _invoice(db)
        fields = _fields(invoice_date="2024-01-01", due_date="2024-01-31")
        assert _suspicious_due_date(inv, fields, db) is None

    def test_one_day_flagged(self, db):
        inv = _invoice(db)
        fields = _fields(invoice_date="2024-01-01", due_date="2024-01-02")
        flag = _suspicious_due_date(inv, fields, db)
        assert flag is not None
        assert flag.anomaly_type == "SUSPICIOUS_DUE_DATE"
        assert flag.severity == "medium"

    def test_over_365_days_flagged(self, db):
        inv = _invoice(db)
        fields = _fields(invoice_date="2024-01-01", due_date="2025-05-01")
        flag = _suspicious_due_date(inv, fields, db)
        assert flag is not None
        assert flag.severity == "low"


# ── Unusual currency ──────────────────────────────────────────────────────────

class TestUnusualCurrency:
    def test_chf_ok(self, db):
        inv = _invoice(db)
        assert _unusual_currency(inv, _fields(currency="CHF"), db) is None

    def test_eur_ok(self, db):
        inv = _invoice(db)
        assert _unusual_currency(inv, _fields(currency="EUR"), db) is None

    def test_rub_flagged(self, db):
        inv = _invoice(db)
        flag = _unusual_currency(inv, _fields(currency="RUB"), db)
        assert flag is not None
        assert flag.anomaly_type == "UNUSUAL_CURRENCY"
        assert flag.score_contribution == 10


# ── Full run_anomaly_detection ────────────────────────────────────────────────

class TestRunAnomalyDetection:
    def test_clean_invoice_low_score(self, db):
        inv = _invoice(db, invoice_number="CLEAN-INV-001")
        fields = _fields(invoice_number="CLEAN-INV-001")
        report = run_anomaly_detection(inv, fields, db)
        assert report.anomaly_score <= 20
        assert report.risk_level in ("low", "medium")

    def test_future_date_raises_score(self, db):
        inv = _invoice(db, invoice_number="FUTURE-INV-001")
        future = (date.today() + timedelta(days=10)).isoformat()
        fields = _fields(invoice_number="FUTURE-INV-001", invoice_date=future)
        report = run_anomaly_detection(inv, fields, db)
        assert report.anomaly_score >= 35

    def test_score_capped_at_100(self, db):
        inv = _invoice(db, invoice_number="MULTI-FLAG-001")
        future = date.today() + timedelta(days=10)
        fields = _fields(
            invoice_number="MULTI-FLAG-001",
            invoice_date=future,
            tax_amount=9999.0, total_amount=100.0,
            swiss_uid=None, vat_number=None,
            currency="XYZ",
        )
        report = run_anomaly_detection(inv, fields, db)
        assert report.anomaly_score <= 100
        assert report.risk_level in ("high", "critical")

    def test_flags_persisted_to_db(self, db):
        from app.models.invoice import AnomalyFlag
        inv = _invoice(db, invoice_number="PERSIST-INV-001")
        future = date.today() + timedelta(days=5)
        fields = _fields(invoice_number="PERSIST-INV-001", invoice_date=future)
        run_anomaly_detection(inv, fields, db)
        flags = db.query(AnomalyFlag).filter(AnomalyFlag.invoice_id == inv.id).all()
        assert len(flags) >= 1

    def test_rerun_clears_old_flags(self, db):
        from app.models.invoice import AnomalyFlag
        inv = _invoice(db, invoice_number="RERUN-INV-001")
        fields = _fields(invoice_number="RERUN-INV-001", swiss_uid=None, vat_number=None)
        run_anomaly_detection(inv, fields, db)
        count_1 = db.query(AnomalyFlag).filter(AnomalyFlag.invoice_id == inv.id).count()
        # Rerun with clean fields — old flags should be cleared
        clean_fields = _fields(invoice_number="RERUN-INV-001")
        run_anomaly_detection(inv, clean_fields, db)
        count_2 = db.query(AnomalyFlag).filter(AnomalyFlag.invoice_id == inv.id).count()
        assert count_2 < count_1 or count_2 == 0
