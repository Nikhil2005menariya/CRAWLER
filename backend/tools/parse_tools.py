"""
tools/parse_tools.py
─────────────────────
LangChain @tool wrappers around the parser core modules.
These are the functions exposed to LangGraph agents.
"""

import json
import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def extract_product_specs(content: str, source_url: str, content_type: str) -> dict:
    """Extract structured product data from raw crawled content using Gemini 2.5 Flash.

    Sends the content to Gemini which extracts product specs, compatibility info,
    and technical data into a structured format matching the ProductRecord schema.

    Args:
        content:      Raw text content from the crawler.
        source_url:   Source URL for provenance tracking.
        content_type: Content type: 'html', 'pdf', or 'docx'.

    Returns:
        Structured product record dict, or empty dict if extraction failed.
    """
    from ..crawler.models import CrawlRecord
    from ..parser.llm_extractor import extract_product_from_record
    from datetime import datetime, timezone

    # Build a minimal CrawlRecord to reuse the extractor's interface
    record = CrawlRecord(
        url=source_url,
        fetched_at=datetime.now(timezone.utc),
        status_code=200,
        content_type=content_type,
        content_hash="",
        text=content,
    )

    result = extract_product_from_record(record)
    return result or {}


@tool
def validate_product_schema(product: dict) -> dict:
    """Validate a product record dict against the Pydantic ProductRecord schema.

    Use this after extraction to confirm the record is structurally valid
    before writing it to the knowledge graph or vector store.

    Args:
        product: Product dict to validate (as returned by extract_product_specs).

    Returns:
        {valid: bool, errors: list[str], confidence: float}
    """
    from ..parser.product_schema import ProductRecord

    try:
        record = ProductRecord(**product)
        return {
            "valid": True,
            "errors": [],
            "confidence": record.extraction_confidence,
        }
    except Exception as exc:
        return {
            "valid": False,
            "errors": [str(exc)],
            "confidence": product.get("extraction_confidence", 0.0),
        }
