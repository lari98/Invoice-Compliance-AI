"""Export Service — Excel, SAP CSV, Power BI JSON."""
from __future__ import annotations
import csv, json
from datetime import datetime
from pathlib import Path
from typing import Optional
import pandas as pd
from loguru import logger
from sqlalchemy.orm import Session
from app.config import settings
from app.models.invoice import Invoice, LineItem, ComplianceResult


class ExportService:
    def __init__(self, db: Session):
        self.db = db
        settings.export_dir.mkdir(parents=True, exist_ok=True)

    def _invoices(self, ids=None):
        q = self.db.query(Invoice)
        if ids: q = q.filter(Invoice.id.in_(ids))
        return q.order_by(Invoice.id).all()

    def _inv_df(self, invoices):
        return pd.DataFrame([{
            "id": i.id, "filename": i.original_filename, "invoice_number": i.invoice_number,
            "vendor_name": i.vendor_name, "currency": i.currency, "total_amount": i.total_amount,
            "tax_amount": i.tax_amount, "tax_rate_percent": i.tax_rate_percent,
            "invoice_date": i.invoice_date, "due_date": i.due_date,
            "swiss_uid": i.swiss_uid, "iban": i.iban, "qr_reference": i.qr_reference,
            "language": i.language.value if i.language else None,
            "status": i.status.value if i.status else None,
            "compliance": i.overall_compliance_status,
            "confidence": i.extraction_confidence,
        } for i in invoices])

    def _comp_df(self, ids):
        rows = self.db.query(ComplianceResult).filter(ComplianceResult.invoice_id.in_(ids)).all()
        return pd.DataFrame([{"invoice_id": r.invoice_id, "rule_id": r.rule_id, "rule_name": r.rule_name,
                               "category": r.category, "status": r.status.value if r.status else None,
                               "message": r.message, "field": r.field_checked, "actual": r.actual_value} for r in rows])

    def _li_df(self, ids):
        rows = self.db.query(LineItem).filter(LineItem.invoice_id.in_(ids)).all()
        return pd.DataFrame([{"invoice_id": r.invoice_id, "pos": r.position, "desc": r.description,
                               "qty": r.quantity, "unit": r.unit, "unit_price": r.unit_price, "total": r.total_price} for r in rows])

    @staticmethod
    def _write_sheet(ws, df, hfill, hfont):
        from openpyxl.utils import get_column_letter
        from openpyxl.styles import Alignment
        for ci, col in enumerate(df.columns, 1):
            c = ws.cell(1, ci, col.replace("_"," ").title()); c.font = hfont; c.fill = hfill; c.alignment = Alignment(horizontal="center")
        for ri, row in enumerate(df.itertuples(index=False), 2):
            for ci, val in enumerate(row, 1):
                ws.cell(ri, ci, val)
        for ci, cells in enumerate(ws.columns, 1):
            ws.column_dimensions[get_column_letter(ci)].width = min(max(len(str(c.value or "")) for c in cells) + 2, 50)

    def export_excel(self, invoice_ids=None, filename=None) -> Path:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        invs = self._invoices(invoice_ids)
        if not invs: raise ValueError("No invoices found.")
        ids = [i.id for i in invs]
        inv_df = self._inv_df(invs); comp_df = self._comp_df(ids); li_df = self._li_df(ids)
        filename = filename or f"swiss_invoices_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        path = settings.export_dir / filename
        wb = Workbook()
        hfill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        hfont = Font(bold=True, color="FFFFFF")
        ws = wb.active; ws.title = "Summary"
        ws["A1"] = "Swiss Invoice Compliance AI"; ws["A2"] = f"Generated: {datetime.now():%Y-%m-%d %H:%M}"; ws["A3"] = f"Total: {len(invs)}"
        ws2 = wb.create_sheet("Invoices");   self._write_sheet(ws2, inv_df, hfill, hfont)
        ws3 = wb.create_sheet("Line Items"); (self._write_sheet(ws3, li_df, hfill, hfont) if not li_df.empty else ws3.__setitem__("A1","No line items."))
        ws4 = wb.create_sheet("Compliance"); self._write_sheet(ws4, comp_df, hfill, hfont) if not comp_df.empty else ws4.__setitem__("A1","No results.")
        if not comp_df.empty:
            sc = list(comp_df.columns).index("status") + 1
            colors = {"pass":"C6EFCE","warning":"FFEB9C","fail":"FFC7CE"}
            for row in ws4.iter_rows(min_row=2, min_col=sc, max_col=sc):
                for cell in row:
                    from openpyxl.styles import PatternFill as PF
                    c = colors.get(str(cell.value or "").lower(),"FFFFFF"); cell.fill = PF(start_color=c,end_color=c,fill_type="solid")
        wb.save(path); logger.info(f"Excel: {path}"); return path

    def export_sap_csv(self, invoice_ids=None, filename=None) -> Path:
        invs = self._invoices(invoice_ids)
        if not invs: raise ValueError("No invoices found.")
        filename = filename or f"sap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path = settings.export_dir / filename
        fields = ["COMPANY_CODE","DOC_TYPE","PSTNG_DATE","DOC_DATE","PMNTTRMS","REF_DOC_NO",
                  "GROSS_AMOUNT","CURRENCY","CALC_TAX_IND","TAX_AMOUNT","ITEM_TEXT",
                  "VENDOR_NAME","IBAN","VAT_REG_NO","SWISS_UID","QR_REFERENCE","COMPLIANCE_STATUS"]
        with open(path,"w",newline="",encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields, delimiter=";"); w.writeheader()
            for inv in invs:
                w.writerow({"COMPANY_CODE":"1000","DOC_TYPE":"RE",
                             "PSTNG_DATE":datetime.now().strftime("%Y%m%d"),
                             "DOC_DATE":(inv.invoice_date or "").replace("-",""),
                             "PMNTTRMS":inv.payment_terms or "","REF_DOC_NO":inv.invoice_number or "",
                             "GROSS_AMOUNT":f"{inv.total_amount:.2f}" if inv.total_amount else "",
                             "CURRENCY":inv.currency or "CHF","CALC_TAX_IND":"X",
                             "TAX_AMOUNT":f"{inv.tax_amount:.2f}" if inv.tax_amount else "",
                             "ITEM_TEXT":f"Invoice {inv.invoice_number} from {inv.vendor_name}",
                             "VENDOR_NAME":inv.vendor_name or "","IBAN":inv.iban or "",
                             "VAT_REG_NO":inv.vat_number or "","SWISS_UID":inv.swiss_uid or "",
                             "QR_REFERENCE":inv.qr_reference or "","COMPLIANCE_STATUS":inv.overall_compliance_status or "unknown"})
        logger.info(f"SAP CSV: {path}"); return path

    def export_powerbi_json(self, invoice_ids=None, filename=None) -> Path:
        invs = self._invoices(invoice_ids)
        if not invs: raise ValueError("No invoices found.")
        filename = filename or f"powerbi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path = settings.export_dir / filename
        records = []
        for inv in invs:
            crs = [{"rule_id":r.rule_id,"status":r.status.value if r.status else None,"message":r.message} for r in inv.compliance_results]
            lis = [{"pos":l.position,"desc":l.description,"qty":l.quantity,"total":l.total_price} for l in inv.line_items]
            statuses = [c["status"] for c in crs]
            overall = "fail" if "fail" in statuses else "warning" if "warning" in statuses else "pass" if statuses else "unknown"
            records.append({"invoice_id":inv.id,"filename":inv.original_filename,"invoice_number":inv.invoice_number,
                             "vendor_name":inv.vendor_name,"currency":inv.currency,"total_amount":inv.total_amount,
                             "invoice_date":inv.invoice_date,"due_date":inv.due_date,"language":inv.language.value if inv.language else None,
                             "swiss_uid":inv.swiss_uid,"iban":inv.iban,"qr_reference":inv.qr_reference,
                             "overall_compliance":overall,"fail_count":statuses.count("fail"),
                             "warning_count":statuses.count("warning"),"compliance_results":crs,"line_items":lis})
        payload = {"metadata":{"generated_at":datetime.utcnow().isoformat()+"Z","total_records":len(records),"schema_version":"1.0"},"invoices":records}
        with open(path,"w",encoding="utf-8") as f: json.dump(payload,f,ensure_ascii=False,indent=2)
        logger.info(f"Power BI JSON: {path}"); return path
