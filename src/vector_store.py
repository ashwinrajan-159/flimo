import faiss
import pickle
import numpy as np
import logging
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class VectorStore:
    DATA_DIR = Path("data")
    INDEX_PATH = DATA_DIR / "vectors.faiss"
    MAP_PATH = DATA_DIR / "id_map.pkl"
    DIMENSION = 384

    def __init__(self):
        self.index = None
        self.id_map: Dict[int, str] = {} # faiss_id -> content_id
        self.inverse_map: Dict[str, int] = {} # content_id -> faiss_id (helper)
        self._load()

    def _load(self):
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # Load Index
        if self.INDEX_PATH.exists():
            try:
                self.index = faiss.read_index(str(self.INDEX_PATH))
                logger.info(f"Loaded FAISS index with {self.index.ntotal} vectors.")
            except Exception as e:
                logger.error(f"Failed to load FAISS index: {e}")
                self._init_index()
        else:
            self._init_index()

        # Load Map
        if self.MAP_PATH.exists():
            try:
                with open(self.MAP_PATH, "rb") as f:
                    self.id_map = pickle.load(f)
                    # Rebuild inverse map
                    self.inverse_map = {v: k for k, v in self.id_map.items()}
            except Exception as e:
                logger.error(f"Failed to load ID map: {e}")
                self.id_map = {}
                self.inverse_map = {}
        else:
            self.id_map = {}
            self.inverse_map = {}

    def _init_index(self):
        # IndexFlatIP = Inner Product. Normalized vectors + Inner Product = Cosine Similarity.
        self.index = faiss.IndexFlatIP(self.DIMENSION)
        logger.info("Initialized new FAISS IndexFlatIP.")

    def add_vectors(self, vectors: np.ndarray, content_ids: List[str]):
        """
        Add vectors to index and update mappings.
        Persists to disk after addition.
        """
        if vectors.shape[0] != len(content_ids):
            raise ValueError("Size mismatch between vectors and content_ids")
            
        start_id = self.index.ntotal
        self.index.add(vectors)
        
        for i, content_id in enumerate(content_ids):
            faiss_id = start_id + i
            self.id_map[faiss_id] = content_id
            self.inverse_map[content_id] = faiss_id
            
        self._save()
        logger.info(f"Added {len(content_ids)} vectors. Total: {self.index.ntotal}")

    def _save(self):
        try:
            faiss.write_index(self.index, str(self.INDEX_PATH))
            with open(self.MAP_PATH, "wb") as f:
                pickle.dump(self.id_map, f)
        except Exception as e:
            logger.error(f"Failed to save FAISS index/map: {e}")
            raise e
            
    def search(self, query_vector: np.ndarray, k: int = 5):
        """
        Search for nearest neighbors.
        Returns: distances, content_ids
        """
        if self.index.ntotal == 0:
            return [], []
            
        # faiss.search expects (n, d)
        if len(query_vector.shape) == 1:
            query_vector = query_vector.reshape(1, -1)
            
        distances, indices = self.index.search(query_vector, k)
        
        # Map indices to content_ids
        result_content_ids = []
        for idx in indices[0]:
            if idx != -1 and idx in self.id_map:
                result_content_ids.append(self.id_map[idx])
            else:
                result_content_ids.append(None)
                
        return distances[0], result_content_ids

    def get_vector(self, content_id: str) -> Optional[np.ndarray]:
        """
        Retrieve vector for a given content_id.
        Returns None if not found.
        """
        if content_id not in self.inverse_map:
            return None
            
        faiss_id = self.inverse_map[content_id]
        try:
            # reconstruct returns the vector at index
            return self.index.reconstruct(faiss_id)
        except Exception as e:
            logger.error(f"Error reconstructing vector for {content_id} (id={faiss_id}): {e}")
            return None

    def get_debug_stats(self) -> Dict:
        """
        Return stats for debug endpoint.
        """
        return {
            "model": "all-MiniLM-L6-v2", # Hardcoded for now as it's the model used by Embedder
            "embedding_dim": self.DIMENSION,
            "total_vectors": self.index.ntotal if self.index else 0,
            "faiss_loaded": self.index is not None
        }
