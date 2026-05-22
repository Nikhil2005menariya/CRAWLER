"""
api/app.py
───────────
FastAPI application factory.

Creates the app, registers all routers, mounts the Prometheus /metrics
endpoint, and starts/stops the APScheduler via FastAPI's lifespan context.

Usage:
    uvicorn backend.api.app:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from .routes import ingest as ingest_router
from .routes import query as query_router
from .routes import webhook as webhook_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start scheduler on startup, stop on shutdown."""
    from ..sync.scheduler import get_scheduler
    scheduler = get_scheduler()
    scheduler.start()
    logger.info("FastAPI started — SyncScheduler running")
    yield
    scheduler.stop()
    logger.info("FastAPI shutdown — SyncScheduler stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="MYK Laticrete Knowledge Engine API",
        description=(
            "Catalog ingestion, knowledge graph retrieval, and webhook sync "
            "for the MYK Laticrete product catalog."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS — allow local dev + any CMS origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(webhook_router.router)
    app.include_router(query_router.router)
    app.include_router(ingest_router.router)

    # Prometheus metrics endpoint
    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # Health check
    @app.get("/health", tags=["Health"])
    def health():
        return {"status": "ok", "service": "myk-laticrete-knowledge-engine"}

    return app


# Module-level app instance (used by uvicorn)
app = create_app()
