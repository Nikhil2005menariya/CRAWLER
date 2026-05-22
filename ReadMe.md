# 🏗️ MYK Laticrete Knowledge Ingestion Engine — Master Index

> **Production-grade AI-powered Knowledge Base with LangGraph Agentic Orchestration**
> Hand ALL these files to Claude Code / Codex to build the complete project.

## 📄 Document Map (Read in this order)

| # | File | Contents |
|---|------|----------|
| 1 | `PROJECT_PLANNER_PART1.md` | Architecture, tech stack, project structure, docker-compose |
| 2 | **`AGENTS_AND_TOOLS.md`** | **⭐ LangGraph agents, tools, state definitions — THE CORE** |
| 3 | `TASK1_CRAWLER.md` | Web crawler: 50+ seed URLs, extractors, dedup |
| 4 | `TASK2_PARSER.md` | Catalog parser: Gemini Flash extraction via LangChain tools |
| 5 | `TASK3_GRAPH.md` | Knowledge graph: Neo4j + ChromaDB + ReAct retrieval agent |
| 6 | `TASK4_SYNC.md` | Sync engine: LangGraph sync pipeline + webhooks |
| 7 | `EXECUTION_PLAYBOOK.md` | Step-by-step build order (7 phases, 7 days) |

## 🤖 Agentic Architecture (What Makes This Production-Grade)

```
┌─ ingestion_graph (LangGraph StateGraph) ─────────────────────┐
│  crawl_node → route_node → parse_node → embed_node → sync   │
│  Each node uses LangChain @tools that wrap core modules      │
└──────────────────────────────────────────────────────────────┘

┌─ retrieval_agent (LangGraph ReAct) ──────────────────────────┐
│  Gemini 2.5 Flash + 6 tools (graph_search, vector_search,   │
│  product_lookup, compare, get_specs, cypher_query)           │
│  Agent DECIDES which tools to call based on user query       │
└──────────────────────────────────────────────────────────────┘

┌─ sync_graph (LangGraph StateGraph) ──────────────────────────┐
│  webhook → check_event → recrawl → reparse → update_graph   │
│  Conditional: update vs delete path                          │
└──────────────────────────────────────────────────────────────┘
```

## 💰 Cost: $0

- **Gemini 2.5 Flash** — free tier (15 RPM)
- **LangGraph + LangChain** — open source
- **sentence-transformers** — local, free
- **Neo4j Community** — free Docker image
- **ChromaDB** — embedded, free

## 🚀 For the AI Agent: Start Here

```
1. Read PROJECT_PLANNER_PART1.md → architecture + structure
2. Read AGENTS_AND_TOOLS.md → LangGraph agents + tools (THE CORE)
3. Read EXECUTION_PLAYBOOK.md → follow exact build order
4. Read TASK1-4 as you reach each phase
5. Build Phase 0-6 in order
```

## 📊 Deliverables

- [ ] 3 LangGraph graphs (ingestion, retrieval, sync)
- [ ] 6 LangChain tools for the retrieval agent
- [ ] 50+ URLs crawled with provenance
- [ ] 30+ SKUs structured with confidence scores
- [ ] Neo4j graph (7 node types, 8 edge types, 10 use cases)
- [ ] ChromaDB vector index
- [ ] ReAct agent answering 5 demo queries autonomously
- [ ] Webhook → graph update pipeline in <5 min
- [ ] Prometheus metrics
- [ ] Docker-compose deployment
