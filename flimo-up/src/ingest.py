import argparse
import logging
from .database import init_db, upsert_content, get_total_count
from .tmdb_client import TMDBClient
from .youtube_client import YouTubeClient
from .config import TMDB_API_KEY, YOUTUBE_API_KEY

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def ingest_tmdb():
    """Standard ingestion: popular + top_rated (quick, ~600 items)"""
    if not TMDB_API_KEY:
        logger.error("Skipping TMDB ingestion: API Key missing.")
        return

    client = TMDBClient()
    total_new = 0
    
    # Fetch POPULAR movies (10 pages = 200 movies)
    logger.info("Starting TMDB Popular Movie ingestion...")
    for page in range(1, 11):
        movies = client.fetch_popular_movies(page)
        for m in movies:
            try:
                upsert_content(m)
                total_new += 1
            except Exception as e:
                pass
    
    # Fetch TOP RATED movies (5 pages)
    logger.info("Starting TMDB Top Rated Movie ingestion...")
    for page in range(1, 6):
        movies = client.fetch_top_rated_movies(page)
        for m in movies:
            try:
                upsert_content(m)
                total_new += 1
            except Exception as e:
                pass
    
    # Fetch POPULAR series (10 pages)
    logger.info("Starting TMDB Popular Series ingestion...")
    for page in range(1, 11):
        series = client.fetch_popular_series(page)
        for s in series:
            try:
                upsert_content(s)
                total_new += 1
            except Exception as e:
                pass
    
    # Fetch TOP RATED series (5 pages)
    logger.info("Starting TMDB Top Rated Series ingestion...")
    for page in range(1, 6):
        series = client.fetch_top_rated_series(page)
        for s in series:
            try:
                upsert_content(s)
                total_new += 1
            except Exception as e:
                pass
                
    logger.info(f"TMDB Ingestion complete. Processed {total_new} items.")

def ingest_tmdb_discover(max_pages: int = 500):
    """
    Large-scale ingestion using discover endpoint.
    500 pages = 10,000 movies. Takes ~25 minutes due to rate limiting.
    """
    if not TMDB_API_KEY:
        logger.error("Skipping TMDB discover: API Key missing.")
        return

    client = TMDBClient()
    total_new = 0
    
    logger.info(f"Starting TMDB Discover ingestion ({max_pages} pages = ~{max_pages * 20} movies)...")
    logger.info("This will take ~25 minutes. Rate limited to 4 req/sec.")
    
    for page in range(1, max_pages + 1):
        try:
            movies = client.discover_movies(page, sort_by="popularity.desc", vote_count_gte=50)
            for m in movies:
                try:
                    upsert_content(m)
                    total_new += 1
                except Exception:
                    pass
            
            # Progress logging every 100 pages
            if page % 100 == 0:
                logger.info(f"Progress: {page}/{max_pages} pages, {total_new} movies ingested")
        except Exception as e:
            logger.error(f"Error on page {page}: {e}")
            continue
    
    logger.info(f"TMDB Discover complete. Processed {total_new} movies.")

def ingest_youtube():
    if not YOUTUBE_API_KEY:
        logger.error("Skipping YouTube ingestion: API Key missing.")
        return

    client = YouTubeClient()
    queries = ["movie reviews", "tv series analysis", "best movies 2024", "cinema deep dive"]
    total_new = 0
    
    logger.info("Starting YouTube ingestion...")
    for query in queries:
        logger.info(f"Searching YouTube for: '{query}'")
        videos = client.search_videos(query, max_results=20)
        for v in videos:
            try:
                upsert_content(v)
                total_new += 1
            except Exception as e:
                pass
    
    logger.info(f"YouTube Ingestion complete. Processed {total_new} items.")

def ingest_multilingual():
    """Ingest popular movies from non-English languages."""
    if not TMDB_API_KEY:
        logger.error("Skipping Multilingual ingestion: API Key missing.")
        return

    client = TMDBClient()
    total_new = 0
    
    # Selected Languages: Hindi, Korean, Spanish, Japanese, French, Tamil, Telugu, Malayalam, German, Italian, Russian, Portuguese, Chinese
    languages = ['hi', 'ko', 'es', 'ja', 'fr', 'ta', 'te', 'ml', 'de', 'it', 'ru', 'pt', 'zh']
    
    logger.info(f"Starting Multilingual Ingestion for: {languages}")
    
    for lang in languages:
        logger.info(f"Fetching top content for language: {lang}")
        # Fetch 20 pages (400 movies) per language to significantly boost volume
        for page in range(1, 21):
            try:
                movies = client.discover_movies(page, with_original_language=lang)
                for m in movies:
                    try:
                        upsert_content(m)
                        total_new += 1
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Error fetching {lang} page {page}: {e}")
                
    logger.info(f"Multilingual Ingestion complete. Processed {total_new} items.")

def main():
    parser = argparse.ArgumentParser(description="Ingest content from TMDB and YouTube.")
    parser.add_argument("--tmdb", action="store_true", help="Ingest popular/top_rated from TMDB")
    parser.add_argument("--discover", type=int, metavar="PAGES", help="Ingest from TMDB discover (500 pages = 10K movies)")
    parser.add_argument("--youtube", action="store_true", help="Ingest from YouTube")
    parser.add_argument("--multilingual", action="store_true", help="Ingest from multiple languages")
    parser.add_argument("--all", action="store_true", help="Ingest from all sources (standard)")
    
    args = parser.parse_args()
    
    init_db()
    
    if args.discover:
        ingest_tmdb_discover(args.discover)
    elif args.tmdb or args.all:
        ingest_tmdb()
        
    if args.multilingual or args.all:
        ingest_multilingual()
        
    if args.youtube or args.all:
        ingest_youtube()
        
    count = get_total_count()
    logger.info(f"Total content in database: {count}")
    
    # Trigger semantic re-indexing if needed (optional optimization)
    # from .embed import generate_embeddings
    # generate_embeddings()


if __name__ == "__main__":
    main()
