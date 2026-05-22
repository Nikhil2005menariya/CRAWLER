# LangGraph Agents & Tools — Core Orchestration Layer

## This is the HEART of the project. Build this FIRST after core modules.

---

## 1. Shared State (`agents/state.py`)

```python
from typing import TypedDict, Annotated, Sequence
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class CrawlRecord(TypedDict):
    url: str
    content_type: str  # html | pdf | docx
    raw_text: str
    content_hash: str
    fetched_at: str
    metadata: dict

class ProductRecord(TypedDict):
    sku: str
    product_name: str
    product_family: str
    description: str
    technical_specs: dict
    grade_classification: str
    substrate_compatibility: list[str]
    tile_compatibility: list[str]
    recommended_use_cases: list[str]
    packaging: dict
    source_urls: list[str]
    extraction_confidence: float
    needs_human_review: bool

# --- INGESTION PIPELINE STATE ---
class IngestionState(TypedDict):
    """State flowing through the crawl→parse→embed→sync pipeline."""
    urls_to_crawl: list[str]
    crawl_records: list[CrawlRecord]
    products: list[ProductRecord]
    graph_updates: list[dict]        # {action: upsert|delete, node_type, data}
    embedding_updates: list[dict]    # {sku, embedding, metadata}
    sync_status: dict                # {added, modified, deleted, unchanged}
    errors: list[str]
    metrics: dict                    # {crawl_count, parse_count, embed_count, ...}
    current_phase: str               # crawl | parse | embed | sync | done

# --- RETRIEVAL AGENT STATE ---
class RetrievalState(TypedDict):
    """State for the retrieval ReAct agent."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    query: str
    extracted_entities: dict          # {substrates, tiles, use_case, constraints}
    graph_results: list[dict]
    vector_results: list[dict]
    final_answer: str
    tool_calls_made: list[str]

# --- SYNC PIPELINE STATE ---
class SyncState(TypedDict):
    """State for webhook-triggered sync pipeline."""
    trigger: dict                    # {event, product_url, sku, timestamp}
    crawl_record: CrawlRecord | None
    parsed_product: ProductRecord | None
    graph_updated: bool
    embeddings_updated: bool
    old_product: ProductRecord | None  # For diff comparison
    is_deletion: bool
    elapsed_seconds: float
```

---

## 2. Ingestion Pipeline Graph (`agents/ingestion_graph.py`)

```python
from langgraph.graph import StateGraph, END
from agents.state import IngestionState

def build_ingestion_graph():
    """
    Main pipeline: crawl → route → parse → embed → sync → done
    
    Graph visualization:
    
    [START] → [crawl_node] → [route_node] ──┬──▶ [parse_node] → [embed_node] → [sync_node] → [END]
                                             │
                                             └──▶ [END] (if no new content)
    """
    graph = StateGraph(IngestionState)
    
    # Add nodes
    graph.add_node("crawl", crawl_node)
    graph.add_node("route", route_node)
    graph.add_node("parse", parse_node)
    graph.add_node("embed", embed_node)
    graph.add_node("sync", sync_node)
    graph.add_node("report", report_node)
    
    # Add edges
    graph.set_entry_point("crawl")
    graph.add_edge("crawl", "route")
    graph.add_conditional_edges(
        "route",
        should_continue,   # Function that checks if there's new content
        {
            "continue": "parse",
            "skip": "report"
        }
    )
    graph.add_edge("parse", "embed")
    graph.add_edge("embed", "sync")
    graph.add_edge("sync", "report")
    graph.add_edge("report", END)
    
    return graph.compile()


def should_continue(state: IngestionState) -> str:
    """Route based on whether we found new/changed content."""
    new_records = [r for r in state["crawl_records"] 
                   if r.get("is_new") or r.get("is_modified")]
    if len(new_records) == 0:
        return "skip"
    return "continue"


# --- NODE IMPLEMENTATIONS ---

async def crawl_node(state: IngestionState) -> IngestionState:
    """Crawl all URLs, detect content type, extract text, dedup."""
    from crawler.spider import CrawlOrchestrator
    
    orchestrator = CrawlOrchestrator()
    records = await orchestrator.crawl_batch(state["urls_to_crawl"])
    
    return {
        **state,
        "crawl_records": records,
        "current_phase": "crawl",
        "metrics": {**state.get("metrics", {}), "crawl_count": len(records)}
    }


async def route_node(state: IngestionState) -> IngestionState:
    """Analyze crawl results, flag new/modified content for parsing."""
    from sync.delta_detector import DeltaDetector
    
    detector = DeltaDetector()
    changes = detector.detect_changes(state["crawl_records"])
    
    return {
        **state,
        "sync_status": changes,
        "crawl_records": changes["added"] + changes["modified"],  # Only process changed
    }


async def parse_node(state: IngestionState) -> IngestionState:
    """Extract structured product data using Gemini Flash."""
    from tools.parse_tools import extract_product_specs
    
    products = []
    for record in state["crawl_records"]:
        product = await extract_product_specs.ainvoke({
            "content": record["raw_text"],
            "source_url": record["url"],
            "content_type": record["content_type"]
        })
        if product:
            products.append(product)
    
    return {
        **state,
        "products": products,
        "current_phase": "parse",
        "metrics": {**state["metrics"], "parse_count": len(products)}
    }


async def embed_node(state: IngestionState) -> IngestionState:
    """Generate embeddings and upsert into Neo4j + ChromaDB."""
    from tools.vector_tools import embed_and_store
    from tools.graph_tools import upsert_to_graph
    
    graph_updates = []
    embedding_updates = []
    
    for product in state["products"]:
        # Build graph nodes + edges
        g_update = await upsert_to_graph.ainvoke(product)
        graph_updates.append(g_update)
        
        # Generate embedding + store in ChromaDB
        e_update = await embed_and_store.ainvoke(product)
        embedding_updates.append(e_update)
    
    return {
        **state,
        "graph_updates": graph_updates,
        "embedding_updates": embedding_updates,
        "current_phase": "embed",
        "metrics": {**state["metrics"], "embed_count": len(embedding_updates)}
    }


async def sync_node(state: IngestionState) -> IngestionState:
    """Handle deletions, update version history, reconcile."""
    from sync.reconciler import Reconciler
    from sync.propagator import Propagator
    
    reconciler = Reconciler()
    
    # Handle deletions
    for url in state["sync_status"].get("deleted", []):
        await reconciler.mark_deprecated_by_url(url)
    
    return {**state, "current_phase": "sync"}


async def report_node(state: IngestionState) -> IngestionState:
    """Generate metrics report and QA summary."""
    from parser.qa_report import generate_report
    
    report = generate_report(state["products"], state["metrics"])
    return {**state, "current_phase": "done", "metrics": {**state["metrics"], "report": report}}
```

