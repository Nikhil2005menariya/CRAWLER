"""
agents/state.py
────────────────
Shared TypedDict state definitions for all LangGraph graphs.

Three state types:
  - IngestionState: main crawl → parse → embed → sync pipeline
  - RetrievalState: ReAct retrieval agent
  - SyncState:      webhook-triggered incremental sync pipeline
"""

from typing import Annotated, Any, Dict, List, Optional, Sequence, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from ..crawler.models import CrawlRecord


# ---------------------------------------------------------------------------
# Ingestion Pipeline State  (crawl → parse → embed → sync)
# ---------------------------------------------------------------------------

class IngestionState(TypedDict, total=False):
    """State flowing through the full ingestion pipeline."""

    # Input
    urls_to_crawl: List[str]

    # Crawler output
    crawl_records: List[CrawlRecord]

    # Parser output — list of ProductRecord dicts
    products: List[Dict[str, Any]]

    # Embed / graph step output
    graph_updates: List[Dict[str, Any]]       # {action, node_type, data}
    embedding_updates: List[Dict[str, Any]]   # {sku, embedding, metadata}

    # Sync step output
    sync_status: Dict[str, Any]               # {added, modified, deleted, unchanged}

    # Shared error log (all phases append here)
    errors: List[str]

    # Prometheus-style metrics dict
    metrics: Dict[str, Any]                   # {crawl_count, parse_count, embed_count, …}

    # Current pipeline phase (for observability / routing)
    current_phase: str                        # crawl | parse | embed | sync | done


# ---------------------------------------------------------------------------
# Retrieval Agent State  (ReAct query agent)
# ---------------------------------------------------------------------------

class RetrievalState(TypedDict, total=False):
    """State for the retrieval ReAct agent."""

    messages: Annotated[Sequence[BaseMessage], add_messages]
    query: str
    extracted_entities: Dict[str, Any]        # {substrates, tiles, use_case, constraints}
    graph_results: List[Dict[str, Any]]
    vector_results: List[Dict[str, Any]]
    final_answer: str
    tool_calls_made: List[str]


# ---------------------------------------------------------------------------
# Sync Pipeline State  (webhook-triggered incremental update)
# ---------------------------------------------------------------------------

class SyncState(TypedDict, total=False):
    """State for the webhook-triggered sync pipeline."""

    trigger: Dict[str, Any]                   # {event, product_url, sku, timestamp}
    crawl_record: Optional[CrawlRecord]
    parsed_product: Optional[Dict[str, Any]]
    graph_updated: bool
    embeddings_updated: bool
    old_product: Optional[Dict[str, Any]]     # For diff comparison
    is_deletion: bool
    elapsed_seconds: float
