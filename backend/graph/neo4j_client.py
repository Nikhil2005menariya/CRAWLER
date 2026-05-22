"""
graph/neo4j_client.py
──────────────────────
Singleton Neo4j client using the raw neo4j driver (no APOC dependency).
Wraps the driver in a thin graph-like object that exposes a .query() method
compatible with the rest of the codebase.

Provides graceful offline fallback so vector-only retrieval still works
when Neo4j is not running.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_client_instance = None  # module-level singleton


class _Neo4jClient:
    """
    Thin wrapper around the raw neo4j.GraphDatabase driver that exposes
    a .query(cypher, params) method — same interface used throughout the
    codebase — without requiring the APOC plugin.
    """

    def __init__(self, uri: str, user: str, password: str):
        from neo4j import GraphDatabase
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        # Verify connectivity
        with self._driver.session() as session:
            session.run("RETURN 1").single()

    def query(self, cypher: str, params: Optional[dict] = None) -> list:
        """Execute a Cypher statement and return results as a list of dicts."""
        params = params or {}
        with self._driver.session() as session:
            result = session.run(cypher, params)
            return [dict(record) for record in result]

    def close(self):
        self._driver.close()


def get_graph(force_reconnect: bool = False) -> Optional[_Neo4jClient]:
    """
    Return a connected _Neo4jClient, or None if Neo4j is not reachable.

    Args:
        force_reconnect: Discard cached instance and reconnect.

    Returns:
        _Neo4jClient or None.
    """
    global _client_instance
    if _client_instance is not None and not force_reconnect:
        return _client_instance

    # Read credentials from Settings (absolute .env path, always works)
    try:
        from ..config.settings import Settings
        s = Settings()
        uri  = s.neo4j_uri
        user = s.neo4j_user
        pwd  = s.neo4j_password
    except Exception:
        uri, user, pwd = "bolt://localhost:7687", "neo4j", ""

    try:
        client = _Neo4jClient(uri, user, pwd)
        _client_instance = client
        logger.info("Neo4j connected: %s", uri)
        # Apply schema constraints/indexes
        from .schema import apply_schema
        apply_schema(client)
        return client

    except Exception as exc:
        logger.warning(
            "Neo4j unavailable (%s). Graph tools will return empty results; "
            "vector search will still work.", exc
        )
        _client_instance = None
        return None


def ping() -> bool:
    """Return True if Neo4j is reachable."""
    return get_graph() is not None


def require_graph() -> _Neo4jClient:
    """Return graph or raise RuntimeError with a clear message."""
    g = get_graph()
    if g is None:
        raise RuntimeError(
            "Neo4j is not running. Start it with:\n"
            "  docker run -d -p7687:7687 -p7474:7474 "
            "-e NEO4J_AUTH=neo4j/myklaticrete2024 neo4j:5"
        )
    return g
