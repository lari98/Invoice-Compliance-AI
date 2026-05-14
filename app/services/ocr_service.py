"""
OCR Service — pluggable abstraction layer.
Engines: tesseract | mock | easyocr
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
        lang = settings.tesseract_languages
        config = "--oem 3 --psm 6"
        if file_type == "pdf":
            from pdf2image import convert_from_path
            images = convert_from_path(str(file_path), dpi=300)
            return "\n\n".join(self._pytesseract.image_to_string(img, lang=lang, config=config) for img in images)
        else:
            img = Image.open(file_path).convert("L")
            return self._pytesseract.image_to_string(img, lang=lang, config=config)


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


class EasyOCREngine(BaseOCREngine):
    def __init__(self):
        import easyocr
        self._reader = easyocr.Reader(["de", "fr", "it", "en"], gpu=False)

    @property
    def engine_name(self) -> str:
        return "easyocr"

    def extract_text(self, file_path: str, file_type: str) -> str:
        result = self._reader.readtext(str(file_path), detail=0)
        return " ".join(result)


def get_ocr_engine(engine: str | None = None) -> BaseOCREngine:
    name = engine or settings.ocr_engine
    if name == "tesseract":
        try:
            return TesseractOCREngine()
        except Exception as e:
            logger.warning(f"Tesseract unavailable ({e}), falling back to mock.")
            return MockOCREngine()
    elif name == "easyocr":
        return EasyOCREngine()
    else:
        return MockOCREngine()
