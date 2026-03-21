import sqlite3
import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple
from .models import UnifiedContent

logger = logging.getLogger(__name__)

DB_PATH = Path("data/content.db")

def init_db():
    """Initialize the SQLite database and create tables with indexes."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Enable WAL mode for better concurrency
    cursor.execute("PRAGMA journal_mode=WAL;")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS content (
            content_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            content_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            genres TEXT,  -- JSON list
            language TEXT,
            release_year INTEGER,
            rating REAL,
            popularity REAL,
            thumbnail_url TEXT,
            source_url TEXT,
            created_at TIMESTAMP,
            embedding_text TEXT NOT NULL,
            embedding_ready BOOLEAN DEFAULT 0
        )
    """)
    
    # Indexes for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_content_type ON content(content_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_release_year ON content(release_year)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rating ON content(rating)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_popularity ON content(popularity)")
    
    # MIGRATION: Ensure embedding_ready exists (for existing DBs)
    try:
        cursor.execute("ALTER TABLE content ADD COLUMN embedding_ready BOOLEAN DEFAULT 0")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_embedding_ready ON content(embedding_ready)")
    except Exception:
        # Ignore error if column already exists
        pass

    # STEP 5: Community Features Tables
    
    # 1. Users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 2. Likes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            user_id TEXT,
            content_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, content_id),
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(content_id) REFERENCES content(content_id)
        )
    """)
    
    # 3. Reviews
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            review_id TEXT PRIMARY KEY,
            user_id TEXT,
            content_id TEXT,
            rating INTEGER,
            review_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(content_id) REFERENCES content(content_id)
        )
    """)
    
    # 4. Watchlists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlists (
            watchlist_id TEXT PRIMARY KEY,
            user_id TEXT,
            name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    """)
    
    # 5. Watchlist Items
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist_items (
            watchlist_id TEXT,
            content_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (watchlist_id, content_id),
            FOREIGN KEY(watchlist_id) REFERENCES watchlists(watchlist_id),
            FOREIGN KEY(content_id) REFERENCES content(content_id)
        )
    """)
    
    # 6. User Profiles (extended user info)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id TEXT PRIMARY KEY,
            display_name TEXT,
            avatar_color TEXT DEFAULT '#3B82F6',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    """)
    
    # 7. Global Chat Messages
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            message_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_messages(created_at DESC)")
    
    # 8. Content Comments (per movie/series)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS content_comments (
            comment_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            content_id TEXT NOT NULL,
            comment_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(content_id) REFERENCES content(content_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_content ON content_comments(content_id, created_at DESC)")
    
    # 9. Watched History (Personalization)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watched_history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            content_id TEXT NOT NULL,
            progress REAL DEFAULT 0,
            watched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(content_id) REFERENCES content(content_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_user ON watched_history(user_id, watched_at DESC)")
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully.")

def upsert_content(content: UnifiedContent):
    """Insert or update content item."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    try:
        # Note: We preserve embedding_ready if it exists, or typically it stays 0 on new insert.
        # On update, if specific fields change, we MIGHT want to reset embedding_ready to 0.
        # For simplicity in this step, we assume updates might invalidate embeddings if text changes.
        # But `upsert_content` replaces `embedding_text`. So we should set `embedding_ready=0`.
        
        cursor.execute("""
            INSERT INTO content (
                content_id, source_id, content_type, title, description, genres,
                language, release_year, rating, popularity, thumbnail_url,
                source_url, created_at, embedding_text, embedding_ready
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(content_id) DO UPDATE SET
                title=excluded.title,
                description=excluded.description,
                genres=excluded.genres,
                rating=excluded.rating,
                popularity=excluded.popularity,
                embedding_text=excluded.embedding_text,
                release_year=excluded.release_year,
                embedding_ready=0  -- Reset embedding status on update
        """, (
            content.content_id,
            content.source_id,
            content.content_type.value,
            content.title,
            content.description,
            json.dumps(content.genres),
            content.language,
            content.release_year,
            content.rating,
            content.popularity,
            content.thumbnail_url,
            content.source_url,
            content.created_at,
            content.embedding_text
        ))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to upsert content {content.content_id}: {e}")
        raise e
    finally:
        conn.close()

