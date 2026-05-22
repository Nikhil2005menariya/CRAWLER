"""
agents/sync_graph.py
─────────────────────
Builds the LangGraph sync_graph — a separate StateGraph triggered by CMS
webhook events to re-ingest a single product or mark it as deprecated.

Flow:
    check_event_node ──┬──▶ recrawl_node → reparse_node → update_graph_node
                       │        → update_vectors_node → sync_report_node
                       └──▶ deprecate_node → sync_report_node
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Literal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

def check_event_node(state: dict) -> dict:
    """
    Reads the webhook trigger and decides the routing direction.
    Sets state["_route"] to "update" or "delete".
    """
    trigger = state.get("trigger") or {}
    event   = trigger.get("event", "product.updated")
    route   = "delete" if event == "product.deleted" else "update"
    logger.info("sync_graph: check_event → route='%s' event='%s'", route, event)
    return {**state, "_route": route, "current_phase": "check_event"}


def _route_decision(state: dict) -> Literal["update", "delete"]:
    return state.get("_route", "update")


def recrawl_node(state: dict) -> dict:
    """Crawl the single product URL from the webhook trigger."""
    trigger = state.get("trigger") or {}
    url = trigger.get("product_url", "")
    if not url:
        return {**state, "crawl_record": None,
                "errors": state.get("errors", []) + ["recrawl: no URL in trigger"]}

    logger.info("sync_graph: recrawl_node → %s", url)
    try:
        from ..config.settings import Settings
        from ..crawler.rate_limiter import RateLimiter
        from ..crawler.robots_handler import RobotsHandler
        from ..crawler.spider import CrawlOrchestrator
        from ..crawler.storage import CrawlStorage

        s = Settings()
        orchestrator = CrawlOrchestrator(
            storage=CrawlStorage(s.sqlite_db_path),
            rate_limiter=RateLimiter(
                min_delay_seconds=s.crawl_delay_seconds,
                max_concurrent=s.max_concurrent_requests,
            ),
            robots_handler=RobotsHandler(s.user_agent),
            user_agent=s.user_agent,
            request_timeout_seconds=s.request_timeout_seconds,
        )
        records = orchestrator.crawl_batch([url])
        record = records[0] if records else None
        return {**state, "crawl_record": record, "current_phase": "recrawl"}
    except Exception as exc:
        logger.error("recrawl_node error: %s", exc)
        return {**state, "crawl_record": None,
                "errors": state.get("errors", []) + [f"recrawl: {exc}"]}


def reparse_node(state: dict) -> dict:
    """Parse the re-crawled record using Gemini."""
    record = state.get("crawl_record")
    if record is None:
        return {**state, "parsed_product": None,
                "errors": state.get("errors", []) + ["reparse: no crawl_record"]}

    logger.info("sync_graph: reparse_node")
    try:
        from ..parser.llm_extractor import extract_product_from_record
        from ..agents.nodes.parse_node import _sanitize_nulls
        from ..parser.product_schema import ProductRecord

        raw = extract_product_from_record(record)
        if raw is None:
            return {**state, "parsed_product": None}

        raw = _sanitize_nulls(raw)
        product = ProductRecord(**raw).model_dump()
        return {**state, "parsed_product": product, "current_phase": "reparse"}
    except Exception as exc:
        logger.error("reparse_node error: %s", exc)
        return {**state, "parsed_product": None,
                "errors": state.get("errors", []) + [f"reparse: {exc}"]}


def update_graph_node(state: dict) -> dict:
    """Upsert the reparsed product into Neo4j."""
    product = state.get("parsed_product")
    if product is None:
        return {**state, "graph_updated": False}

    logger.info("sync_graph: update_graph_node → %s", product.get("product_name"))
    try:
        from ..graph.neo4j_client import get_graph
        from ..graph.builder import GraphBuilder
        from ..config.settings import Settings

        s = Settings()
        graph = get_graph()
        builder = GraphBuilder(db_path=s.sqlite_db_path, neo4j_graph=graph)
        builder._merge_product_node(product)
        builder._merge_relationships(product)
        return {**state, "graph_updated": True, "current_phase": "update_graph"}
    except Exception as exc:
        logger.error("update_graph_node error: %s", exc)
        return {**state, "graph_updated": False,
                "errors": state.get("errors", []) + [f"update_graph: {exc}"]}


def update_vectors_node(state: dict) -> dict:
    """Upsert the reparsed product into ChromaDB."""
    product = state.get("parsed_product")
    if product is None:
        return {**state, "embeddings_updated": False}

    logger.info("sync_graph: update_vectors_node → %s", product.get("product_name"))
    try:
        from ..graph.embedder import ProductEmbedder
        from ..graph.vector_store import ProductVectorStore

        embedder = ProductEmbedder()
        store    = ProductVectorStore()
        vec      = embedder.embed_product_dict(product)
        store.upsert(product, vec)
        return {**state, "embeddings_updated": True, "current_phase": "update_vectors"}
    except Exception as exc:
        logger.error("update_vectors_node error: %s", exc)
        return {**state, "embeddings_updated": False,
                "errors": state.get("errors", []) + [f"update_vectors: {exc}"]}


def deprecate_node(state: dict) -> dict:
    """Mark the product as deprecated in all stores (soft delete)."""
    trigger = state.get("trigger") or {}
    url     = trigger.get("product_url", "")
    logger.info("sync_graph: deprecate_node → %s", url)
    try:
        from ..graph.neo4j_client import get_graph
        from ..graph.vector_store import ProductVectorStore
        from ..sync.reconciler import Reconciler
        from ..config.settings import Settings

        s = Settings()
        reconciler = Reconciler(
            db_path=s.sqlite_db_path,
            neo4j_graph=get_graph(),
            vector_store=ProductVectorStore(),
        )
        result = reconciler.deprecate_by_url(url)
        return {
            **state,
            "graph_updated":      result.get("deprecated_neo4j", 0) > 0,
            "embeddings_updated": result.get("deprecated_chroma", 0) > 0,
            "current_phase":      "deprecate",
        }
    except Exception as exc:
        logger.error("deprecate_node error: %s", exc)
        return {**state, "graph_updated": False, "embeddings_updated": False,
                "errors": state.get("errors", []) + [f"deprecate: {exc}"]}


def sync_report_node(state: dict) -> dict:
    """Record sync metrics and elapsed time."""
    from ..sync.metrics import (
        webhooks_received_total, embeddings_updated_total,
        e2e_latency, refresh_active_products_gauge,
    )
    from ..config.settings import Settings

    trigger = state.get("trigger") or {}
    event   = trigger.get("event", "other")
    elapsed = state.get("elapsed_seconds", 0.0)

    webhooks_received_total.labels(event=event).inc()
    if state.get("embeddings_updated"):
        embeddings_updated_total.inc()
    if elapsed:
        e2e_latency.observe(elapsed)

    s = Settings()
    refresh_active_products_gauge(s.sqlite_db_path)

    logger.info(
        "sync_graph: report — graph_updated=%s embeddings_updated=%s elapsed=%.1fs errors=%d",
        state.get("graph_updated"), state.get("embeddings_updated"),
        elapsed, len(state.get("errors", [])),
    )
    return {**state, "current_phase": "done"}


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_sync_graph():
    """
    Assemble and compile the sync LangGraph StateGraph.

    Returns:
        Compiled LangGraph graph (supports .ainvoke(SyncState)).
    """
    from langgraph.graph import StateGraph, START, END
    from .state import SyncState

    graph = StateGraph(SyncState)

    graph.add_node("check_event",     check_event_node)
    graph.add_node("recrawl",         recrawl_node)
    graph.add_node("reparse",         reparse_node)
    graph.add_node("update_graph",    update_graph_node)
    graph.add_node("update_vectors",  update_vectors_node)
    graph.add_node("deprecate",       deprecate_node)
    graph.add_node("sync_report",     sync_report_node)

    graph.add_edge(START, "check_event")

    # Conditional routing: update vs delete
    graph.add_conditional_edges(
        "check_event",
        _route_decision,
        {"update": "recrawl", "delete": "deprecate"},
    )

    # Update path
    graph.add_edge("recrawl",        "reparse")
    graph.add_edge("reparse",        "update_graph")
    graph.add_edge("update_graph",   "update_vectors")
    graph.add_edge("update_vectors", "sync_report")

    # Delete path
    graph.add_edge("deprecate", "sync_report")
    graph.add_edge("sync_report", END)

    compiled = graph.compile()
    logger.info("sync_graph compiled: check_event → [update|delete] → sync_report")
    return compiled
