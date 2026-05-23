import sqlite3
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from backend.api.routes.auth import get_current_user
from backend.config.settings import Settings

logger = logging.getLogger(__name__)
router = APIRouter()

def get_admin_user(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user

# ---------------------------------------------------------------------------
# Background Task for Asynchronous Sync to Neo4j + ChromaDB
# ---------------------------------------------------------------------------
def sync_approved_product_task(product_data: dict, is_delete: bool = False):
    """Background task to sync an approved/updated product to Neo4j + ChromaDB."""
    try:
        from backend.graph.neo4j_client import get_graph
        from backend.graph.vector_store import ProductVectorStore
        from backend.graph.embedder import ProductEmbedder
        from backend.graph.builder import GraphBuilder
        
        # Ensure correct type flags
        product_data["needs_human_review"] = False
        
        g = get_graph()
        
        # 1. Handle Deletion Sync
        if is_delete:
            if g is not None:
                name = product_data.get("product_name")
                if name:
                    logger.info("Sync Task: deleting '%s' from Neo4j", name)
                    g.query("MATCH (p:Product {name: $name}) DETACH DELETE p", {"name": name})
            try:
                vs = ProductVectorStore()
                logger.info("Sync Task: deleting from ChromaDB")
                vs.delete(product_data)
            except Exception as e:
                logger.warning("Sync Task: ChromaDB delete failed: %s", e)
            return

        # 2. Handle Upsert Sync (Neo4j Graph)
        try:
            vs = ProductVectorStore()
            emb = ProductEmbedder()
        except Exception as e:
            logger.error("Sync Task: failed to load vector database layers: %s", e)
            vs = emb = None

        if g is not None:
            try:
                logger.info("Sync Task: merging '%s' node & relationships in Neo4j", product_data.get("product_name"))
                builder = GraphBuilder(neo4j_graph=g, vector_store=vs, embedder=emb)
                builder._merge_product_node(product_data)
                builder._merge_relationships(product_data)
            except Exception as e:
                logger.error("Sync Task: Neo4j merge failed: %s", e)

        # 3. Handle Upsert Sync (ChromaDB Vectors)
        if vs is not None and emb is not None:
            try:
                logger.info("Sync Task: embedding and upserting '%s' in ChromaDB", product_data.get("product_name"))
                embeddings = emb.embed_batch([product_data])
                vs.upsert_batch([product_data], embeddings)
            except Exception as e:
                logger.error("Sync Task: ChromaDB upsert failed: %s", e)

    except Exception as e:
        logger.error("Global background sync task crash: %s", e)


# ---------------------------------------------------------------------------
# Router Endpoints
# ---------------------------------------------------------------------------

@router.get("/crawl/records")
async def get_crawl_records(admin: dict = Depends(get_admin_user)):
    s = Settings()
    conn = sqlite3.connect(s.sqlite_db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, url, title, fetched_at FROM crawl_records ORDER BY fetched_at DESC LIMIT 100")
    records = cursor.fetchall()
    conn.close()
    
    result = []
    for row in records:
        result.append({
            "id": row[0],
            "url": row[1],
            "title": row[2],
            "timestamp": row[3]
        })
    return {"records": result}


@router.get("/metrics")
async def get_admin_metrics(admin: dict = Depends(get_admin_user)):
    s = Settings()
    conn = sqlite3.connect(s.sqlite_db_path)
    cursor = conn.cursor()
    
    # 1. Total crawl records
    cursor.execute("SELECT COUNT(*) FROM crawl_records")
    total_crawled = cursor.fetchone()[0]
    
    # 2. Total parsed products
    cursor.execute("SELECT COUNT(*) FROM products")
    total_products = cursor.fetchone()[0]
    
    # 3. Products needing review
    cursor.execute("SELECT COUNT(*) FROM products WHERE needs_review = 1")
    needs_review = cursor.fetchone()[0]
    
    conn.close()
    
    # 4. Refresh Prometheus active_products gauge
    try:
        from backend.sync.metrics import refresh_active_products_gauge, active_products, freshness_lag
        refresh_active_products_gauge(s.sqlite_db_path)
        active_val = active_products._value.get() if hasattr(active_products, "_value") else total_products
        lag_val = freshness_lag._value.get() if hasattr(freshness_lag, "_value") else 0.0
    except Exception:
        active_val = total_products
        lag_val = 0.0
        
    return {
        "crawled_pages_count": total_crawled,
        "parsed_products_count": total_products,
        "needs_review_count": needs_review,
        "active_products_gauge": active_val,
        "freshness_lag_seconds": lag_val
    }


@router.get("/review/products")
async def get_review_products(admin: dict = Depends(get_admin_user)):
    """Fetch all SQLite products flagged as needing review (needs_review = 1)."""
    s = Settings()
    conn = sqlite3.connect(s.sqlite_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, sku, product_name, product_family, data_json, confidence, needs_review, version FROM products WHERE needs_review = 1"
    )
    rows = cursor.fetchall()
    conn.close()
    
    products = []
    for r in rows:
        try:
            p_dict = json.loads(r["data_json"])
        except Exception:
            p_dict = {}
        
        products.append({
            "id": r["id"],
            "sku": r["sku"],
            "product_name": r["product_name"],
            "product_family": r["product_family"],
            "confidence": r["confidence"],
            "needs_review": r["needs_review"],
            "version": r["version"],
            "details": p_dict
        })
    return {"products": products}


@router.put("/review/products/{id}")
async def update_review_product(
    id: int, 
    payload: dict, 
    bg_tasks: BackgroundTasks, 
    admin: dict = Depends(get_admin_user)
):
    """
    Update product details in SQLite, option to approve (set needs_review = 0),
    and trigger a background task to synchronize with Neo4j and ChromaDB.
    """
    s = Settings()
    conn = sqlite3.connect(s.sqlite_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    existing = cursor.execute("SELECT * FROM products WHERE id = ?", (id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Product not found")
        
    # Extract details from update payload
    product_details = payload.get("details", {})
    approve = payload.get("approve", False)
    
    # Recalculate confidence if edited
    from backend.parser.field_validator import compute_confidence
    conf = compute_confidence(product_details)
    
    sku = (product_details.get("sku") or "").strip() or None
    name = product_details.get("product_name", existing["product_name"])
    family = product_details.get("product_family", existing["product_family"])
    
    needs_review = 0 if approve else 1
    product_details["needs_human_review"] = bool(needs_review)
    product_details["extraction_confidence"] = conf
    
    now = datetime.now(timezone.utc).isoformat()
    data_json = json.dumps(product_details, default=str)
    
    cursor.execute(
        """
        UPDATE products
        SET sku = ?, product_name = ?, product_family = ?, data_json = ?, confidence = ?, needs_review = ?, extracted_at = ?
        WHERE id = ?
        """,
        (sku, name, family, data_json, conf, needs_review, now, id)
    )
    conn.commit()
    conn.close()
    
    # If approved (needs_review = 0), trigger asynchronous sync in the background
    if approve:
        bg_tasks.add_task(sync_approved_product_task, product_details, is_delete=False)
        
    return {
        "status": "success", 
        "needs_review": needs_review, 
        "confidence": conf,
        "message": "Product approved and queued for graph sync!" if approve else "Product changes saved!"
    }


@router.delete("/review/products/{id}")
async def delete_review_product(
    id: int, 
    bg_tasks: BackgroundTasks, 
    admin: dict = Depends(get_admin_user)
):
    """Delete the product from SQLite database and schedule a background task to delete from Neo4j + ChromaDB."""
    s = Settings()
    conn = sqlite3.connect(s.sqlite_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    existing = cursor.execute("SELECT * FROM products WHERE id = ?", (id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Product not found")
        
    try:
        product_details = json.loads(existing["data_json"])
    except Exception:
        product_details = {
            "product_name": existing["product_name"],
            "sku": existing["sku"],
            "product_family": existing["product_family"]
        }
        
    cursor.execute("DELETE FROM products WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    
    # Schedule deletion from Neo4j + ChromaDB in the background
    bg_tasks.add_task(sync_approved_product_task, product_details, is_delete=True)
    
    return {"status": "success", "message": "Product deleted successfully from catalog"}
