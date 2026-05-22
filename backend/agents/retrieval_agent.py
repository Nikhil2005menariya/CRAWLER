"""
agents/retrieval_agent.py
──────────────────────────
LangGraph ReAct retrieval agent powered by Gemini 2.5 Flash with 6 tools:
  1. graph_search_tool    — Cypher-based filtered search
  2. product_lookup_tool  — Direct SKU/name lookup
  3. compare_products_tool — Side-by-side comparison
  4. get_specs_tool       — Detailed technical specs
  5. cypher_query_tool    — Raw Cypher queries
  6. vector_search_tool   — Semantic similarity search

The agent autonomously decides which tools to call based on the query.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env (backend/agents/ → parents[1]=backend/, parents[2]=repo root)
for _c in [Path(__file__).parents[1] / ".env", Path(__file__).parents[2] / ".env"]:
    if _c.exists():
        load_dotenv(_c, override=False)
        break


def build_retrieval_agent():
    """
    Build and return a compiled LangGraph ReAct agent.

    The agent uses Gemini 2.5 Flash as the reasoning LLM and has access
    to all 6 retrieval tools. It runs a ReAct loop until it produces
    a final answer.

    Returns:
        A compiled LangGraph CompiledGraph (supports .invoke() and .ainvoke()).
    """
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langgraph.prebuilt import create_react_agent

    from .nodes.embed_node import embed_node  # noqa — ensure graph is ready
    from ..tools.graph_tools import GRAPH_TOOLS
    from ..tools.vector_tools import VECTOR_TOOLS

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY not set. Check backend/.env.")

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0,
        google_api_key=api_key,
    )

    all_tools = GRAPH_TOOLS + VECTOR_TOOLS

    system_prompt = """You are a technical assistant specializing in MYK Laticrete construction chemicals.
You help contractors, architects, and engineers select the right adhesive, grout, waterproofing, or surface treatment product.

You have access to these tools:
- graph_search_tool: Search products by substrate, tile type, use case, or environment constraints
- product_lookup_tool: Look up a specific product by name or SKU
- compare_products_tool: Compare two products side by side
- get_specs_tool: Get full technical specs (open time, coverage rate, etc.)
- cypher_query_tool: Execute custom graph database queries
- vector_search_tool: Find products by semantic similarity

Strategy:
1. For constraint-based queries (substrate + tile + environment) → use graph_search_tool first
2. For named product queries → use product_lookup_tool or get_specs_tool
3. For comparison questions → use compare_products_tool
4. For vague/semantic queries → use vector_search_tool
5. Always provide specific product names, grades (C2TE, C1, etc.), and key specs in your answer
6. If a product has needs_review=True or confidence < 0.6, mention it may need verification

Always be specific, technical, and cite the product name and grade classification in your answer."""

    agent = create_react_agent(
        model=llm,
        tools=all_tools,
        prompt=system_prompt,
    )

    logger.info("Retrieval agent built with %d tools", len(all_tools))
    return agent


async def run_query(question: str, agent=None) -> dict:
    """
    Run a single natural language query through the ReAct agent.

    Args:
        question: User's natural language question.
        agent:    Optional pre-built agent (builds one if not provided).

    Returns:
        dict with 'answer', 'tools_used', and 'messages' fields.
    """
    if agent is None:
        agent = build_retrieval_agent()

    result = await agent.ainvoke({
        "messages": [("user", question)]
    })

    messages = result.get("messages", [])
    final_answer = messages[-1].content if messages else "No answer generated."
    tools_used = [
        m.name for m in messages
        if hasattr(m, "name") and m.name
    ]

    return {
        "question":   question,
        "answer":     final_answer,
        "tools_used": tools_used,
        "messages":   messages,
    }


def run_query_sync(question: str, agent=None) -> dict:
    """Synchronous wrapper around run_query for non-async contexts."""
    import asyncio
    return asyncio.run(run_query(question, agent=agent))
