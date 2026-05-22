"""
graph/builder.py
─────────────────
GraphBuilder: reads products from the SQLite `products` table,
upserts Neo4j nodes/relationships, and populates ChromaDB vectors.

Designed to be idempotent — safe to re-run after new crawl/parse cycles.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class GraphBuilder:
    """
    Reads product records from SQLite and populates:
      1. Neo4j knowledge graph (nodes + relationships)
      2. ChromaDB vector index (embeddings)

    Both stores are updated via MERGE/upsert so re-runs are safe.
    """

    def __init__(
        self,
        db_path: str = "./data/crawl.db",
        neo4j_graph=None,         # langchain_neo4j.Neo4jGraph or None (offline)
        vector_store=None,        # ProductVectorStore or None (skip embeddings)
        embedder=None,            # ProductEmbedder or None
    ):
        self.db_path = db_path
        self.graph = neo4j_graph
        self.vector_store = vector_store
        self.embedder = embedder

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_from_sqlite(self, limit: Optional[int] = None) -> dict:
        """
        Full build: load products from SQLite → Neo4j → ChromaDB.

        Args:
            limit: If set, only process the first N products (for testing).

        Returns:
            dict: {loaded, neo4j_merged, neo4j_failed, chroma_upserted}
        """
        products = self._load_products(limit=limit)
        logger.info("GraphBuilder: loaded %d products from SQLite", len(products))

        neo4j_merged = neo4j_failed = chroma_upserted = 0

        # --- Neo4j ---
        if self.graph is not None:
            for p in products:
                try:
                    self._merge_product_node(p)
                    self._merge_relationships(p)
                    neo4j_merged += 1
                except Exception as exc:
                    logger.error("Neo4j merge failed for '%s': %s", p.get("product_name"), exc)
                    neo4j_failed += 1
            logger.info("Neo4j: merged %d products (%d failed)", neo4j_merged, neo4j_failed)
        else:
            logger.info("Neo4j offline — skipping graph population")

        # --- ChromaDB ---
        if self.vector_store is not None and self.embedder is not None:
            embeddings = self.embedder.embed_batch(products)
            chroma_upserted = self.vector_store.upsert_batch(products, embeddings)
            logger.info("ChromaDB: upserted %d vectors", chroma_upserted)
        else:
            logger.info("Vector store or embedder not provided — skipping embeddings")

        return {
            "loaded":          len(products),
            "neo4j_merged":    neo4j_merged,
            "neo4j_failed":    neo4j_failed,
            "chroma_upserted": chroma_upserted,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_products(self, limit: Optional[int] = None) -> list:
        """Load all (or first N) products from the SQLite products table."""
        query = "SELECT data_json FROM products ORDER BY id"
        if limit:
            query += f" LIMIT {limit}"
        try:
            conn = sqlite3.connect(self.db_path, timeout=10)
            rows = conn.execute(query).fetchall()
            conn.close()
            return [json.loads(r[0]) for r in rows]
        except sqlite3.OperationalError:
            logger.warning("products table not found in %s", self.db_path)
            return []

    def _merge_product_node(self, product: dict) -> None:
        """Create or update a Product node in Neo4j."""
        sku  = (product.get("sku") or "").strip() or None
        name = product.get("product_name", "unknown")
        specs = json.dumps(product.get("technical_specs") or {})

        self.graph.query(
            """
            MERGE (p:Product {name: $name})
            SET p.sku             = $sku,
                p.family          = $family,
                p.description     = $description,
                p.grade           = $grade,
                p.specs_json      = $specs_json,
                p.confidence      = $confidence,
                p.needs_review    = $needs_review,
                p.is_active       = true,
                p.updated_at      = $updated_at
            """,
            {
                "name":        name,
                "sku":         sku,
                "family":      product.get("product_family"),
                "description": product.get("description"),
                "grade":       product.get("grade_classification"),
                "specs_json":  specs,
                "confidence":  product.get("extraction_confidence", 0.0),
                "needs_review": product.get("needs_human_review", False),
                "updated_at":  datetime.now(timezone.utc).isoformat(),
            },
        )

    def _merge_relationships(self, product: dict) -> None:
        """Create edges: ProductFamily, Substrate, TileType, UseCase, Document."""
        name = product.get("product_name", "unknown")

        # BELONGS_TO → ProductFamily
        family = product.get("product_family")
        if family:
            self.graph.query(
                """
                MERGE (f:ProductFamily {name: $family})
                WITH f
                MATCH (p:Product {name: $name})
                MERGE (p)-[:BELONGS_TO]->(f)
                """,
                {"family": family, "name": name},
            )

        # COMPATIBLE_WITH → Substrate
        for sub in product.get("substrate_compatibility") or []:
            if sub:
                self.graph.query(
                    """
                    MERGE (s:Substrate {name: $sub})
                    WITH s
                    MATCH (p:Product {name: $name})
                    MERGE (p)-[:COMPATIBLE_WITH]->(s)
                    """,
                    {"sub": sub.lower().replace(" ", "_"), "name": name},
                )

        # SUITABLE_FOR → TileType
        for tile in product.get("tile_compatibility") or []:
            if tile:
                self.graph.query(
                    """
                    MERGE (t:TileType {name: $tile})
                    WITH t
                    MATCH (p:Product {name: $name})
                    MERGE (p)-[:SUITABLE_FOR]->(t)
                    """,
                    {"tile": tile.lower().replace(" ", "_"), "name": name},
                )

        # RECOMMENDED_FOR → UseCase (matched by keyword)
        for use in product.get("recommended_use_cases") or []:
            if use:
                self.graph.query(
                    """
                    MERGE (u:UseCase {name: $use})
                    WITH u
                    MATCH (p:Product {name: $name})
                    MERGE (p)-[:RECOMMENDED_FOR]->(u)
                    """,
                    {"use": use.lower().replace(" ", "_"), "name": name},
                )

        # COMPLIES_WITH → Standard (grade classification)
        grade = product.get("grade_classification")
        if grade:
            self.graph.query(
                """
                MERGE (s:Standard {code: $code})
                WITH s
                MATCH (p:Product {name: $name})
                MERGE (p)-[:COMPLIES_WITH]->(s)
                """,
                {"code": grade, "name": name},
            )

        # DOCUMENTED_IN → Document (source URLs)
        for url in product.get("source_urls") or []:
            if url:
                self.graph.query(
                    """
                    MERGE (d:Document {url: $url})
                    SET d.type = 'webpage', d.fetched_at = $fetched_at
                    WITH d
                    MATCH (p:Product {name: $name})
                    MERGE (p)-[:DOCUMENTED_IN]->(d)
                    """,
                    {"url": url, "fetched_at": datetime.now(timezone.utc).isoformat(), "name": name},
                )
