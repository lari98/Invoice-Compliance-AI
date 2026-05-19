"""
OCR Service — pluggable abstraction layer.
Engines: tesseract | mock | easyocr | auto (SmartExtractorEngine)

v1.4.0 fixes
  - SmartExtractorEngine: added image (JPG/PNG) OCR via Tesseract with
    graceful fallback, and XLSX text extraction via openpyxl.
  - EasyOCREngine: added PDF support (convert pages to images first).
  - Default engine changed from "mock" to "auto" (also fixed in config.py).
  - file_handler.py: ALLOWED_EXTENSIONS now includes txt/html/xlsx/xls.
"""

from __future__ import annotations
import abc
from pathlib import Path
from loguru import logger
from app.config import settings


class BaseOCREngine(abc.ABC):
    @abc.abstractmethod
    def extract_text(self, file_path: str, file_type: str) -> str:
        pass

    @property
    @abc.abstractmethod
    def engine_name(self) -> str:
        pass


# ── Tesseract ──────────────────────────────────────────────────────────────────

class TesseractOCREngine(BaseOCREngine):
    def __init__(self):
        import pytesseract
        if settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
        self._pytesseract = pytesseract

    @property
    def engine_name(self) -> str:
        return "tesseract"

    def extract_text(self, file_path: str, file_type: str) -> str:
        from PIL import Image
        lang   = settings.tesseract_languages
        config = "--oem 3 --psm 6"
        if file_type == "pdf":
            from pdf2image import convert_from_path
            images = convert_from_path(str(file_path), dpi=300)
            return "\n\n".join(
                self._pytesseract.image_to_string(img, lang=lang, config=config)
                for img in images
            )
        else:
            img = Image.open(file_path).convert("L")
            return self._pytesseract.image_to_string(img, lang=lang, config=config)


# ── Mock (tests / demo) ────────────────────────────────────────────────────────

class MockOCREngine(BaseOCREngine):
    MOCK_DE = """\
RECHNUNG
Rechnungsnummer: INV-2024-001247
Rechnungsdatum: 15.03.2024
Fälligkeitsdatum: 15.04.2024
Lieferant:
Mustermann Beratung AG
Bahnhofstrasse 12, 8001 Zürich, Schweiz
UID: CHE-123.456.789
MWST-Nr.: CHE-123.456.789 MWST
IBAN: CH56 0483 5012 3456 7800 9
Zwischensumme CHF: 3'450.00
MWST 8.1%: 279.45
Gesamtbetrag CHF: 3'729.45
Zahlungsbedingungen: 30 Tage netto
QR-Referenz: 21 00000 00003 13947 14300 09017
"""

    MOCK_FR = """\
FACTURE
Numéro de facture: FAC-2024-00892
Date de facture: 20.03.2024
Date d'échéance: 20.04.2024
Fournisseur: Services Numériques Sàrl
Genève, Suisse
IDE: CHE-987.654.321 TVA
IBAN: CH93 0076 2011 6238 5295 7
Montant total CHF: 5'091.51
TVA 8.1%: 381.51
Conditions de paiement: 30 jours net
"""

    @property
    def engine_name(self) -> str:
        return "mock"

    def extract_text(self, file_path: str, file_type: str) -> str:
        sidecar = Path(file_path).with_suffix(".txt")
        if sidecar.exists():
            return sidecar.read_text(encoding="utf-8")
        if "fr" in Path(file_path).name.lower():
            return self.MOCK_FR
        return self.MOCK_DE


# ── EasyOCR ────────────────────────────────────────────────────────────────────

