from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.database import get_db
from app.models.invoice import Invoice
from app.models.schemas import DashboardStats

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db)):
    invoices = db.query(Invoice).all()
    by_status = {}; by_compliance = {}; by_currency = {}; by_language = {}
    vendor_amounts = {}; total_chf = 0.0
    for inv in invoices:
        s = inv.status.value if inv.status else "unknown"
        by_status[s] = by_status.get(s, 0) + 1
        c = inv.overall_compliance_status or "unknown"
        by_compliance[c] = by_compliance.get(c, 0) + 1
        cur = inv.currency or "unknown"
        by_currency[cur] = by_currency.get(cur, 0) + 1
        lang = inv.language.value if inv.language else "unknown"
        by_language[lang] = by_language.get(lang, 0) + 1
        if inv.vendor_name and inv.total_amount and inv.currency == "CHF":
            vendor_amounts[inv.vendor_name] = vendor_amounts.get(inv.vendor_name, 0.0) + inv.total_amount
            total_chf += inv.total_amount
    top_vendors = sorted([{"vendor": k, "total_chf": round(v, 2)} for k, v in vendor_amounts.items()],
                         key=lambda x: x["total_chf"], reverse=True)[:10]
    return DashboardStats(total_invoices=len(invoices), by_status=by_status, by_compliance=by_compliance,
                          by_currency=by_currency, by_language=by_language, top_vendors=top_vendors,
                          total_amount_chf=round(total_chf, 2))


@router.get("/vendors")
def vendor_summary(db: Session = Depends(get_db)):
    rows = (db.query(Invoice.vendor_name, func.count(Invoice.id).label("count"),
                     func.sum(Invoice.total_amount).label("total"), Invoice.currency)
            .filter(Invoice.vendor_name.isnot(None))
            .group_by(Invoice.vendor_name, Invoice.currency)
            .order_by(func.count(Invoice.id).desc()).all())
    return [{"vendor_name": r.vendor_name, "invoice_count": r.count,
             "total_amount": round(r.total or 0, 2), "currency": r.currency} for r in rows]
