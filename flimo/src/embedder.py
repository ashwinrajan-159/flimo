import logging
import numpy as np
from typing import List
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class Embedder:
    MODEL_NAME = "all-MiniLM-L6-v2"
    DIMENSION = 384

    def __init__(self):
        logger.info(f"Loading embedding model: {self.MODEL_NAME}...")
        try:
            self.model = SentenceTransformer(self.MODEL_NAME)
            logger.info("Model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load model {self.MODEL_NAME}: {e}")
            raise e

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for a list of texts.
        Returns normalized vectors of shape (N, 384).
        """
        if not texts:
            return np.array([])

        try:
            # Generate embeddings
            embeddings = self.model.encode(texts, convert_to_numpy=True)
            
            # L2 Normalize for Cosine Similarity
            # FAISS IndexFlatIP calculates inner product.
            # Inner Product of normalized vectors == Cosine Similarity.
            norm = np.linalg.norm(embeddings, axis=1, keepdims=True)
            
            # Use a small epsilon to avoid division by zero (though unlikely with model output)
            normalized_embeddings = embeddings / (norm + 1e-10)
            
            # Verify shape
            if normalized_embeddings.shape[1] != self.DIMENSION:
                raise ValueError(f"Embedding dimension mismatch. Expected {self.DIMENSION}, got {normalized_embeddings.shape[1]}")
                
            return normalized_embeddings
            
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise e
