"""
graph/vector_store.py
──────────────────────
ChromaDB-backed vector store for product embeddings.
Persists to CHROMA_PERSIST_DIR (default: ./data/chroma).
"""

import json
import logging
import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env
for _candidate in [
    Path(__file__).parents[2] / ".env",
    Path(__file__).parents[3] / ".env",
]:
    if _candidate.exists():
        load_dotenv(_candidate, override=False)
        break

_COLLECTION_NAME = "myk_products"


class ProductVectorStore:
    """
    Wraps ChromaDB for storing and querying product embeddings.

    All vectors are 384-dimensional (all-MiniLM-L6-v2).
    Documents stored alongside vectors carry product metadata for display.
    """

    def __init__(self, persist_dir: Optional[str] = None):
        persist_dir = persist_dir or os.environ.get("CHROMA_PERSIST_DIR", "./data/chroma")
        os.makedirs(persist_dir, exist_ok=True)

        import chromadb
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},   # cosine similarity
        )
        logger.info(
            "ChromaDB collection '%s' loaded (%d items) from %s",
            _COLLECTION_NAME, self._collection.count(), persist_dir,
        )

    def upsert(self, product: dict, embedding: List[float]) -> None:
        """
        Add or update a product vector in ChromaDB.

        Args:
            product:   ProductRecord dict.
            embedding: 384-dim float list from ProductEmbedder.
        """
        doc_id = self._doc_id(product)
        metadata = {
            "product_name":   product.get("product_name", ""),
            "product_family": product.get("product_family", ""),
            "sku":            product.get("sku") or "",
            "confidence":     float(product.get("extraction_confidence", 0.0)),
            "needs_review":   str(product.get("needs_human_review", False)),
        }
        # Store a short text document for display
        document = (
            f"{product.get('product_name','')} "
            f"({product.get('product_family','')}) — "
            f"{product.get('description','')[:200]}"
        )
        self._collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[document],
            metadatas=[metadata],
        )

    def upsert_batch(self, products: list, embeddings: List[List[float]]) -> int:
        """Batch upsert products and their embeddings. Returns count upserted."""
        ids, docs, metas = [], [], []
        for p, emb in zip(products, embeddings):
            ids.append(self._doc_id(p))
            docs.append(
                f"{p.get('product_name','')} ({p.get('product_family','')}) — "
                f"{p.get('description','')[:200]}"
            )
            metas.append({
                "product_name":   p.get("product_name", ""),
                "product_family": p.get("product_family", ""),
                "sku":            p.get("sku") or "",
                "confidence":     float(p.get("extraction_confidence", 0.0)),
                "needs_review":   str(p.get("needs_human_review", False)),
            })
        self._collection.upsert(ids=ids, embeddings=embeddings, documents=docs, metadatas=metas)
        return len(ids)

    def similarity_search(
        self,
        query_embedding: List[float],
        k: int = 5,
        where: Optional[dict] = None,
    ) -> List[dict]:
        """
        Return top-k most similar products.

        Args:
            query_embedding: 384-dim float list.
            k:               Number of results.
            where:           Optional ChromaDB metadata filter dict.

        Returns:
            List of dicts: {id, document, metadata, distance}.
        """
        kwargs = {"query_embeddings": [query_embedding], "n_results": min(k, self.count() or 1)}
        if where:
            kwargs["where"] = where

        result = self._collection.query(**kwargs)
        hits = []
        for i, doc_id in enumerate(result["ids"][0]):
            hits.append({
                "id":       doc_id,
                "document": result["documents"][0][i],
                "metadata": result["metadatas"][0][i],
                "distance": result["distances"][0][i],
            })
        return hits

    def count(self) -> int:
        """Return number of vectors stored."""
        return self._collection.count()

    def get_all_ids(self) -> List[str]:
        """Return all document IDs in the collection."""
        result = self._collection.get(include=[])
        return result["ids"]

    def delete(self, product: dict) -> None:
        """Remove a product from the vector store."""
        self._collection.delete(ids=[self._doc_id(product)])

    @staticmethod
    def _doc_id(product: dict) -> str:
        """Stable ID: SKU if present, else normalised product name."""
        sku = (product.get("sku") or "").strip()
        if sku:
            return f"sku:{sku}"
        name = (product.get("product_name") or "unknown").strip().lower().replace(" ", "_")
        return f"name:{name}"
