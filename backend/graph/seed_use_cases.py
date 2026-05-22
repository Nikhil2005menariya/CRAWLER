"""
graph/seed_use_cases.py
───────────────────────
10 canonical construction use cases for the MYK Laticrete knowledge graph.
Each use case links to substrates and tile types via Neo4j relationships.
"""

import logging

logger = logging.getLogger(__name__)

USE_CASES = [
    {
        "name": "wet_area_bathroom_walls",
        "description": "Tile installation on bathroom walls in wet areas",
        "environment": "interior_wet",
        "substrates": ["concrete", "cement_plaster"],
        "tiles": ["ceramic", "vitrified", "glass_mosaic"],
    },
    {
        "name": "swimming_pool_tiling",
        "description": "Underwater tile and mosaic installation in swimming pools",
        "environment": "submerged",
        "substrates": ["concrete"],
        "tiles": ["ceramic", "glass_mosaic"],
    },
    {
        "name": "exterior_facade_cladding",
        "description": "Stone and tile cladding on building exterior facades",
        "environment": "exterior",
        "substrates": ["concrete", "brick"],
        "tiles": ["natural_stone", "vitrified"],
    },
    {
        "name": "commercial_kitchen_flooring",
        "description": "Heavy-duty flooring for commercial kitchens with heavy traffic",
        "environment": "interior_wet_heavy_traffic",
        "substrates": ["concrete"],
        "tiles": ["vitrified", "ceramic"],
    },
    {
        "name": "heated_floor_installation",
        "description": "Tile installation over underfloor heating (UFH) systems",
        "environment": "interior_heated",
        "substrates": ["concrete", "cement_screed"],
        "tiles": ["vitrified", "ceramic", "natural_stone"],
    },
    {
        "name": "large_format_vitrified",
        "description": "Installation of large format vitrified tiles (60x60cm and above)",
        "environment": "interior",
        "substrates": ["concrete", "cement_screed"],
        "tiles": ["large_format_vitrified"],
    },
    {
        "name": "natural_stone_on_concrete",
        "description": "Fixing natural stone, marble, and granite on concrete substrates",
        "environment": "interior_exterior",
        "substrates": ["concrete"],
        "tiles": ["natural_stone", "marble", "granite"],
    },
    {
        "name": "industrial_warehouse_epoxy",
        "description": "Industrial epoxy flooring for warehouses and factories",
        "environment": "industrial",
        "substrates": ["concrete"],
        "tiles": ["vitrified", "industrial_tile"],
    },
    {
        "name": "balcony_waterproofing",
        "description": "Waterproofing membrane and tile installation on balconies",
        "environment": "exterior_wet",
        "substrates": ["concrete"],
        "tiles": ["vitrified", "ceramic"],
    },
    {
        "name": "terrace_garden_tiling",
        "description": "Tiling of terrace gardens exposed to weather",
        "environment": "exterior_wet",
        "substrates": ["concrete"],
        "tiles": ["vitrified", "natural_stone"],
    },
]


def seed_use_cases(graph) -> dict:
    """
    Upsert the 10 canonical use cases into Neo4j with their substrate/tile edges.

    Args:
        graph: A langchain_neo4j.Neo4jGraph instance.

    Returns:
        dict with 'seeded' count.
    """
    seeded = 0
    for uc in USE_CASES:
        try:
            # Merge the UseCase node
            graph.query(
                """
                MERGE (u:UseCase {name: $name})
                SET u.description = $description, u.environment = $environment
                """,
                {"name": uc["name"], "description": uc["description"], "environment": uc["environment"]},
            )

            # Merge each Substrate and create the relationship
            for sub in uc["substrates"]:
                graph.query(
                    """
                    MERGE (s:Substrate {name: $name})
                    WITH s
                    MATCH (u:UseCase {name: $uc_name})
                    MERGE (u)-[:REQUIRES_SUBSTRATE]->(s)
                    """,
                    {"name": sub, "uc_name": uc["name"]},
                )

            # Merge each TileType and create the relationship
            for tile in uc["tiles"]:
                graph.query(
                    """
                    MERGE (t:TileType {name: $name})
                    WITH t
                    MATCH (u:UseCase {name: $uc_name})
                    MERGE (u)-[:USES_TILE]->(t)
                    """,
                    {"name": tile, "uc_name": uc["name"]},
                )

            seeded += 1
            logger.debug("Seeded use case: %s", uc["name"])

        except Exception as exc:
            logger.error("Failed to seed use case '%s': %s", uc["name"], exc)

    logger.info("Seeded %d/%d use cases into Neo4j", seeded, len(USE_CASES))
    return {"seeded": seeded}
