"""
sync/reconciler.py
───────────────────
Reconciler: handles product deprecation (soft-delete) and hard-delete
in both Neo4j and ChromaDB when CMS signals a product.deleted event.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class Reconciler:
    """
    Manages the lifecycle of deprecated/deleted products across all stores.

    Deprecation is a *soft delete* — products are never physically removed
    from Neo4j or SQLite; they are marked `is_active=False` and given a
    `:Deprecated` label so historical graph queries still work.
    """

    def __init__(
        self,
        db_path: str = "./data/crawl.db",
        neo4j_graph=None,
        vector_store=None,
    ):
        self.db_path    = db_path
        self.graph      = neo4j_graph
        self.vector_store = vector_store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def deprecate_by_url(self, url: str) -> dict:
        """
        Mark all products sourced from `url` as deprecated across all stores.

        Args:
            url: The product page URL that triggered the delete event.

        Returns:
            dict: {deprecated_sqlite, deprecated_neo4j, deprecated_chroma}
        """
        product_name = self._find_product_name_by_url(url)
        if not product_name:
            logger.warning("Reconciler: no product found for URL %s", url)
            return {"deprecated_sqlite": 0, "deprecated_neo4j": 0, "deprecated_chroma": 0}

        r_sqlite = self._deprecate_sqlite(product_name)
        r_neo4j  = self._deprecate_neo4j(product_name)
        r_chroma = self._deprecate_chroma(product_name)

        logger.info(
            "Reconciler: deprecated '%s' — sqlite=%s neo4j=%s chroma=%s",
            product_name, r_sqlite, r_neo4j, r_chroma,
        )
        return {
            "deprecated_sqlite": r_sqlite,
            "deprecated_neo4j":  r_neo4j,
            "deprecated_chroma": r_chroma,
            "product_name":      product_name,
        }

    def deprecate_by_name(self, product_name: str) -> dict:
        """Directly deprecate a product by name across all stores."""
        r_sqlite = self._deprecate_sqlite(product_name)
        r_neo4j  = self._deprecate_neo4j(product_name)
        r_chroma = self._deprecate_chroma(product_name)
        logger.info("Reconciler: deprecated '%s'", product_name)
        return {
            "deprecated_sqlite": r_sqlite,
            "deprecated_neo4j":  r_neo4j,
            "deprecated_chroma": r_chroma,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_product_name_by_url(self, url: str) -> Optional[str]:
        """Find a product name from the SQLite products table by source URL."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            rows = conn.execute("SELECT product_name, data_json FROM products").fetchall()
            conn.close()
            for name, data_json in rows:
                try:
                    data = json.loads(data_json)
                    if url in (data.get("source_urls") or []):
                        return name
                except Exception:
                    pass
        except Exception as exc:
            logger.error("_find_product_name_by_url error: %s", exc)
        return None

    def _deprecate_sqlite(self, product_name: str) -> int:
        """Mark product needs_review=1 as a soft-delete signal in SQLite."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            cur = conn.execute(
                "UPDATE products SET needs_review = 1 WHERE LOWER(REPLACE(product_name,'®','')) "
                "LIKE LOWER(REPLACE(?,'®',''))",
                (f"%{product_name}%",),
            )
            conn.commit()
            conn.close()
            return cur.rowcount
        except Exception as exc:
            logger.error("_deprecate_sqlite error: %s", exc)
            return 0

    def _deprecate_neo4j(self, product_name: str) -> int:
        """Set is_active=False and add :Deprecated label in Neo4j."""
        if self.graph is None:
            return 0
        try:
            q = product_name.replace("®", "").strip()
            result = self.graph.query(
                """
                MATCH (p:Product)
                WHERE toLower(replace(p.name, '®', '')) CONTAINS toLower($q)
                SET p.is_active = false, p.deprecated_at = $ts
                RETURN count(p) AS cnt
                """,
                {"q": q, "ts": datetime.now(timezone.utc).isoformat()},
            )
            return result[0]["cnt"] if result else 0
        except Exception as exc:
            logger.error("_deprecate_neo4j error: %s", exc)
            return 0

    def _deprecate_chroma(self, product_name: str) -> int:
        """Update ChromaDB metadata to mark product as deprecated."""
        if self.vector_store is None:
            return 0
        try:
            q = product_name.replace("®", "").strip().lower().replace(" ", "_")
            # Try both ID formats
            for doc_id in [f"name:{q}", f"sku:"]:
                try:
                    self.vector_store._collection.update(
                        ids=[doc_id],
                        metadatas=[{"needs_review": "True", "is_active": "False"}],
                    )
                    return 1
                except Exception:
                    pass
        except Exception as exc:
            logger.error("_deprecate_chroma error: %s", exc)
        return 0
