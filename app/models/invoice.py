import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import relationship
from app.models.database import Base


class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ComplianceStatus(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    UNKNOWN = "unknown"


class InvoiceLanguage(str, enum.Enum):
    DE = "de"
    FR = "fr"
    IT = "it"
    EN = "en"
    UNKNOWN = "unknown"


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_type = Column(String(10))
    file_size_bytes = Column(Integer)
    status = Column(SAEnum(ProcessingStatus), default=ProcessingStatus.PENDING)
    ocr_engine_used = Column(String(50))
    raw_text = Column(Text)
    processing_error = Column(Text)
    invoice_number = Column(String(100))
    vendor_name = Column(String(255))
    vendor_country = Column(String(100))
    vat_number = Column(String(100))
    swiss_uid = Column(String(50))
    iban = Column(String(34))
    qr_reference = Column(String(50))
    currency = Column(String(3))
    total_amount = Column(Float)
    tax_amount = Column(Float)
    tax_rate_percent = Column(Float)
    invoice_date = Column(String(20))
    due_date = Column(String(20))
    payment_terms = Column(String(255))
    language = Column(SAEnum(InvoiceLanguage), default=InvoiceLanguage.UNKNOWN)
    extraction_confidence = Column(Float)
    line_items = relationship("LineItem", back_populates="invoice", cascade="all, delete-orphan")
    compliance_results = relationship("ComplianceResult", back_populates="invoice", cascade="all, delete-orphan")

    @property
    def overall_compliance_status(self) -> str:
        if not self.compliance_results:
            return ComplianceStatus.UNKNOWN
        statuses = [r.status for r in self.compliance_results]
        if ComplianceStatus.FAIL in statuses:
            return ComplianceStatus.FAIL
        if ComplianceStatus.WARNING in statuses:
            return ComplianceStatus.WARNING
        return ComplianceStatus.PASS


class LineItem(Base):
    __tablename__ = "line_items"
    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    position = Column(Integer)
    description = Column(String(500))
    quantity = Column(Float)
    unit = Column(String(50))
    unit_price = Column(Float)
    total_price = Column(Float)
    tax_rate = Column(Float)
    invoice = relationship("Invoice", back_populates="line_items")


class ComplianceResult(Base):
    __tablename__ = "compliance_results"
    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    checked_at = Column(DateTime, default=datetime.utcnow)
    rule_id = Column(String(50), nullable=False)
    rule_name = Column(String(150), nullable=False)
    category = Column(String(50))
    status = Column(SAEnum(ComplianceStatus), nullable=False)
    message = Column(Text)
    field_checked = Column(String(100))
    actual_value = Column(String(255))
    expected_pattern = Column(String(255))
    invoice = relationship("Invoice", back_populates="compliance_results")