---

## 3. Retrieval Agent (`agents/retrieval_agent.py`)

```python
from langgraph.prebuilt import create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from tools.graph_tools import graph_search_tool, product_lookup_tool, cypher_query_tool
from tools.vector_tools import vector_search_tool
from tools.compare_tools import compare_products_tool, get_specs_tool

def build_retrieval_agent():
    """
    ReAct agent that uses tools to answer product queries.
    
    The agent DECIDES which tools to call based on the query:
    - Simple lookup → product_lookup_tool
    - Semantic search → vector_search_tool  
    - Constrained search → graph_search_tool (Cypher)
    - Comparison → compare_products_tool
    - Specs → get_specs_tool
    
    It can call MULTIPLE tools and combine results.
    """
    
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0,
    )
    
    tools = [
        graph_search_tool,
        vector_search_tool,
        product_lookup_tool,
        compare_products_tool,
        get_specs_tool,
        cypher_query_tool,
    ]
    
    system_prompt = """You are an AI sales assistant for MYK Laticrete, a leading 
    construction chemicals manufacturer in India. You help contractors, architects, 
    and dealers find the right products.
    
    You have access to a knowledge base of MYK Laticrete products including tile 
    adhesives, grouts, waterproofing, stone care, and specialty products.
    
    STRATEGY:
    1. First, extract key entities from the query (substrate, tile type, use case, constraints)
    2. Use graph_search_tool for structured queries with specific constraints
    3. Use vector_search_tool for semantic/fuzzy queries
    4. Use both and combine results for best accuracy
    5. Use compare_products_tool when user asks to compare options
    6. Use get_specs_tool to fetch detailed technical specifications
    
    Always provide:
    - Product name and SKU
    - Why it's recommended (matching criteria)
    - Key technical specs relevant to the query
    - Application tips if relevant
    
    Be specific and technical. These are B2B professionals.
    """
    
    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=system_prompt,
    )
    
    return agent
```

---

## 4. LangChain Tools (`tools/`)