def get_unembedded_content(limit: int = 32) -> List[tuple]:
    """Fetch rows where embedding_ready is 0."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    # Fetch content_id and embedding_text
    cursor.execute("SELECT content_id, embedding_text FROM content WHERE embedding_ready = 0 LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def mark_embedded(content_ids: List[str]):
    """Mark specified content_ids as embedded."""
    if not content_ids:
        return
        
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    placeholders = ",".join(["?"] * len(content_ids))
    try:
        cursor.execute(f"UPDATE content SET embedding_ready = 1 WHERE content_id IN ({placeholders})", content_ids)
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to mark content as embedded: {e}")
    finally:
        conn.close()

def get_total_count() -> int:
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM content")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_content_by_ids(content_ids: List[str]) -> List[UnifiedContent]:
    """Fetch full UnifiedContent objects for a list of IDs."""
    if not content_ids:
        return []
        
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    placeholders = ",".join(["?"] * len(content_ids))
    # Note: We select all fields to reconstruct UnifiedContent
    query = f"""
        SELECT content_id, source_id, content_type, title, description, genres,
               language, release_year, rating, popularity, thumbnail_url,
               source_url, created_at, embedding_text
        FROM content WHERE content_id IN ({placeholders})
    """
    
    cursor.execute(query, content_ids)
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    from .models import ContentType # Import here to avoid circular ref issues if any
    
    for row in rows:
        try:
            # Row mapping
            # 0:content_id, 1:source_id, 2:content_type, 3:title, 4:description, 5:genres(json)
            # 6:language, 7:release_year, 8:rating, 9:popularity, 10:thumb, 11:source, 12:created, 13:text
            
            c = UnifiedContent(
                content_id=row[0],
                source_id=row[1],
                content_type=ContentType(row[2]),
                title=row[3],
                description=row[4],
                genres=json.loads(row[5]) if row[5] else [],
                language=row[6],
                release_year=row[7],
                rating=row[8],
                popularity=row[9],
                thumbnail_url=row[10],
                source_url=row[11],
                # created_at handled by pydantic default or parse if needed. 
                # row[12] is string or timestamp. Pydantic might parse string.
                embedding_text=row[13]
            )
            results.append(c)
        except Exception as e:
            logger.error(f"Failed to parse content row {row[0]}: {e}")
            
    # Return in order of input IDs? 
    # FAISS returns order by relevance. SQL returns arbitrary order.
    # We should reorder 'results' to match 'content_ids' order if we want to preserve VectorStore relevance?
    # BUT, SearchService will pass these to Ranker along with similarity scores. 
    # So we need to map content_id -> Content and return a list aligned with input IDs?
    # OR, we return a map or lookup.
    
    # Better: return list mapped to input order provided we have similarity scores separately.
    # Actually, SearchService will get (distance, id) pairs.
    # We can just return the list and let SearchService match them up.
    
    return results

def get_trending(page: int = 1, limit: int = 20, content_type: Optional[str] = None) -> List[UnifiedContent]:
    """Get trending content (Recent & Popular)."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    import datetime
    current_year = datetime.datetime.now().year
    min_year = current_year - 2
    offset = (page - 1) * limit
    
    query = """
        SELECT content_id, source_id, content_type, title, description, genres,
               language, release_year, rating, popularity, thumbnail_url,
               source_url, created_at, embedding_text
        FROM content
        WHERE release_year >= ?
          AND rating >= 7.0
          AND popularity >= 10.0
    """
    params = [min_year]
    
    if content_type:
        query += " AND content_type = ?"
        params.append(content_type)
        
    query += " ORDER BY popularity DESC, content_id ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return _rows_to_content(rows)

def get_latest(page: int = 1, limit: int = 20, content_type: Optional[str] = None) -> List[UnifiedContent]:
    """Get latest content."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    offset = (page - 1) * limit
    
    query = """
        SELECT content_id, source_id, content_type, title, description, genres,
               language, release_year, rating, popularity, thumbnail_url,
               source_url, created_at, embedding_text
        FROM content
        WHERE rating >= 7.0
          AND popularity >= 5.0
    """
    params = []
    
    if content_type:
        query += " AND content_type = ?"
        params.append(content_type)
        
    query += " ORDER BY release_year DESC, popularity DESC, content_id ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return _rows_to_content(rows)

def get_top_rated(page: int = 1, limit: int = 20, content_type: Optional[str] = None) -> List[UnifiedContent]:
    """Get top rated content (min rating 7)."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    offset = (page - 1) * limit
    
    query = """
        SELECT content_id, source_id, content_type, title, description, genres,
               language, release_year, rating, popularity, thumbnail_url,
               source_url, created_at, embedding_text
        FROM content
        WHERE rating >= 7.0
          AND popularity >= 15.0
          AND release_year < 2024
    """
    params = []
    
    if content_type:
        query += " AND content_type = ?"
        params.append(content_type)
        
    query += " ORDER BY rating DESC, popularity DESC, content_id ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return _rows_to_content(rows)

