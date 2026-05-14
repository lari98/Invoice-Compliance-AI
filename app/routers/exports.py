from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.services.export_service import ExportService

router = APIRouter(prefix="/exports", tags=["Exports"])


def _parse_ids(ids: str | None) -> list[int] | None:
    if not ids: return None
    try: return [int(i.strip()) for i in ids.split(",") if i.strip()]
    except ValueError: raise HTTPException(400, "ids must be comma-separated integers")


@router.get("/excel")
def export_excel(ids: str | None = Query(None), db: Session = Depends(get_db)):
    """Download Excel report (.xlsx) — all 4 sheets."""
    try: path = ExportService(db).export_excel(invoice_ids=_parse_ids(ids))
    except ValueError as e: raise HTTPException(404, str(e))
    return FileResponse(str(path), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=path.name)


@router.get("/sap-csv")
def export_sap_csv(ids: str | None = Query(None), db: Session = Depends(get_db)):
    """Download SAP FI/MM-compatible CSV."""
    try: path = ExportService(db).export_sap_csv(invoice_ids=_parse_ids(ids))
    except ValueError as e: raise HTTPException(404, str(e))
    return FileResponse(str(path), media_type="text/csv", filename=path.name)


@router.get("/powerbi-json")
def export_powerbi(ids: str | None = Query(None), db: Session = Depends(get_db)):
    """Download denormalised JSON for Power BI."""
    try: path = ExportService(db).export_powerbi_json(invoice_ids=_parse_ids(ids))
    except ValueError as e: raise HTTPException(404, str(e))
    return FileResponse(str(path), media_type="application/json", filename=path.name)
