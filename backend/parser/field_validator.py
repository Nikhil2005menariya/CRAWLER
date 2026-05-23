"""
field_validator.py
───────────────────
Confidence scoring for extracted ProductRecord dicts.

The score is the fraction of 12 key fields that are populated.
A score < 0.6 (fewer than 8/12 fields) triggers `needs_human_review`.
"""

from typing import Any


# Ordered list of (label, extractor_fn) for the 12 scored fields
_CHECKS: list[tuple[str, Any]] = [
    ("product_name",       lambda d: bool(d.get("product_name"))),
    ("sku",                lambda d: bool(d.get("sku"))),
    ("product_family",     lambda d: bool(d.get("product_family"))),
    ("description",        lambda d: bool(d.get("description"))),
    ("coverage_rate",      lambda d: bool(
        (d.get("technical_specs") or {}).get("coverage_rate")
    )),
    ("open_time",          lambda d: bool(
        (d.get("technical_specs") or {}).get("open_time")
    )),
    ("grade_classification", lambda d: bool(d.get("grade_classification"))),
    ("substrate_compatibility", lambda d: len(
        d.get("substrate_compatibility") or []
    ) > 0),
    ("tile_compatibility", lambda d: len(
        d.get("tile_compatibility") or []
    ) > 0),
    ("recommended_use_cases", lambda d: len(
        d.get("recommended_use_cases") or []
    ) > 0),
    ("packaging_sizes",    lambda d: len(
        (d.get("packaging") or {}).get("sizes") or []
    ) > 0),
    ("shelf_life",         lambda d: bool(
        (d.get("packaging") or {}).get("shelf_life")
    )),
]

_TOTAL = len(_CHECKS)


def compute_confidence(product: dict) -> float:
    """
    Compute a confidence score in [0.0, 1.0] for an extracted product dict.

    Args:
        product: Raw dict returned by the LLM extractor.

    Returns:
        Float confidence score where 1.0 = all 12 fields populated.
    """
    if not product or not isinstance(product, dict):
        return 0.0
    passed = sum(1 for _, check in _CHECKS if check(product))
    return round(passed / _TOTAL, 4)


def field_report(product: dict) -> dict[str, bool]:
    """
    Return a per-field boolean map showing which fields are populated.

    Useful for QA reporting.
    """
    if not product or not isinstance(product, dict):
        return {label: False for label, _ in _CHECKS}
    return {label: check(product) for label, check in _CHECKS}
