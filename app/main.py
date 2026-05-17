"""
Swiss Invoice Compliance AI — FastAPI Entry Point

Run:  uvicorn app.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from loguru import logger
from app.config import settings
from app.models.database import init_db
from app.routers import invoices, compliance, dashboard, exports, anomalies

# Resolve path to dashboard.html at project root (one level above app/)
_DASHBOARD_HTML = Path(__file__).parent.parent / "dashboard.html"


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="AI-powered Swiss invoice compliance system — OCR, field extraction, compliance checks, Excel/SAP/PowerBI export.",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

    app.include_router(invoices.router)
    app.include_router(compliance.router)
    app.include_router(dashboard.router)
    app.include_router(exports.router)
    app.include_router(anomalies.router)

    @app.on_event("startup")
    def on_startup():
        logger.info(f"Starting {settings.app_name} v{settings.app_version}")
        init_db()
        logger.info("DB ready.")

    @app.get("/health", tags=["System"])
    def health():
        return {"status": "ok", "app": settings.app_name, "version": settings.app_version, "ocr_engine": settings.ocr_engine}

    @app.get("/", tags=["System"], include_in_schema=False)
    def root():
        # Serve the dashboard UI if dashboard.html exists at project root
        if _DASHBOARD_HTML.exists():
            return FileResponse(str(_DASHBOARD_HTML), media_type="text/html")
        return JSONResponse({"message": f"Welcome to {settings.app_name}", "docs": "/docs", "health": "/health"})

    @app.get("/api", tags=["System"])
    def api_info():
        return JSONResponse({"message": f"Welcome to {settings.app_name}", "docs": "/docs", "health": "/health"})

    return app


app = create_app()
