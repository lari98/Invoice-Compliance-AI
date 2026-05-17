from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class LineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    invoice_id: int
    position: Optional[int] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    tax_rate: Optional[float] = None


class ComplianceResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    rule_id: str
    rule_name: str
    category: Optional[str] = None
    status: str
    message: Optional[str] = None
    field_checked: Optional[str] = None
    actual_value: Optional[str] = None
    expected_pattern: Optional[str] = None
    checked_at: datetime


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    original_filename: str
    file_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    status: str
    ocr_engine_used: Optional[str] = None
    extraction_confidence: Optional[float] = None
    processing_error: Optional[str] = None
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
    language: Optional[str] = None
    line_items: list[LineItemOut] = []
    compliance_results: list[ComplianceResultOut] = []
    overall_compliance_status: Optional[str] = None


class InvoiceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    original_filename: str
    invoice_number: Optional[str] = None
    vendor_name: Optional[str] = None
    currency: Optional[str] = None
    total_amount: Optional[float] = None
    invoice_date: Optional[str] = None
    status: str
    language: Optional[str] = None
    overall_compliance_status: Optional[str] = None
    created_at: datetime


class UploadResponse(BaseModel):
    invoice_id: int
    filename: str
    message: str
    status: str


class ComplianceSummary(BaseModel):
    invoice_id: int
    overall_status: str
    total_checks: int
    passed: int
    warnings: int
    failed: int
    results: list[ComplianceResultOut]


class DashboardStats(BaseModel):
    total_invoices: int
    by_status: dict[str, int]
    by_compliance: dict[str, int]
    by_currency: dict[str, int]
    by_language: dict[str, int]
    top_vendors: list[dict]
    total_amount_chf: Optional[float] = None


# ── Anomaly schemas (v1.1) ────────────────────────────────────────────────────

class AnomalyFlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    invoice_id: int
    anomaly_type: str
    severity: str                  # low | medium | high | critical
    score_contribution: int
    description: Optional[str] = None
    recommended_action: Optional[str] = None


class AnomalyReportOut(BaseModel):
    invoice_id: int
    anomaly_score: int             # 0 – 100
    risk_level: str                # low | medium | high | critical
    flags: list[AnomalyFlagOut] = []


class VendorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    uid: Optional[str] = None
    invoice_count: int = 0
    avg_invoice_amount: float = 0.0


class UploadedFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    original_filename: Optional[str] = None
    stored_filename: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
