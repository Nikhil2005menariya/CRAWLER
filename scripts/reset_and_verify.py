#!/usr/bin/env python
"""
scripts/reset_and_verify.py
────────────────────────────
Full reset + end-to-end verification for the entire Task 1→4 pipeline.

Steps:
  1. RESET:  Clear SQLite tables, Neo4j graph, ChromaDB collection
  2. CRAWL:  Crawl N product pages from seed URLs
  3. PARSE:  Extract structured products via Gemini
  4. EMBED:  Build Neo4j graph + ChromaDB vectors
  5. VERIFY: Check counts in all stores + run 3 agent queries

Usage:
  # Full reset + run (default)
  backend/.venv/bin/python scripts/reset_and_verify.py

  # Reset only (wipe all data)
  backend/.venv/bin/python scripts/reset_and_verify.py --reset-only

  # Skip crawl+parse (use existing SQLite data), just re-embed
  backend/.venv/bin/python scripts/reset_and_verify.py --skip-crawl --skip-parse

  # Choose how many seed URLs to crawl
  backend/.venv/bin/python scripts/reset_and_verify.py --n-urls 10
"""

import argparse
import asyncio
import logging
import sqlite3
import sys
import time

sys.path.insert(0, ".")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("reset_verify")


# ---------------------------------------------------------------------------
# Reset helpers
# ---------------------------------------------------------------------------

