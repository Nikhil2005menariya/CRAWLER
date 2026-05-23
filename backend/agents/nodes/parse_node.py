"""
agents/nodes/parse_node.py
───────────────────────────
LangGraph node: parse_node

Reads `crawl_records` from IngestionState, calls Gemini 2.5 Flash to
extract structured ProductRecord dicts, validates them, tracks versions,
and writes products back to state.

Also persists parsed products to a `products` table in SQLite so that
Task 3 (Graph) can read them independently between pipeline runs.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone

from ..state import IngestionState
from ...config.settings import Settings
from ...parser.llm_extractor import extract_batch
from ...parser.product_schema import ProductRecord
from ...parser.qa_report import generate_report

logger = logging.getLogger(__name__)

_QA_REPORT_PATH = "data/qa_report.md"

# Fields used when computing version diffs
_VERSION_DIFF_FIELDS = [
    "product_name", "product_family", "description", "technical_specs",
    "grade_classification", "substrate_compatibility", "tile_compatibility",
    "recommended_use_cases", "packaging",
]


# ---------------------------------------------------------------------------
# SQLite helpers — all share a single connection passed in
# ---------------------------------------------------------------------------

def _get_connection(db_path: str) -> sqlite3.Connection:
    """Open a WAL-mode SQLite connection with row_factory set."""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_tables(conn: sqlite3.Connection) -> None:
    """Ensure products and product_versions tables exist."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS products (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            sku           TEXT,
            product_name  TEXT NOT NULL,
            product_family TEXT,
            data_json     TEXT NOT NULL,
            confidence    REAL,
            needs_review  INTEGER DEFAULT 0,
            version       INTEGER DEFAULT 1,
            extracted_at  TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);

        CREATE TABLE IF NOT EXISTS product_versions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            sku          TEXT NOT NULL,
            version      INTEGER NOT NULL,
            data_json    TEXT NOT NULL,
            extracted_at TEXT NOT NULL,
            diff_summary TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_pv_sku ON product_versions(sku);
        """
    )
    conn.commit()


def _version_key(product: dict) -> str:
    return (product.get("product_name") or "unknown").strip().lower()


def _diff_summary(old: dict, new: dict) -> str:
    changes = [f for f in _VERSION_DIFF_FIELDS if old.get(f) != new.get(f)]
    return "; ".join(f"{f} changed" for f in changes) or "no structural changes"


def _upsert_version(conn: sqlite3.Connection, product: dict) -> int:
    """Track version history; returns the version number written."""
    sku_key = _version_key(product)
    now = datetime.now(timezone.utc).isoformat()

    row = conn.execute(
        """
        SELECT data_json, version FROM product_versions
        WHERE sku = ?
        ORDER BY version DESC LIMIT 1
        """,
        (sku_key,),
    ).fetchone()

    if row is None:
        version = 1
        diff = "initial extraction"
    else:
        prev = json.loads(row["data_json"])
        has_changes = any(prev.get(f) != product.get(f) for f in _VERSION_DIFF_FIELDS)
        if not has_changes:
            product["version"] = row["version"]
            logger.debug("Product '%s' unchanged — stays at v%d", sku_key, row["version"])
            return row["version"]
        version = row["version"] + 1
        diff = _diff_summary(prev, product)

    product["version"] = version
    conn.execute(
        """
        INSERT INTO product_versions (sku, version, data_json, extracted_at, diff_summary)
        VALUES (?, ?, ?, ?, ?)
        """,
        (sku_key, version, json.dumps(product, default=str), now, diff),
    )
    logger.info("Version tracker: '%s' → v%d (%s)", sku_key, version, diff)
    return version


def _upsert_product(conn: sqlite3.Connection, product: dict) -> None:
    """Insert or update a product row."""
    sku = (product.get("sku") or "").strip() or None
    name = product.get("product_name", "")
    now = datetime.now(timezone.utc).isoformat()
    data_json = json.dumps(product, default=str)

    existing = conn.execute(
        "SELECT id FROM products WHERE product_name = ? LIMIT 1",
        (name,),
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE products
            SET sku=?, product_family=?, data_json=?, confidence=?,
                needs_review=?, version=?, extracted_at=?
            WHERE id=?
            """,
            (
                sku, product.get("product_family"), data_json,
                product.get("extraction_confidence", 0.0),
                1 if product.get("needs_human_review") else 0,
                product.get("version", 1), now,
                existing["id"],
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO products
              (sku, product_name, product_family, data_json, confidence, needs_review, version, extracted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sku, name, product.get("product_family"), data_json,
                product.get("extraction_confidence", 0.0),
                1 if product.get("needs_human_review") else 0,
                product.get("version", 1), now,
            ),
        )


# ---------------------------------------------------------------------------
# Null-sanitizer: Gemini may return null for list/dict fields
# ---------------------------------------------------------------------------

_LIST_FIELDS = [
    "substrate_compatibility", "tile_compatibility",
    "recommended_use_cases", "source_urls",
]


def _sanitize_nulls(product: dict) -> dict:
    """Replace None values for list/dict fields with proper defaults."""
    p = dict(product)
    for field in _LIST_FIELDS:
        if p.get(field) is None:
            p[field] = []
    pkg = p.get("packaging")
    if pkg is None:
        p["packaging"] = {"sizes": [], "shelf_life": None}
    elif isinstance(pkg, dict) and pkg.get("sizes") is None:
        pkg["sizes"] = []
    if p.get("technical_specs") is None:
        p["technical_specs"] = {}
    return p