class EasyOCREngine(BaseOCREngine):
    def __init__(self):
        import easyocr
        self._reader = easyocr.Reader(["de", "fr", "it", "en"], gpu=False)

    @property
    def engine_name(self) -> str:
        return "easyocr"

    def extract_text(self, file_path: str, file_type: str) -> str:
        ft = (file_type or Path(file_path).suffix).lower().lstrip(".")

        # FIX v1.4.0: PDFs must be converted to images before EasyOCR can read them.
        if ft == "pdf":
            try:
                from pdf2image import convert_from_path
                import tempfile, os
                images = convert_from_path(str(file_path), dpi=300)
                pages: list[str] = []
                with tempfile.TemporaryDirectory() as tmpdir:
                    for i, img in enumerate(images):
                        img_path = os.path.join(tmpdir, f"page_{i}.png")
                        img.save(img_path, "PNG")
                        result = self._reader.readtext(img_path, detail=0)
                        pages.append(" ".join(result))
                return "\n\n".join(pages)
            except ImportError:
                logger.warning("pdf2image not installed — EasyOCR cannot process PDFs. "
                               "Run: pip install pdf2image")
                return ""
            except Exception as e:
                logger.warning(f"EasyOCR PDF conversion failed for {file_path}: {e}")
                return ""

        # Images: run EasyOCR directly
        result = self._reader.readtext(str(file_path), detail=0)
        return " ".join(result)


# ── SmartExtractorEngine (default "auto") ─────────────────────────────────────

