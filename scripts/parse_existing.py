#!/usr/bin/env python
import logging
import sys
import time

sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("parse_existing")

def run():
    from backend.agents.nodes.parse_node import parse_node
    from backend.agents.nodes.embed_node import embed_node
    
    state = {
        "urls_to_crawl": [],
        "crawl_records": [],
        "products": [],
        "graph_updates": [],
        "embedding_updates": [],
        "errors": [],
        "metrics": {},
        "current_phase": "start",
    }
    
    logger.info("Executing parse_node directly to resolve unparsed crawl records...")
    state = parse_node(state)
    
    logger.info("Phase complete. Metrics: %s", state.get("metrics"))
    logger.info("Errors: %s", state.get("errors"))
    
    if state.get("products"):
        logger.info("Executing embed_node to populate Neo4j and ChromaDB...")
        state = embed_node(state)
        logger.info("Embedding complete. Final Metrics: %s", state.get("metrics"))
    else:
        logger.warning("No new products parsed.")

if __name__ == "__main__":
    run()
