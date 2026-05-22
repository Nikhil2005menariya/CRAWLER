# TASK 3 — Knowledge Graph + Retrieval Agent (LangGraph)

## Objective
Build Neo4j graph + ChromaDB vectors via `embed_node`.
Build a **LangGraph ReAct agent** for hybrid retrieval with tools.

## How it fits in LangGraph

```
embed_node: Receives products from parse_node, builds graph + vectors.
retrieval_agent: Standalone ReAct agent (create_react_agent) with 6 tools.
  The agent DECIDES which tools to call based on the user's query.
```

## Graph Schema (Neo4j)

### Nodes
```
Product       → {sku, name, family, description, specs, confidence, is_active}
ProductFamily → {name, description}
UseCase       → {name, description, environment, constraints}
Substrate     → {name, type}
TileType      → {name, size_category}
Standard      → {code, name, body}
Document      → {url, type, title, fetched_at}
```

### Edges
```
(Product)-[:BELONGS_TO]->(ProductFamily)
(Product)-[:RECOMMENDED_FOR]->(UseCase)
(Product)-[:COMPATIBLE_WITH]->(Substrate)
(Product)-[:SUITABLE_FOR]->(TileType)
(Product)-[:COMPLIES_WITH]->(Standard)
(Product)-[:DOCUMENTED_IN]->(Document)
(UseCase)-[:REQUIRES_SUBSTRATE]->(Substrate)
(UseCase)-[:USES_TILE]->(TileType)
```

## 10 Seed Use Cases (`graph/seed_use_cases.py`)

```python
USE_CASES = [
    {"name": "wet_area_bathroom_walls", "description": "Tile on bathroom walls", 
     "environment": "interior_wet", "substrates": ["concrete", "cement_plaster"], 
     "tiles": ["ceramic", "vitrified", "glass_mosaic"]},
    {"name": "swimming_pool_tiling", "description": "Underwater tile/mosaic", 
     "environment": "submerged", "substrates": ["concrete"], 
     "tiles": ["ceramic", "glass_mosaic"]},
    {"name": "exterior_facade_cladding", "description": "Stone/tile on building exteriors",
     "environment": "exterior", "substrates": ["concrete", "brick"], 
     "tiles": ["natural_stone", "vitrified"]},
    {"name": "commercial_kitchen_flooring", "description": "Heavy-duty kitchen floors",
     "environment": "interior_wet_heavy_traffic", "substrates": ["concrete"], 
     "tiles": ["vitrified", "ceramic"]},
    {"name": "heated_floor_installation", "description": "Tile over underfloor heating",
     "environment": "interior_heated", "substrates": ["concrete", "cement_screed"], 
     "tiles": ["vitrified", "ceramic", "natural_stone"]},
    {"name": "large_format_vitrified", "description": "60x60+ vitrified tiles",
     "environment": "interior", "substrates": ["concrete", "cement_screed"], 
     "tiles": ["large_format_vitrified"]},
    {"name": "natural_stone_on_concrete", "description": "Natural stone fixing",
     "environment": "interior_exterior", "substrates": ["concrete"], 
     "tiles": ["natural_stone", "marble", "granite"]},
    {"name": "industrial_warehouse_epoxy", "description": "Industrial epoxy flooring",
     "environment": "industrial", "substrates": ["concrete"], 
     "tiles": ["vitrified", "industrial_tile"]},
    {"name": "balcony_waterproofing", "description": "Waterproofing + tiling balconies",
     "environment": "exterior_wet", "substrates": ["concrete"], 
     "tiles": ["vitrified", "ceramic"]},
    {"name": "terrace_garden_tiling", "description": "Tiling terrace gardens",
     "environment": "exterior_wet", "substrates": ["concrete"], 
     "tiles": ["vitrified", "natural_stone"]},
]
```

## Embedder (`graph/embedder.py`)

```python
from sentence_transformers import SentenceTransformer

class ProductEmbedder:
    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")  # Free, local
    
    def embed_product_dict(self, product: dict) -> list[float]:
        text = f"Product: {product['product_name']}. Family: {product['product_family']}. "
        text += f"Description: {product.get('description', '')}. "
        text += f"Substrates: {', '.join(product.get('substrate_compatibility', []))}. "
        text += f"Tiles: {', '.join(product.get('tile_compatibility', []))}. "
        text += f"Uses: {', '.join(product.get('recommended_use_cases', []))}."
        return self.model.encode(text).tolist()
    
    def embed_query(self, query: str) -> list[float]:
        return self.model.encode(query).tolist()
```

**Why all-MiniLM-L6-v2**: Free, local, 384-dim, fast, good for technical content.

## Retrieval Agent — The Key Differentiator

The retrieval agent is built with `create_react_agent` from LangGraph.
It has 6 tools defined in `tools/` (see AGENTS_AND_TOOLS.md):

1. **graph_search_tool** — Cypher queries with substrate/tile/usecase filters
2. **vector_search_tool** — Semantic similarity via ChromaDB
3. **product_lookup_tool** — Direct SKU/name lookup
4. **compare_products_tool** — Side-by-side comparison
5. **get_specs_tool** — Detailed technical specs
6. **cypher_query_tool** — Custom Cypher for complex queries

The agent's ReAct loop:
```
User query → LLM thinks → decides tool(s) → calls tool(s) → 
observes results → thinks again → calls more tools OR answers
```

## 5 Demo Queries (for notebook)

```python
from agents.retrieval_agent import build_retrieval_agent

agent = build_retrieval_agent()

queries = [
    # 1. Multi-constraint (should use graph_search)
    "Recommend an adhesive for 80×80 vitrified tiles on a heated bathroom floor over concrete",
    
    # 2. Semantic (should use vector_search)
    "What waterproofing solution works for swimming pools?",
    
    # 3. Comparison (should use compare_products + get_specs)
    "Compare SP-100 tile joint options for a hospital bathroom",
    
    # 4. Graph + vector combined
    "I need to fix natural stone on an exterior facade — which adhesive and what coverage rate?",
    
    # 5. Specs-focused (should use product_lookup + get_specs)
    "What is the open time and coverage rate of MYK Laticrete 335 Super Flex?",
]

for q in queries:
    result = await agent.ainvoke({"messages": [("user", q)]})
    print(f"Q: {q}")
    print(f"A: {result['messages'][-1].content}\n")
    print(f"Tools used: {[m.name for m in result['messages'] if hasattr(m, 'name')]}\n")
```

## Deliverable Checklist
- [ ] Neo4j schema with constraints and indexes
- [ ] Graph populated from 30+ products
- [ ] 10 use cases seeded with substrate/tile associations
- [ ] ChromaDB vector index with all embeddings
- [ ] LangGraph ReAct agent with 6 tools
- [ ] Agent decides autonomously which tools to call
- [ ] Jupyter notebook with 5 demo queries showing tool usage
- [ ] Each query shows which tools the agent chose and why