def browse_all(
    page: int = 1,
    page_size: int = 20,
    content_type: Optional[str] = None,
    genre: Optional[str] = None,
    language: Optional[str] = None,
    min_year: Optional[int] = None,
    max_year: Optional[int] = None,
    min_rating: Optional[float] = None
) -> Tuple[List[UnifiedContent], int]:
    """Browse content with filters and pagination. Returns (results, total_count)."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    params = []
    conditions = ["1=1"] # Default true condition
    
    if content_type:
        conditions.append("content_type = ?")
        params.append(content_type)
    if genre:
        conditions.append("genres LIKE ?")
        params.append(f"%{genre}%")
    if language:
        conditions.append("language = ?")
        params.append(language)
    if min_year:
        conditions.append("release_year >= ?")
        params.append(min_year)
    if max_year:
        conditions.append("release_year <= ?")
        params.append(max_year)
    if min_rating:
        conditions.append("rating >= ?")
        params.append(min_rating)
        
    where_clause = " AND ".join(conditions)
    offset = (page - 1) * page_size
    
    # Get Total Count
    count_query = f"SELECT COUNT(*) FROM content WHERE {where_clause}"
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]
    
    # Get Items
    query = f"""
        SELECT content_id, source_id, content_type, title, description, genres,
               language, release_year, rating, popularity, thumbnail_url,
               source_url, created_at, embedding_text
        FROM content
        WHERE {where_clause}
        ORDER BY popularity DESC, content_id ASC -- Deterministic sort
        LIMIT ? OFFSET ?
    """
    cursor.execute(query, params + [page_size, offset])
    rows = cursor.fetchall()
    conn.close()
    
    return _rows_to_content(rows), total

def _rows_to_content(rows: List[tuple]) -> List[UnifiedContent]:
    """Helper to convert DB rows to matching objects."""
    results = []
    from .models import ContentType
    
    for row in rows:
        try:
            c = UnifiedContent(
                content_id=row[0],
                source_id=row[1],
                content_type=ContentType(row[2]),
                title=row[3],
                description=row[4],
                genres=json.loads(row[5]) if row[5] else [],
                language=row[6],
                release_year=row[7],
                rating=row[8],
                popularity=row[9],
                thumbnail_url=row[10],
                source_url=row[11],
                embedding_text=row[13]
            )
            results.append(c)
        except Exception as e:
            logger.error(f"Failed to parse content row {row[0]}: {e}")
            
    return results

# ===========================================
# HYBRID SEARCH FUNCTIONS
# ===========================================

def search_by_title(query: str, limit: int = 20) -> List[UnifiedContent]:
    """
    MODE 1: Exact/fuzzy title match via SQL LIKE.
    Used when query looks like a title (short, specific).
    QUALITY GATE: rating >= 7.0 (per master prompt)
    """
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Case-insensitive title search
    search_term = f"%{query.lower()}%"
    
    # Sort by: 1) content type (movies first), 2) rating, 3) popularity
    # HARD QUALITY GATE: rating >= 7.0 (per master prompt)
    query_sql = """
        SELECT content_id, source_id, content_type, title, description, genres,
               language, release_year, rating, popularity, thumbnail_url,
               source_url, created_at, embedding_text
        FROM content
        WHERE LOWER(title) LIKE ?
          AND rating >= 7.0
        ORDER BY 
            CASE content_type 
                WHEN 'movie' THEN 1 
                WHEN 'series' THEN 2 
                ELSE 3 
            END,
            rating DESC, 
            popularity DESC
        LIMIT ?
    """
    cursor.execute(query_sql, (search_term, limit))
    rows = cursor.fetchall()
    conn.close()
    
    logger.info(f"[HYBRID] Title search for '{query}' returned {len(rows)} results")
    return _rows_to_content(rows)

def search_by_genre(genre: str, limit: int = 50) -> List[UnifiedContent]:
    """
    MODE 2: Genre browse with popularity sort.
    Used when query is a pure genre keyword.
    QUALITY GATE: rating >= 7.0 (per master prompt)
    """
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Case-insensitive genre search in JSON array
    search_term = f"%{genre}%"
    
    # HARD QUALITY GATE: rating >= 7.0 (per master prompt)
    query_sql = """
        SELECT content_id, source_id, content_type, title, description, genres,
               language, release_year, rating, popularity, thumbnail_url,
               source_url, created_at, embedding_text
        FROM content
        WHERE LOWER(genres) LIKE LOWER(?)
          AND rating >= 7.0
        ORDER BY popularity DESC
        LIMIT ?
    """
    cursor.execute(query_sql, (search_term, limit))
    rows = cursor.fetchall()
    conn.close()
    
    logger.info(f"[HYBRID] Genre browse for '{genre}' returned {len(rows)} results")
    return _rows_to_content(rows)

def search_by_intent(tags: List[str], quality_threshold: float = 7.0, limit: int = 20) -> List[UnifiedContent]:
    """
    LAYER 3+4: Intent-aware search with quality gate.
    Searches for tags in TITLE ONLY (not description) for precision.
    """
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Build OR conditions for each tag - TITLE ONLY for precision
    conditions = []
    params = []
    for tag in tags:
        conditions.append("LOWER(title) LIKE ?")
        params.append(f"%{tag.lower()}%")
    
    where_clause = " OR ".join(conditions) if conditions else "1=1"
    
    # Quality gate + sorting by rating then popularity
    # Allow ALL content types (movies, series, animation) as long as title matches
    query_sql = f"""
        SELECT content_id, source_id, content_type, title, description, genres,
               language, release_year, rating, popularity, thumbnail_url,
               source_url, created_at, embedding_text
        FROM content
        WHERE ({where_clause})
          AND rating >= ?
        ORDER BY 
            rating DESC,
            popularity DESC
        LIMIT ?
    """
    params.extend([quality_threshold, limit])
    
    cursor.execute(query_sql, params)
    rows = cursor.fetchall()
    conn.close()
    
    logger.info(f"[INTENT] Search for tags {tags} (quality>={quality_threshold}) returned {len(rows)} results")
    return _rows_to_content(rows)


# MOOD → Genre mapping for filtering
MOOD_GENRE_MAP = {
    "happy": ["adventure", "comedy", "family", "animation"],
    "dark": ["horror", "thriller", "crime", "mystery"],
    "thoughtful": ["drama", "mystery", "documentary"],
    "epic": ["action", "adventure", "science fiction", "fantasy"],
    "emotional": ["drama", "romance"]
}


def discover_content(mode: str = "popular", mood: str = None, genres: list = None,
                     query: str = None, quality_threshold: float = 7.0, limit: int = 20) -> List[UnifiedContent]:
    """
    Discover content by mode (trending/popular/latest) with mood and genre filters.
    Quality gate: rating >= 7.0
    YouTube excluded.
    """
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Build WHERE conditions
    conditions = ["content_type IN ('movie', 'series')", f"rating >= {quality_threshold}"]
    params = []
    
    # Mood filter → hard genre gate
    if mood and mood.lower() in MOOD_GENRE_MAP:
        mood_genres = MOOD_GENRE_MAP[mood.lower()]
        genre_conditions = []
        for g in mood_genres:
            genre_conditions.append("LOWER(genres) LIKE ?")
            params.append(f"%{g.lower()}%")
        if genre_conditions:
            conditions.append(f"({' OR '.join(genre_conditions)})")
    
    # User-selected genre filter (hard gate)
    if genres:
        genre_conditions = []
        for g in genres:
            genre_conditions.append("LOWER(genres) LIKE ?")
            params.append(f"%{g.lower()}%")
        if genre_conditions:
            conditions.append(f"({' OR '.join(genre_conditions)})")

    # Full text query filter (Multi-word flexible search)
    if query:
        stop_words = {"movie", "movies", "film", "films", "with", "show", "shows", "series", "about", "like", "recommend", "me", "a", "an", "the"}
        words = query.lower().split()
        for word in words:
            if len(word) < 3 or word in stop_words: continue 
            search_term = f"%{word}%"
            conditions.append("(LOWER(title) LIKE ? OR LOWER(description) LIKE ?)")
            params.extend([search_term, search_term])
    
    where_clause = " AND ".join(conditions)
    
    # Order by based on mode
    if mode == "trending":
        order_by = "popularity DESC, release_year DESC"
    elif mode == "latest":
        order_by = "release_year DESC, rating DESC"
    else:  # popular
        order_by = "popularity DESC, rating DESC"
    
    query_sql = f"""
        SELECT content_id, source_id, content_type, title, description, genres,
               language, release_year, rating, popularity, thumbnail_url,
               source_url, created_at, embedding_text
        FROM content
        WHERE {where_clause}
        ORDER BY {order_by}
        LIMIT ?
    """
    params.append(limit)
    
    cursor.execute(query_sql, params)
    rows = cursor.fetchall()
    conn.close()
    
    
    logger.info(f"[DISCOVER] mode={mode}, mood={mood}, genres={genres}, query={query} returned {len(rows)} results")
    return _rows_to_content(rows)

