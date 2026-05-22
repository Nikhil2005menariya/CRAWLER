#!/usr/bin/env python
"""
scripts/run_pipeline.py
────────────────────────
End-to-end orchestration: crawl → parse → embed (→ Neo4j + ChromaDB).

Usage:
  # Full pipeline (3 product pages)
  backend/.venv/bin/python scripts/run_pipeline.py

  # Skip crawl + parse (use existing SQLite data), just build graph
  backend/.venv/bin/python scripts/run_pipeline.py --skip-crawl --skip-parse

  # Crawl only specific URLs
  backend/.venv/bin/python scripts/run_pipeline.py --urls-file urls.txt
"""

import argparse
import logging
import sys
import time

sys.path.insert(0, ".")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")


def main():
    parser = argparse.ArgumentParser(description="MYK Laticrete ingestion pipeline")
    parser.add_argument("--skip-crawl",  action="store_true", help="Skip crawl step")
    parser.add_argument("--skip-parse",  action="store_true", help="Skip parse step")
    parser.add_argument("--skip-embed",  action="store_true", help="Skip embed step")
    parser.add_argument("--n-urls",      type=int, default=5,  help="Number of seed URLs to crawl")
    parser.add_argument("--urls-file",   type=str, default=None, help="File with URLs (one per line)")
    args = parser.parse_args()

    t0 = time.time()
    state = {
        "urls_to_crawl":     [],
        "crawl_records":     [],
        "products":          [],
        "errors":            [],
        "metrics":           {},
        "current_phase":     "init",
        "graph_updates":     [],
        "embedding_updates": [],
    }

    # ── Step 1: Crawl ──────────────────────────────────────────────────────
    if not args.skip_crawl:
        logger.info("=== STEP 1: crawl_node ===")
        from backend.config.seed_urls import SEED_URLS
        from backend.agents.nodes.crawl_node import crawl_node

        if args.urls_file:
            with open(args.urls_file) as f:
                urls = [l.strip() for l in f if l.strip()]
        else:
            # Use product detail pages (index 13+)
            urls = SEED_URLS[13: 13 + args.n_urls]

        state["urls_to_crawl"] = urls
        logger.info("Crawling %d URLs…", len(urls))
        state = crawl_node(state)
        logger.info("Crawled: %d records", len(state["crawl_records"]))
    else:
        logger.info("=== STEP 1: crawl_node [SKIPPED] ===")
        # Load from DB for display
        import sqlite3
        conn = sqlite3.connect("data/crawl.db")
        n = conn.execute("SELECT COUNT(*) FROM crawl_records").fetchone()[0]
        conn.close()
        logger.info("Using %d existing records from SQLite", n)

    # ── Step 2: Parse ──────────────────────────────────────────────────────
    if not args.skip_parse and state.get("crawl_records"):
        logger.info("=== STEP 2: parse_node (Gemini 2.5 Flash) ===")
        from backend.agents.nodes.parse_node import parse_node
        state = parse_node(state)
        logger.info("Parsed: %d products", len(state["products"]))
        if state.get("errors"):
            logger.warning("Parse errors: %s", state["errors"])
    else:
        logger.info("=== STEP 2: parse_node [SKIPPED] ===")

    # ── Step 3: Embed ──────────────────────────────────────────────────────
    if not args.skip_embed:
        logger.info("=== STEP 3: embed_node (Neo4j + ChromaDB) ===")
        from backend.agents.nodes.embed_node import embed_node
        state = embed_node(state)
        m = state.get("metrics", {})
        logger.info(
            "Embed complete: %d vectors, %d neo4j nodes, Neo4j online=%s",
            m.get("embed_count", 0), m.get("neo4j_merged", 0), m.get("neo4j_online"),
        )
    else:
        logger.info("=== STEP 3: embed_node [SKIPPED] ===")

    # ── Summary ───────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    metrics = state.get("metrics", {})
    errors  = state.get("errors", [])

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Time elapsed:    {elapsed:.1f}s")
    print(f"  Crawl records:   {metrics.get('crawl_count', len(state.get('crawl_records', [])))}")
    print(f"  Products parsed: {metrics.get('parse_count', len(state.get('products', [])))}")
    print(f"  Vectors stored:  {metrics.get('embed_count', 0)}")
    print(f"  Neo4j nodes:     {metrics.get('neo4j_merged', 0)}")
    print(f"  Use cases seeded:{metrics.get('use_cases_seeded', 0)}")
    print(f"  Neo4j online:    {metrics.get('neo4j_online', False)}")
    print(f"  Errors:          {len(errors)}")
    if errors:
        for e in errors[:5]:
            print(f"    ⚠ {e}")
    print("=" * 60)

    if not errors:
        print("\n✅ Pipeline succeeded. Run demo_queries.py to test retrieval.")
    else:
        print("\n⚠  Pipeline completed with errors.")


if __name__ == "__main__":
    main()
