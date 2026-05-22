"""
agents/ingestion_graph.py
──────────────────────────
Builds and compiles the full ingestion LangGraph pipeline:
    crawl_node → parse_node → embed_node

Returns a compiled LangGraph graph that can be invoked with an IngestionState.
"""

import logging

logger = logging.getLogger(__name__)


def build_ingestion_graph():
    """
    Assemble the full ingestion pipeline as a LangGraph StateGraph.

    Flow:
        START → crawl_node → parse_node → embed_node → END

    Returns:
        A compiled LangGraph graph (supports .invoke() and .ainvoke()).
    """
    from langgraph.graph import StateGraph, START, END
    from .state import IngestionState
    from .nodes.crawl_node import crawl_node
    from .nodes.parse_node import parse_node
    from .nodes.embed_node import embed_node

    graph = StateGraph(IngestionState)

    graph.add_node("crawl",  crawl_node)
    graph.add_node("parse",  parse_node)
    graph.add_node("embed",  embed_node)

    graph.add_edge(START,   "crawl")
    graph.add_edge("crawl", "parse")
    graph.add_edge("parse", "embed")
    graph.add_edge("embed", END)

    compiled = graph.compile()
    logger.info("ingestion_graph compiled: crawl → parse → embed")
    return compiled
