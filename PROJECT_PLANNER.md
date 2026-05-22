# MYK Laticrete Knowledge Ingestion Engine — Project Planner

> Give this to Claude Code / Codex to build the complete project.
> ALL services FREE. LLM = Gemini 2.5 Flash. Orchestration = **LangGraph**.

## Architecture (Agentic)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     LANGGRAPH ORCHESTRATION LAYER                        │
│                                                                          │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐    ┌──────────────┐ │
│  │  CRAWL     │───▶│  PARSE     │───▶│  EMBED +   │───▶│  SYNC        │ │
│  │  NODE      │    │  NODE      │    │  GRAPH NODE│    │  NODE        │ │
│  │            │    │            │    │            │    │              │ │
│  │ Scrapy +   │    │ Gemini 2.5 │    │ Neo4j CE + │    │ Webhooks +   │ │
│  │ BS4 Tools  │    │ Flash Tool │    │ ChromaDB   │    │ APScheduler  │ │
│  └────────────┘    └────────────┘    └────────────┘    └──────────────┘ │
│         │                │                 │                  │          │
│         ▼                ▼                 ▼                  ▼          │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                    SHARED STATE (TypedDict)                         │ │
│  │  crawl_records, products, graph_updates, sync_status, metrics      │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
              ┌─────────────────────────────────────────┐
              │      RETRIEVAL AGENT (LangGraph ReAct)   │
              │                                          │
              │  Tools:                                  │
              │   • graph_search_tool (Neo4j Cypher)     │
              │   • vector_search_tool (ChromaDB)        │
              │   • product_lookup_tool (by SKU)         │
              │   • compare_products_tool                │
              │   • get_specs_tool                       │
              │                                          │
              │  Agent decides which tools to call,      │
              │  combines results, generates answer      │
              └─────────────────────────────────────────┘
```

## Tech Stack (100% Free)

| Layer | Tech | Why |
|-------|------|-----|
| **Orchestration** | **LangGraph** | Stateful agent graphs, tool routing, retries |
| **Agent Framework** | **LangChain** | Tool abstractions, Gemini integration |
| Language | Python 3.11+ | ML/NLP ecosystem |
| LLM | Gemini 2.5 Flash (`langchain-google-genai`) | Free tier, fast |
| Embeddings | `sentence-transformers` `all-MiniLM-L6-v2` | Free, local, 384-dim |
| Vector DB | ChromaDB (`langchain-chroma`) | Free, embedded |
| Graph DB | Neo4j Community (`langchain-neo4j`) | Free graph DB |
| Metadata DB | SQLite | Crawl state, provenance |
| Crawling | Scrapy + BeautifulSoup4 | robots.txt, rate limiting |
| PDF Parse | PyMuPDF + pdfplumber + camelot-py | Table extraction |
| DOCX Parse | python-docx | DOCX extraction |
| API | FastAPI + Uvicorn | Webhooks, queries |
| Scheduler | APScheduler | Re-crawl cycles |
| Containers | Docker + docker-compose | Reproducible deploy |
| Metrics | prometheus-client | Observability |
| Testing | pytest | Unit + integration |
| Validation | Pydantic v2 | Schema enforcement |

## Project Structure

```
myk-laticrete-engine/
├── docker-compose.yml          # Neo4j CE + app
├── Dockerfile
├── requirements.txt
├── .env.example
├── config/
│   ├── settings.py             # Pydantic Settings
│   ├── seed_urls.py            # 50+ MYK Laticrete URLs
│   └── logging_config.py
│
├── agents/                     # LANGGRAPH AGENTS
│   ├── __init__.py
│   ├── state.py                # Shared TypedDict state definitions
│   ├── ingestion_graph.py      # Main pipeline: crawl→parse→embed→sync
│   ├── retrieval_agent.py      # ReAct agent for hybrid retrieval
│   └── nodes/                  # LangGraph node functions
│       ├── __init__.py
│       ├── crawl_node.py       # Crawl step
│       ├── parse_node.py       # Parse step
│       ├── embed_node.py       # Embed + graph build step
│       ├── sync_node.py        # Sync/delta step
│       └── router_node.py      # Conditional routing logic
│
├── tools/                      # LANGCHAIN TOOLS (for agents)
│   ├── __init__.py
│   ├── crawl_tools.py          # fetch_page, extract_pdf, discover_links
│   ├── parse_tools.py          # extract_product_specs, validate_schema
│   ├── graph_tools.py          # graph_search, get_product, cypher_query
│   ├── vector_tools.py         # vector_search, embed_product
│   ├── compare_tools.py        # compare_products, get_specs
│   └── sync_tools.py           # check_delta, trigger_update
│
├── crawler/                    # TASK 1: Core crawl logic
│   ├── __init__.py
│   ├── spider.py
│   ├── robots_handler.py
│   ├── rate_limiter.py
│   ├── content_detector.py
│   ├── extractors/
│   │   ├── html_extractor.py
│   │   ├── pdf_extractor.py
│   │   └── docx_extractor.py
│   ├── storage.py
│   ├── dedup.py
│   └── models.py
│
├── parser/                     # TASK 2: Core parse logic
│   ├── __init__.py
│   ├── product_schema.py
│   ├── llm_extractor.py
│   ├── pdf_table_parser.py
│   ├── field_validator.py
│   ├── version_tracker.py
│   └── qa_report.py
│
├── graph/                      # TASK 3: Core graph logic
│   ├── __init__.py
│   ├── schema.py
│   ├── builder.py
│   ├── neo4j_client.py
│   ├── embedder.py
│   ├── vector_store.py
│   └── seed_use_cases.py
│
├── sync/                       # TASK 4: Core sync logic
│   ├── __init__.py
│   ├── delta_detector.py
│   ├── reconciler.py
│   ├── scheduler.py
│   ├── propagator.py
│   └── metrics.py
│
├── api/                        # FastAPI endpoints
│   ├── main.py
│   └── routes/
│       ├── query.py            # Calls retrieval_agent
│       ├── webhook.py          # Triggers ingestion_graph
│       ├── health.py
│       └── metrics.py
│
├── notebooks/
│   └── retrieval_demo.ipynb
├── tests/
├── scripts/
│   ├── run_pipeline.py         # Runs ingestion_graph end-to-end
│   └── simulate_webhook.py
└── data/
    ├── raw/
    ├── structured/
    └── crawl.db