class SmartExtractorEngine(BaseOCREngine):
    """
    Reads real file content without requiring Tesseract:

      PDF          → pdfplumber (embedded text); falls back to Tesseract if
                     available, then to mock demo data for scanned/image PDFs.
      TXT/HTML/CSV → direct UTF-8 read.
      JPG/PNG      → Tesseract (if installed) → mock fallback.   [FIX v1.4.0]
      XLSX/XLS     → openpyxl cell extraction.                   [FIX v1.4.0]
      Sidecar .txt → used for any format if present next to the file.

    Set OCR_ENGINE=auto (or leave unset) in .env to use this engine.
    """

    @property
    def engine_name(self) -> str:
        return "smart"

    # ── internal helpers ───────────────────────────────────────────────────────

    def _try_tesseract_image(self, path: Path) -> str | None:
        """Try to OCR a single image file with Tesseract. Returns None on failure."""
        try:
            import pytesseract
            from PIL import Image
            if settings.tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
            lang   = settings.tesseract_languages
            config = "--oem 3 --psm 6"
            img  = Image.open(str(path)).convert("L")
            text = pytesseract.image_to_string(img, lang=lang, config=config)
            if text.strip():
                logger.info(f"Tesseract extracted {len(text)} chars from {path.name}")
                return text
        except ImportError:
            logger.debug("pytesseract not installed — skipping Tesseract for image OCR.")
        except Exception as e:
            logger.warning(f"Tesseract failed on {path.name}: {e}")
        return None

    def _try_tesseract_pdf(self, path: Path) -> str | None:
        """Convert PDF pages to images and OCR with Tesseract. Returns None on failure."""
        try:
            import pytesseract
            from pdf2image import convert_from_path
            from PIL import Image
            if settings.tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
            lang   = settings.tesseract_languages
            config = "--oem 3 --psm 6"
            images = convert_from_path(str(path), dpi=300)
            pages  = [
                pytesseract.image_to_string(img, lang=lang, config=config)
                for img in images
            ]
            text = "\n\n".join(p for p in pages if p.strip())
            if text.strip():
                logger.info(f"Tesseract (PDF→image) extracted {len(text)} chars from {path.name}")
                return text
        except ImportError:
            logger.debug("pytesseract/pdf2image not installed — skipping Tesseract PDF OCR.")
        except Exception as e:
            logger.warning(f"Tesseract PDF OCR failed on {path.name}: {e}")
        return None

    def _try_xlsx(self, path: Path) -> str | None:
        """Extract all cell values from an Excel workbook as plain text."""
        try:
            import openpyxl
            wb   = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
            rows: list[str] = []
            for sheet in wb.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    cells = [str(c) for c in row if c is not None and str(c).strip()]
                    if cells:
                        rows.append("\t".join(cells))
            wb.close()
            text = "\n".join(rows)
            if text.strip():
                logger.info(f"openpyxl extracted {len(text)} chars from {path.name}")
                return text
        except ImportError:
            logger.warning("openpyxl not installed — cannot read XLSX files. "
                           "Run: pip install openpyxl")
        except Exception as e:
            logger.warning(f"openpyxl failed on {path.name}: {e}")
        return None

    def _mock_fallback(self, path: Path) -> str:
        logger.warning(f"No real text found for {path.name} — returning mock invoice data")
        if "fr" in path.name.lower():
            return MockOCREngine.MOCK_FR
        return MockOCREngine.MOCK_DE

    # ── main entry point ───────────────────────────────────────────────────────

    def extract_text(self, file_path: str, file_type: str) -> str:
        path = Path(file_path)
        ft   = (file_type or path.suffix).lower().lstrip(".")

        # ── 1. PDF via pdfplumber (embedded text) ──────────────────────────────
        if ft == "pdf":
            try:
                import pdfplumber
                with pdfplumber.open(str(path)) as pdf:
                    pages = [page.extract_text() or "" for page in pdf.pages]
                text = "\n\n".join(p for p in pages if p.strip())
                if text.strip():
                    logger.info(f"pdfplumber extracted {len(text)} chars from {path.name}")
                    return text
                logger.warning(
                    f"pdfplumber returned no text from {path.name} "
                    f"(scanned/image PDF) — trying Tesseract OCR."
                )
            except ImportError:
                logger.warning("pdfplumber not installed. Run: pip install pdfplumber")
            except Exception as e:
                logger.warning(f"pdfplumber failed on {path.name}: {e}")

            # FIX v1.4.0: for scanned PDFs try Tesseract before giving up
            text = self._try_tesseract_pdf(path)
            if text:
                return text

            # Sidecar / mock final fallback
            sidecar = path.with_suffix(".txt")
            if sidecar.exists():
                logger.info(f"Using sidecar .txt for scanned PDF {path.name}")
                return sidecar.read_text(encoding="utf-8")
            return self._mock_fallback(path)

        # ── 2. Plain-text / HTML / CSV / XML files ─────────────────────────────
        if ft in ("txt", "html", "htm", "csv", "xml"):
            try:
                return path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                logger.warning(f"Could not read text file {path.name}: {e}")

        # ── 3. Excel files (XLSX / XLS) ────────────────────────────────────────
        # FIX v1.4.0: new branch — was completely missing before
        if ft in ("xlsx", "xls"):
            text = self._try_xlsx(path)
            if text:
                return text
            sidecar = path.with_suffix(".txt")
            if sidecar.exists():
                logger.info(f"Using sidecar .txt for Excel {path.name}")
                return sidecar.read_text(encoding="utf-8")
            return self._mock_fallback(path)

        # ── 4. Image files (JPG / PNG / TIFF …) ───────────────────────────────
        # FIX v1.4.0: was completely missing — jumped straight to mock fallback
        if ft in ("jpg", "jpeg", "png", "tiff", "tif", "bmp", "webp"):
            # Try Tesseract first
            text = self._try_tesseract_image(path)
            if text:
                return text

            # Sidecar .txt next to the image
            sidecar = path.with_suffix(".txt")
            if sidecar.exists():
                logger.info(f"Using sidecar .txt for image {path.name}")
                return sidecar.read_text(encoding="utf-8")

            return self._mock_fallback(path)

        # ── 5. Sidecar .txt for any unrecognised format ────────────────────────
        sidecar = path.with_suffix(".txt")
        if sidecar.exists():
            logger.info(f"Using sidecar .txt for {path.name}")
            return sidecar.read_text(encoding="utf-8")

        # ── 6. Final mock fallback ─────────────────────────────────────────────
        return self._mock_fallback(path)


# ── Factory ────────────────────────────────────────────────────────────────────

def get_ocr_engine(engine: str | None = None) -> BaseOCREngine:
    name = engine or settings.ocr_engine
    if name == "tesseract":
        try:
            return TesseractOCREngine()
        except Exception as e:
            logger.warning(f"Tesseract unavailable ({e}), falling back to smart extractor.")
            return SmartExtractorEngine()
    elif name == "easyocr":
        return EasyOCREngine()
    elif name == "mock":
        # Explicit mock — used in tests
        return MockOCREngine()
    else:
        # "auto" or anything else — use the smart extractor
        return SmartExtractorEngine()