def reset_sqlite(db_path: str) -> None:
    """Drop and recreate all tables in the SQLite database."""
    logger.info("Resetting SQLite: %s", db_path)
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS product_versions;
        DROP TABLE IF EXISTS crawl_records;
        DROP TABLE IF EXISTS crawl_history;
    """)
    conn.commit()
    conn.close()
    logger.info("SQLite reset ✅")


def reset_neo4j() -> None:
    """Delete all nodes and relationships from Neo4j."""
    from backend.graph.neo4j_client import get_graph
    graph = get_graph()
    if graph is None:
        logger.warning("Neo4j offline — skipping graph reset")
        return
    graph.query("MATCH (n) DETACH DELETE n")
    logger.info("Neo4j reset ✅ (all nodes deleted)")


def reset_chroma() -> None:
    """Delete and recreate the ChromaDB product collection."""
    import chromadb, os
    from backend.config.settings import Settings
    s = Settings()
    client = chromadb.PersistentClient(path=s.chroma_persist_dir)
    try:
        client.delete_collection("myk_products")
        logger.info("ChromaDB collection deleted ✅")
    except Exception:
        logger.info("ChromaDB collection did not exist — nothing to delete")


# ---------------------------------------------------------------------------
# Verification helpers
# ---------------------------------------------------------------------------

def verify_counts(db_path: str) -> dict:
    """Return current row/node/vector counts across all stores."""
    from backend.graph.neo4j_client import get_graph
    from backend.graph.vector_store import ProductVectorStore

    counts = {"sqlite_crawl": 0, "sqlite_products": 0, "neo4j_nodes": 0, "chroma_vectors": 0}

    try:
        conn = sqlite3.connect(db_path, timeout=5)
        counts["sqlite_crawl"]    = conn.execute("SELECT COUNT(*) FROM crawl_records").fetchone()[0]
        counts["sqlite_products"] = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        conn.close()
    except Exception as e:
        logger.warning("SQLite count error: %s", e)

    try:
        g = get_graph()
        if g:
            r = g.query("MATCH (n) RETURN count(n) AS c")
            counts["neo4j_nodes"] = r[0]["c"] if r else 0
    except Exception:
        pass

    try:
        counts["chroma_vectors"] = ProductVectorStore().count()
    except Exception:
        pass

    return counts


async def run_agent_queries() -> list:
    """Run 3 test queries and return results."""
    from backend.agents.retrieval_agent import build_retrieval_agent, run_query

    agent = build_retrieval_agent()
    queries = [
        "What is the application thickness of LATICRETE 335 Maxi?",
        "Find a tile adhesive compatible with vitrified tiles on concrete",
        "Which products are suitable for exterior facade cladding?",
    ]
    results = []
    for q in queries:
        try:
            r = await run_query(q, agent=agent)
            results.append({"q": q, "answer": r["answer"][:200], "tools": r["tools_used"]})
            await asyncio.sleep(15)   # respect 5 RPM
        except Exception as exc:
            results.append({"q": q, "answer": f"ERROR: {exc}", "tools": []})
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Reset + end-to-end verify Task 1→4")
    parser.add_argument("--reset-only",  action="store_true", help="Only reset data, don't run pipeline")
    parser.add_argument("--skip-crawl",  action="store_true")
    parser.add_argument("--skip-parse",  action="store_true")
    parser.add_argument("--skip-embed",  action="store_true")
    parser.add_argument("--skip-query",  action="store_true", help="Skip agent query verification")
    parser.add_argument("--n-urls",      type=int, default=8)
    args = parser.parse_args()

    from backend.config.settings import Settings
    s = Settings()
    t_total = time.time()

    # ── Step 1: Reset ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 1: RESETTING ALL DATA STORES")
    print("=" * 60)
    reset_sqlite(s.sqlite_db_path)
    reset_neo4j()
    reset_chroma()

    counts = verify_counts(s.sqlite_db_path)
    print(f"  After reset → SQLite crawl={counts['sqlite_crawl']} products={counts['sqlite_products']}")
    print(f"                Neo4j nodes={counts['neo4j_nodes']}  ChromaDB vectors={counts['chroma_vectors']}")

    if args.reset_only:
        print("\n✅ Reset complete.")
        return

    # ── Step 2: Crawl ──────────────────────────────────────────────
    state = {
        "urls_to_crawl": [], "crawl_records": [], "products": [],
        "graph_updates": [], "embedding_updates": [], "errors": [],
        "metrics": {}, "current_phase": "start",
    }

    if not args.skip_crawl:
        print("\n" + "=" * 60)
        print(f"STEP 2: CRAWL (n_urls={args.n_urls})")
        print("=" * 60)
        from backend.config.seed_urls import SEED_URLS
        from backend.agents.nodes.crawl_node import crawl_node

        urls = SEED_URLS[13: 13 + args.n_urls]
        state["urls_to_crawl"] = urls
        t0 = time.time()
        state = crawl_node(state)
        print(f"  Crawled {len(state['crawl_records'])} records in {time.time()-t0:.1f}s")
    else:
        print("\nSTEP 2: CRAWL [SKIPPED]")

    # ── Step 3: Parse ──────────────────────────────────────────────
    if not args.skip_parse and state.get("crawl_records"):
        print("\n" + "=" * 60)
        print("STEP 3: PARSE (Gemini 2.5 Flash)")
        print("=" * 60)
        from backend.agents.nodes.parse_node import parse_node
        t0 = time.time()
        state = parse_node(state)
        print(f"  Parsed {len(state['products'])} products in {time.time()-t0:.1f}s")
    else:
        print("\nSTEP 3: PARSE [SKIPPED]")

    # ── Step 4: Embed ──────────────────────────────────────────────
    if not args.skip_embed:
        print("\n" + "=" * 60)
        print("STEP 4: EMBED (Neo4j + ChromaDB)")
        print("=" * 60)
        from backend.agents.nodes.embed_node import embed_node
        t0 = time.time()
        state = embed_node(state)
        m = state.get("metrics", {})
        print(f"  Neo4j merged:  {m.get('neo4j_merged', 0)}  failed: {m.get('neo4j_failed', 0)}")
        print(f"  Chroma vectors:{m.get('embed_count', 0)}")
        print(f"  Use cases:     {m.get('use_cases_seeded', 0)}")
        print(f"  Time:          {time.time()-t0:.1f}s")
    else:
        print("\nSTEP 4: EMBED [SKIPPED]")

    # ── Verify counts ─────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("STORE COUNTS AFTER PIPELINE")
    print("=" * 60)
    counts = verify_counts(s.sqlite_db_path)
    print(f"  SQLite crawl records: {counts['sqlite_crawl']}")
    print(f"  SQLite products:      {counts['sqlite_products']}")
    print(f"  Neo4j nodes:          {counts['neo4j_nodes']}")
    print(f"  ChromaDB vectors:     {counts['chroma_vectors']}")

    # ── Agent query verification ───────────────────────────────────
    if not args.skip_query and counts["sqlite_products"] > 0:
        print("\n" + "=" * 60)
        print("STEP 5: AGENT QUERY VERIFICATION")
        print("=" * 60)
        results = asyncio.run(run_agent_queries())
        for i, r in enumerate(results, 1):
            print(f"\n  Q{i}: {r['q']}")
            print(f"  A:  {r['answer']}")
            print(f"  Tools: {r['tools']}")
    elif args.skip_query:
        print("\nSTEP 5: AGENT QUERIES [SKIPPED]")
    else:
        print("\nSTEP 5: AGENT QUERIES [SKIPPED — no products in DB]")

    # ── Final report ──────────────────────────────────────────────
    elapsed = time.time() - t_total
    errors  = state.get("errors", [])

    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    print(f"  Total time:       {elapsed:.1f}s")
    print(f"  Crawl records:    {counts['sqlite_crawl']}")
    print(f"  Products parsed:  {counts['sqlite_products']}")
    print(f"  Neo4j nodes:      {counts['neo4j_nodes']}")
    print(f"  ChromaDB vectors: {counts['chroma_vectors']}")
    print(f"  Errors:           {len(errors)}")

    all_ok = counts["sqlite_products"] > 0 and counts["chroma_vectors"] > 0
    print(f"\n{'✅ ALL CHECKS PASS' if all_ok and not errors else '⚠  COMPLETED WITH ISSUES'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
