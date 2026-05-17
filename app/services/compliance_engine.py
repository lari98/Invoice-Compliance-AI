"""
Swiss Invoice Compliance Engine — 12 rules.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional
from loguru import logger
from app.services.field_extractor import ExtractionResult

VALID_VAT_RATES = {8.1, 7.7, 2.5, 2.6, 3.8, 3.7, 0.0}
RE_UID   = re.compile(r"^CHE-\d{3}\.\d{3}\.\d{3}$")
RE_IBAN  = re.compile(r"^CH\d{2}[A-Z0-9]{17}$")
RE_QR    = re.compile(r"^\d{26,27}$")
RE_DATE  = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class ComplianceCheckResult:
    rule_id: str
    rule_name: str
    category: str
    status: str
    message: str
    field_checked: str
    actual_value: Optional[str] = None
    expected_pattern: Optional[str] = None


def check_invoice_number(d: ExtractionResult) -> ComplianceCheckResult:
    if not d.invoice_number:
        return ComplianceCheckResult("CH_INVNUM_MISSING","Invoice Number Present","mandatory","fail","No invoice number found. Every invoice must have a unique identifier.","invoice_number")
    return ComplianceCheckResult("CH_INVNUM_PRESENT","Invoice Number Present","mandatory","pass",f"Invoice number: {d.invoice_number}","invoice_number",d.invoice_number)

def check_vendor_name(d: ExtractionResult) -> ComplianceCheckResult:
    if not d.vendor_name:
        return ComplianceCheckResult("CH_VENDOR_MISSING","Vendor Name Present","identity","fail","No vendor name found on invoice.","vendor_name")
    return ComplianceCheckResult("CH_VENDOR_PRESENT","Vendor Name Present","identity","pass",f"Vendor: {d.vendor_name}","vendor_name",d.vendor_name)

def check_invoice_date(d: ExtractionResult) -> ComplianceCheckResult:
    if not d.invoice_date:
        return ComplianceCheckResult("CH_DATE_MISSING","Invoice Date Present","mandatory","fail","No invoice date found.","invoice_date")
    return ComplianceCheckResult("CH_DATE_PRESENT","Invoice Date Present","mandatory","pass",f"Invoice date: {d.invoice_date}","invoice_date",d.invoice_date)

def check_due_date(d: ExtractionResult) -> ComplianceCheckResult:
    if not d.due_date:
        return ComplianceCheckResult("CH_DUEDATE_MISSING","Due Date Present","mandatory","warning","No due date found. Recommended for clear payment terms.","due_date")
    if d.invoice_date and RE_DATE.match(d.invoice_date) and RE_DATE.match(d.due_date):
        if d.due_date < d.invoice_date:
            return ComplianceCheckResult("CH_DUEDATE_LOGIC","Due Date After Invoice Date","mandatory","fail",f"Due date ({d.due_date}) is before invoice date ({d.invoice_date}).","due_date",d.due_date,f"> {d.invoice_date}")
    return ComplianceCheckResult("CH_DUEDATE_PRESENT","Due Date Present","mandatory","pass",f"Due date: {d.due_date}","due_date",d.due_date)

def check_currency(d: ExtractionResult) -> ComplianceCheckResult:
    if not d.currency:
        return ComplianceCheckResult("CH_CURRENCY_MISSING","Currency Specified","mandatory","fail","No currency found on invoice.","currency")
    if d.currency == "CHF":
        return ComplianceCheckResult("CH_CURRENCY","Accepted Currency","mandatory","pass","Currency: CHF","currency","CHF")
    if d.currency in ("EUR","USD","GBP"):
        return ComplianceCheckResult("CH_CURRENCY","Accepted Currency","mandatory","warning",f"Currency: {d.currency}. Non-CHF — verify exchange rate.","currency",d.currency)
    return ComplianceCheckResult("CH_CURRENCY","Accepted Currency","mandatory","warning",f"Currency '{d.currency}' is unusual.","currency",d.currency,"CHF|EUR|USD")

def check_total_amount(d: ExtractionResult) -> ComplianceCheckResult:
    if d.total_amount is None:
        return ComplianceCheckResult("CH_TOTAL_MISSING","Total Amount Present","mandatory","fail","No total amount found.","total_amount")
    if d.total_amount <= 0:
        return ComplianceCheckResult("CH_TOTAL_NEGATIVE","Total Amount Positive","mandatory","fail",f"Total {d.total_amount} must be positive.","total_amount",str(d.total_amount))
    return ComplianceCheckResult("CH_TOTAL_PRESENT","Total Amount Present","mandatory","pass",f"Total: {d.currency or ''} {d.total_amount:,.2f}","total_amount",str(d.total_amount))

def check_swiss_uid(d: ExtractionResult) -> ComplianceCheckResult:
    if not d.swiss_uid:
        return ComplianceCheckResult("CH_UID_MISSING","Swiss UID Present","identity","warning","No Swiss UID (CHE-xxx.xxx.xxx) found.","swiss_uid",None,"CHE-xxx.xxx.xxx")
    if RE_UID.match(d.swiss_uid):
        return ComplianceCheckResult("CH_UID_FORMAT","Swiss UID Format","identity","pass",f"UID valid: {d.swiss_uid}","swiss_uid",d.swiss_uid,"CHE-xxx.xxx.xxx")
    return ComplianceCheckResult("CH_UID_FORMAT","Swiss UID Format","identity","fail",f"UID '{d.swiss_uid}' invalid format.","swiss_uid",d.swiss_uid,"CHE-xxx.xxx.xxx")

def check_iban(d: ExtractionResult) -> ComplianceCheckResult:
    if not d.iban:
        return ComplianceCheckResult("CH_IBAN_MISSING","IBAN Present","payment","fail","No IBAN found on invoice.","iban",None,"CH xx xxxx xxxx xxxx xxxx x")
    clean = re.sub(r"\s","",d.iban).upper()
    if clean.startswith("CH"):
        if len(clean) != 21:
            return ComplianceCheckResult("CH_IBAN_LENGTH","Swiss IBAN Length","payment","fail",f"IBAN must be 21 chars, got {len(clean)}.","iban",clean)
        if RE_IBAN.match(clean):
            return ComplianceCheckResult("CH_IBAN_FORMAT","Swiss IBAN Format","payment","pass",f"IBAN valid: {clean}","iban",clean)
    return ComplianceCheckResult("CH_IBAN_FOREIGN","IBAN Country","payment","warning",f"IBAN '{d.iban}' is not a Swiss IBAN.","iban",d.iban,"Starts with CH")

def check_qr_reference(d: ExtractionResult) -> ComplianceCheckResult:
    if not d.qr_reference:
        return ComplianceCheckResult("CH_QR_MISSING","QR-Bill Reference","payment","warning","No QR-Rechnung reference found.","qr_reference",None,"26-27 digit number")
    if RE_QR.match(d.qr_reference):
        return ComplianceCheckResult("CH_QR_FORMAT","QR-Bill Reference Format","payment","pass",f"QR reference valid: {d.qr_reference}","qr_reference",d.qr_reference)
    return ComplianceCheckResult("CH_QR_FORMAT","QR-Bill Reference Format","payment","fail",f"QR reference '{d.qr_reference}' invalid.","qr_reference",d.qr_reference,"26-27 digits")

def check_vat_number(d: ExtractionResult) -> ComplianceCheckResult:
    if not d.vat_number:
        return ComplianceCheckResult("CH_VAT_MISSING","VAT Number Present","tax","warning","No VAT number found.","vat_number",None,"CHE-xxx.xxx.xxx MWST")
    return ComplianceCheckResult("CH_VAT_PRESENT","VAT Number Present","tax","pass",f"VAT: {d.vat_number}","vat_number",d.vat_number)

def check_vat_rate(d: ExtractionResult) -> ComplianceCheckResult:
    if d.tax_rate_percent is None:
        return ComplianceCheckResult("CH_VAT_RATE_MISSING","VAT Rate Specified","tax","warning","No VAT rate found.","tax_rate_percent",None,"8.1%|2.6%|3.8%|0%")
    if d.tax_rate_percent in VALID_VAT_RATES:
        return ComplianceCheckResult("CH_VAT_RATE","Swiss VAT Rate Valid","tax","pass",f"VAT rate {d.tax_rate_percent}% is valid.","tax_rate_percent",str(d.tax_rate_percent))
    return ComplianceCheckResult("CH_VAT_RATE","Swiss VAT Rate Valid","tax","fail",f"VAT rate {d.tax_rate_percent}% is not a valid Swiss rate.","tax_rate_percent",str(d.tax_rate_percent),"8.1%|2.6%|3.8%|0%")

def check_tax_consistency(d: ExtractionResult) -> ComplianceCheckResult:
    if d.total_amount and d.tax_rate_percent and d.tax_amount:
        base = round(d.total_amount / (1 + d.tax_rate_percent / 100), 2)
        expected = round(base * d.tax_rate_percent / 100, 2)
        if abs(expected - d.tax_amount) <= 0.05:
            return ComplianceCheckResult("CH_TAX_CALC","Tax Calculation Consistent","tax","pass",f"Tax CHF {d.tax_amount} consistent with {d.tax_rate_percent}%.","tax_amount",str(d.tax_amount),f"~{expected}")
        return ComplianceCheckResult("CH_TAX_CALC","Tax Calculation Consistent","tax","warning",f"Tax CHF {d.tax_amount} differs from expected CHF {expected}.","tax_amount",str(d.tax_amount),f"~{expected}")
    return ComplianceCheckResult("CH_TAX_CALC","Tax Calculation Consistent","tax","warning","Cannot verify tax — missing total, rate, or tax amount.","tax_amount")


# ── New rules v1.1 ────────────────────────────────────────────────────────────

def check_tax_not_gt_total(d: ExtractionResult) -> ComplianceCheckResult:
    """Tax amount must never exceed total amount — impossible accounting."""
    if d.tax_amount and d.total_amount:
        if d.tax_amount > d.total_amount:
            return ComplianceCheckResult(
                "CH_TAX_GT_TOTAL", "Tax Not Greater Than Total", "tax", "fail",
                f"Tax ({d.tax_amount:.2f}) exceeds total ({d.total_amount:.2f}) — invalid invoice.",
                "tax_amount", str(d.tax_amount), f"<= {d.total_amount}",
            )
    return ComplianceCheckResult("CH_TAX_GT_TOTAL","Tax Not Greater Than Total","tax","pass",
        "Tax amount is within total.", "tax_amount")


def check_suspicious_amount(d: ExtractionResult) -> ComplianceCheckResult:
    """Flag zero totals or perfectly round large amounts as potentially suspicious."""
    if d.total_amount is None:
        return ComplianceCheckResult("CH_AMOUNT_SUSPICIOUS","Amount Not Suspicious","mandatory","warning",
            "Total amount not found.", "total_amount")
    if d.total_amount == 0:
        return ComplianceCheckResult("CH_AMOUNT_SUSPICIOUS","Amount Not Suspicious","mandatory","fail",
            "Total amount is zero.", "total_amount", "0")
    if d.total_amount > 10_000 and d.total_amount == int(d.total_amount) and str(int(d.total_amount)).endswith("000"):
        return ComplianceCheckResult("CH_AMOUNT_SUSPICIOUS","Amount Not Suspicious","mandatory","warning",
            f"Total {d.total_amount:,.2f} is a suspiciously round number. Verify with supporting documents.",
            "total_amount", str(d.total_amount), "non-round value")
    return ComplianceCheckResult("CH_AMOUNT_SUSPICIOUS","Amount Not Suspicious","mandatory","pass",
        f"Total {d.total_amount:,.2f} looks reasonable.", "total_amount", str(d.total_amount))


def check_date_order(d: ExtractionResult) -> ComplianceCheckResult:
    """Invoice date must be on or before due date."""
    if d.invoice_date and d.due_date:
        if d.invoice_date > d.due_date:
            return ComplianceCheckResult("CH_DATE_ORDER","Invoice Date Before Due","mandatory","fail",
                f"Invoice date {d.invoice_date} is after due date {d.due_date}.",
                "invoice_date", str(d.invoice_date), f"<= {d.due_date}")
        return ComplianceCheckResult("CH_DATE_ORDER","Invoice Date Before Due","mandatory","pass",
            f"Invoice date {d.invoice_date} precedes due date {d.due_date}.",
            "invoice_date", str(d.invoice_date))
    return ComplianceCheckResult("CH_DATE_ORDER","Invoice Date Before Due","mandatory","warning",
        "Cannot verify date order — dates missing.", "invoice_date")


def check_payment_terms(d: ExtractionResult) -> ComplianceCheckResult:
    """Payment terms should be present and reasonable (not > 365 days)."""
    import re as _re
    if not d.payment_terms:
        return ComplianceCheckResult("CH_PAYMENT_TERMS","Payment Terms Reasonable","mandatory","warning",
            "No payment terms found on invoice.", "payment_terms")
    m = _re.search(r"(\d+)\s*(?:days?|Tage?|jours?|giorni?)", d.payment_terms, _re.I)
    if m:
        days = int(m.group(1))
        if days > 365:
            return ComplianceCheckResult("CH_PAYMENT_TERMS","Payment Terms Reasonable","mandatory","warning",
                f"Payment term of {days} days exceeds 365 days — unusual.",
                "payment_terms", d.payment_terms, "<= 365 days")
    return ComplianceCheckResult("CH_PAYMENT_TERMS","Payment Terms Reasonable","mandatory","pass",
        f"Payment terms: {d.payment_terms}", "payment_terms", d.payment_terms)


ALL_RULES = [check_invoice_number, check_vendor_name, check_invoice_date, check_due_date,
             check_currency, check_total_amount, check_swiss_uid, check_iban,
             check_qr_reference, check_vat_number, check_vat_rate, check_tax_consistency,
    # v1.1 additions
    check_tax_not_gt_total, check_suspicious_amount, check_date_order, check_payment_terms,
]


def run_compliance_checks(data: ExtractionResult) -> list[ComplianceCheckResult]:
    results = []
    for fn in ALL_RULES:
        try:
            results.append(fn(data))
        except Exception as e:
            logger.error(f"Rule {fn.__name__} failed: {e}")
    passed  = sum(1 for r in results if r.status == "pass")
    warns   = sum(1 for r in results if r.status == "warning")
    failed  = sum(1 for r in results if r.status == "fail")
    logger.info(f"Compliance: {passed} pass / {warns} warning / {failed} fail")
    return results


def summarise_compliance(results: list[ComplianceCheckResult]) -> dict:
    statuses = [r.status for r in results]
    overall = "fail" if "fail" in statuses else ("warning" if "warning" in statuses else "pass")
    return {"overall_status": overall, "total_checks": len(results),
            "passed": statuses.count("pass"), "warnings": statuses.count("warning"), "failed": statuses.count("fail")}
