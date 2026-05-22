"""
tools/graph_tools.py
─────────────────────
LangChain @tool wrappers for Neo4j graph queries.
All tools degrade gracefully when Neo4j is offline (return empty list + message).
"""

import json
import logging
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _graph():
    """Get Neo4j graph, returning None if offline."""
    from ..graph.neo4j_client import get_graph
    return get_graph()


# ---------------------------------------------------------------------------
# Tool 1 — Graph-filtered product search
# ---------------------------------------------------------------------------

@tool
def graph_search_tool(
    substrate: str = "",
    tile_type: str = "",
    use_case: str = "",
    environment: str = "",
    limit: int = 5,
) -> str:
    """
    Search the Neo4j product knowledge graph using substrate, tile type,
    use case, or environment filters. Use this when the user specifies
    installation constraints (e.g. 'vitrified tile on concrete').

    Args:
        substrate:   Substrate type (e.g. 'concrete', 'cement_plaster').
        tile_type:   Tile type (e.g. 'vitrified', 'ceramic', 'natural_stone').
        use_case:    Use case name (e.g. 'heated_floor_installation').
        environment: Environment type (e.g. 'interior_wet', 'exterior').
        limit:       Max results to return.

    Returns:
        JSON string listing matching products with name, family, grade, specs.
    """
    graph = _graph()
    if graph is None:
        return json.dumps({"error": "Neo4j offline", "results": []})

    # Build Cypher WHERE clauses dynamically
    filters, params = [], {}

    if substrate:
        filters.append("(p)-[:COMPATIBLE_WITH]->(:Substrate {name: $substrate})")
        params["substrate"] = substrate.lower().replace(" ", "_")

    if tile_type:
        filters.append("(p)-[:SUITABLE_FOR]->(:TileType {name: $tile_type})")
        params["tile_type"] = tile_type.lower().replace(" ", "_")

    if use_case:
        filters.append("(p)-[:RECOMMENDED_FOR]->(:UseCase {name: $use_case})")
        params["use_case"] = use_case.lower().replace(" ", "_")

    where_clause = "WHERE " + " AND ".join(filters) if filters else ""
    params["limit"] = limit

    cypher = f"""
        MATCH (p:Product)
        {where_clause}
        RETURN p.name AS name, p.family AS family, p.grade AS grade,
               p.description AS description, p.specs_json AS specs,
               p.confidence AS confidence
        ORDER BY p.confidence DESC
        LIMIT $limit
    """

    try:
        results = graph.query(cypher, params)
        for r in results:
            if r.get("specs"):
                try:
                    r["specs"] = json.loads(r["specs"])
                except Exception:
                    pass
        return json.dumps({"results": results}, default=str)
    except Exception as exc:
        logger.error("graph_search_tool error: %s", exc)
        return json.dumps({"error": str(exc), "results": []})


# ---------------------------------------------------------------------------
# Tool 2 — Direct SKU / name lookup
# ---------------------------------------------------------------------------

@tool
def product_lookup_tool(name_or_sku: str) -> str:
    """
    Look up a specific MYK Laticrete product by its name or SKU code.
    Use this when the user asks about a specific product (e.g. 'LATAFIX 305').

    Args:
        name_or_sku: Product name or SKU string.

    Returns:
        JSON string with full product details, or an error if not found.
    """
    graph = _graph()
    # Normalize ® for matching
    q = name_or_sku.replace("®", "").strip()
    if graph is None:
        return _sqlite_lookup(name_or_sku)

    cypher = """
        MATCH (p:Product)
        WHERE toLower(replace(p.name, '®', '')) CONTAINS toLower($q) OR p.sku = $q
        RETURN p.name AS name, p.sku AS sku, p.family AS family,
               p.grade AS grade, p.description AS description,
               p.specs_json AS specs, p.confidence AS confidence
        LIMIT 1
    """
    try:
        results = graph.query(cypher, {"q": q})
        if results:
            r = results[0]
            if r.get("specs"):
                r["specs"] = json.loads(r["specs"])
            return json.dumps({"found": True, "product": r}, default=str)
        return json.dumps({"found": False, "query": name_or_sku})
    except Exception as exc:
        logger.error("product_lookup_tool error: %s", exc)
        return json.dumps({"error": str(exc)})


