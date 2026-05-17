"""
Field Extraction Engine — extracts 15+ fields from raw OCR invoice text.
Supports DE / FR / IT / EN invoices.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger

try:
    from langdetect import detect
    _LANGDETECT = True
except ImportError:
    _LANGDETECT = False

# ── Patterns ──────────────────────────────────────────────────────────────────
RE_SWISS_UID   = re.compile(r"\bCHE[-\s]?\d{3}[.\s]?\d{3}[.\s]?\d{3}\b", re.I)
RE_IBAN        = re.compile(r"\bCH\d{2}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{1,4}\b", re.I)
RE_QR_REF      = re.compile(r"\b\d{2}[\s]?\d{5}[\s]?\d{5}[\s]?\d{5}[\s]?\d{5}[\s]?\d{5}\b")
RE_VAT         = re.compile(r"\b(?:CHE[-\s]?\d{3}[.\s]?\d{3}[.\s]?\d{3}\s*(?:MWST|TVA|IVA)?|DE\d{9})\b", re.I)
RE_DATE        = re.compile(
    r"\b(\d{2}[./]\d{2}[./]\d{4}|\d{4}-\d{2}-\d{2}|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\.?\s+\d{1,2},?\s+\d{4})\b", re.I)
RE_AMOUNT      = re.compile(r"(?<!\w)(\d{1,3}(?:[,'\s]\d{3})*(?:\.\d{2})?|\d+(?:[.,]\d{2})?)(?!\w)")
RE_CURRENCY    = re.compile(
    r"\b(CHF|EUR|USD|GBP|CAD|JPY|SGD|AUD|AED|CNY|KRW|INR|BRL|HKD|NOK|SEK|DKK|NZD|"
    r"ZAR|TRY|THB|PLN|SAR|MYR|MXN|CZK|HUF|ILS|PHP|IDR|TWD|EGP|NGN|UAH|RUB|"
    r"BTC|ETH|USDT|BNB|XRP)\b", re.I)
RE_INV_NUM     = re.compile(
    r"(?:Rechnungs(?:nummer|nr\.?)|Invoice\s*(?:No\.?|Number|#)|"
    r"Num[eé]ro\s+de\s+facture|Facture\s*(?:No\.?|Nr\.?)|"
    r"Numero\s+di\s+fattura|Fattura\s*(?:No\.?|Nr\.?|Numero)?)"
    r"[\s:/#-]*([A-Z0-9][-A-Z0-9/_. ]{2,30})", re.I)
RE_PAYMENT     = re.compile(r"(?:Zahlungsbedingungen|Conditions de paiement|Payment terms)[:\s]*(.{5,80})", re.I)
RE_TAX_RATE    = re.compile(r"\b(2[.,]5|2[.,]6|3[.,]7|3[.,]8|7[.,]7|8[.,]1)\s*%")
# (?![\s-]*Nr) — skip "MWST-Nr." lines so the UID is never captured
# [^0-9\n]*    — don't cross line boundaries
RE_TAX_AMOUNT  = re.compile(
    r"(?:MWST|MwSt|TVA|IVA|Tax|VAT)(?![\s-]*Nr)"
    r"[^\n]*?:[ \t]*[A-Za-z ]*"
    r"(\d{1,3}(?:['\s]\d{3})*(?:[.,]\d{2})?)", re.I)
RE_TOTAL       = re.compile(
    r"(?:Gesamtbetrag|Total\s*(?:CHF|EUR|USD)?|Montant total|Totale|Grand total|Amount due)"
    r"[^0-9$€£\n]*[$€£]?"
    r"(\d{1,3}(?:[,'\s]\d{3})*(?:\.\d{2})?|\d+(?:[.,]\d{2})?)", re.I)

INV_DATE_LABELS = ["Rechnungsdatum","Datum","Date de facture","Date","Data fattura","Invoice Date"]
DUE_DATE_LABELS = ["Fälligkeitsdatum","Fällig","Date d'échéance","Échéance","Due Date","Payment Due"]
VENDOR_LABELS   = ["Bill From","Lieferant","Auftragnehmer","Fournisseur","Prestataire","Vendor","Supplier","Seller","From"]
COUNTRY_MAP     = {"Schweiz":"CH","Suisse":"CH","Svizzera":"CH","Switzerland":"CH",
                   "Deutschland":"DE","Germany":"DE","Österreich":"AT","Austria":"AT"}


@dataclass
class ExtractedLineItem:
    position: Optional[int] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    tax_rate: Optional[float] = None


@dataclass
class ExtractionResult:
    invoice_number: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_country: Optional[str] = None
    vat_number: Optional[str] = None
    swiss_uid: Optional[str] = None
    iban: Optional[str] = None
    qr_reference: Optional[str] = None
    currency: Optional[str] = None
    total_amount: Optional[float] = None
    tax_amount: Optional[float] = None
    tax_rate_percent: Optional[float] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    payment_terms: Optional[str] = None
    language: str = "unknown"
    line_items: list[ExtractedLineItem] = field(default_factory=list)
    extraction_confidence: float = 0.0
    raw_text: str = ""


def _clean_amount(raw: str) -> Optional[float]:
    if not raw:
        return None
    # Strip currency symbols and letter codes
    raw = re.sub(r"[$€£¥]", "", raw)
    raw = re.sub(r"[A-Za-z\s']", "", raw)
    raw = raw.strip()
    if not raw:
        return None
    if "," in raw and "." in raw:
        # American format: comma=thousands, period=decimal  →  1,234.56
        # European format: period=thousands, comma=decimal  →  1.234,56
        if raw.rfind(".") > raw.rfind(","):
            raw = raw.replace(",", "")          # remove thousands commas
        else:
            raw = raw.replace(".", "").replace(",", ".")   # European → standard
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return round(float(raw), 2)
    except ValueError:
        return None


def _normalise_uid(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)[-9:]
    return f"CHE-{digits[:3]}.{digits[3:6]}.{digits[6:]}"


def _normalise_iban(raw: str) -> str:
    return re.sub(r"\s", "", raw).upper()


_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_date(raw: str) -> Optional[str]:
    raw = raw.strip()
    # DD.MM.YYYY  or  DD/MM/YYYY
    m = re.match(r"(\d{2})[./](\d{2})[./](\d{4})", raw)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    # YYYY-MM-DD  (already ISO)
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    # "May 17, 2026"  or  "May 17 2026"
    m = re.match(r"([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})", raw)
    if m:
        mon = _MONTH_MAP.get(m.group(1)[:3].lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}"
    # "17 May 2026"
    m = re.match(r"(\d{1,2})\s+([A-Za-z]+)\.?\s+(\d{4})", raw)
    if m:
        mon = _MONTH_MAP.get(m.group(2)[:3].lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    return raw


def _label_value(text: str, labels: list[str]) -> Optional[str]:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        for lbl in labels:
            if re.search(re.escape(lbl), line, re.I):
                parts = re.split(re.escape(lbl), line, maxsplit=1, flags=re.I)
                if len(parts) > 1 and parts[1].strip(" :.-/"):
                    return parts[1].strip(" :.-/")
                if i + 1 < len(lines) and lines[i+1].strip():
                    return lines[i+1].strip()
    return None


def _detect_lang(text: str) -> str:
    de = len(re.findall(r"\b(Rechnung|Betrag|Fälligkeit|Mwst|Gesamt)\b", text, re.I))
    fr = len(re.findall(r"\b(Facture|Montant|Échéance|TVA|Total)\b", text, re.I))
    it = len(re.findall(r"\b(Fattura|Importo|Scadenza|IVA|Totale)\b", text, re.I))
    en = len(re.findall(r"\b(Invoice|Amount|Due|Tax|Total)\b", text, re.I))
    scores = {"de": de, "fr": fr, "it": it, "en": en}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "unknown"


def _confidence(r: ExtractionResult) -> float:
    core = [r.invoice_number, r.vendor_name, r.iban, r.currency, r.total_amount, r.invoice_date, r.due_date]
    opt  = [r.swiss_uid, r.vat_number, r.qr_reference, r.tax_amount, r.payment_terms]
    return round(sum(1 for f in core if f) / len(core) * 0.75 + sum(1 for f in opt if f) / len(opt) * 0.25, 2)


def extract_fields(raw_text: str) -> ExtractionResult:
    r = ExtractionResult(raw_text=raw_text)
    text = raw_text

    r.language = _detect_lang(text)

    m = RE_SWISS_UID.search(text)
    if m: r.swiss_uid = _normalise_uid(m.group())

    m = RE_IBAN.search(text)
    if m: r.iban = _normalise_iban(m.group())

    qr_m = re.search(r"(?:QR[-\s]?Referenz|QR[-\s]?Reference)[:\s]*([\d\s]{26,40})", text, re.I)
    if qr_m:
        r.qr_reference = re.sub(r"\s", "", qr_m.group(1))
    else:
        m = RE_QR_REF.search(text)
        if m:
            cand = re.sub(r"\s", "", m.group())
            if len(cand) in (26, 27): r.qr_reference = cand

    m = RE_VAT.search(text)
    if m: r.vat_number = m.group().strip()

    m = RE_CURRENCY.search(text)
    if m:
        r.currency = m.group().upper()
    else:
        # Detect currency from symbols when no ISO code is written
        if re.search(r"\$", text):
            r.currency = "USD"
        elif re.search(r"€", text):
            r.currency = "EUR"
        elif re.search(r"£", text):
            r.currency = "GBP"
        elif re.search(r"¥", text):
            r.currency = "JPY"

    m = RE_INV_NUM.search(text)
    if m: r.invoice_number = m.group(1).strip()

    raw_inv = _label_value(text, INV_DATE_LABELS)
    if raw_inv:
        dm = RE_DATE.search(raw_inv)
        r.invoice_date = _parse_date(dm.group() if dm else raw_inv[:10])

    raw_due = _label_value(text, DUE_DATE_LABELS)
    if raw_due:
        dm = RE_DATE.search(raw_due)
        r.due_date = _parse_date(dm.group() if dm else raw_due[:10])

    all_dates = RE_DATE.findall(text)
    if all_dates and not r.invoice_date: r.invoice_date = _parse_date(all_dates[0])
    if len(all_dates) >= 2 and not r.due_date: r.due_date = _parse_date(all_dates[1])

    m = RE_TAX_RATE.search(text)
    if m: r.tax_rate_percent = float(m.group(1).replace(",", "."))

    m = RE_TAX_AMOUNT.search(text)
    if m: r.tax_amount = _clean_amount(m.group(1))

    m = RE_TOTAL.search(text)
    if m: r.total_amount = _clean_amount(m.group(1))
    if r.total_amount is None:
        amounts = [_clean_amount(x.group()) for x in RE_AMOUNT.finditer(text) if _clean_amount(x.group())]
        if amounts: r.total_amount = max(amounts)

    m = RE_PAYMENT.search(text)
    if m: r.payment_terms = m.group(1).strip()[:255]

    vendor_raw = _label_value(text, VENDOR_LABELS)
    if vendor_raw:
        r.vendor_name = re.sub(r"\s{2,}", " ", vendor_raw).strip()[:255]
    else:
        cm = re.search(r"^([A-Z][A-Za-z\s&]+(?:AG|GmbH|SA|Sàrl|Ltd|Inc))\s*$", text, re.M)
        if cm: r.vendor_name = cm.group(1).strip()

    for indicator, code in COUNTRY_MAP.items():
        if re.search(r"\b" + re.escape(indicator) + r"\b", text, re.I):
            r.vendor_country = code
            break

    r.extraction_confidence = _confidence(r)
    logger.info(f"Extraction done — confidence={r.extraction_confidence:.0%} lang={r.language} total={r.total_amount}")
    return r
