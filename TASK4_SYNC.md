# TASK 4 — Sync Engine (LangGraph Pipeline)

## Objective
Keep knowledge base fresh via a **LangGraph sync_graph** triggered by webhooks.
Delta detection → targeted re-ingestion → graph/vector update in < 5 minutes.

## How it fits in LangGraph

```
sync_graph is a SEPARATE LangGraph StateGraph (not part of ingestion_graph).
Triggered by: POST /webhook/cms → sync_graph.ainvoke(SyncState)

Flow:
[check_event] ──┬──▶ [recrawl] → [reparse] → [update_graph] → [update_vectors] → [report]
                └──▶ [deprecate] → [report]
```

## Sync Graph Nodes (see AGENTS_AND_TOOLS.md for full code)

### check_event_node
- Reads webhook payload event type
- Routes: product.updated/published → "update", product.deleted → "delete"

### recrawl_node
- Calls `crawl_tools.fetch_page` tool for the specific URL
- Returns updated CrawlRecord

### reparse_node
- Calls `parse_tools.extract_product_specs` tool (Gemini Flash)
- Returns structured ProductRecord

### update_graph_node
- Calls `graph_tools.upsert_to_graph` tool
- Creates/updates nodes + edges in Neo4j

### update_vectors_node
- Calls `vector_tools.embed_and_store` tool
- Updates ChromaDB embedding

### deprecate_node
- Marks product as deprecated in Neo4j (adds :Deprecated label, is_active=false)
- Updates ChromaDB metadata

### sync_report_node
- Records metrics, calculates elapsed time

## Delta Detection (`sync/delta_detector.py`)

```python
class DeltaDetector:
    def detect_changes(self, records: list[CrawlRecord]) -> dict:
        result = {"added": [], "modified": [], "unchanged": [], "deleted": []}
        seen_urls = set()
        for record in records:
            seen_urls.add(record["url"])
            stored_hash = self.db.get_hash(record["url"])
            if stored_hash is None:
                result["added"].append(record)
            elif stored_hash != record["content_hash"]:
                result["modified"].append(record)
            else:
                result["unchanged"].append(record)
        # Detect deletions
        for url in self.db.get_all_urls():
            if url not in seen_urls:
                result["deleted"].append(url)
        return result
```

## Webhook Endpoint (`api/routes/webhook.py`)

```python
from agents.sync_graph import build_sync_graph

sync_pipeline = build_sync_graph()

@router.post("/webhook/cms")
async def handle_webhook(payload: WebhookPayload):
    """Triggers the LangGraph sync pipeline."""
    import time
    start = time.time()
    
    result = await sync_pipeline.ainvoke({
        "trigger": payload.dict(),
        "is_deletion": payload.event == "product.deleted",
        "crawl_record": None,
        "parsed_product": None,
        "graph_updated": False,
        "embeddings_updated": False,
        "elapsed_seconds": 0.0,
    })
    
    result["elapsed_seconds"] = time.time() - start
    return {
        "status": "complete",
        "elapsed_seconds": result["elapsed_seconds"],
        "graph_updated": result["graph_updated"],
        "embeddings_updated": result["embeddings_updated"],
    }
```

## Scheduler (`sync/scheduler.py`)

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from agents.ingestion_graph import build_ingestion_graph

class SyncScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.pipeline = build_ingestion_graph()
    
    def start(self):
        # Full pipeline every 24h
        self.scheduler.add_job(self.full_cycle, 'interval', hours=24)
        # Priority pages every 6h
        self.scheduler.add_job(self.priority_cycle, 'interval', hours=6)
        self.scheduler.start()
    
    async def full_cycle(self):
        """Run the full LangGraph ingestion pipeline."""
        from config.seed_urls import SEED_URLS
        await self.pipeline.ainvoke({
            "urls_to_crawl": SEED_URLS,
            "crawl_records": [], "products": [],
            "graph_updates": [], "embedding_updates": [],
            "sync_status": {}, "errors": [], "metrics": {},
            "current_phase": "start"
        })
```

## Metrics (`sync/metrics.py`)

```python
from prometheus_client import Counter, Histogram, Gauge

crawl_total = Counter('crawl_pages_total', 'Pages crawled', ['status'])
parse_total = Counter('parse_products_total', 'Products parsed', ['result'])
embeddings_updated = Counter('embeddings_updated_total', 'Embeddings updated')
webhook_received = Counter('webhooks_received_total', 'Webhooks', ['event'])
crawl_latency = Histogram('crawl_latency_seconds', 'Crawl latency')
e2e_latency = Histogram('e2e_update_latency_seconds', 'End-to-end update latency')
active_products = Gauge('active_products_count', 'Active products')
freshness_lag = Gauge('freshness_lag_seconds', 'Time since last sync')
```

## Demo Script (`scripts/simulate_webhook.py`)

```python
"""Run: python scripts/simulate_webhook.py
Shows: webhook → LangGraph sync pipeline → graph update → retrieval update"""

import httpx, asyncio, time

async def demo():
    print("=== Sync Engine Demo ===\n")
    
    # 1. Query BEFORE
    r = httpx.post("http://localhost:8000/api/query", 
                   json={"query": "waterproofing for bathroom"})
    print(f"BEFORE: {r.json()['answer'][:200]}...\n")
    
    # 2. Send webhook
    start = time.time()
    r = httpx.post("http://localhost:8000/webhook/cms", json={
        "event": "product.updated",
        "product_url": "https://myklaticrete.com/products/waterproofing/myk-laticrete-hydro-ban/",
        "product_sku": "HYDRO-BAN",
        "timestamp": "2024-01-01T00:00:00Z",
        "source": "simulated_cms"
    })
    elapsed = r.json()["elapsed_seconds"]
    print(f"Pipeline completed in {elapsed:.1f}s\n")
    
    # 3. Query AFTER
    r = httpx.post("http://localhost:8000/api/query",
                   json={"query": "waterproofing for bathroom"})
    print(f"AFTER: {r.json()['answer'][:200]}...\n")
    
    print(f"✅ End-to-end: {elapsed:.1f}s (target: <300s)")

asyncio.run(demo())
```

## Deliverable Checklist
- [ ] LangGraph sync_graph with conditional routing (update vs delete)
- [ ] Webhook endpoint triggers sync_graph.ainvoke()
- [ ] Delta detection via content hash
- [ ] Deprecated products marked, not deleted
- [ ] APScheduler runs full ingestion_graph every 24h
- [ ] Prometheus metrics for crawl, parse, embed, freshness
- [ ] Demo script shows webhook → updated retrieval in <5 min
