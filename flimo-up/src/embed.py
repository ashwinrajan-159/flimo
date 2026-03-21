import logging
import time
from .database import get_unembedded_content, mark_embedded
from .embedder import Embedder
from .vector_store import VectorStore

# Configure Logging (if not already by config)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ingestion.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("EmbedScript")

def main():
    logger.info("Starting Embedding Process...")
    
    # Initialize components
    try:
        embedder = Embedder()
        vector_store = VectorStore()
    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        return

    BATCH_SIZE = 32
    total_processed = 0

    while True:
        # 1. Fetch Batch
        rows = get_unembedded_content(limit=BATCH_SIZE)
        if not rows:
            logger.info("No more unembedded content found.")
            break
            
        logger.info(f"Processing batch of {len(rows)} items...")

        content_ids = [r[0] for r in rows]
        texts = [r[1] for r in rows]
        
        try:
            # 2. Generate Embeddings
            t0 = time.time()
            vectors = embedder.embed_texts(texts)
            t1 = time.time()
            logger.debug(f"Embedding generation took {t1 - t0:.2f}s")
            
            # 3. Add to Vector Store
            vector_store.add_vectors(vectors, content_ids)
            
            # 4. Mark as Embedded
            mark_embedded(content_ids)
            
            total_processed += len(rows)
            logger.info(f"Processed {total_processed} items so far.")
            
        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            # If a batch fails, we might want to skip or break. 
            # For this script, we break to avoid infinite loops if it's a persistent error.
            break

    logger.info("Embedding Process Complete.")

if __name__ == "__main__":
    main()
