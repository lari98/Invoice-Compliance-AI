from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, BackgroundTasks
from sqlalchemy.orm import Session
from loguru import logger
from app.models.database import get_db
from app.models.invoice import Invoice, LineItem, ComplianceResult, ProcessingStatus, InvoiceLanguage, ComplianceStatus
from app.models.schemas import InvoiceOut, InvoiceSummary, UploadResponse
from app.services.ocr_service import get_ocr_engine
from app.services.field_extractor import extract_fields
from app.services.compliance_engine import run_compliance_checks
from app.utils.file_handler import validate_upload, save_upload, delete_upload

router = APIRouter(prefix="/invoices", tags=["Invoices"])
LANG_MAP   = {"de": InvoiceLanguage.DE, "fr": InvoiceLanguage.FR, "it": InvoiceLanguage.IT, "en": InvoiceLanguage.EN}
STATUS_MAP = {"pass": ComplianceStatus.PASS, "fail": ComplianceStatus.FAIL, "warning": ComplianceStatus.WARNING}


def _process_invoice(invoice_id: int, db: Session):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        return
    try:
        invoice.status = ProcessingStatus.PROCESSING
        db.commit()
        engine = get_ocr_engine()
        raw_text = engine.extract_text(file_path=str(invoice.file_path), file_type=invoice.file_type or "pdf")
        invoice.raw_text = raw_text
        invoice.ocr_engine_used = engine.engine_name
        ex = extract_fields(raw_text)
        invoice.invoice_number  = ex.invoice_number
        invoice.vendor_name     = ex.vendor_name
        invoice.vendor_country  = ex.vendor_country
        invoice.vat_number      = ex.vat_number
        invoice.swiss_uid       = ex.swiss_uid
        invoice.iban            = ex.iban
        invoice.qr_reference    = ex.qr_reference
        invoice.currency        = ex.currency
        invoice.total_amount    = ex.total_amount
        invoice.tax_amount      = ex.tax_amount
        invoice.tax_rate_percent = ex.tax_rate_percent
        invoice.invoice_date    = ex.invoice_date
        invoice.due_date        = ex.due_date
        invoice.payment_terms   = ex.payment_terms
        invoice.extraction_confidence = ex.extraction_confidence
        invoice.language        = LANG_MAP.get(ex.language, InvoiceLanguage.UNKNOWN)
        db.query(LineItem).filter(LineItem.invoice_id == invoice_id).delete()
        for li in ex.line_items:
            db.add(LineItem(invoice_id=invoice_id, position=li.position, description=li.description,
                            quantity=li.quantity, unit=li.unit, unit_price=li.unit_price, total_price=li.total_price))
        db.query(ComplianceResult).filter(ComplianceResult.invoice_id == invoice_id).delete()
        for cr in run_compliance_checks(ex):
            db.add(ComplianceResult(invoice_id=invoice_id, rule_id=cr.rule_id, rule_name=cr.rule_name,
                                    category=cr.category, status=STATUS_MAP.get(cr.status, ComplianceStatus.UNKNOWN),
                                    message=cr.message, field_checked=cr.field_checked,
                                    actual_value=cr.actual_value, expected_pattern=cr.expected_pattern))
        invoice.status = ProcessingStatus.COMPLETED
        db.commit()
        logger.info(f"Invoice {invoice_id} processed OK.")
    except Exception as exc:
        logger.error(f"Invoice {invoice_id} failed: {exc}")
        invoice.status = ProcessingStatus.FAILED
        invoice.processing_error = str(exc)
        db.commit()


@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload_invoice(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    ext = validate_upload(file)
    invoice = Invoice(original_filename=file.filename or "unknown", file_path="", file_type=ext, status=ProcessingStatus.PENDING)
    db.add(invoice)
    db.flush()
    saved_path, size_bytes = await save_upload(file, invoice.id)
    invoice.file_path = str(saved_path)
    invoice.file_size_bytes = size_bytes
    db.commit()
    _process_invoice(invoice.id, db)
    db.refresh(invoice)
    return UploadResponse(invoice_id=invoice.id, filename=invoice.original_filename,
                          message="Invoice uploaded and processed.", status=invoice.status.value)


@router.get("/", response_model=list[InvoiceSummary])
def list_invoices(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
                  status: str | None = None, language: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Invoice)
    if status:   q = q.filter(Invoice.status == status)
    if language: q = q.filter(Invoice.language == language)
    invoices = q.order_by(Invoice.created_at.desc()).offset(skip).limit(limit).all()
    return invoices


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv: raise HTTPException(404, "Invoice not found.")
    return inv


@router.get("/{invoice_id}/raw")
def get_raw_text(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv: raise HTTPException(404, "Invoice not found.")
    return {"invoice_id": invoice_id, "raw_text": inv.raw_text}


@router.post("/{invoice_id}/reprocess", response_model=UploadResponse)
def reprocess(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv: raise HTTPException(404, "Invoice not found.")
    _process_invoice(invoice_id, db)
    db.refresh(inv)
    return UploadResponse(invoice_id=inv.id, filename=inv.original_filename, message="Reprocessed.", status=inv.status.value)


@router.delete("/{invoice_id}", status_code=204)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv: raise HTTPException(404, "Invoice not found.")
    delete_upload(inv.file_path)
    db.delete(inv)
    db.commit()
    return None
