"""
graph/embedder.py
──────────────────
Local sentence-transformer embeddings for products and queries.
Uses all-MiniLM-L6-v2 (384-dim, free, no API key needed).
"""

import logging
from typing import List

logger = logging.getLogger(__name__)

_model_instance = None


def _get_model():
    """Lazy-load the SentenceTransformer model (cached after first call)."""
    global _model_instance
    if _model_instance is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading SentenceTransformer (all-MiniLM-L6-v2)…")
        _model_instance = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("SentenceTransformer loaded.")
    return _model_instance


class ProductEmbedder:
    """
    Generates 384-dimensional dense vectors for products and user queries
    using the all-MiniLM-L6-v2 sentence transformer model.
    """

    def embed_product_dict(self, product: dict) -> List[float]:
        """
        Build a rich text representation of a product and return its embedding.

        Args:
            product: A ProductRecord dict (from the `products` SQLite table).

        Returns:
            List of 384 floats.
        """
        specs = product.get("technical_specs") or {}
        spec_parts = []
        for k, v in specs.items():
            if v:
                spec_parts.append(f"{k.replace('_', ' ')}: {v}")

        text = (
            f"Product: {product.get('product_name', '')}. "
            f"Family: {product.get('product_family', '')}. "
            f"Description: {product.get('description', '')}. "
            f"Grade: {product.get('grade_classification', '')}. "
            f"Substrates: {', '.join(product.get('substrate_compatibility') or [])}. "
            f"Tiles: {', '.join(product.get('tile_compatibility') or [])}. "
            f"Uses: {', '.join(product.get('recommended_use_cases') or [])}. "
            f"Specs: {'; '.join(spec_parts)}."
        )
        model = _get_model()
        return model.encode(text, normalize_embeddings=True).tolist()

    def embed_query(self, query: str) -> List[float]:
        """
        Embed a user query string.

        Args:
            query: Natural language question.

        Returns:
            List of 384 floats.
        """
        model = _get_model()
        return model.encode(query, normalize_embeddings=True).tolist()

    def embed_batch(self, products: list) -> List[List[float]]:
        """Batch embed a list of product dicts (more efficient than one by one)."""
        texts = []
        for p in products:
            specs = p.get("technical_specs") or {}
            spec_parts = [f"{k.replace('_',' ')}: {v}" for k, v in specs.items() if v]
            texts.append(
                f"Product: {p.get('product_name','')}.  "
                f"Family: {p.get('product_family','')}.  "
                f"Description: {p.get('description','')}.  "
                f"Grade: {p.get('grade_classification','')}.  "
                f"Substrates: {', '.join(p.get('substrate_compatibility') or [])}.  "
                f"Tiles: {', '.join(p.get('tile_compatibility') or [])}.  "
                f"Uses: {', '.join(p.get('recommended_use_cases') or [])}.  "
                f"Specs: {'; '.join(spec_parts)}."
            )
        model = _get_model()
        return model.encode(texts, normalize_embeddings=True, batch_size=16).tolist()
