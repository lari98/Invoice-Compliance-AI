"""
Exports router — v1.2
Endpoints:
  GET /exports/excel           → 7-sheet Excel workbook
  GET /exports/sap-csv         → SAP/ERP semicolon CSV
  GET /exports/powerbi-excel   → 4-page Power BI Excel
  GET /exports/powerbi-json    → denormalised JSON (legacy)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.services.export_service import ExportService

router = APIRouter(prefix="/exports", tags=["Exports"])


def _parse_ids(ids: str | None) -> list[int] | None:
    if not ids:
        return None
    try:
        return [int(i.strip()) for i in ids.split(",") if i.strip()]
    except ValueError:
        raise HTTPException(400, "ids must be comma-separated integers, e.g. '1,2,5'")


# ── Excel full export ─────────────────────────────────────────────────────────

@router.get(
    "/excel",
    summary="Download full Excel report",
    description="""
Downloads a multi-sheet `.xlsx` workbook containing:

| Sheet | Contents |
|-------|----------|
| **Summary** | KPI overview (totals, pass rate, risk counts) |
| **Invoices** | All invoice fields including anomaly score |
| **Vendors** | Aggregated vendor stats, risk level |
| **Compliance Issues** | Only FAIL/WARNING rule results |
| **Anomalies** | All detected anomaly flags |
| **Manual Review** | Invoices needing human review (score ≥ 40 or fail) |
| **Line Items** | Individual invoice line items |

**Request examples:**
- All invoices: `GET /exports/excel`
- Specific invoices: `GET /exports/excel?ids=1,3,7`

**Response:** Binary `.xlsx` file download.
""",
)
def export_excel(
    ids: str | None = Query(None, examples=["1,2,3"],
                             description="Comma-separated invoice IDs to include (omit for all)"),
    db: Session = Depends(get_db),
):
    try:
        path = ExportService(db).export_excel(invoice_ids=_parse_ids(ids))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )


# ── SAP / ERP CSV ─────────────────────────────────────────────────────────────

@router.get(
    "/sap-csv",
    summary="Download SAP/ERP-ready CSV",
    description="""
Downloads a semicolon-delimited CSV suitable for direct SAP FI/MM or ERP import.

**Columns exported:**

| Column | Description |
|--------|-------------|
| `vendor_name` | Supplier name |
| `invoice_number` | Document reference |
| `invoice_date` | Invoice date (YYYY-MM-DD) |
| `due_date` | Payment due date |
| `iban` | Supplier IBAN |
| `currency` | ISO currency code (CHF, EUR, USD, BTC …) |
| `total_amount` | Gross invoice amount |
| `tax_amount` | VAT/tax amount |
| `payment_reference` | QR reference or invoice number |
| `compliance_status` | pass / warning / fail |
| `anomaly_score` | 0–100 risk score |
| `COMPANY_CODE` … | Standard SAP FI fields |

**Request example:** `GET /exports/sap-csv?ids=4,5`
""",
)
def export_sap_csv(
    ids: str | None = Query(None, examples=["1,2,3"],
                             description="Comma-separated invoice IDs (omit for all)"),
    db: Session = Depends(get_db),
):
    try:
        path = ExportService(db).export_sap_csv(invoice_ids=_parse_ids(ids))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return FileResponse(str(path), media_type="text/csv", filename=path.name)


# ── Power BI Excel ────────────────────────────────────────────────────────────

@router.get(
    "/powerbi-excel",
    summary="Download Power BI-ready Excel (4 dashboard pages)",
    description="""
Downloads a `.xlsx` workbook designed for direct import into **Power BI Desktop**
(File → Import → Excel Workbook).  Each sheet maps to one dashboard page:

| Sheet | Dashboard Page | Key Metrics |
|-------|----------------|-------------|
| **Executive Overview** | Page 1 | Total invoices, total value, by language/currency, compliance rate, anomaly count |
| **Compliance Monitoring** | Page 2 | Per-rule fail/warning/pass counts, fail rate %, missing VAT/IBAN/due-date |
| **Vendor Risk** | Page 3 | Vendors ranked by anomaly score, IBAN risk, duplicate invoice numbers |
| **Manual Review Queue** | Page 4 | Invoice ID, vendor, issue, severity, recommended action |

**Request example:** `GET /exports/powerbi-excel`

**Power BI import steps:**
1. Open Power BI Desktop
2. Home → Get Data → Excel Workbook
3. Select the downloaded file
4. Select all 4 sheets → Load
5. Build visuals from the loaded tables
""",
)
def export_powerbi_excel(
    ids: str | None = Query(None, examples=["1,2,3"],
                             description="Comma-separated invoice IDs (omit for all)"),
    db: Session = Depends(get_db),
):
    try:
        path = ExportService(db).export_powerbi_excel(invoice_ids=_parse_ids(ids))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )


# ── Power BI JSON (legacy) ────────────────────────────────────────────────────

@router.get(
    "/powerbi-json",
    summary="Download denormalised JSON (Power BI / legacy)",
    description="""
Downloads a fully denormalised JSON file containing all invoice data, compliance
results, and anomaly flags in a single flat structure — suitable for Power BI,
Tableau, custom dashboards, or data pipelines.

**Response structure:**
```json
{
  "metadata": {
    "generated_at": "2024-03-15T10:30:00Z",
    "total_records": 42,
    "schema_version": "1.2"
  },
  "invoices": [
    {
      "invoice_id": 1,
      "vendor_name": "Mustermann AG",
      "currency": "CHF",
      "total_amount": 3729.45,
      "anomaly_score": 15,
      "overall_compliance": "pass",
      "compliance_results": [...],
      "anomaly_flags": [...],
      "line_items": [...]
    }
  ]
}
```
""",
)
def export_powerbi_json(
    ids: str | None = Query(None, examples=["1,2,3"],
                             description="Comma-separated invoice IDs (omit for all)"),
    db: Session = Depends(get_db),
):
    try:
        path = ExportService(db).export_powerbi_json(invoice_ids=_parse_ids(ids))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return FileResponse(str(path), media_type="application/json", filename=path.name)
