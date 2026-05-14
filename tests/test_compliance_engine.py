import pytest
from app.services.field_extractor import ExtractionResult
from app.services.compliance_engine import (
    check_swiss_uid, check_iban, check_vat_rate, check_tax_consistency,
    check_qr_reference, check_invoice_number, check_invoice_date, check_due_date,
    check_currency, check_total_amount, run_compliance_checks, summarise_compliance
)


def make(**kw) -> ExtractionResult:
    base = dict(invoice_number="INV-001", vendor_name="Test AG", vendor_country="CH",
                vat_number="CHE-123.456.789 MWST", swiss_uid="CHE-123.456.789",
                iban="CH5604835012345678009", qr_reference="21000000000313947143000090",
                currency="CHF", total_amount=3729.45, tax_amount=279.45, tax_rate_percent=8.1,
                invoice_date="2024-03-15", due_date="2024-04-15", payment_terms="30 Tage netto", language="de")
    base.update(kw)
    return ExtractionResult(**base)


class TestUID:
    def test_valid(self):    assert check_swiss_uid(make()).status == "pass"
    def test_missing(self):  assert check_swiss_uid(make(swiss_uid=None)).status == "warning"
    def test_bad_fmt(self):  assert check_swiss_uid(make(swiss_uid="CHE-123456789")).status == "fail"


class TestIBAN:
    def test_valid(self):        assert check_iban(make()).status == "pass"
    def test_missing(self):      assert check_iban(make(iban=None)).status == "fail"
    def test_short(self):        assert check_iban(make(iban="CH560483501234567800")).status == "fail"
    def test_foreign(self):      assert check_iban(make(iban="DE89370400440532013000")).status == "warning"


class TestVATRate:
    @pytest.mark.parametrize("rate", [8.1, 7.7, 2.5, 2.6, 3.8, 0.0])
    def test_valid_rates(self, rate): assert check_vat_rate(make(tax_rate_percent=rate)).status == "pass"
    def test_invalid(self):           assert check_vat_rate(make(tax_rate_percent=20.0)).status == "fail"
    def test_missing(self):           assert check_vat_rate(make(tax_rate_percent=None)).status == "warning"


class TestTaxConsistency:
    def test_consistent(self):    assert check_tax_consistency(make()).status == "pass"
    def test_inconsistent(self):  assert check_tax_consistency(make(tax_amount=500.0)).status == "warning"
    def test_missing(self):       assert check_tax_consistency(make(total_amount=None, tax_amount=None, tax_rate_percent=None)).status == "warning"


class TestDates:
    def test_valid(self):      assert check_invoice_date(make()).status == "pass"
    def test_missing(self):    assert check_invoice_date(make(invoice_date=None)).status == "fail"
    def test_due_before(self): assert check_due_date(make(due_date="2024-02-01")).status == "fail"
    def test_due_missing(self):assert check_due_date(make(due_date=None)).status == "warning"


class TestCurrency:
    def test_chf(self):     assert check_currency(make()).status == "pass"
    def test_eur(self):     assert check_currency(make(currency="EUR")).status == "warning"
    def test_missing(self): assert check_currency(make(currency=None)).status == "fail"


class TestTotal:
    def test_positive(self):  assert check_total_amount(make()).status == "pass"
    def test_missing(self):   assert check_total_amount(make(total_amount=None)).status == "fail"
    def test_negative(self):  assert check_total_amount(make(total_amount=-1.0)).status == "fail"


class TestFullRun:
    def test_compliant(self):
        s = summarise_compliance(run_compliance_checks(make()))
        assert s["overall_status"] == "pass"
        assert s["failed"] == 0

    def test_noncompliant(self):
        s = summarise_compliance(run_compliance_checks(
            make(swiss_uid=None, iban=None, invoice_number=None, currency="GBP", tax_rate_percent=20.0, total_amount=None)))
        assert s["overall_status"] == "fail"
        assert s["failed"] > 0

    def test_twelve_rules(self):
        assert len(run_compliance_checks(make())) == 12
