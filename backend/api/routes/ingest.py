"""
api/routes/ingest.py
─────────────────────
POST /api/ingest — trigger full ingestion pipeline in the background
GET  /api/status — return system health + metrics
"""

import logging
import sqlite3
import time
import uuid

from fastapi import APIRouter, BackgroundTasks

from ..models import IngestRequest, IngestResponse, StatusResponse

router = APIRouter()
logger = logging.getLogger(__name__)

# Track running tasks
_tasks: dict = {}


async def _run_ingestion(task_id: str, request: IngestRequest):
    """Background ingestion task."""
    _tasks[task_id] = {"status": "running", "started_at": time.time()}
    try:
        from ...config.settings import Settings
        from ...config.seed_urls import SEED_URLS

        s = Settings()
        urls = request.urls or SEED_URLS[:10]

        state = {
            "urls_to_crawl":     urls,
            "crawl_records":     [],
            "products":          [],
            "graph_updates":     [],
            "embedding_updates": [],
            "errors":            [],
            "metrics":           {},
            "current_phase":     "start",
        }

        if not request.skip_crawl:
            from ...agents.nodes.crawl_node import crawl_node
            state = crawl_node(state)

        if not request.skip_parse and state.get("crawl_records"):
            from ...agents.nodes.parse_node import parse_node
            state = parse_node(state)

        if not request.skip_embed:
            from ...agents.nodes.embed_node import embed_node
            state = embed_node(state)

        _tasks[task_id] = {
            "status": "done",
            "metrics": state.get("metrics", {}),
            "errors": state.get("errors", []),
            "elapsed": time.time() - _tasks[task_id]["started_at"],
        }
        logger.info("Ingestion task %s done: %s", task_id, _tasks[task_id]["metrics"])
    except Exception as exc:
        _tasks[task_id] = {"status": "error", "error": str(exc)}
        logger.error("Ingestion task %s failed: %s", task_id, exc)


@router.post("/api/ingest", response_model=IngestResponse, tags=["Ingestion"])
async def trigger_ingest(request: IngestRequest, background_tasks: BackgroundTasks):
    """
    Trigger the full ingestion pipeline (crawl → parse → embed) as a background task.
    Returns immediately with a task_id; poll /api/status for progress.
    """
    task_id = str(uuid.uuid4())[:8]
    background_tasks.add_task(_run_ingestion, task_id, request)
    return IngestResponse(
        status="accepted",
        task_id=task_id,
        message=f"Pipeline started (task_id={task_id}). Poll /api/status for progress.",
    )


@router.get("/api/status", response_model=StatusResponse, tags=["Ingestion"])
def get_status():
    """Return system health: Neo4j connectivity, vector count, product count, scheduler state."""
    from ...graph.neo4j_client import ping
    from ...graph.vector_store import ProductVectorStore
    from ...config.settings import Settings
    from ...sync.scheduler import get_scheduler

    s         = Settings()
    neo4j_ok  = ping()
    scheduler = get_scheduler()

    # SQLite counts
    sqlite_products = sqlite_crawl = 0
    try:
        conn = sqlite3.connect(s.sqlite_db_path, timeout=5)
        r1 = conn.execute("SELECT COUNT(*) FROM products").fetchone()
        r2 = conn.execute("SELECT COUNT(*) FROM crawl_records").fetchone()
        conn.close()
        sqlite_products = r1[0] if r1 else 0
        sqlite_crawl    = r2[0] if r2 else 0
    except Exception:
        pass

    # Chroma count
    chroma_count = 0
    try:
        vs = ProductVectorStore()
        chroma_count = vs.count()
    except Exception:
        pass

    return StatusResponse(
        neo4j_online=neo4j_ok,
        chroma_vectors=chroma_count,
        sqlite_products=sqlite_products,
        sqlite_crawl_records=sqlite_crawl,
        last_sync_ts=scheduler.last_sync_ts or None,
        scheduler_running=scheduler.scheduler.running if hasattr(scheduler.scheduler, "running") else False,
    )
