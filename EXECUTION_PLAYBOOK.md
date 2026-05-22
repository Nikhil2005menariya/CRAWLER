# Execution Playbook — LangGraph Agentic Build Order

> Follow this EXACT order. Each phase depends on the previous.

## Phase 0: Project Setup (30 min)
```
1. Create myk-laticrete-engine/ directory
2. python -m venv venv && source venv/bin/activate
3. Create requirements.txt (see PROJECT_PLANNER_PART1.md)
4. pip install -r requirements.txt
5. Create .env from .env.example (get free Gemini key at aistudio.google.com)
6. docker-compose up -d neo4j
7. Create config/settings.py, config/seed_urls.py, config/logging_config.py
8. Verify: Neo4j at bolt://localhost:7687, Gemini API key works
```

## Phase 1: Core Modules (Day 1-2)
```
Build the low-level modules that LangGraph nodes/tools will call:

1. crawler/models.py — CrawlRecord dataclass
2. crawler/robots_handler.py — robots.txt parser
3. crawler/rate_limiter.py — 2s delay, 4 concurrent
4. crawler/content_detector.py — HTML/PDF/DOCX routing
5. crawler/extractors/{html,pdf,docx}_extractor.py
6. crawler/storage.py — SQLite schema + CRUD
7. crawler/dedup.py — xxhash dedup
8. crawler/spider.py — CrawlOrchestrator class
9. parser/product_schema.py — Pydantic ProductRecord
10. parser/pdf_table_parser.py — pdfplumber tables
11. parser/llm_extractor.py — Gemini Flash extraction
12. parser/field_validator.py — confidence scoring
13. parser/version_tracker.py — SQLite version history
14. parser/qa_report.py — report generator
15. graph/schema.py — node/edge types
16. graph/neo4j_client.py — driver wrapper
17. graph/builder.py — graph construction
18. graph/embedder.py — sentence-transformers
19. graph/vector_store.py — ChromaDB wrapper
20. graph/seed_use_cases.py — 10 use cases
TEST: Unit test each module independently
```

## Phase 2: LangChain Tools (Day 2-3)
```
Wrap core modules as LangChain @tool functions:

1. tools/crawl_tools.py — fetch_page, extract_pdf, discover_links
2. tools/parse_tools.py — extract_product_specs, validate_product_schema
3. tools/graph_tools.py — graph_search_tool, product_lookup_tool, 
                          cypher_query_tool, upsert_to_graph
4. tools/vector_tools.py — vector_search_tool, embed_and_store
5. tools/compare_tools.py — compare_products_tool, get_specs_tool
6. tools/sync_tools.py — check_delta_tool, trigger_recrawl_tool
TEST: Call each tool directly, verify outputs
```

## Phase 3: LangGraph Agents (Day 3-4) ⭐ CORE
```
Build the agentic orchestration layer:

1. agents/state.py — IngestionState, RetrievalState, SyncState TypedDicts
2. agents/ingestion_graph.py — Main pipeline StateGraph:
   crawl_node → route_node → parse_node → embed_node → sync_node → report_node
   with conditional edge (should_continue)
3. agents/retrieval_agent.py — ReAct agent via create_react_agent with 6 tools
4. agents/sync_graph.py — Webhook-triggered StateGraph:
   check_event → recrawl/deprecate → reparse → update_graph → update_vectors → report
5. agents/nodes/ — Individual node function implementations

TEST: 
  - Run ingestion_graph on 5 URLs end-to-end
  - Ask retrieval_agent 3 test questions
  - Trigger sync_graph with mock webhook
```

## Phase 4: API Layer (Day 4-5)
```
1. api/main.py — FastAPI app
2. api/routes/query.py — POST /api/query → calls retrieval_agent
3. api/routes/webhook.py — POST /webhook/cms → calls sync_graph
4. api/routes/health.py — GET /health
5. api/routes/metrics.py — GET /metrics
6. sync/scheduler.py — APScheduler for periodic ingestion_graph runs
7. sync/metrics.py — Prometheus counters/histograms

TEST: curl all endpoints, verify responses
```

## Phase 5: Full Pipeline Run (Day 5-6)
```
1. scripts/run_pipeline.py — Invoke ingestion_graph with all 50+ seed URLs
2. Wait for full pipeline: crawl → parse → embed → sync
3. Verify: 30+ products in Neo4j, embeddings in ChromaDB
4. scripts/seed_graph.py — Seed use cases if not done by pipeline
5. notebooks/retrieval_demo.ipynb — 5 demo queries showing agent tool selection
6. scripts/simulate_webhook.py — Webhook demo showing <5 min update
7. Dockerfile — containerize everything

TEST: docker-compose up → full system works
```

## Phase 6: Testing & Polish (Day 6-7)
```
1. tests/test_crawler.py — extractors, dedup, robots
2. tests/test_parser.py — schema validation, confidence
3. tests/test_graph.py — graph queries, hybrid retrieval
4. tests/test_sync.py — delta detection, webhooks
5. tests/test_agents.py — ingestion_graph, retrieval_agent, sync_graph
6. tests/test_api.py — API endpoints
7. pytest --tb=short -v
8. Update README.md
```

## Key Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Pipeline orchestration | LangGraph StateGraph | Stateful, conditional routing, retries |
| Retrieval | LangGraph ReAct agent | Agent decides tools autonomously |
| Sync | Separate LangGraph graph | Isolated, triggered by webhook |
| LLM | Gemini 2.5 Flash via langchain-google-genai | Free, fast, structured output |
| Embeddings | sentence-transformers (local) | Free, no API dependency |
| Graph DB | Neo4j Community | Production graph, free |
| Vector DB | ChromaDB | Embedded, free, easy |
| Tools | LangChain @tool decorator | Clean interface for agents |

## Critical Notes for AI Agent

1. **Three LangGraph graphs**: ingestion_graph (pipeline), retrieval_agent (ReAct), sync_graph (webhook)
2. **Tools are the bridge**: Core modules (crawler/, parser/, graph/) are wrapped as @tool for agents
3. **State flows through**: Each node reads/writes to the shared TypedDict state
4. **Gemini free tier**: 15 RPM limit. Add 4s delays between extraction calls in parse_node.
5. **The website is WordPress**: Standard HTML, no SPA. Content in standard elements.
6. **robots.txt**: Only blocks /wp-admin/. All products crawlable.
7. **create_react_agent**: From langgraph.prebuilt — simplest way to build the retrieval agent.
