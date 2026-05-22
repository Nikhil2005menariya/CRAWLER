#!/usr/bin/env python
"""
scripts/demo_queries.py
────────────────────────
Runs 5 demo queries against the ReAct retrieval agent and prints:
  - The agent's answer
  - Which tools it chose to call
  - Execution time per query

Run with:
  backend/.venv/bin/python scripts/demo_queries.py
"""

import asyncio
import logging
import sys
import time

sys.path.insert(0, ".")
logging.basicConfig(
    level=logging.WARNING,   # suppress tool-level debug noise
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

DEMO_QUERIES = [
    # 1. Multi-constraint (substrate + tile + environment) → should use graph_search_tool
    (
        "1. Multi-constraint (graph search expected)",
        "Recommend an adhesive for 80×80 vitrified tiles on a heated bathroom floor over concrete",
    ),
    # 2. Semantic / conceptual → should use vector_search_tool
    (
        "2. Semantic search (vector search expected)",
        "What waterproofing solution works for swimming pools?",
    ),
    # 3. Product comparison → should use compare_products_tool + get_specs_tool
    (
        "3. Comparison (compare_products + get_specs expected)",
        "Compare LATAFIX 305 and LATICRETE 335 Maxi — which is better for large format tiles?",
    ),
    # 4. Graph + vector combined → may use both
    (
        "4. Multi-hop (graph + vector expected)",
        "I need to fix natural stone on an exterior facade — which adhesive and what coverage rate?",
    ),
    # 5. Specific specs → should use product_lookup_tool + get_specs_tool
    (
        "5. Specs lookup (product_lookup + get_specs expected)",
        "What is the open time and application thickness of LATICRETE 335 Maxi?",
    ),
]


async def run_all():
    from backend.agents.retrieval_agent import build_retrieval_agent, run_query

    print("Building retrieval agent…")
    agent = build_retrieval_agent()
    print("Agent ready.\n")
    print("=" * 70)

    total_queries = len(DEMO_QUERIES)
    for idx, (label, question) in enumerate(DEMO_QUERIES, 1):
        print(f"\n{'─' * 70}")
        print(f"Query {idx}/{total_queries}: {label}")
        print(f"Q: {question}")

        t0 = time.time()
        result = await run_query(question, agent=agent)
        elapsed = time.time() - t0

        print(f"\nA: {result['answer']}")
        if result["tools_used"]:
            print(f"\n🛠  Tools used: {result['tools_used']}")
        else:
            print("\n🛠  No tools called (answered from context)")
        print(f"⏱  Time: {elapsed:.1f}s")

        # Respect 5 RPM free-tier limit — each multi-step query uses 2-3 calls
        if idx < total_queries:
            print("   (waiting 15s to respect rate limit…)")
            await asyncio.sleep(15)

    print(f"\n{'=' * 70}")
    print("Demo complete.")


if __name__ == "__main__":
    asyncio.run(run_all())
