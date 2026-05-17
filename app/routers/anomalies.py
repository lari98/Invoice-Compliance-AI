"""
GET /invoices/{invoice_id}/anomalies  — return stored anomaly flags + score
POST /invoices/{invoice_id}/anomalies/rerun — re-run detection on existing invoice
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.invoice import AnomalyFlag, Invoice
from app.models.schemas import AnomalyFlagOut, AnomalyReportOut
from app.services.anomaly_service import run_anomaly_detection
from app.services.field_extractor import extract_fields, ExtractionResult

router = APIRouter(prefix="/invoices", tags=["anomalies"])


@router.get("/{invoice_id}/anomalies", response_model=AnomalyReportOut)
def get_anomalies(invoice_id: int, db: Session = Depends(get_db)):
    """Return stored anomaly report for an invoice."""
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Invoice not found.")
    flags = (
        db.query(AnomalyFlag)
        .filter(AnomalyFlag.invoice_id == invoice_id)
        .order_by(AnomalyFlag.score_contribution.desc())
        .all()
    )
    return AnomalyReportOut(
        invoice_id=invoice_id,
        anomaly_score=inv.anomaly_score or 0,
        risk_level=_risk_label(inv.anomaly_score or 0),
        flags=[AnomalyFlagOut.model_validate(f) for f in flags],
    )


@router.post("/{invoice_id}/anomalies/rerun", response_model=AnomalyReportOut)
def rerun_anomalies(invoice_id: int, db: Session = Depends(get_db)):
    """Re-run anomaly detection using the stored raw OCR text."""
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Invoice not found.")
    if not inv.raw_text:
        raise HTTPException(422, "No raw OCR text available. Reprocess the invoice first.")
    fields = extract_fields(inv.raw_text)
    report = run_anomaly_detection(inv, fields, db)
    flags_out = [
        AnomalyFlagOut(
            id=None,
            invoice_id=invoice_id,
            anomaly_type=f.anomaly_type,
            severity=f.severity,
            score_contribution=f.score_contribution,
            description=f.description,
            recommended_action=f.recommended_action,
        )
        for f in report.flags
    ]
    return AnomalyReportOut(
        invoice_id=invoice_id,
        anomaly_score=report.anomaly_score,
        risk_level=report.risk_level,
        flags=flags_out,
    )


def _risk_label(score: int) -> str:
    if score >= 70: return "critical"
    if score >= 40: return "high"
    if score >= 20: return "medium"
    return "low"
