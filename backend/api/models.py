"""
api/models.py
──────────────
Pydantic request/response models for the FastAPI endpoints.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class WebhookPayload(BaseModel):
    """CMS webhook payload from an external content management system."""
    event: str = Field(..., description="Event type: product.updated | product.published | product.deleted")
    product_url: str = Field(..., description="Full URL of the affected product page")
    product_sku: Optional[str] = Field(None, description="Optional SKU of the product")
    timestamp: Optional[str] = Field(None, description="ISO 8601 event timestamp")
    source: Optional[str] = Field(None, description="CMS system name / identifier")


class WebhookResponse(BaseModel):
    status: str
    event: str
    elapsed_seconds: float
    graph_updated: bool
    embeddings_updated: bool
    errors: List[str] = []


class QueryRequest(BaseModel):
    """Natural language query for the retrieval agent."""
    query: str = Field(..., description="User's natural language question")
    k: int = Field(5, description="Max results for vector search tools")


class QueryResponse(BaseModel):
    query: str
    answer: str
    tools_used: List[str]
    elapsed_seconds: float


class IngestRequest(BaseModel):
    """Trigger a full or partial ingestion pipeline run."""
    urls: Optional[List[str]] = Field(None, description="Specific URLs to crawl (None = seed URLs)")
    skip_crawl: bool = False
    skip_parse: bool = False
    skip_embed: bool = False


class IngestResponse(BaseModel):
    status: str
    task_id: str
    message: str


class ProductSummary(BaseModel):
    product_name: str
    product_family: Optional[str]
    sku: Optional[str]
    confidence: float
    needs_review: bool
    version: int


class StatusResponse(BaseModel):
    neo4j_online: bool
    chroma_vectors: int
    sqlite_products: int
    sqlite_crawl_records: int
    last_sync_ts: Optional[float]
    scheduler_running: bool
