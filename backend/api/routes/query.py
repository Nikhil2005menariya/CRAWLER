"""
api/routes/query.py
────────────────────
POST /api/query  — natural language query via the ReAct retrieval agent
GET  /api/products — list all products from SQLite
"""

import json
import logging
import sqlite3
import time
from typing import List

from fastapi import APIRouter, HTTPException

from ..models import ProductSummary, QueryRequest, QueryResponse

router  = APIRouter()
logger  = logging.getLogger(__name__)
_agent  = None


def _get_agent():
    global _agent
    if _agent is None:
        from ...agents.retrieval_agent import build_retrieval_agent
        _agent = build_retrieval_agent()
    return _agent


@router.post("/api/query", response_model=QueryResponse, tags=["Retrieval"])
async def query_agent(request: QueryRequest):
    """
    Send a natural language question to the ReAct retrieval agent.
    The agent autonomously selects among 6 tools (graph search, vector search,
    product lookup, specs, comparison, Cypher) to answer.
    """
    logger.info("Query: %s", request.query)
    t0 = time.time()
    try:
        from ...agents.retrieval_agent import run_query
        result = await run_query(request.query, agent=_get_agent())
    except Exception as exc:
        logger.error("Query failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    elapsed = time.time() - t0
    return QueryResponse(
        query=request.query,
        answer=result["answer"],
        tools_used=result["tools_used"],
        elapsed_seconds=round(elapsed, 2),
    )


@router.get("/api/products", response_model=List[ProductSummary], tags=["Retrieval"])
def list_products():
    """Return all products from the SQLite products table."""
    from ...config.settings import Settings
    s = Settings()
    try:
        conn = sqlite3.connect(s.sqlite_db_path, timeout=5)
        rows = conn.execute(
            "SELECT product_name, data_json, confidence, needs_review, version FROM products ORDER BY confidence DESC"
        ).fetchall()
        conn.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    results = []
    for name, data_json, conf, review, ver in rows:
        try:
            data = json.loads(data_json)
            results.append(ProductSummary(
                product_name=name,
                product_family=data.get("product_family"),
                sku=data.get("sku"),
                confidence=conf or 0.0,
                needs_review=bool(review),
                version=ver or 1,
            ))
        except Exception:
            pass
    return results
