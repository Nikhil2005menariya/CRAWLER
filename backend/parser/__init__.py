"""parser package — Catalog extraction, validation and version tracking."""

from .field_validator import compute_confidence, field_report
from .llm_extractor import extract_batch, extract_product_from_record
from .product_schema import Packaging, ProductFamily, ProductRecord, TechnicalSpecs
from .qa_report import generate_report
from .version_tracker import VersionTracker

__all__ = [
    "compute_confidence",
    "field_report",
    "extract_batch",
    "extract_product_from_record",
    "ProductFamily",
    "ProductRecord",
    "TechnicalSpecs",
    "Packaging",
    "generate_report",
    "VersionTracker",
]