def _sqlite_lookup(name_or_sku: str) -> str:
    """SQLite fallback lookup when Neo4j is offline."""
    import sqlite3, os
    db_path = os.environ.get("SQLITE_DB_PATH", "./data/crawl.db")
    # Strip ® and normalize for fuzzy matching
    q = name_or_sku.replace("®", "").replace("  ", " ").strip()
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        rows = conn.execute(
            "SELECT data_json FROM products WHERE LOWER(REPLACE(product_name,'®','')) LIKE LOWER(?) OR sku = ? LIMIT 1",
            (f"%{q}%", name_or_sku),
        ).fetchall()
        conn.close()
        if rows:
            return json.dumps({"found": True, "product": json.loads(rows[0][0]), "source": "sqlite"})
        return json.dumps({"found": False, "query": name_or_sku, "source": "sqlite"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Tool 3 — Side-by-side product comparison
# ---------------------------------------------------------------------------

@tool
def compare_products_tool(product_a: str, product_b: str) -> str:
    """
    Compare two MYK Laticrete products side by side on key technical specs,
    substrate compatibility, and use cases. Use this when the user asks
    which product is better for a specific application.

    Args:
        product_a: Name or SKU of the first product.
        product_b: Name or SKU of the second product.

    Returns:
        JSON string with a comparison table of both products.
    """
    graph = _graph()
    results = {}

    for key, name in [("a", product_a), ("b", product_b)]:
        raw = product_lookup_tool.invoke({"name_or_sku": name})
        data = json.loads(raw)
        results[key] = data.get("product", {"error": f"not found: {name}"})

    compare_fields = [
        "name", "family", "grade", "specs",
    ]
    comparison = {}
    for field in compare_fields:
        comparison[field] = {
            product_a: results["a"].get(field),
            product_b: results["b"].get(field),
        }

    return json.dumps({"comparison": comparison}, default=str)


# ---------------------------------------------------------------------------
# Tool 4 — Detailed technical specs retrieval
# ---------------------------------------------------------------------------

@tool
def get_specs_tool(product_name: str) -> str:
    """
    Get the full technical specifications for a named MYK Laticrete product
    (open time, coverage rate, compressive strength, mixing ratio, etc.).
    Use this when the user asks for specific numbers or spec values.

    Args:
        product_name: The product name (e.g. 'LATICRETE 335 Maxi').

    Returns:
        JSON string with all technical spec fields and their values.
    """
    raw = product_lookup_tool.invoke({"name_or_sku": product_name})
    data = json.loads(raw)
    if not data.get("found"):
        return json.dumps({"error": f"Product not found: {product_name}"})

    product = data["product"]
    specs = product.get("specs") or {}
    packaging = {}

    # Also fetch packaging from SQLite for completeness
    import sqlite3, os
    db_path = os.environ.get("SQLITE_DB_PATH", "./data/crawl.db")
    q = product_name.replace("®", "").strip()
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        row = conn.execute(
            "SELECT data_json FROM products WHERE LOWER(REPLACE(product_name,'®','')) LIKE LOWER(?) LIMIT 1",
            (f"%{q}%",),
        ).fetchone()
        conn.close()
        if row:
            full = json.loads(row[0])
            packaging = full.get("packaging") or {}
            if not specs:
                specs = full.get("technical_specs") or {}
    except Exception:
        pass

    return json.dumps({
        "product": product.get("name", product_name),
        "technical_specs": specs,
        "packaging": packaging,
        "grade_classification": product.get("grade"),
    }, default=str)


# ---------------------------------------------------------------------------
# Tool 5 — Raw Cypher query
# ---------------------------------------------------------------------------

@tool
def cypher_query_tool(cypher: str) -> str:
    """
    Execute a custom Cypher query against the Neo4j knowledge graph.
    Use this for complex multi-hop queries that other tools cannot answer,
    e.g. 'find all products compatible with concrete AND vitrified tiles
    that comply with C2TE standards'.

    Args:
        cypher: A valid read-only Cypher query string.

    Returns:
        JSON string with the query results or an error message.
    """
    graph = _graph()
    if graph is None:
        return json.dumps({"error": "Neo4j offline"})
    try:
        # Safety: only allow read queries
        stripped = cypher.strip().upper()
        if not stripped.startswith(("MATCH", "RETURN", "WITH", "CALL", "SHOW")):
            return json.dumps({"error": "Only read queries (MATCH/RETURN) are allowed."})
        results = graph.query(cypher)
        return json.dumps({"results": results}, default=str)
    except Exception as exc:
        logger.error("cypher_query_tool error: %s", exc)
        return json.dumps({"error": str(exc), "results": []})


# ---------------------------------------------------------------------------
# All graph tools (for agent registration)
# ---------------------------------------------------------------------------

GRAPH_TOOLS = [
    graph_search_tool,
    product_lookup_tool,
    compare_products_tool,
    get_specs_tool,
    cypher_query_tool,
]
