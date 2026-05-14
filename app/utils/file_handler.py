import hashlib
from pathlib import Path
from fastapi import UploadFile, HTTPException
from loguru import logger
from app.config import settings

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}


def get_file_extension(filename: str) -> str:
    return Path(filename).suffix.lstrip(".").lower()


def validate_upload(file: UploadFile) -> str:
    ext = get_file_extension(file.filename or "")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '.{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}")
    return ext


async def save_upload(file: UploadFile, invoice_id: int) -> tuple[Path, int]:
    ext = get_file_extension(file.filename or "unknown")
    filename = f"invoice_{invoice_id:05d}.{ext}"
    dest = settings.upload_dir / filename
    content = await file.read()
    size_bytes = len(content)
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise HTTPException(status_code=413, detail=f"File too large: {size_bytes/1024/1024:.1f} MB. Max: {settings.max_upload_size_mb} MB.")
    dest.write_bytes(content)
    logger.info(f"Saved: {dest} ({size_bytes} bytes)")
    return dest, size_bytes


def delete_upload(file_path: str) -> bool:
    path = Path(file_path)
    if path.exists():
        path.unlink()
        return True
    return False
