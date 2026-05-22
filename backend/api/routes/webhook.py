"""
api/routes/webhook.py
──────────────────────
POST /webhook/cms — receives CMS events and triggers the LangGraph sync_graph.
"""

import logging
import time

from fastapi import APIRouter, HTTPException

from ..models import WebhookPayload, WebhookResponse

router = APIRouter()
logger = logging.getLogger(__name__)

# Pre-compiled sync graph (singleton — compiled once on first request)
_sync_graph = None


def _get_sync_graph():
    global _sync_graph
    if _sync_graph is None:
        from ...agents.sync_graph import build_sync_graph
        _sync_graph = build_sync_graph()
    return _sync_graph


@router.post("/webhook/cms", response_model=WebhookResponse, tags=["Sync"])
async def handle_webhook(payload: WebhookPayload):
    """
    Receive a CMS product event and run the LangGraph sync pipeline.

    - **product.updated** / **product.published** → recrawl → reparse → update graph + vectors
    - **product.deleted** → deprecate product (soft delete) in all stores
    """
    logger.info("Webhook received: event=%s url=%s", payload.event, payload.product_url)

    from ...sync.metrics import webhooks_received_total
    webhooks_received_total.labels(event=payload.event).inc()

    start = time.time()
    initial_state = {
        "trigger":            payload.model_dump(),
        "is_deletion":        payload.event == "product.deleted",
        "crawl_record":       None,
        "parsed_product":     None,
        "graph_updated":      False,
        "embeddings_updated": False,
        "old_product":        None,
        "elapsed_seconds":    0.0,
        "errors":             [],
    }

    try:
        sync_graph = _get_sync_graph()
        result = await sync_graph.ainvoke(initial_state)
    except Exception as exc:
        logger.error("Sync pipeline error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Sync pipeline failed: {exc}")

    elapsed = time.time() - start
    result["elapsed_seconds"] = elapsed

    return WebhookResponse(
        status="complete",
        event=payload.event,
        elapsed_seconds=round(elapsed, 2),
        graph_updated=result.get("graph_updated", False),
        embeddings_updated=result.get("embeddings_updated", False),
        errors=result.get("errors", []),
    )
