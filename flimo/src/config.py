import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ingestion.log"),
        logging.StreamHandler()
    ]
)

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

if not TMDB_API_KEY:
    logging.warning("TMDB_API_KEY is missing in environment variables.")

if not YOUTUBE_API_KEY:
    logging.warning("YOUTUBE_API_KEY is missing in environment variables.")

# Debug Mode
DEBUG_MODE = True
