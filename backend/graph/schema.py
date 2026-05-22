"""
graph/schema.py
───────────────
Neo4j schema: constraints, indexes, and constant strings for node labels
and relationship types used throughout the knowledge graph.
"""

# ---------------------------------------------------------------------------
# Node Labels
# ---------------------------------------------------------------------------
LABEL_PRODUCT        = "Product"
LABEL_FAMILY         = "ProductFamily"
LABEL_USE_CASE       = "UseCase"
LABEL_SUBSTRATE      = "Substrate"
LABEL_TILE_TYPE      = "TileType"
LABEL_STANDARD       = "Standard"
LABEL_DOCUMENT       = "Document"

# ---------------------------------------------------------------------------
# Relationship Types
# ---------------------------------------------------------------------------
REL_BELONGS_TO        = "BELONGS_TO"
REL_RECOMMENDED_FOR   = "RECOMMENDED_FOR"
REL_COMPATIBLE_WITH   = "COMPATIBLE_WITH"
REL_SUITABLE_FOR      = "SUITABLE_FOR"
REL_COMPLIES_WITH     = "COMPLIES_WITH"
REL_DOCUMENTED_IN     = "DOCUMENTED_IN"
REL_REQUIRES_SUBSTRATE = "REQUIRES_SUBSTRATE"
REL_USES_TILE         = "USES_TILE"

# ---------------------------------------------------------------------------
# Cypher DDL — run once on startup to ensure schema exists
# ---------------------------------------------------------------------------
SCHEMA_STATEMENTS = [
    # Uniqueness constraints (also create backing indexes)
    "CREATE CONSTRAINT product_sku IF NOT EXISTS FOR (p:Product) REQUIRE p.sku IS UNIQUE",
    "CREATE CONSTRAINT product_name IF NOT EXISTS FOR (p:Product) REQUIRE p.name IS UNIQUE",
    "CREATE CONSTRAINT family_name IF NOT EXISTS FOR (f:ProductFamily) REQUIRE f.name IS UNIQUE",
    "CREATE CONSTRAINT usecase_name IF NOT EXISTS FOR (u:UseCase) REQUIRE u.name IS UNIQUE",
    "CREATE CONSTRAINT substrate_name IF NOT EXISTS FOR (s:Substrate) REQUIRE s.name IS UNIQUE",
    "CREATE CONSTRAINT tiletype_name IF NOT EXISTS FOR (t:TileType) REQUIRE t.name IS UNIQUE",
    "CREATE CONSTRAINT standard_code IF NOT EXISTS FOR (s:Standard) REQUIRE s.code IS UNIQUE",
    "CREATE CONSTRAINT document_url IF NOT EXISTS FOR (d:Document) REQUIRE d.url IS UNIQUE",
    # Extra lookup indexes
    "CREATE INDEX product_family_idx IF NOT EXISTS FOR (p:Product) ON (p.family)",
    "CREATE INDEX product_confidence_idx IF NOT EXISTS FOR (p:Product) ON (p.confidence)",
]


def apply_schema(graph) -> None:
    """Apply all schema constraints and indexes to the Neo4j graph.

    Args:
        graph: A langchain_neo4j.Neo4jGraph instance (or any object with .query()).
    """
    for stmt in SCHEMA_STATEMENTS:
        try:
            graph.query(stmt)
        except Exception as exc:
            # Ignore 'already exists' errors; log anything unexpected
            if "already exists" not in str(exc).lower():
                import logging
                logging.getLogger(__name__).warning("Schema stmt failed: %s — %s", stmt[:60], exc)
