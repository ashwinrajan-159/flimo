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
        logging.FileHandler("ingestion.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

if not TMDB_API_KEY:
    logging.warning("TMDB_API_KEY is missing in environment variables.")

if not YOUTUBE_API_KEY:
    logging.warning("YOUTUBE_API_KEY is missing in environment variables.")

# --- AWS Cognito Configuration ---
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID", "")
COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID", "")
COGNITO_CLIENT_SECRET = os.getenv("COGNITO_CLIENT_SECRET", "")
COGNITO_DOMAIN = os.getenv("COGNITO_DOMAIN", "")
COGNITO_REDIRECT_URI = os.getenv("COGNITO_REDIRECT_URI", "http://localhost:8000/auth/callback")
COGNITO_REGION = os.getenv("COGNITO_REGION", "us-east-1")

def is_cognito_configured() -> bool:
    """Check if Cognito credentials are properly set (not placeholders)."""
    return bool(
        COGNITO_USER_POOL_ID
        and COGNITO_CLIENT_ID
        and "XXXXXXXXX" not in COGNITO_USER_POOL_ID
        and "YOUR_" not in COGNITO_CLIENT_ID
    )

# Debug Mode
DEBUG_MODE = True
