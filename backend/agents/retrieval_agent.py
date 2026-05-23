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


def build_retrieval_agent(force_model: str = None):
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

    # 1. Groq Free Tier
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        from langchain_openai import ChatOpenAI
        if force_model:
            selected_model = force_model
        else:
            # Select best available model (handling 429 daily limits dynamically)
            model_options = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
            selected_model = "llama-3.3-70b-versatile"
            
            for model_name in model_options:
                try:
                    # Test connectivity/quota
                    test_llm = ChatOpenAI(
                        openai_api_base="https://api.groq.com/openai/v1",
                        openai_api_key=groq_key,
                        model_name=model_name,
                        max_retries=0
                    )
                    test_llm.invoke("ping")
                    selected_model = model_name
                    break
                except Exception as exc:
                    exc_str = str(exc)
                    if "429" in exc_str or "rate_limit" in exc_str:
                        logger.warning("Groq model %s rate limited/quota hit. Trying next model...", model_name)
                        continue
                    else:
                        selected_model = model_name
                        break
        
        logger.info("Retrieval Agent using Groq model: %s", selected_model)
        llm = ChatOpenAI(
            openai_api_base="https://api.groq.com/openai/v1",
            openai_api_key=groq_key,
            model_name=selected_model,
            temperature=0.0
        )
    # 2. OpenRouter Free Tier
    elif os.environ.get("OPENROUTER_API_KEY"):
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            openai_api_base="https://openrouter.ai/api/v1",
            openai_api_key=os.environ.get("OPENROUTER_API_KEY"),
            model_name="meta-llama/llama-3-8b-instruct:free",
            temperature=0.0
        )
    # 3. Gemini Default
    else:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY, GROQ_API_KEY, or OPENROUTER_API_KEY not set.")
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            google_api_key=api_key,
        )

    all_tools = GRAPH_TOOLS + VECTOR_TOOLS

    system_prompt = """You are a technical assistant specializing in MYK Laticrete construction chemicals.
You help contractors, architects, and engineers select the right adhesive, grout, waterproofing, or surface treatment product.

NEO4J GRAPH SCHEMA CHEAT SHEET:
When generating raw cypher queries using cypher_query_tool, you MUST conform precisely to this schema structure:
Nodes:
- (p:Product) properties:
  - name: string (e.g. 'LATICRETE 345 Super Flex')
  - family: string (e.g. 'tile_adhesive')
  - grade: string (e.g. 'C2TE S1')
  - description: string (e.g. 'A high-strength adhesive...')
  - specs_json: string (JSON string of technical specs)
  - confidence: float (0.0 to 1.0)
  - needs_review: boolean (0 or 1)
- (f:ProductFamily) properties: name
- (u:UseCase) properties: name
- (s:Substrate) properties: name
- (t:TileType) properties: name
- (std:Standard) properties: code
- (d:Document) properties: url

Relationships:
- (:Product)-[:BELONGS_TO]->(:ProductFamily)
- (:Product)-[:RECOMMENDED_FOR]->(:UseCase)
- (:Product)-[:COMPATIBLE_WITH]->(:Substrate)
- (:Product)-[:SUITABLE_FOR]->(:TileType)
- (:Product)-[:COMPLIES_WITH]->(:Standard)
- (:Product)-[:DOCUMENTED_IN]->(:Document)

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
7. If graph_search_tool returns no matches or empty results, you MUST fall back and call vector_search_tool with the query terms before concluding that a product is not available in the database.

CRITICAL TOOL CALL CONSTRAINTS:
- You MUST only call EXACTLY ONE tool per turn. Never call multiple tools or try to batch tool calls in a single response turn.
- Never output conversational text or punctuation inside your tool call JSON arguments. Keep argument values clean and direct (e.g. use "SP-100 DUO" instead of "the SP-100 DUO grout").

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

    try:
        result = await agent.ainvoke({
            "messages": [("user", question)]
        })
    except Exception as exc:
        exc_str = str(exc)
        if any(w in exc_str for w in ["429", "rate_limit", "400", "tool_use_failed", "BadRequestError", "Failed to call a function"]):
            logger.warning("Active agent model rate limited or tool-use failed. Re-building agent using Llama 8B fallback...")
            fallback_agent = build_retrieval_agent(force_model="llama-3.1-8b-instant")
            try:
                result = await fallback_agent.ainvoke({
                    "messages": [("user", question)]
                })
            except Exception as inner_exc:
                logger.error("Fallback agent also failed: %s. Proceeding with a simple text model without tools...", inner_exc)
                from langchain_openai import ChatOpenAI
                from langchain_core.messages import AIMessage, HumanMessage
                direct_llm = ChatOpenAI(
                    openai_api_base="https://api.groq.com/openai/v1",
                    openai_api_key=os.environ.get("GROQ_API_KEY"),
                    model_name="llama-3.1-8b-instant",
                    temperature=0.0
                )
                direct_res = direct_llm.invoke([("user", question)])
                return {
                    "question":   question,
                    "answer":     direct_res.content,
                    "tools_used": ["direct_llm_fallback"],
                    "messages":   [HumanMessage(content=question), AIMessage(content=direct_res.content)],
                }
        else:
            raise exc

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
