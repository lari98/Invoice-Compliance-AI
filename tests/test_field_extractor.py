import pytest
from app.services.field_extractor import extract_fields, _clean_amount, _normalise_uid, _parse_date, _detect_lang
from tests.conftest import SAMPLE_DE, SAMPLE_FR, SAMPLE_BAD


class TestCleanAmount:
    def test_apostrophe(self):   assert _clean_amount("3'729.45") == 3729.45
    def test_european(self):     assert _clean_amount("3.729,45") == 3729.45
    def test_plain(self):        assert _clean_amount("279.45")   == 279.45
    def test_chf_prefix(self):   assert _clean_amount("CHF 3'729.45") == 3729.45
    def test_empty(self):        assert _clean_amount("") is None
    def test_garbage(self):      assert _clean_amount("N/A") is None


class TestNormaliseUID:
    def test_compact(self): assert _normalise_uid("CHE123456789") == "CHE-123.456.789"
    def test_spaced(self):  assert _normalise_uid("CHE 123 456 789") == "CHE-123.456.789"


class TestParseDate:
    def test_swiss_dot(self): assert _parse_date("15.03.2024") == "2024-03-15"
    def test_iso(self):       assert _parse_date("2024-03-15") == "2024-03-15"
    def test_slash(self):     assert _parse_date("15/03/2024") == "2024-03-15"


class TestLanguage:
    def test_german(self):  assert _detect_lang(SAMPLE_DE) == "de"
    def test_french(self):  assert _detect_lang(SAMPLE_FR) == "fr"
    def test_english(self): assert _detect_lang(SAMPLE_BAD) == "en"


class TestGermanExtraction:
    @pytest.fixture(autouse=True)
    def run(self): self.r = extract_fields(SAMPLE_DE)
    def test_number(self):    assert self.r.invoice_number == "INV-2024-001247"
    def test_uid(self):       assert self.r.swiss_uid == "CHE-123.456.789"
    def test_iban(self):      assert self.r.iban and self.r.iban.startswith("CH")
    def test_qr(self):        assert self.r.qr_reference and len(self.r.qr_reference) in (26,27)
    def test_currency(self):  assert self.r.currency == "CHF"
    def test_total(self):     assert abs(self.r.total_amount - 3729.45) < 0.01
    def test_tax(self):       assert self.r.tax_amount is not None and abs(self.r.tax_amount - 279.45) < 0.10
    def test_rate(self):      assert abs(self.r.tax_rate_percent - 8.1) < 0.1
    def test_inv_date(self):  assert self.r.invoice_date == "2024-03-15"
    def test_due_date(self):  assert self.r.due_date == "2024-04-15"
    def test_lang(self):      assert self.r.language == "de"
    def test_country(self):   assert self.r.vendor_country == "CH"
    def test_confidence(self):assert self.r.extraction_confidence > 0.6


class TestFrenchExtraction:
    @pytest.fixture(autouse=True)
    def run(self): self.r = extract_fields(SAMPLE_FR)
    def test_number(self):  assert self.r.invoice_number == "FAC-2024-00892"
    def test_lang(self):    assert self.r.language == "fr"
    def test_currency(self):assert self.r.currency == "CHF"
    def test_uid(self):     assert self.r.swiss_uid is not None
    def test_iban(self):    assert self.r.iban is not None


class TestNonCompliantExtraction:
    @pytest.fixture(autouse=True)
    def run(self): self.r = extract_fields(SAMPLE_BAD)
    def test_no_uid(self):         assert self.r.swiss_uid is None
    def test_currency_gbp(self):   assert self.r.currency == "GBP"
    def test_lang_en(self):        assert self.r.language == "en"
    def test_low_confidence(self): assert self.r.extraction_confidence < 0.6