### `tools/graph_tools.py`
```python
from langchain_core.tools import tool
from graph.neo4j_client import Neo4jClient

@tool
def graph_search_tool(
    substrates: list[str] = None,
    tile_types: list[str] = None, 
    use_case: str = None,
    product_family: str = None,
    min_bond_strength: str = None
) -> list[dict]:
    """Search the knowledge graph for products matching specific criteria.
    
    Use this when the query mentions specific substrates (concrete, plywood),
    tile types (vitrified, ceramic, natural stone), use cases (swimming pool,
    bathroom, facade), or product families (adhesive, grout, waterproofing).
    
    Args:
        substrates: List of substrates like ["concrete", "cement_screed"]
        tile_types: List of tile types like ["vitrified", "large_format"]
        use_case: Use case like "swimming_pool" or "heated_floor"
        product_family: Product family like "tile_adhesive" or "grout"
        min_bond_strength: Minimum bond strength requirement
    
    Returns:
        List of matching products with names, SKUs, and relevance info
    """
    neo4j = Neo4jClient()
    cypher = "MATCH (p:Product) WHERE p.is_active = true "
    params = {}
    
    if substrates:
        cypher += "AND EXISTS { MATCH (p)-[:COMPATIBLE_WITH]->(s:Substrate) WHERE s.name IN $substrates } "
        params["substrates"] = substrates
    if tile_types:
        cypher += "AND EXISTS { MATCH (p)-[:SUITABLE_FOR]->(t:TileType) WHERE t.name IN $tile_types } "
        params["tile_types"] = tile_types
    if use_case:
        cypher += "AND EXISTS { MATCH (p)-[:RECOMMENDED_FOR]->(u:UseCase) WHERE u.name CONTAINS $use_case } "
        params["use_case"] = use_case
    if product_family:
        cypher += "AND p.family = $product_family "
        params["product_family"] = product_family
    
    cypher += "RETURN p.sku AS sku, p.name AS name, p.family AS family, p.description AS description, p.specs AS specs LIMIT 10"
    return neo4j.run(cypher, params)


@tool
def product_lookup_tool(sku: str) -> dict:
    """Look up a specific product by its SKU or product code.
    
    Use this when the user mentions a specific product name or code 
    like '335 Super Flex' or 'SP-100' or 'Hydro Ban'.
    
    Args:
        sku: Product SKU or partial name to search for
    
    Returns:
        Full product record with all specs, compatibility info, and docs
    """
    neo4j = Neo4jClient()
    result = neo4j.run("""
        MATCH (p:Product)
        WHERE p.sku CONTAINS $sku OR p.name CONTAINS $sku
        OPTIONAL MATCH (p)-[:COMPATIBLE_WITH]->(s:Substrate)
        OPTIONAL MATCH (p)-[:SUITABLE_FOR]->(t:TileType)
        OPTIONAL MATCH (p)-[:RECOMMENDED_FOR]->(u:UseCase)
        OPTIONAL MATCH (p)-[:COMPLIES_WITH]->(st:Standard)
        RETURN p, collect(DISTINCT s.name) AS substrates, 
               collect(DISTINCT t.name) AS tiles,
               collect(DISTINCT u.name) AS use_cases,
               collect(DISTINCT st.code) AS standards
        LIMIT 1
    """, {"sku": sku})
    return result


@tool
def cypher_query_tool(query: str) -> list[dict]:
    """Run a custom Cypher query against the Neo4j knowledge graph.
    
    Use this for complex queries that don't fit the other tools.
    The graph has: Product, ProductFamily, UseCase, Substrate, TileType, Standard, Document nodes.
    Relationships: BELONGS_TO, RECOMMENDED_FOR, COMPATIBLE_WITH, SUITABLE_FOR, COMPLIES_WITH, DOCUMENTED_IN.
    
    Args:
        query: A valid Cypher query string
    
    Returns:
        Query results as list of dictionaries
    """
    neo4j = Neo4jClient()
    return neo4j.run(query)
```

### `tools/vector_tools.py`
```python
from langchain_core.tools import tool
from graph.embedder import ProductEmbedder
from graph.vector_store import VectorStore

@tool
def vector_search_tool(query: str, top_k: int = 5) -> list[dict]:
    """Semantic search across all products using natural language.
    
    Use this when the query is descriptive or fuzzy and doesn't map cleanly
    to specific graph attributes. Good for questions like "best adhesive for 
    tricky installations" or "something waterproof and flexible".
    
    Args:
        query: Natural language search query
        top_k: Number of results to return (default 5)
    
    Returns:
        List of products ranked by semantic similarity with scores
    """
    embedder = ProductEmbedder()
    store = VectorStore()
    
    query_embedding = embedder.embed_query(query)
    results = store.query(query_embedding, n_results=top_k)
    return results


@tool  
def embed_and_store(product: dict) -> dict:
    """Generate embedding for a product and store in ChromaDB.
    
    Called during the ingestion pipeline to index new/updated products.
    
    Args:
        product: Product record dictionary
    
    Returns:
        Status of the embedding operation
    """
    embedder = ProductEmbedder()
    store = VectorStore()
    
    embedding = embedder.embed_product_dict(product)
    store.upsert_product(
        sku=product["sku"],
        embedding=embedding,
        metadata={
            "name": product["product_name"],
            "family": product["product_family"],
            "description": product.get("description", ""),
        }
    )
    return {"status": "stored", "sku": product["sku"]}
```

