"""
tools/vector_tools.py
──────────────────────
LangChain @tool for ChromaDB vector similarity search.
"""

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_store = None
_embedder = None


def _get_store():
    global _store
    if _store is None:
        from ..graph.vector_store import ProductVectorStore
        _store = ProductVectorStore()
    return _store


def _get_embedder():
    global _embedder
    if _embedder is None:
        from ..graph.embedder import ProductEmbedder
        _embedder = ProductEmbedder()
    return _embedder


@tool
def vector_search_tool(query: str, k: int = 5) -> str:
    """
    Perform semantic similarity search over MYK Laticrete products using
    natural language. Use this when the user's question is conceptual or
    doesn't map to an exact product name, substrate, or tile type
    (e.g. 'something waterproof for pools', 'flexible adhesive for stone').

    Args:
        query: Natural language description of desired product properties.
        k:     Number of results to return (default 5).

    Returns:
        JSON string listing the most semantically similar products,
        sorted by similarity score.
    """
    try:
        store = _get_store()
        if store.count() == 0:
            return json.dumps({
                "warning": "Vector store is empty. Run the embed_node first.",
                "results": [],
            })

        embedder = _get_embedder()
        query_vec = embedder.embed_query(query)
        hits = store.similarity_search(query_vec, k=k)

        results = []
        for h in hits:
            results.append({
                "product_name":   h["metadata"].get("product_name"),
                "product_family": h["metadata"].get("product_family"),
                "sku":            h["metadata"].get("sku") or None,
                "similarity":     round(1 - h["distance"], 4),   # cosine → similarity
                "snippet":        h["document"],
            })

        return json.dumps({"query": query, "results": results}, default=str)

    except Exception as exc:
        logger.error("vector_search_tool error: %s", exc)
        return json.dumps({"error": str(exc), "results": []})


# ---------------------------------------------------------------------------
# All vector tools (for agent registration)
# ---------------------------------------------------------------------------

VECTOR_TOOLS = [vector_search_tool]
