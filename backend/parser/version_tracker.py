"""
version_tracker.py
───────────────────
Tracks version history of extracted ProductRecord dicts in SQLite.

Table: product_versions
Columns:
  sku          TEXT  — product identifier (or product_name if sku is null)
  version      INTEGER
  data_json    TEXT  — full JSON snapshot of the product at this version
  extracted_at TEXT  — ISO-8601 UTC timestamp
  diff_summary TEXT  — human-readable change summary vs previous version

On each call to `upsert`:
  1. Load the last version from the DB.
  2. If the data has changed → increment version, write diff_summary.
  3. If unchanged → no-op (returns existing version number).

Uses the same SQLite file as the crawler (data/crawl.db) to keep everything
in one place.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Fields compared for the diff summary (skip volatile fields)
_DIFF_FIELDS = [
    "product_name",
    "product_family",
    "description",
    "technical_specs",
    "grade_classification",
    "substrate_compatibility",
    "tile_compatibility",
    "recommended_use_cases",
    "packaging",
]


def _key_for(product: dict) -> str:
    """Stable identifier: prefer sku, fall back to product_name."""
    sku = (product.get("sku") or "").strip()
    if sku:
        return sku
    return (product.get("product_name") or "unknown").strip().lower()


def _diff_summary(old: dict, new: dict) -> str:
    """Return a concise summary of what changed between two versions."""
    changes = []
    for field in _DIFF_FIELDS:
        old_val = old.get(field)
        new_val = new.get(field)
        if old_val != new_val:
            changes.append(f"{field} changed")
    return "; ".join(changes) if changes else "no structural changes"


class VersionTracker:
    """SQLite-backed version tracker for parsed products."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # allow concurrent readers
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS product_versions (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku          TEXT NOT NULL,
                    version      INTEGER NOT NULL,
                    data_json    TEXT NOT NULL,
                    extracted_at TEXT NOT NULL,
                    diff_summary TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pv_sku ON product_versions(sku)"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_latest(self, sku: str) -> Optional[dict]:
        """Return the latest version record for a given sku key, or None."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT data_json, version
                FROM product_versions
                WHERE sku = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (sku,),
            ).fetchone()
            if not row:
                return None
            return {"data": json.loads(row["data_json"]), "version": row["version"]}

    def upsert(self, product: dict) -> int:
        """
        Insert a new version if the product data has changed, or no-op.

        Args:
            product: The extracted product dict (will be mutated to set version).

        Returns:
            The current version number (1 for new, N for updated).
        """
        sku = _key_for(product)
        latest = self.get_latest(sku)

        if latest is None:
            # First time we've seen this product
            version = 1
            diff = "initial extraction"
        else:
            prev_data = latest["data"]
            diff = _diff_summary(prev_data, product)
            # Check if anything actually changed
            has_changes = any(
                prev_data.get(f) != product.get(f) for f in _DIFF_FIELDS
            )
            if not has_changes:
                logger.debug("Product '%s' unchanged — version stays at %d", sku, latest["version"])
                product["version"] = latest["version"]
                return latest["version"]

            version = latest["version"] + 1

        product["version"] = version
        now = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO product_versions (sku, version, data_json, extracted_at, diff_summary)
                VALUES (?, ?, ?, ?, ?)
                """,
                (sku, version, json.dumps(product, default=str), now, diff),
            )

        logger.info(
            "Version tracker: '%s' → v%d (%s)", sku, version, diff
        )
        return version

    def list_products(self, latest_only: bool = True) -> list[dict]:
        """
        List all tracked products (latest version only by default).

        Returns:
            List of product dicts.
        """
        with self._connect() as conn:
            if latest_only:
                rows = conn.execute(
                    """
                    SELECT data_json
                    FROM product_versions
                    WHERE (sku, version) IN (
                        SELECT sku, MAX(version) FROM product_versions GROUP BY sku
                    )
                    ORDER BY sku
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT data_json FROM product_versions ORDER BY sku, version"
                ).fetchall()
            return [json.loads(r["data_json"]) for r in rows]