### `tools/compare_tools.py`
```python
from langchain_core.tools import tool

@tool
def compare_products_tool(sku_list: list[str]) -> dict:
    """Compare multiple products side by side on key specifications.
    
    Use when the user wants to compare two or more products, e.g.,
    "Compare 335 Super Flex vs 345 Super Flex" or "SP-100 vs SP-100 Duo".
    
    Args:
        sku_list: List of 2-5 product SKUs to compare
    
    Returns:
        Comparison table with specs, compatibility, and recommendations
    """
    neo4j = Neo4jClient()
    products = []
    for sku in sku_list:
        result = neo4j.run("MATCH (p:Product) WHERE p.sku CONTAINS $sku RETURN p LIMIT 1", {"sku": sku})
        if result:
            products.append(result[0])
    
    # Build comparison dict
    comparison = {
        "products": [p["name"] for p in products],
        "specs_comparison": {},
        "compatibility_diff": {},
    }
    # ... populate comparison fields
    return comparison


@tool
def get_specs_tool(sku: str) -> dict:
    """Get detailed technical specifications for a product.
    
    Use when the user asks about specific specs like coverage rate,
    open time, pot life, bond strength, cure time, etc.
    
    Args:
        sku: Product SKU or name
    
    Returns:
        Full technical specification sheet
    """
    neo4j = Neo4jClient()
    result = neo4j.run("""
        MATCH (p:Product) WHERE p.sku CONTAINS $sku OR p.name CONTAINS $sku
        RETURN p.specs AS specs, p.name AS name, p.sku AS sku
        LIMIT 1
    """, {"sku": sku})
    return result
```

### `tools/sync_tools.py`
```python
from langchain_core.tools import tool

@tool
def check_delta_tool(url: str) -> dict:
    """Check if a URL's content has changed since last crawl.
    
    Args:
        url: URL to check
    
    Returns:
        {changed: bool, old_hash: str, new_hash: str}
    """
    from sync.delta_detector import DeltaDetector
    detector = DeltaDetector()
    return detector.check_single(url)


@tool
def trigger_recrawl_tool(url: str) -> dict:
    """Trigger a targeted re-crawl and re-processing of a single URL.
    
    Used by the sync engine when a webhook indicates content has changed.
    
    Args:
        url: URL to re-crawl
    
    Returns:
        {job_id: str, status: str}
    """
    from sync.propagator import Propagator
    propagator = Propagator()
    return propagator.trigger_update(url)
```

---

## 5. Sync Pipeline Graph (`agents/sync_graph.py`)

```python
from langgraph.graph import StateGraph, END
from agents.state import SyncState

def build_sync_graph():
    """
    Webhook-triggered pipeline: 
    
    [webhook] → [check_event] ──┬──▶ [recrawl] → [reparse] → [update_graph] → [update_vectors] → [report]
                                │
                                └──▶ [deprecate] → [report]
    """
    graph = StateGraph(SyncState)
    
    graph.add_node("check_event", check_event_node)
    graph.add_node("recrawl", recrawl_node)
    graph.add_node("reparse", reparse_node)
    graph.add_node("update_graph", update_graph_node)
    graph.add_node("update_vectors", update_vectors_node)
    graph.add_node("deprecate", deprecate_node)
    graph.add_node("report", sync_report_node)
    
    graph.set_entry_point("check_event")
    graph.add_conditional_edges(
        "check_event",
        route_by_event,
        {
            "update": "recrawl",
            "delete": "deprecate"
        }
    )
    graph.add_edge("recrawl", "reparse")
    graph.add_edge("reparse", "update_graph")
    graph.add_edge("update_graph", "update_vectors")
    graph.add_edge("update_vectors", "report")
    graph.add_edge("deprecate", "report")
    graph.add_edge("report", END)
    
    return graph.compile()


def route_by_event(state: SyncState) -> str:
    if state["trigger"]["event"] == "product.deleted":
        return "delete"
    return "update"
```

---

## 6. How the API Uses the Agents

```python
# api/routes/query.py
from agents.retrieval_agent import build_retrieval_agent

agent = build_retrieval_agent()

@router.post("/api/query")
async def query_knowledge_base(request: QueryRequest):
    """User sends a question, the ReAct agent decides tools and answers."""
    result = await agent.ainvoke({"messages": [("user", request.query)]})
    return {"answer": result["messages"][-1].content}


# api/routes/webhook.py
from agents.sync_graph import build_sync_graph

sync_pipeline = build_sync_graph()

@router.post("/webhook/cms")
async def handle_webhook(payload: WebhookPayload):
    """Webhook triggers the sync LangGraph pipeline."""
    result = await sync_pipeline.ainvoke({
        "trigger": payload.dict(),
        "is_deletion": payload.event == "product.deleted",
    })
    return {"status": "complete", "elapsed": result["elapsed_seconds"]}
```
