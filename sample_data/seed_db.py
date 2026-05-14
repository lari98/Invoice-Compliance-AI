"""
Seed the database with sample invoices.
Usage: python sample_data/seed_db.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from app.models.database import SessionLocal, init_db
from app.models.invoice import Invoice, LineItem, ComplianceResult, ProcessingStatus, InvoiceLanguage, ComplianceStatus
from app.services.field_extractor import extract_fields
from app.services.compliance_engine import run_compliance_checks

SAMPLE_DIR = Path(__file__).parent / "invoices"
LANG_MAP   = {"de": InvoiceLanguage.DE, "fr": InvoiceLanguage.FR, "it": InvoiceLanguage.IT, "en": InvoiceLanguage.EN}
STATUS_MAP = {"pass": ComplianceStatus.PASS, "fail": ComplianceStatus.FAIL, "warning": ComplianceStatus.WARNING}


def seed():
    init_db()
    db = SessionLocal()
    txt_files = sorted(SAMPLE_DIR.glob("*.txt"))
    if not txt_files:
        logger.error(f"No .txt files found in {SAMPLE_DIR}")
        return
    for txt in txt_files:
        raw = txt.read_text(encoding="utf-8")
        inv = Invoice(original_filename=txt.stem + ".pdf", file_path=str(txt), file_type="pdf",
                      file_size_bytes=len(raw.encode()), status=ProcessingStatus.PROCESSING,
                      ocr_engine_used="mock", raw_text=raw)
        db.add(inv); db.flush()
        ex = extract_fields(raw)
        inv.invoice_number = ex.invoice_number; inv.vendor_name = ex.vendor_name
        inv.vendor_country = ex.vendor_country; inv.vat_number = ex.vat_number
        inv.swiss_uid = ex.swiss_uid; inv.iban = ex.iban; inv.qr_reference = ex.qr_reference
        inv.currency = ex.currency; inv.total_amount = ex.total_amount; inv.tax_amount = ex.tax_amount
        inv.tax_rate_percent = ex.tax_rate_percent; inv.invoice_date = ex.invoice_date
        inv.due_date = ex.due_date; inv.payment_terms = ex.payment_terms
        inv.extraction_confidence = ex.extraction_confidence
        inv.language = LANG_MAP.get(ex.language, InvoiceLanguage.UNKNOWN)
        for li in ex.line_items:
            db.add(LineItem(invoice_id=inv.id, position=li.position, description=li.description,
                            quantity=li.quantity, unit=li.unit, unit_price=li.unit_price, total_price=li.total_price))
        for cr in run_compliance_checks(ex):
            db.add(ComplianceResult(invoice_id=inv.id, rule_id=cr.rule_id, rule_name=cr.rule_name,
                                    category=cr.category, status=STATUS_MAP.get(cr.status, ComplianceStatus.UNKNOWN),
                                    message=cr.message, field_checked=cr.field_checked,
                                    actual_value=cr.actual_value, expected_pattern=cr.expected_pattern))
        inv.status = ProcessingStatus.COMPLETED; db.commit()
        logger.info(f"Seeded: {txt.name} → ID {inv.id} | {ex.language.upper()} | {inv.overall_compliance_status}")
    db.close()
    logger.success(f"Done. {len(txt_files)} invoices seeded.")


if __name__ == "__main__":
    seed()
