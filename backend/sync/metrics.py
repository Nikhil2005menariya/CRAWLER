"""
sync/metrics.py
────────────────
Prometheus metrics for the ingestion + sync pipeline.
All metrics are module-level singletons; import and increment anywhere.
"""

from prometheus_client import Counter, Gauge, Histogram

# ------------------------------------------------------------------
# Counters
# ------------------------------------------------------------------

crawl_total = Counter(
    "crawl_pages_total",
    "Total pages crawled",
    ["status"],          # labels: success | error | skipped
)

parse_total = Counter(
    "parse_products_total",
    "Total products parsed",
    ["result"],          # labels: success | error | skipped
)

embeddings_updated_total = Counter(
    "embeddings_updated_total",
    "Total embeddings upserted to ChromaDB",
)

webhooks_received_total = Counter(
    "webhooks_received_total",
    "Total CMS webhooks received",
    ["event"],           # labels: product.updated | product.deleted | other
)

# ------------------------------------------------------------------
# Histograms
# ------------------------------------------------------------------

crawl_latency = Histogram(
    "crawl_latency_seconds",
    "Time to crawl a single page",
    buckets=[0.5, 1, 2, 5, 10, 30],
)

e2e_latency = Histogram(
    "e2e_update_latency_seconds",
    "End-to-end webhook → graph update latency",
    buckets=[5, 10, 30, 60, 120, 300],
)

# ------------------------------------------------------------------
# Gauges
# ------------------------------------------------------------------

active_products = Gauge(
    "active_products_count",
    "Number of active products in the knowledge graph",
)

freshness_lag = Gauge(
    "freshness_lag_seconds",
    "Seconds since the last successful sync cycle completed",
)


# ------------------------------------------------------------------
# Helper: refresh active_products gauge from SQLite
# ------------------------------------------------------------------

def refresh_active_products_gauge(db_path: str = "./data/crawl.db") -> None:
    """Update the active_products gauge from SQLite products table."""
    import sqlite3
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        row = conn.execute(
            "SELECT COUNT(*) FROM products WHERE needs_review = 0"
        ).fetchone()
        conn.close()
        active_products.set(row[0] if row else 0)
    except Exception:
        pass
