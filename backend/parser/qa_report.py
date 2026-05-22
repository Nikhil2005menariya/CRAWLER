"""
qa_report.py
─────────────
Generates a markdown QA report for a batch of extracted products.

Sections:
  1. Summary stats (total, confidence distribution, flagged count)
  2. Field fill rates (% of products with each field populated)
  3. Flagged items (needs_human_review = True)
  4. Per-product confidence table

Output: saved to data/qa_report.md (path configurable).
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

from .field_validator import field_report

logger = logging.getLogger(__name__)

DEFAULT_REPORT_PATH = "data/qa_report.md"


def _confidence_band(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.6:
        return "medium"
    return "low"


def generate_report(
    products: list[dict],
    metrics: dict | None = None,
    output_path: str = DEFAULT_REPORT_PATH,
) -> str:
    """
    Generate a markdown QA report and save it to disk.

    Args:
        products:    List of extracted product dicts.
        metrics:     Optional metrics dict from IngestionState.
        output_path: Where to write the report file.

    Returns:
        The markdown string (also written to output_path).
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total = len(products)

    # --- Confidence distribution ---
    bands: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    flagged: list[dict] = []
    for p in products:
        score = p.get("extraction_confidence", 0.0)
        bands[_confidence_band(score)] += 1
        if p.get("needs_human_review"):
            flagged.append(p)

    # --- Field fill rates ---
    if total > 0:
        field_totals: dict[str, int] = {}
        for p in products:
            for field, populated in field_report(p).items():
                field_totals[field] = field_totals.get(field, 0) + (1 if populated else 0)
        fill_rates = {
            field: round(count / total * 100, 1)
            for field, count in sorted(field_totals.items())
        }
    else:
        fill_rates = {}

    # --- Build markdown ---
    lines: list[str] = [
        f"# MYK Laticrete — Parser QA Report",
        f"",
        f"**Generated:** {now}",
        f"",
        f"---",
        f"",
        f"## 1. Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total products extracted | {total} |",
        f"| High confidence (≥ 0.8) | {bands['high']} |",
        f"| Medium confidence (0.6–0.8) | {bands['medium']} |",
        f"| Low confidence (< 0.6) | {bands['low']} |",
        f"| Flagged for human review | {len(flagged)} |",
    ]

    if metrics:
        crawl_count = metrics.get("crawl_count", "—")
        lines += [
            f"| Records crawled | {crawl_count} |",
        ]

    lines += [
        f"",
        f"---",
        f"",
        f"## 2. Field Fill Rates",
        f"",
        f"| Field | Fill Rate |",
        f"|-------|-----------|",
    ]
    for field, rate in fill_rates.items():
        indicator = "✅" if rate >= 80 else ("⚠️" if rate >= 50 else "❌")
        lines.append(f"| {field} | {rate}% {indicator} |")

    lines += [
        f"",
        f"---",
        f"",
        f"## 3. Flagged for Human Review ({len(flagged)})",
        f"",
    ]
    if flagged:
        lines += [
            "| Product | SKU | Confidence | Source URL |",
            "|---------|-----|------------|------------|",
        ]
        for p in flagged:
            name = p.get("product_name", "Unknown")
            sku = p.get("sku") or "—"
            conf = p.get("extraction_confidence", 0.0)
            url = (p.get("source_urls") or ["—"])[0]
            lines.append(f"| {name} | {sku} | {conf:.2f} | {url} |")
    else:
        lines.append("_None — all products passed confidence threshold._")

    lines += [
        f"",
        f"---",
        f"",
        f"## 4. All Products",
        f"",
        "| # | Product Name | SKU | Family | Confidence | Review? |",
        "|---|-------------|-----|--------|------------|---------|",
    ]
    for i, p in enumerate(products, 1):
        name = p.get("product_name", "Unknown")
        sku = p.get("sku") or "—"
        family = p.get("product_family") or "—"
        conf = p.get("extraction_confidence", 0.0)
        review = "⚠️ Yes" if p.get("needs_human_review") else "✅ No"
        lines.append(f"| {i} | {name} | {sku} | {family} | {conf:.2f} | {review} |")

    markdown = "\n".join(lines)

    # Write to disk
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    logger.info("QA report written to %s (%d products)", output_path, total)
    return markdown