```

## Environment (.env.example)

```env
GEMINI_API_KEY=your-free-key-from-aistudio.google.com
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=myklaticrete2024
CHROMA_PERSIST_DIR=./data/chroma
CRAWL_DELAY_SECONDS=2
MAX_CONCURRENT_REQUESTS=4
SQLITE_DB_PATH=./data/crawl.db
API_PORT=8000
```

## docker-compose.yml

```yaml
version: '3.8'
services:
  neo4j:
    image: neo4j:5-community
    ports: ["7474:7474", "7687:7687"]
    environment:
      NEO4J_AUTH: neo4j/myklaticrete2024
      NEO4J_PLUGINS: '["apoc"]'
    volumes: [neo4j_data:/data]
  app:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [neo4j]
    volumes: [./data:/app/data]
volumes:
  neo4j_data:
```

## requirements.txt

```
# LangGraph + LangChain (orchestration)
langgraph>=0.2.0
langchain>=0.3.0
langchain-core>=0.3.0
langchain-google-genai>=2.0.0
langchain-chroma>=0.2.0
langchain-neo4j>=0.1.0
langchain-community>=0.3.0

# Core
fastapi==0.115.0
uvicorn[standard]==0.30.0
pydantic==2.9.0
pydantic-settings==2.5.0
python-dotenv==1.0.1

# Crawler
scrapy==2.11.0
beautifulsoup4==4.12.3
requests==2.32.0
lxml==5.3.0

# PDF/DOCX
PyMuPDF==1.24.0
pdfplumber==0.11.0
camelot-py[cv]==0.11.0
python-docx==1.1.0

# Embeddings & Vector
sentence-transformers==3.0.0
chromadb==0.5.0

# Graph
neo4j==5.24.0

# Data
pandas==2.2.0
pyarrow==17.0.0

# Scheduling & Metrics
apscheduler==3.10.4
prometheus-client==0.21.0

# Hashing
xxhash==3.5.0

# Testing
pytest==8.3.0
pytest-asyncio==0.24.0
httpx==0.27.0
```
