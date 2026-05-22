#!/usr/bin/env python
"""
scripts/simulate_webhook.py
────────────────────────────
Demonstrates the full Task 4 sync flow:
  1. Query BEFORE webhook → shows current knowledge
  2. POST /webhook/cms with product.updated event
  3. Wait for pipeline to complete
  4. Query AFTER webhook → shows updated knowledge

Requires the FastAPI server to be running:
  backend/.venv/bin/uvicorn backend.api.app:app --port 8000

Run with:
  backend/.venv/bin/python scripts/simulate_webhook.py
"""

import asyncio
import sys
import time

import httpx

BASE_URL = "http://localhost:8000"

# Product to simulate an update for — use one we have in DB
DEMO_URL   = "https://myklaticrete.com/products/tile-adhesive/polymer-modified-thin-set-adhesives/myk-laticrete-335-super-flex-plus/"
DEMO_QUERY = "What is the open time and coverage rate of LATICRETE 335 Maxi?"


async def main():
    print("=" * 65)
    print("MYK LATICRETE — SYNC ENGINE DEMO (Task 4)")
    print("=" * 65)

    async with httpx.AsyncClient(timeout=60.0) as client:

        # ── Health check ──────────────────────────────────────────────
        try:
            r = await client.get(f"{BASE_URL}/health")
            r.raise_for_status()
            print(f"\n✅ Server online: {r.json()}")
        except Exception as e:
            print(f"\n❌ Cannot reach server at {BASE_URL}")
            print(f"   Start it with: backend/.venv/bin/uvicorn backend.api.app:app --port 8000")
            print(f"   Error: {e}")
            sys.exit(1)

        # ── Status check ──────────────────────────────────────────────
        r = await client.get(f"{BASE_URL}/api/status")
        status = r.json()
        print(f"\n📊 System Status:")
        print(f"   Neo4j online:      {status['neo4j_online']}")
        print(f"   SQLite products:   {status['sqlite_products']}")
        print(f"   ChromaDB vectors:  {status['chroma_vectors']}")
        print(f"   Scheduler running: {status['scheduler_running']}")

        # ── Query BEFORE webhook ───────────────────────────────────────
        print(f"\n{'─' * 65}")
        print(f"[BEFORE] Query: {DEMO_QUERY}")
        r = await client.post(f"{BASE_URL}/api/query", json={"query": DEMO_QUERY})
        before = r.json()
        print(f"Answer: {before['answer'][:300]}")
        print(f"Tools:  {before['tools_used']}")
        print(f"Time:   {before['elapsed_seconds']}s")

        # ── Simulate webhook ───────────────────────────────────────────
        print(f"\n{'─' * 65}")
        print(f"[WEBHOOK] Sending product.updated event...")
        print(f"   URL: {DEMO_URL}")
        t0 = time.time()
        r = await client.post(
            f"{BASE_URL}/webhook/cms",
            json={
                "event":       "product.updated",
                "product_url": DEMO_URL,
                "product_sku": None,
                "timestamp":   "2026-05-22T10:00:00Z",
                "source":      "simulated_cms",
            },
            timeout=300.0,   # sync pipeline can take up to 5 minutes
        )
        wh = r.json()
        elapsed = time.time() - t0
        print(f"   Status:            {wh['status']}")
        print(f"   Graph updated:     {wh['graph_updated']}")
        print(f"   Embeddings updated:{wh['embeddings_updated']}")
        print(f"   Pipeline time:     {elapsed:.1f}s")
        if wh.get("errors"):
            print(f"   ⚠ Errors: {wh['errors']}")

        # ── Query AFTER webhook ────────────────────────────────────────
        print(f"\n{'─' * 65}")
        print(f"[AFTER] Query: {DEMO_QUERY}")
        r = await client.post(f"{BASE_URL}/api/query", json={"query": DEMO_QUERY})
        after = r.json()
        print(f"Answer: {after['answer'][:300]}")
        print(f"Tools:  {after['tools_used']}")
        print(f"Time:   {after['elapsed_seconds']}s")

        # ── List products ──────────────────────────────────────────────
        print(f"\n{'─' * 65}")
        r = await client.get(f"{BASE_URL}/api/products")
        products = r.json()
        print(f"[PRODUCTS] {len(products)} products in knowledge base:")
        for p in products:
            flag = "⚠️" if p["needs_review"] else "✅"
            print(f"  {flag} [{p['product_family']}] {p['product_name']}  conf={p['confidence']:.2f}  v{p['version']}")

    print(f"\n{'=' * 65}")
    target = 300
    status_str = "✅ PASS" if elapsed < target else "❌ FAIL (exceeded 5 min target)"
    print(f"End-to-end sync: {elapsed:.1f}s (target <{target}s) — {status_str}")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
