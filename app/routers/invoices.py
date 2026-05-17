"""
Invoices router — v1.2
Endpoints with full OpenAPI request/response examples.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, BackgroundTasks
from sqlalchemy.orm import Session
from loguru import logger

from app.models.database import get_db
from app.models.invoice import (
    Invoice, LineItem, ComplianceResult,
    ProcessingStatus, InvoiceLanguage, ComplianceStatus,
)
from app.models.schemas import InvoiceOut, InvoiceSummary, UploadResponse
from app.services.ocr_service import get_ocr_engine
from app.services.field_extractor import extract_fields
from app.services.compliance_engine import run_compliance_checks
from app.utils.file_handler import validate_upload, save_upload, delete_upload
from app.services.anomaly_service import run_anomaly_detection

router = APIRouter(prefix="/invoices", tags=["Invoices"])

LANG_MAP   = {"de": InvoiceLanguage.DE, "fr": InvoiceLanguage.FR,
               "it": InvoiceLanguage.IT, "en": InvoiceLanguage.EN}
STATUS_MAP = {"pass": ComplianceStatus.PASS, "fail": ComplianceStatus.FAIL,
               "warning": ComplianceStatus.WARNING}


# ── Core processing pipeline ──────────────────────────────────────────────────

def _process_invoice(invoice_id: int, db: Session):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        return
    try:
        invoice.status = ProcessingStatus.PROCESSING
        db.commit()

        engine   = get_ocr_engine()
        raw_text = engine.extract_text(
            file_path=str(invoice.file_path),
            file_type=invoice.file_type or "pdf",
        )
        invoice.raw_text       = raw_text
        invoice.ocr_engine_used = engine.engine_name

        ex = extract_fields(raw_text)
        invoice.invoice_number       = ex.invoice_number
        invoice.vendor_name          = ex.vendor_name
        invoice.vendor_country       = ex.vendor_country
        invoice.vat_number           = ex.vat_number
        invoice.swiss_uid            = ex.swiss_uid
        invoice.iban                 = ex.iban
        invoice.qr_reference         = ex.qr_reference
        invoice.currency             = ex.currency
        invoice.total_amount         = ex.total_amount
        invoice.tax_amount           = ex.tax_amount
        invoice.tax_rate_percent     = ex.tax_rate_percent
        invoice.invoice_date         = ex.invoice_date
        invoice.due_date             = ex.due_date
        invoice.payment_terms        = ex.payment_terms
        invoice.extraction_confidence = ex.extraction_confidence
        invoice.language             = LANG_MAP.get(ex.language, InvoiceLanguage.UNKNOWN)

        db.query(LineItem).filter(LineItem.invoice_id == invoice_id).delete()
        for li in ex.line_items:
            db.add(LineItem(
                invoice_id=invoice_id, position=li.position,
                description=li.description, quantity=li.quantity,
                unit=li.unit, unit_price=li.unit_price, total_price=li.total_price,
            ))

        db.query(ComplianceResult).filter(ComplianceResult.invoice_id == invoice_id).delete()
        for cr in run_compliance_checks(ex):
            db.add(ComplianceResult(
                invoice_id=invoice_id, rule_id=cr.rule_id, rule_name=cr.rule_name,
                category=cr.category,
                status=STATUS_MAP.get(cr.status, ComplianceStatus.UNKNOWN),
                message=cr.message, field_checked=cr.field_checked,
                actual_value=cr.actual_value, expected_pattern=cr.expected_pattern,
            ))

        # Anomaly detection (v1.1) — non-fatal
        try:
            run_anomaly_detection(invoice, ex, db)
        except Exception as ae:
            logger.warning(f"Anomaly detection for invoice {invoice_id} failed (non-fatal): {ae}")

        invoice.status = ProcessingStatus.COMPLETED
        db.commit()
        logger.info(f"Invoice {invoice_id} processed OK.")
    except Exception as exc:
        logger.error(f"Invoice {invoice_id} failed: {exc}")
        invoice.status          = ProcessingStatus.FAILED
        invoice.processing_error = str(exc)
        db.commit()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=201,
    summary="Upload and process an invoice",
    description="""
Upload an invoice file (PDF, JPG, PNG, TXT, HTML, XLSX). The system will:

1. Save the file to the upload directory
2. Extract text via OCR / pdfplumber (digital PDFs need no Tesseract)
3. Extract structured fields (vendor, IBAN, amounts, dates …)
4. Run **16 Swiss compliance rules**
5. Run **8 anomaly/fraud detectors**

**Accepted file types:** PDF, JPG, JPEG, PNG, TXT, HTML, XLSX, XLS

**Request example (curl):**
```bash
curl -X POST http://localhost:8000/invoices/upload \\
  -F "file=@invoice.pdf"
```

