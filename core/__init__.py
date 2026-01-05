"""
Core module for document extraction and processing.

This module provides the main classes and interfaces for:
- Document models (InvoiceData, BoletoData, DanfeData, etc.)
- Text extraction strategies
- Batch processing
- Document correlation

SOLID Principles applied:
- SRP: Each module has a single responsibility
- OCP: Extensible via registries and inheritance
- DIP: Depends on abstractions (interfaces)
"""

# Re-export from extractors module for backwards compatibility
from extractors.xml_extractor import XmlExtractor, extract_xml

from .batch_processor import BatchProcessor, process_email_batch, process_legacy_folder
from .batch_result import BatchResult, CorrelationResult
from .correlation_service import CorrelationService, correlate_batch
from .diagnostics import ExtractionDiagnostics
from .extractors import BaseExtractor, find_linha_digitavel, register_extractor
from .interfaces import EmailIngestorStrategy, TextExtractionStrategy
from .metadata import EmailMetadata
from .models import (
    BoletoData,
    DanfeData,
    DocumentData,
    InvoiceData,
    OtherDocumentData,
)
from .processor import BaseInvoiceProcessor

__all__ = [
    # Models
    "DocumentData",
    "InvoiceData",
    "BoletoData",
    "DanfeData",
    "OtherDocumentData",
    # Interfaces
    "TextExtractionStrategy",
    "EmailIngestorStrategy",
    # Extractors
    "BaseExtractor",
    "register_extractor",
    "find_linha_digitavel",
    "XmlExtractor",
    "extract_xml",
    # Processors
    "BaseInvoiceProcessor",
    "BatchProcessor",
    "process_email_batch",
    "process_legacy_folder",
    # Results
    "BatchResult",
    "CorrelationResult",
    # Services
    "CorrelationService",
    "correlate_batch",
    # Metadata
    "EmailMetadata",
    # Diagnostics
    "ExtractionDiagnostics",
]
