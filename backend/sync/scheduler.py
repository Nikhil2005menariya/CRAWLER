"""
sync/scheduler.py
──────────────────
APScheduler-based background scheduler that runs the ingestion pipeline
on a fixed schedule: full cycle every 24h, priority pages every 6h.
"""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

_scheduler_instance: Optional["SyncScheduler"] = None


class SyncScheduler:
    """
    Wraps APScheduler's AsyncIOScheduler to run LangGraph ingestion cycles
    on a timer. Designed to be started/stopped via FastAPI's lifespan context.
    """

    def __init__(self, db_path: str = "./data/crawl.db"):
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        self.scheduler = AsyncIOScheduler()
        self.db_path   = db_path
        self._last_sync_ts: float = 0.0

    def start(self) -> None:
        """Register jobs and start the scheduler."""
        # Full pipeline every 24 hours
        self.scheduler.add_job(
            self._full_cycle,
            trigger="interval",
            hours=24,
            id="full_cycle",
            replace_existing=True,
        )
        # Priority product pages every 6 hours
        self.scheduler.add_job(
            self._priority_cycle,
            trigger="interval",
            hours=6,
            id="priority_cycle",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info("SyncScheduler started (full=24h, priority=6h)")

    def stop(self) -> None:
        """Gracefully stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("SyncScheduler stopped")

    @property
    def last_sync_ts(self) -> float:
        return self._last_sync_ts

    # ------------------------------------------------------------------
    # Scheduled jobs
    # ------------------------------------------------------------------

    async def _full_cycle(self) -> None:
        """Run the full crawl → parse → embed pipeline on all seed URLs."""
        logger.info("SyncScheduler: starting full cycle")
        t0 = time.time()
        try:
            from ..config.seed_urls import SEED_URLS
            from ..agents.ingestion_graph import build_ingestion_graph

            pipeline = build_ingestion_graph()
            state = {
                "urls_to_crawl":     SEED_URLS,
                "crawl_records":     [],
                "products":          [],
                "graph_updates":     [],
                "embedding_updates": [],
                "errors":            [],
                "metrics":           {},
                "current_phase":     "start",
            }
            await pipeline.ainvoke(state)
            self._last_sync_ts = time.time()

            from .metrics import freshness_lag
            freshness_lag.set(0)
            logger.info("SyncScheduler: full cycle done in %.1fs", time.time() - t0)
        except Exception as exc:
            logger.error("SyncScheduler: full cycle failed: %s", exc)

    async def _priority_cycle(self) -> None:
        """Run a targeted crawl on high-priority product detail pages."""
        logger.info("SyncScheduler: starting priority cycle")
        t0 = time.time()
        try:
            from ..config.seed_urls import SEED_URLS
            from ..agents.ingestion_graph import build_ingestion_graph

            # Priority = product detail pages (index 13 onward in seed list)
            priority_urls = [u for u in SEED_URLS if "/products/" in u and u.count("/") >= 6][:20]

            pipeline = build_ingestion_graph()
            state = {
                "urls_to_crawl": priority_urls,
                "crawl_records": [], "products": [],
                "graph_updates": [], "embedding_updates": [],
                "errors": [], "metrics": {}, "current_phase": "start",
            }
            await pipeline.ainvoke(state)
            self._last_sync_ts = time.time()
            logger.info("SyncScheduler: priority cycle done in %.1fs", time.time() - t0)
        except Exception as exc:
            logger.error("SyncScheduler: priority cycle failed: %s", exc)


def get_scheduler() -> SyncScheduler:
    """Return or create the global scheduler singleton."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = SyncScheduler()
    return _scheduler_instance
