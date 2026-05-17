"""
Rule-based fraud and anomaly detection for Swiss invoices.
Produces an anomaly score (0-100) and a list of AnomalyFlag records.

Score weights per rule:
  DUPLICATE_INVOICE_NUMBER   → 40
  SAME_IBAN_DIFFERENT_VENDOR → 35
  INVOICE_DATE_FUTURE        → 35
  AMOUNT_MISMATCH            → 30
  AMOUNT_UNUSUALLY_HIGH      → 25
  MISSING_VAT_UID            → 20
  SUSPICIOUS_DUE_DATE        → 15
  UNUSUAL_CURRENCY           → 10

Total is capped at 100.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.services.field_extractor import ExtractionResult as ExtractedFields


def _to_date(val):
    """Convert string date (YYYY-MM-DD or None) to date object, or pass through if already date."""
    if val is None:
        return None
    if hasattr(val, 'year'):   # already a date object
        return val
    try:
        from datetime import date as _date
        return _date.fromisoformat(str(val)[:10])
    except Exception:
        return None


_WEIGHTS: dict[str, int] = {
    "DUPLICATE_INVOICE_NUMBER":      40,
    "SAME_IBAN_DIFFERENT_VENDOR":    35,
    "INVOICE_DATE_FUTURE":           35,
    "AMOUNT_MISMATCH":               30,
    "AMOUNT_UNUSUALLY_HIGH":         25,
    "MISSING_VAT_UID":               20,
    "SUSPICIOUS_DUE_DATE":           15,
    "UNUSUAL_CURRENCY":              10,
}

_STANDARD_CURRENCIES = {"CHF", "EUR", "USD"}


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class AnomalyFlagDTO:
    anomaly_type: str
    severity: str          # low | medium | high | critical
    score_contribution: int
    description: str
    recommended_action: str


@dataclass
class AnomalyReport:
    invoice_id: int
    anomaly_score: int     # 0 – 100
    risk_level: str        # low | medium | high | critical
    flags: List[AnomalyFlagDTO] = field(default_factory=list)
    detected_at: datetime  = field(default_factory=datetime.utcnow)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _severity(score: int) -> str:
    if score >= 35: return "critical"
    if score >= 25: return "high"
    if score >= 15: return "medium"
    return "low"


def _risk_level(total: int) -> str:
    if total >= 70: return "critical"
    if total >= 40: return "high"
    if total >= 20: return "medium"
    return "low"


# ── Individual checks ─────────────────────────────────────────────────────────

def _dup_invoice_number(inv, fields: ExtractedFields, db: Session) -> Optional[AnomalyFlagDTO]:
    if not fields.invoice_number:
        return None
    from app.models.invoice import Invoice
    dup = db.query(Invoice).filter(
        Invoice.invoice_number == fields.invoice_number,
        Invoice.id != inv.id,
    ).first()
    if dup:
        w = _WEIGHTS["DUPLICATE_INVOICE_NUMBER"]
        return AnomalyFlagDTO(
            anomaly_type="DUPLICATE_INVOICE_NUMBER",
            severity=_severity(w),
            score_contribution=w,
            description=f"Invoice number '{fields.invoice_number}' already exists (invoice #{dup.id}).",
            recommended_action="Verify this is not a duplicate submission. Contact the vendor to clarify.",
        )
    return None


def _same_iban_diff_vendor(inv, fields: ExtractedFields, db: Session) -> Optional[AnomalyFlagDTO]:
    if not fields.iban or not fields.vendor_name:
        return None
    from app.models.invoice import Invoice
    conflict = db.query(Invoice).filter(
        Invoice.iban == fields.iban,
        Invoice.vendor_name != fields.vendor_name,
        Invoice.id != inv.id,
    ).first()
    if conflict:
        w = _WEIGHTS["SAME_IBAN_DIFFERENT_VENDOR"]
        return AnomalyFlagDTO(
            anomaly_type="SAME_IBAN_DIFFERENT_VENDOR",
            severity=_severity(w),
            score_contribution=w,
            description=(
                f"IBAN {fields.iban} already used by vendor '{conflict.vendor_name}' "
                f"(invoice #{conflict.id})."
            ),
            recommended_action=(
                "Possible payment redirection fraud. "
                "Verify IBAN directly with vendor via phone — not email."
            ),
        )
    return None


def _invoice_date_future(inv, fields: ExtractedFields, db: Session) -> Optional[AnomalyFlagDTO]:
    inv_date = _to_date(fields.invoice_date)
    if not inv_date:
        return None
    today = date.today()
    if inv_date > today:
        w = _WEIGHTS["INVOICE_DATE_FUTURE"]
        return AnomalyFlagDTO(
            anomaly_type="INVOICE_DATE_FUTURE",
            severity=_severity(w),
            score_contribution=w,
            description=f"Invoice date {inv_date} is in the future (today: {today}).",
            recommended_action="Reject invoice. Request a corrected invoice with a valid date.",
        )
    return None


def _amount_unusually_high(inv, fields: ExtractedFields, db: Session) -> Optional[AnomalyFlagDTO]:
    if not fields.total_amount or not fields.vendor_name:
        return None
    from app.models.invoice import Invoice
    historical = (
        db.query(Invoice)
        .filter(
            Invoice.vendor_name == fields.vendor_name,
            Invoice.total_amount.isnot(None),
            Invoice.id != inv.id,
        )
        .all()
    )
    amounts = [h.total_amount for h in historical if h.total_amount]
    if len(amounts) < 3:
        return None  # not enough history
    avg = statistics.mean(amounts)
    std = statistics.stdev(amounts) if len(amounts) > 1 else avg * 0.3
    threshold = avg + 3 * std
    if fields.total_amount > threshold:
        w = _WEIGHTS["AMOUNT_UNUSUALLY_HIGH"]
        return AnomalyFlagDTO(
            anomaly_type="AMOUNT_UNUSUALLY_HIGH",
            severity=_severity(w),
            score_contribution=w,
            description=(
                f"Amount {fields.total_amount:,.2f} is unusually high for "
                f"'{fields.vendor_name}' (avg: {avg:,.2f}, 3σ threshold: {threshold:,.2f})."
            ),
            recommended_action="Request supporting documentation. Obtain secondary approval before payment.",
        )
    return None


def _missing_vat_uid(inv, fields: ExtractedFields, db: Session) -> Optional[AnomalyFlagDTO]:
    if not fields.swiss_uid and not fields.vat_number:
        w = _WEIGHTS["MISSING_VAT_UID"]
        return AnomalyFlagDTO(
            anomaly_type="MISSING_VAT_UID",
            severity=_severity(w),
            score_contribution=w,
            description="No VAT number or Swiss UID found on the invoice.",
            recommended_action="Request a corrected invoice with valid UID (CHE-xxx.xxx.xxx format).",
        )
    return None


def _suspicious_due_date(inv, fields: ExtractedFields, db: Session) -> Optional[AnomalyFlagDTO]:
    inv_date = _to_date(fields.invoice_date)
    due_date = _to_date(fields.due_date)
    if not inv_date or not due_date:
        return None
    delta = (due_date - inv_date).days
    if delta < 0:
        return None  # caught by compliance engine already
    w = _WEIGHTS["SUSPICIOUS_DUE_DATE"]
    if delta < 3:
        return AnomalyFlagDTO(
            anomaly_type="SUSPICIOUS_DUE_DATE",
            severity="medium",
            score_contribution=w,
            description=f"Due date is only {delta} day(s) after invoice date — extremely urgent.",
            recommended_action="Verify the due date is correct. Artificial urgency is a red flag for fraud.",
        )
    if delta > 365:
        return AnomalyFlagDTO(
            anomaly_type="SUSPICIOUS_DUE_DATE",
            severity="low",
            score_contribution=w // 2,
            description=f"Due date is {delta} days after invoice date — unusually long payment term.",
            recommended_action="Confirm with vendor contract that this payment term is agreed.",
        )
    return None


def _amount_mismatch(inv, fields: ExtractedFields, db: Session) -> Optional[AnomalyFlagDTO]:
    if fields.tax_amount and fields.total_amount and fields.tax_amount > fields.total_amount:
        w = _WEIGHTS["AMOUNT_MISMATCH"]
        return AnomalyFlagDTO(
            anomaly_type="AMOUNT_MISMATCH",
            severity=_severity(w),
            score_contribution=w,
            description=(
                f"Tax amount ({fields.tax_amount:.2f}) exceeds total amount "
                f"({fields.total_amount:.2f}) — impossible accounting."
            ),
            recommended_action="Reject invoice. Request corrected invoice with consistent amounts.",
        )
    return None


def _unusual_currency(inv, fields: ExtractedFields, db: Session) -> Optional[AnomalyFlagDTO]:
    if fields.currency and fields.currency.upper() not in _STANDARD_CURRENCIES:
        w = _WEIGHTS["UNUSUAL_CURRENCY"]
        return AnomalyFlagDTO(
            anomaly_type="UNUSUAL_CURRENCY",
            severity="low",
            score_contribution=w,
            description=f"Currency '{fields.currency}' is not standard for Swiss vendors (CHF/EUR/USD).",
            recommended_action="Verify currency with vendor. Flag for FX compliance review.",
        )
    return None



# ── Public interface ──────────────────────────────────────────────────────────

_ALL_CHECKS: List[Callable] = [
    _dup_invoice_number,
    _same_iban_diff_vendor,
    _invoice_date_future,
    _amount_unusually_high,
    _missing_vat_uid,
    _suspicious_due_date,
    _amount_mismatch,
    _unusual_currency,
]


def run_anomaly_detection(inv, fields: ExtractedFields, db: Session) -> AnomalyReport:
    """
    Run all anomaly checks against `inv` / `fields`.
    Persists AnomalyFlag ORM rows and updates inv.anomaly_score.
    Returns an AnomalyReport with score 0-100 and list of flags.
    """
    from app.models.invoice import AnomalyFlag

    flag_dtos: List[AnomalyFlagDTO] = []
    for check in _ALL_CHECKS:
        try:
            result = check(inv, fields, db)
            if result:
                flag_dtos.append(result)
        except Exception as exc:
            logger.warning(f"Anomaly check {check.__name__} failed: {exc}")

    total_score = min(sum(f.score_contribution for f in flag_dtos), 100)

    # Persist — delete old flags first (idempotent reprocess)
    db.query(AnomalyFlag).filter(AnomalyFlag.invoice_id == inv.id).delete()
    for dto in flag_dtos:
        db.add(AnomalyFlag(
            invoice_id=inv.id,
            anomaly_type=dto.anomaly_type,
            severity=dto.severity,
            score_contribution=dto.score_contribution,
            description=dto.description,
            recommended_action=dto.recommended_action,
        ))

    inv.anomaly_score = total_score
    db.commit()

    logger.info(f"Invoice #{inv.id}: anomaly_score={total_score}, flags={len(flag_dtos)}")
    return AnomalyReport(
        invoice_id=inv.id,
        anomaly_score=total_score,
        risk_level=_risk_level(total_score),
        flags=flag_dtos,
    )
