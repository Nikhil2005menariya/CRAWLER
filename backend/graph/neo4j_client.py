"""
graph/neo4j_client.py
──────────────────────
Singleton-style Neo4j client. Loads credentials from .env, applies the
graph schema on first connection, and provides a graceful offline fallback
so that vector-only retrieval still works when Neo4j is not running.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env (backend/.env or repo root)
for _candidate in [
    Path(__file__).parents[2] / ".env",   # backend/.env
    Path(__file__).parents[3] / ".env",   # repo root .env
]:
    if _candidate.exists():
        load_dotenv(_candidate, override=False)
        break

_graph_instance = None  # module-level singleton


def get_graph(force_reconnect: bool = False):
    """
    Return a connected langchain_neo4j.Neo4jGraph instance, or None if
    Neo4j is not reachable (graceful fallback for vector-only mode).

    Args:
        force_reconnect: If True, discard cached instance and reconnect.

    Returns:
        Neo4jGraph instance or None.
    """
    global _graph_instance
    if _graph_instance is not None and not force_reconnect:
        return _graph_instance

    uri  = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER")
    pwd  = os.environ.get("NEO4J_PASSWORD")

    # Fallback to pydantic-settings (handles .env loading reliably)
    if not all([uri, user, pwd]):
        try:
            from ..config.settings import Settings
            s = Settings()
            uri  = uri  or s.neo4j_uri
            user = user or s.neo4j_user
            pwd  = pwd  or s.neo4j_password
        except Exception:
            pass

    uri  = uri  or "bolt://localhost:7687"
    user = user or "neo4j"
    pwd  = pwd  or ""

    try:
        from langchain_neo4j import Neo4jGraph
        graph = Neo4jGraph(url=uri, username=user, password=pwd)
        # Quick connectivity ping
        graph.query("RETURN 1 AS ok")
        _graph_instance = graph
        logger.info("Neo4j connected: %s", uri)
        # Apply schema on first successful connection
        from .schema import apply_schema
        apply_schema(graph)
        return graph

    except Exception as exc:
        logger.warning(
            "Neo4j unavailable (%s). Graph tools will return empty results; "
            "vector search will still work.", exc
        )
        _graph_instance = None
        return None


def ping() -> bool:
    """Return True if Neo4j is reachable."""
    return get_graph() is not None


def require_graph():
    """Return graph or raise RuntimeError with a clear message."""
    g = get_graph()
    if g is None:
        raise RuntimeError(
            "Neo4j is not running. Start it with:\n"
            "  docker run -d -p7687:7687 -p7474:7474 "
            "-e NEO4J_AUTH=neo4j/myklaticrete2024 neo4j:5"
        )
    return g
