"""
agents/nodes/embed_node.py
───────────────────────────
LangGraph node: embed_node

Reads products from IngestionState (output of parse_node), populates
the Neo4j knowledge graph and ChromaDB vector store, then seeds the
10 canonical use cases into Neo4j.
"""

import logging
from typing import Any, Dict

from ..state import IngestionState

logger = logging.getLogger(__name__)


def embed_node(state: IngestionState) -> IngestionState:
    """
    LangGraph node: build graph + embeddings from parsed products.

    Pipeline:
      1. Load GraphBuilder with Neo4j client (or None if offline) + ChromaDB
      2. Run build_from_sqlite() — idempotent upserts to both stores
      3. Seed 10 use cases into Neo4j (skipped if offline)
      4. Update state metrics and graph_updates

    Args:
        state: IngestionState with products populated by parse_node.

    Returns:
        Updated IngestionState with graph_updates, embedding_updates, metrics.
    """
    from ...config.settings import Settings
    from ...graph.neo4j_client import get_graph
    from ...graph.embedder import ProductEmbedder
    from ...graph.vector_store import ProductVectorStore
    from ...graph.builder import GraphBuilder
    from ...graph.seed_use_cases import seed_use_cases

    settings = Settings()
    existing_metrics = dict(state.get("metrics") or {})
    existing_errors  = list(state.get("errors") or [])

    # --- Connect to stores ---
    graph = get_graph()   # None if Neo4j offline (graceful)
    embedder     = ProductEmbedder()
    vector_store = ProductVectorStore()

    builder = GraphBuilder(
        db_path=settings.sqlite_db_path,
        neo4j_graph=graph,
        vector_store=vector_store,
        embedder=embedder,
    )

    # --- Build graph + vectors ---
    logger.info("embed_node: starting graph + vector build")
    result = builder.build_from_sqlite()
    logger.info("embed_node: %s", result)

    # --- Seed use cases ---
    use_case_result = {"seeded": 0}
    if graph is not None:
        try:
            use_case_result = seed_use_cases(graph)
        except Exception as exc:
            msg = f"embed_node: use case seeding failed: {exc}"
            logger.error(msg)
            existing_errors.append(msg)

    # --- Build state update entries ---
    graph_updates = [
        {
            "action":    "build",
            "neo4j_merged":    result["neo4j_merged"],
            "neo4j_failed":    result["neo4j_failed"],
            "use_cases_seeded": use_case_result["seeded"],
        }
    ]
    embedding_updates = [
        {
            "action":  "upsert",
            "count":   result["chroma_upserted"],
            "store":   "chromadb",
        }
    ]

    updated_metrics = {
        **existing_metrics,
        "embed_count":       result["chroma_upserted"],
        "neo4j_merged":      result["neo4j_merged"],
        "neo4j_failed":      result["neo4j_failed"],
        "use_cases_seeded":  use_case_result["seeded"],
        "neo4j_online":      graph is not None,
    }

    return {
        **state,
        "current_phase":      "embed",
        "graph_updates":      graph_updates,
        "embedding_updates":  embedding_updates,
        "metrics":            updated_metrics,
        "errors":             existing_errors,
    }