# ---------------------------------------------------------------------------
# Pydantic validation helper
# ---------------------------------------------------------------------------

def _validate(product: dict) -> tuple[bool, list[str]]:
    """Validate a product dict against the Pydantic schema."""
    try:
        ProductRecord(**product)
        return True, []
    except Exception as exc:
        return False, [str(exc)]


# ---------------------------------------------------------------------------
# LangGraph Node
# ---------------------------------------------------------------------------

def parse_node(state: IngestionState) -> IngestionState:
    """
    LangGraph node: extract structured products from crawl records.

    Pipeline:
      1. Filter crawl_records to those worth parsing (text ≥ 200 chars)
      2. Call Gemini 2.5 Flash via extract_batch (rate-limited to 4s/call)
      3. Validate each result against ProductRecord Pydantic schema
      4. Track versions in SQLite (product_versions table)
      5. Persist to `products` table in SQLite
      6. Generate QA report markdown
      7. Update state with products + metrics

    All SQLite writes use a single shared connection to avoid lock contention.
    """
    settings = Settings()
    db_path = settings.sqlite_db_path

    crawl_records = state.get("crawl_records") or []
    
    # If state.get("crawl_records") is empty, load any existing crawl records from SQLite
    # that haven't been parsed into the products table yet! This ensures missing
    # products (e.g. from an expanded seed list on a subsequent crawl run) are successfully parsed.
    if not crawl_records:
        logger.info("parse_node: state.crawl_records is empty. Querying SQLite for unparsed crawl records...")
        try:
            with _get_connection(db_path) as conn:
                # 1. Fetch already parsed URLs
                parsed_urls = set()
                try:
                    p_rows = conn.execute("SELECT data_json FROM products").fetchall()
                    for pr in p_rows:
                        data = json.loads(pr["data_json"])
                        for s_url in data.get("source_urls") or []:
                            parsed_urls.add(s_url)
                except Exception:
                    pass
                
                # 2. Fetch all crawl records and filter out already parsed URLs
                rows = conn.execute("SELECT url, fetched_at, status_code, content_type, content_hash, title, text, discovered_urls, etag, last_modified FROM crawl_records").fetchall()
                from ...crawler.models import CrawlRecord
                for r in rows:
                    if r["url"] not in parsed_urls:
                        crawl_records.append(
                            CrawlRecord(
                                url=r["url"],
                                fetched_at=r["fetched_at"],
                                status_code=r["status_code"],
                                content_type=r["content_type"],
                                content_hash=r["content_hash"],
                                title=r["title"],
                                text=r["text"],
                                discovered_urls=r["discovered_urls"].split(",") if r["discovered_urls"] else [],
                                etag=r["etag"],
                                last_modified=r["last_modified"]
                            )
                        )
            logger.info("parse_node: Resolved %d unparsed crawl records from SQLite database history.", len(crawl_records))
        except Exception as exc:
            logger.error("parse_node: Failed resolving unparsed historical crawl records: %s", exc)

    existing_errors = list(state.get("errors") or [])
    existing_metrics = dict(state.get("metrics") or {})

    logger.info("parse_node: processing %d crawl records", len(crawl_records))

    # --- Step 1: Filter records worth parsing ---
    parseable = [r for r in crawl_records if r.text and len(r.text) >= 200]
    skipped = len(crawl_records) - len(parseable)
    if skipped:
        logger.info("Skipping %d records (text too short)", skipped)

    if not parseable:
        logger.warning("parse_node: no parseable records — returning empty products")
        return {
            **state,
            "products": [],
            "current_phase": "parse",
            "errors": existing_errors,
            "metrics": {**existing_metrics, "parse_count": 0, "parse_skipped": skipped},
        }

    # --- Step 2: Extract products (Gemini, rate-limited) ---
    raw_products = extract_batch(parseable)

    # --- Step 3–5: Validate, version-track, and persist using ONE connection ---
    valid_products: list[dict] = []
    errors = list(existing_errors)

    with _get_connection(db_path) as conn:
        _init_tables(conn)

        for product in raw_products:
            # Sanitize None → [] for list fields before Pydantic validation
            product = _sanitize_nulls(product)

            ok, errs = _validate(product)
            if not ok:
                msg = f"Schema validation failed for '{product.get('product_name', '?')}': {errs}"
                logger.warning(msg)
                errors.append(msg)
                product["needs_human_review"] = True
                product.setdefault("extraction_confidence", 0.0)

            # Version tracking + product upsert share the same connection
            _upsert_version(conn, product)
            _upsert_product(conn, product)
            valid_products.append(product)

        conn.commit()

    logger.info(
        "parse_node: %d products stored (%d skipped, %d schema errors)",
        len(valid_products), skipped, len(errors) - len(existing_errors),
    )

    # --- Step 6: QA report ---
    updated_metrics = {
        **existing_metrics,
        "crawl_count": existing_metrics.get("crawl_count", len(crawl_records)),
        "parse_count": len(valid_products),
        "parse_skipped": skipped,
        "parse_errors": len(errors) - len(existing_errors),
    }
    generate_report(valid_products, updated_metrics, output_path=_QA_REPORT_PATH)

    return {
        **state,
        "products": valid_products,
        "current_phase": "parse",
        "errors": errors,
        "metrics": updated_metrics,
    }
