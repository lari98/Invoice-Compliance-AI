from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.database import get_db
from app.models.invoice import Invoice, ComplianceResult, ComplianceStatus
from app.models.schemas import ComplianceSummary, ComplianceResultOut

router = APIRouter(prefix="/compliance", tags=["Compliance"])


@router.get("/{invoice_id}", response_model=ComplianceSummary)
def get_compliance(invoice_id: int, db: Session = Depends(get_db)):
    if not db.get(Invoice, invoice_id):
        raise HTTPException(404, "Invoice not found.")
    results = db.query(ComplianceResult).filter(ComplianceResult.invoice_id == invoice_id).all()
    statuses = [r.status.value for r in results]
    overall = "fail" if "fail" in statuses else ("warning" if "warning" in statuses else "pass")
    return ComplianceSummary(invoice_id=invoice_id, overall_status=overall,
                             total_checks=len(results), passed=statuses.count("pass"),
                             warnings=statuses.count("warning"), failed=statuses.count("fail"),
                             results=[ComplianceResultOut.model_validate(r) for r in results])


@router.get("/stats/overview")
def compliance_overview(db: Session = Depends(get_db)):
    invoices = db.query(Invoice).all()
    pass_c = warn_c = fail_c = 0
    for inv in invoices:
        s = inv.overall_compliance_status
        if s == "pass": pass_c += 1
        elif s == "warning": warn_c += 1
        elif s == "fail": fail_c += 1
    top_fails = (db.query(ComplianceResult.rule_id, ComplianceResult.rule_name,
                          func.count(ComplianceResult.id).label("count"))
                 .filter(ComplianceResult.status == ComplianceStatus.FAIL)
                 .group_by(ComplianceResult.rule_id, ComplianceResult.rule_name)
                 .order_by(func.count(ComplianceResult.id).desc()).limit(10).all())
    return {"total_invoices": len(invoices),
            "compliance_breakdown": {"pass": pass_c, "warning": warn_c, "fail": fail_c},
            "top_failing_rules": [{"rule_id": r.rule_id, "rule_name": r.rule_name, "count": r.count} for r in top_fails]}
