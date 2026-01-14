from .fallback import SmartExtractionStrategy
from .native import NativePdfStrategy
from .ocr import TesseractOcrStrategy
from .pdf_utils import (
    abrir_pdfplumber_com_senha,
    abrir_pypdfium_com_senha,
    gerar_candidatos_senha,
)
from .table import TablePdfStrategy

__all__ = [
    "NativePdfStrategy",
    "TablePdfStrategy",
    "TesseractOcrStrategy",
    "SmartExtractionStrategy",
    "gerar_candidatos_senha",
    "abrir_pdfplumber_com_senha",
    "abrir_pypdfium_com_senha",
]