**Response example:**
```json
{
  "invoice_id": 42,
  "filename": "invoice.pdf",
  "message": "Invoice uploaded and processed.",
  "status": "completed"
}
```
""",
)
async def upload_invoice(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Invoice file — PDF, JPG, PNG, TXT, HTML, XLSX"),
    db: Session = Depends(get_db),
):
    ext     = validate_upload(file)
    invoice = Invoice(
        original_filename=file.filename or "unknown",
        file_path="", file_type=ext, status=ProcessingStatus.PENDING,
    )
    db.add(invoice)
    db.flush()
    saved_path, size_bytes = await save_upload(file, invoice.id)
    invoice.file_path       = str(saved_path)
    invoice.file_size_bytes = size_bytes
    db.commit()
    _process_invoice(invoice.id, db)
    db.refresh(invoice)
    return UploadResponse(
        invoice_id=invoice.id, filename=invoice.original_filename,
        message="Invoice uploaded and processed.", status=invoice.status.value,
    )


@router.get(
    "/",
    response_model=list[InvoiceSummary],
    summary="List all invoices",
    description="""
Returns a paginated list of invoice summaries.

**Query parameters:**
- `skip` — offset for pagination (default 0)
- `limit` — max results (default 50, max 200)
- `status` — filter by processing status: `pending | processing | completed | failed`
- `language` — filter by detected language: `de | fr | it | en | unknown`

**Request examples:**
```
GET /invoices/
GET /invoices/?skip=0&limit=20
GET /invoices/?status=completed&language=de
```

**Response example:**
```json
[
  {
    "id": 1,
    "original_filename": "rechnung_2024.pdf",
    "invoice_number": "INV-2024-001247",
    "vendor_name": "Mustermann Beratung AG",
    "currency": "CHF",
    "total_amount": 3729.45,
    "invoice_date": "2024-03-15",
    "status": "completed",
    "language": "de",
    "overall_compliance_status": "pass",
    "created_at": "2024-03-15T10:30:00"
  }
]
```
""",
)
def list_invoices(
    skip: int     = Query(0, ge=0, description="Number of records to skip"),
    limit: int    = Query(50, ge=1, le=200, description="Max records to return"),
    status: str | None   = Query(None, examples=["completed"],
                                  description="Filter by status: pending|processing|completed|failed"),
    language: str | None = Query(None, examples=["de"],
                                  description="Filter by language: de|fr|it|en|unknown"),
    db: Session = Depends(get_db),
):
    q = db.query(Invoice)
    if status:   q = q.filter(Invoice.status   == status)
    if language: q = q.filter(Invoice.language == language)
    return q.order_by(Invoice.created_at.desc()).offset(skip).limit(limit).all()


@router.get(
    "/{invoice_id}",
    response_model=InvoiceOut,
    summary="Get full invoice detail",
    description="""
Returns the complete invoice record including extracted fields, all compliance
rule results, and anomaly flags.

**Response example:**
```json
{
  "id": 1,
  "invoice_number": "INV-2024-001247",
  "vendor_name": "Mustermann Beratung AG",
  "currency": "CHF",
  "total_amount": 3729.45,
  "tax_amount": 279.45,
  "tax_rate_percent": 8.1,
  "invoice_date": "2024-03-15",
  "due_date": "2024-04-15",
  "swiss_uid": "CHE-123.456.789",
  "iban": "CH56 0483 5012 3456 7800 9",
  "overall_compliance_status": "pass",
  "compliance_results": [
    {
      "rule_id": "CH_UID_FORMAT",
      "rule_name": "Swiss UID Format",
      "status": "pass",
      "message": "UID format is valid"
    }
  ],
  "line_items": []
}
```
""",
)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, f"Invoice {invoice_id} not found.")
    return inv


@router.get(
    "/{invoice_id}/raw",
    summary="Get raw OCR text",
    description="""
Returns the raw text extracted from the invoice file — useful for debugging
OCR quality or checking what the field extractor received.

**Response example:**
```json
{
  "invoice_id": 1,
  "raw_text": "RECHNUNG\\nRechnungsnummer: INV-2024-001247\\n..."
}
```
""",
)
def get_raw_text(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Invoice not found.")
    return {"invoice_id": invoice_id, "raw_text": inv.raw_text}


@router.post(
    "/{invoice_id}/reprocess",
    response_model=UploadResponse,
    summary="Reprocess an existing invoice",
    description="""
Re-runs the full processing pipeline on an already-uploaded invoice —
useful after updating OCR settings or compliance rules.

**Response example:**
```json
{
  "invoice_id": 1,
  "filename": "rechnung.pdf",
  "message": "Reprocessed.",
  "status": "completed"
}
```
""",
)
def reprocess(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Invoice not found.")
    _process_invoice(invoice_id, db)
    db.refresh(inv)
    return UploadResponse(
        invoice_id=inv.id, filename=inv.original_filename,
        message="Reprocessed.", status=inv.status.value,
    )


@router.delete(
    "/{invoice_id}",
    status_code=204,
    summary="Delete an invoice",
    description="""
Permanently deletes the invoice record and its uploaded file.

Returns HTTP **204 No Content** on success.

**Request example:**
```
DELETE /invoices/5
```
""",
)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Invoice not found.")
    delete_upload(inv.file_path)
    db.delete(inv)
    db.commit()
    return None
