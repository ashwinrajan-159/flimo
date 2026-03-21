from typing import List, Optional, Tuple
import logging
import numpy as np
from .schemas import SearchRequest, SearchResultItem
from .prompt_builder import PromptBuilder
from .embedder import Embedder
from .vector_store import VectorStore
from .database import get_content_by_ids, search_by_title, search_by_genre, search_by_intent
from .ranker import Ranker
from .personalization_service import PersonalizationService
from .intent_resolver import IntentResolver
from .prompt_parser import PromptParser

logger = logging.getLogger(__name__)

# Known genres for query classification
KNOWN_GENRES = {
    "comedy", "thriller", "romance", "horror", "action", "drama", 
    "sci-fi", "scifi", "animation", "documentary", "crime", "mystery",
    "adventure", "fantasy", "family", "war", "history", "biography",
    "musical", "western", "sport"
}

class SearchService:
    # ===========================================
    # STRICT AND LOGIC: GATE CONFIGURATIONS
    # All gates are applied BEFORE ranking
    # ===========================================
    
    # MOOD GATES: Mood filtering with allowed/forbidden genres
    # Content must have at least one ALLOWED genre AND zero FORBIDDEN genres
    MOOD_GATES = {
        "happy": {
            "allowed": ["comedy", "family", "animation", "adventure", "science fiction", "fantasy"],
            "forbidden": ["horror", "thriller", "war", "crime"]
        },
        "dark": {
            "allowed": ["horror", "thriller", "crime", "mystery"],
            "forbidden": ["comedy", "family", "animation", "romance"]
        },
        "epic": {
            "allowed": ["action", "adventure", "science fiction", "fantasy", "war"],
            "forbidden": ["comedy", "romance", "family"]
        },
        "emotional": {
            "allowed": ["drama", "romance"],
            "forbidden": ["comedy", "action", "horror", "thriller"]
        },
        "sad": {
            "allowed": ["drama", "romance"],
            "forbidden": ["comedy", "action", "horror", "thriller", "animation"]
        },
        "thoughtful": {
            "allowed": ["drama", "mystery", "documentary", "biography"],
            "forbidden": ["action", "horror", "comedy"]
        },
        "romantic": {
            "allowed": ["romance", "drama"],
            "forbidden": ["horror", "war", "action", "thriller"]
        },
        "inspiring": {
            "allowed": ["biography", "sports", "drama", "documentary"],
            "forbidden": ["horror", "thriller", "crime"]
        },
        "chill": {
            "allowed": ["documentary", "family", "animation", "comedy"],
            "forbidden": ["thriller", "action", "horror", "war"]
        }
    }
    
    # QUALITY GATE: Hard minimum rating (6.5 for more results)
    QUALITY_GATE = 6.5
    
    # Story archetype keywords for filtering
    STORY_KEYWORDS = {
        "family": ["father", "mother", "son", "daughter", "parent", "child", "family", "dad", "mom"],
        "journey": ["journey", "search", "searching", "looking for", "find", "travel", "quest"],
        "loss": ["lost", "missing", "death", "dies", "grief"],
        "revenge": ["revenge", "vengeance", "payback", "kill"],
        "redemption": ["redemption", "forgiveness", "second chance"],
        "survival": ["survive", "survival", "escape", "trapped"]
    }
    
    # ===========================================
    # ANTI-GRAVITY GATES (Strict AND Logic)
    # ALL gates must pass - NO averaging, NO soft similarity
    # ===========================================
    
    # Mood gate: Tone validation (happy = light/comedic, NOT serious/epic)
    ANTIGRAVITY_MOOD = {
        "happy": {
            "required_tones": ["comedy", "family", "animation"],
            "allowed_tones": ["adventure", "fantasy"],  # Can combine with these
            "forbidden_tones": ["horror", "thriller", "drama", "war", "crime", "mystery"],
            "tone_keywords": ["fun", "funny", "hilarious", "heartwarming", "charming", "delightful", "whimsical"],
            "serious_markers": ["thought-provoking", "philosophical", "intense", "dark", "gritty", 
                               "emotional", "tragic", "devastating", "haunting", "brutal", "epic", "profound"]
        },
        "dark": {
            "required_tones": ["horror", "thriller", "crime"],
            "forbidden_tones": ["comedy", "family", "animation", "romance"],
            "tone_keywords": ["dark", "gritty", "intense", "psychological", "disturbing"]
        }
    }
    
    # Entity gate: Subject must be CENTRAL to story
    ANTIGRAVITY_ENTITY = {
        "space": {
            "core_keywords": ["space", "universe", "galaxy", "cosmos", "astronaut", "orbit", "mars", "moon"],
            "required_genres": ["science fiction", "documentary"],
            "forbidden_genres": ["fantasy", "musical", "romance"], # No "Sailor Moon" (Fantasy) or "Under Same Moon" (Romance)
            "importance_check": False
        },
        "alien": {
            "core_keywords": ["alien", "extraterrestrial", "aliens", "creature", "species", "xenomorph"],
            "setting_keywords": ["outer space", "spacecraft", "spaceship", "starship", "galaxy", "planet"],
            "background_titles": ["edge of tomorrow", "pacific rim", "independence day"],
            "required_genres": ["science fiction", "horror"],
            "forbidden_genres": ["romance", "musical", "family"],
            "importance_check": True
        },
        "robot": {
            "core_keywords": ["robot", "android", "cyborg", "droid", "automaton", "artificial intelligence", "ai"],
            "required_genres": ["science fiction", "crime", "family", "animation"],
            "forbidden_genres": ["history", "western", "fantasy"],
            "importance_check": True
        },
        "magic": {
            "core_keywords": ["magic", "wizard", "witch", "spell", "magical", "sorcerer"],
            "required_genres": ["fantasy", "family", "animation"],
            "forbidden_genres": ["science fiction", "history", "documentary", "crime"], # No "Magic Mike"
            "importance_check": True
        },
        "war": {
            "core_keywords": ["war", "soldier", "battle", "army", "military", "combat", "ww2"],
            "required_genres": ["war", "history", "action", "drama"],
            "forbidden_genres": ["comedy", "musical", "family", "fantasy"],
            "importance_check": True
        },
        "love": {
            "core_keywords": ["love", "romance", "relationship", "dating", "marriage"],
            "required_genres": ["romance", "drama", "comedy"],
            "forbidden_genres": ["horror", "thriller", "science fiction", "action"],
            "importance_check": False
        }
    }
    
    # Plot gate: Plot type must be PRIMARY driver
    ANTIGRAVITY_PLOT = {
        "adventure": {
            "required_genres": ["adventure"],
            "supporting_genres": ["action", "fantasy", "science fiction"],
            "plot_keywords": ["journey", "quest", "mission", "rescue", "escape", "voyage", "expedition", "discover"],
            "non_adventure_markers": ["courtroom", "political", "romance-focused", "philosophical debate"]
        }
    }
    
    def __init__(self):
        self.embedder = Embedder()
        self.vector_store = VectorStore()
        self.ranker = Ranker()
        self.prompt_builder = PromptBuilder()
        self.personalization_service = PersonalizationService(self.vector_store)
        self.intent_resolver = IntentResolver()
        self.prompt_parser = PromptParser()  # 6-stage prompt understanding
        self.last_search_mode = "semantic"
        self.last_detected_concepts = []
        self.last_detected_intent = None
        self.last_parsed_intent = None
        # Stage tracking for debug
        self.last_stage_counts = {"sbert": 0, "theme_gate": 0, "mood_gate": 0, "genre_gate": 0, "quality_gate": 0, "final": 0}
    
    # ===========================================
    # GATE FUNCTIONS - Applied BEFORE ranking
    # ===========================================
    
    def _passes_quality_gate(self, content) -> bool:
        """
        QUALITY GATE: Rating must be >= 7.0
        Returns False if movie should be DISCARDED
        """
        if content.rating is None:
            return False  # No rating = can't verify quality
        return content.rating >= self.QUALITY_GATE
    
    def _passes_mood_gate(self, content, mood: str) -> bool:
        """
        MOOD GATE: Content must have allowed genre AND no forbidden genres
        Returns False if movie should be DISCARDED
        """
        if not mood:
            return True  # No mood filter = pass
        
        mood_lower = mood.lower()
        if mood_lower not in self.MOOD_GATES:
            return True  # Unknown mood = pass
        
        gate = self.MOOD_GATES[mood_lower]
        content_genres_lower = [g.lower() for g in (content.genres or [])]
        
        # Check FORBIDDEN genres first (hard fail)
        for forbidden in gate.get("forbidden", []):
            if any(forbidden in g for g in content_genres_lower):
                return False  # HAS forbidden genre → DISCARD
        
        # Check ALLOWED genres (must have at least one)
        for allowed in gate.get("allowed", []):
            if any(allowed in g for g in content_genres_lower):
                return True  # HAS allowed genre → PASS
        
        return False  # No allowed genre found → DISCARD
    
    def _passes_genre_gate(self, content, genres: list) -> bool:
        """
        GENRE GATE: Content must have at least one user-selected genre
        Returns False if movie should be DISCARDED
        """
        if not genres or len(genres) == 0:
            return True  # No genre filter = pass
        
        content_genres_lower = [g.lower() for g in (content.genres or [])]
        
        # Must match at least one selected genre
        for selected in genres:
            if any(selected.lower() in g for g in content_genres_lower):
                return True
        
        return False  # No matching genre → DISCARD
    
    def _passes_all_gates(self, content, mood: str = None, genres: list = None) -> dict:
        """
        Run ALL gates and return detailed result for logging.
        Returns {"passed": bool, "failed_gate": str or None}
        """
        # Gate 1: Quality
        if not self._passes_quality_gate(content):
            return {"passed": False, "failed_gate": "quality", "rating": content.rating}
        
        # Gate 2: Mood
        if not self._passes_mood_gate(content, mood):
            return {"passed": False, "failed_gate": "mood", "mood": mood, "genres": content.genres}
        
        # Gate 3: Genre
        if not self._passes_genre_gate(content, genres):
            return {"passed": False, "failed_gate": "genre", "required": genres, "actual": content.genres}
        
        return {"passed": True, "failed_gate": None}
    
    # ===========================================
    # ANTI-GRAVITY GATE FUNCTIONS (Hard AND Logic)
    # ===========================================
    
    def _antigravity_parse_query(self, query: str) -> dict:
        """
        Parse query to extract mood, entities, and plot types for Anti-Gravity filtering.
        Returns: {"mood": str, "entities": [], "plot_types": []}
        """
        q = query.lower()
        result = {"mood": None, "entities": [], "plot_types": []}
        
        # Detect mood
        if any(kw in q for kw in ["happy", "fun", "funny", "comedy", "light", "cheerful"]):
            result["mood"] = "happy"
        elif any(kw in q for kw in ["dark", "scary", "horror", "thriller", "intense"]):
            result["mood"] = "dark"
        
        # Detect entities
        if any(kw in q for kw in ["alien", "aliens", "extraterrestrial"]):
            result["entities"].append("alien")
        if any(kw in q for kw in ["robot", "robots", "android", "cyborg", "ai"]):
            result["entities"].append("robot")
            
        # New Ambiguous Entities
        if any(kw in q for kw in ["space", "universe", "galaxy", "cosmos", "orbit"]):
            result["entities"].append("space")
        if any(kw in q for kw in ["magic", "wizard", "witch", "spell"]):
             result["entities"].append("magic")
        if any(kw in q for kw in ["war", "battle", "soldier", "army"]):
             result["entities"].append("war")
        if any(kw in q for kw in ["love", "romance", "dating"]):
             result["entities"].append("love")
        
        # Detect plot types
        if any(kw in q for kw in ["adventure", "quest", "journey", "mission"]):
            result["plot_types"].append("adventure")
        
        return result
    
    def _antigravity_mood_gate(self, content, mood: str) -> tuple:
        """
        ANTI-GRAVITY MOOD GATE: Validates tone is genuinely happy/light.
        Rejects serious/epic/philosophical even if genre seems OK.
        Returns: (passed: bool, reason: str)
        """
        if not mood or mood.lower() not in self.ANTIGRAVITY_MOOD:
            return (True, "no mood filter")
        
        config = self.ANTIGRAVITY_MOOD[mood.lower()]
        genres = [g.lower() for g in (content.genres or [])]
        desc = (content.description or "").lower()
        title = content.title.lower()
        
        # CHECK 1: Forbidden tones (INSTANT REJECT)
        for forbidden in config.get("forbidden_tones", []):
            if any(forbidden in g for g in genres):
                return (False, f"has forbidden genre: {forbidden}")
        
        # CHECK 2: Serious markers in description (REJECT for happy mood)
        if mood.lower() == "happy":
            for marker in config.get("serious_markers", []):
                if marker in desc:
                    return (False, f"serious marker found: {marker}")
        
        # CHECK 3: Must have at least one required OR allowed tone genre
        required = config.get("required_tones", [])
        allowed = config.get("allowed_tones", [])
        all_valid = required + allowed
        
        has_valid_genre = any(
            any(valid in g for g in genres)
            for valid in all_valid
        )
        
        # CHECK 4: Or has tone keywords in description
        has_tone_keyword = any(kw in desc for kw in config.get("tone_keywords", []))
        
        if has_valid_genre or has_tone_keyword:
            return (True, "mood validated")
        
        return (False, "no matching mood genre or keyword")
    
    def _antigravity_entity_gate(self, content, entity: str) -> tuple:
        """
        ANTI-GRAVITY ENTITY GATE: Entity must be CENTRAL to story.
        Rejects movies where entity is background/symbolic.
        Returns: (passed: bool, reason: str)
        """
        if not entity or entity.lower() not in self.ANTIGRAVITY_ENTITY:
            return (True, "no entity filter")
        
        config = self.ANTIGRAVITY_ENTITY[entity.lower()]
        desc = (content.description or "").lower()
        title = content.title.lower()
        
        # CHECK 1: Blacklisted titles (known background entity movies)
        for blocked_title in config.get("background_titles", []):
            if blocked_title in title:
                return (False, f"entity is background in: {blocked_title}")
        
        # CHECK 2: Forbidden Genres (Strict Reject)
        # Exception: Only forbid if movie lacks basic relevance? 
        # Actually safer to be strict for high precision.
        forbidden_genres = config.get("forbidden_genres", [])
        genres_lower = [g.lower() for g in (content.genres or [])]
        
        for fg in forbidden_genres:
            if any(fg in g for g in genres_lower):
                 return (False, f"has forbidden genre for {entity}: {fg}")

        # CHECK 3: Required Genres (Must have at least one)
        required_genres = config.get("required_genres", [])
        if required_genres:
            has_req = any(any(req in g for g in genres_lower) for req in required_genres)
            if not has_req:
                return (False, f"missing required genre for {entity}: {required_genres}")

        # CHECK 4: Entity must be present somewhere
        core_keywords = config.get("core_keywords", [])
        setting_keywords = config.get("setting_keywords", [])
        all_keywords = core_keywords + setting_keywords
        
        has_entity = any(kw in desc or kw in title for kw in all_keywords)
        if not has_entity:
            return (False, f"entity '{entity}' not mentioned")
        
        # CHECK 5: Importance check - entity should be in title OR first 150 chars
        if config.get("importance_check", False):
            first_150 = desc[:150]
            is_central = any(kw in title for kw in core_keywords) or \
                        any(kw in first_150 for kw in core_keywords)
            if not is_central:
                return (False, f"entity '{entity}' not central to story")
        
        return (True, "entity is central")
    
    def _antigravity_plot_gate(self, content, plot_type: str) -> tuple:
        """
        ANTI-GRAVITY PLOT GATE: Plot type must be PRIMARY driver.
        Returns: (passed: bool, reason: str)
        """
        if not plot_type or plot_type.lower() not in self.ANTIGRAVITY_PLOT:
            return (True, "no plot filter")
        
        config = self.ANTIGRAVITY_PLOT[plot_type.lower()]
        genres = [g.lower() for g in (content.genres or [])]
        desc = (content.description or "").lower()
        
        # CHECK 1: Non-matching markers (REJECT)
        for marker in config.get("non_adventure_markers", []):
            if marker in desc:
                return (False, f"has non-{plot_type} marker: {marker}")
        
        # CHECK 2: Must have required genre
        required = config.get("required_genres", [])
        has_required = any(
            any(req in g for g in genres)
            for req in required
        )
        
        # CHECK 3: Or has supporting genre + plot keywords
        supporting = config.get("supporting_genres", [])
        has_supporting = any(
            any(sup in g for g in genres)
            for sup in supporting
        )
        has_plot_keyword = any(kw in desc for kw in config.get("plot_keywords", []))
        
        if has_required or (has_supporting and has_plot_keyword):
            return (True, "plot validated")
        
        return (False, f"'{plot_type}' is not primary driver")
    
    def _passes_antigravity_filter(self, content, query: str) -> dict:
        """
        MASTER ANTI-GRAVITY FILTER: Apply ALL gates with strict AND logic.
        A movie must pass EVERY gate to be included.
        Returns: {"passed": bool, "failed_gate": str, "reason": str}
        """
        # Parse query for mood, entities, plot types
        parsed = self._antigravity_parse_query(query)
        
        # GATE 1: Mood (happy/dark tone validation)
        if parsed["mood"]:
            passed, reason = self._antigravity_mood_gate(content, parsed["mood"])
            if not passed:
                return {"passed": False, "failed_gate": "mood", "reason": reason, "title": content.title}
        
        # GATE 2: Entity (all detected entities must be central)
        for entity in parsed["entities"]:
            passed, reason = self._antigravity_entity_gate(content, entity)
            if not passed:
                return {"passed": False, "failed_gate": "entity", "reason": reason, "title": content.title}
        
        # GATE 3: Plot (all detected plot types must be primary)
        for plot_type in parsed["plot_types"]:
            passed, reason = self._antigravity_plot_gate(content, plot_type)
            if not passed:
                return {"passed": False, "failed_gate": "plot", "reason": reason, "title": content.title}
        
        return {"passed": True, "failed_gate": None, "reason": "all gates passed"}
    
    def _matches_story_intent(self, content, parsed_themes: list) -> bool:
        """
        STAGE 2: Story intent validation.
        Movie description must contain keywords from the detected themes.
        """
        if not parsed_themes:
            return True  # No story filter if no themes
        
        desc = (content.description or "").lower()
        title = content.title.lower()
        
        # Check each theme for keyword matches
        for theme in parsed_themes:
            if theme in self.STORY_KEYWORDS:
                keywords = self.STORY_KEYWORDS[theme]
                if any(kw in desc or kw in title for kw in keywords):
                    return True
        
        return False
    
    def _story_match_strength(self, content, parsed_themes: list) -> float:
        """Calculate how strongly a movie matches the story intent (0.0-1.0)"""
        if not parsed_themes:
            return 1.0
        
        desc = (content.description or "").lower()
        matches = 0
        total_themes = len(parsed_themes)
        
        for theme in parsed_themes:
            if theme in self.STORY_KEYWORDS:
                keywords = self.STORY_KEYWORDS[theme]
                if any(kw in desc for kw in keywords):
                    matches += 1
        
        return matches / max(total_themes, 1)
    
    def _compute_theme_score(self, content, term: str, expansion_data: dict) -> float:
        """
        Compute multi-axis theme score for ambiguous terms (alien, robot, etc.)
        Uses subject/event/setting modes with weighted scoring.
        """
        from .prompt_parser import AMBIGUOUS_TERMS
        
        if term not in AMBIGUOUS_TERMS:
            return 0.0
        
        term_config = AMBIGUOUS_TERMS[term]
        if "modes" not in term_config:
            return 0.0
        
        desc = (content.description or "").lower()
        title = content.title.lower()
        genres_lower = [g.lower() for g in (content.genres or [])]
        
        total_score = 0.0
        
        for mode_name, mode_config in term_config["modes"].items():
            keywords = mode_config.get("keywords", [])
            mode_genres = mode_config.get("genres", [])
            weight = mode_config.get("weight", 0.5)
            
            # Check keyword matches in title/description
            keyword_match = any(kw in desc or kw in title for kw in keywords)
            
            # Check genre matches
            genre_match = any(g in genres_lower for g in mode_genres)
            
            if keyword_match:
                total_score += weight
            if genre_match:
                total_score += weight * 0.5  # Half weight for genre alone
        
        return total_score
    
    # Thematic hint words that indicate semantic search
    THEMATIC_HINTS = {"movies", "movie", "films", "film", "about", "related", "genre", "like", "similar", "type"}
    # Words that indicate NOT a title search
    GENRE_WORDS = {"movie", "movies", "film", "films", "genre", "type", "show", "series"}
        
    def _looks_like_genre(self, query: str) -> bool:
        """Check if query is a pure genre keyword."""
        return query.lower().strip() in KNOWN_GENRES
    
    def _looks_like_title(self, query: str) -> bool:
        """
        STAGE 1: Check if query looks like a title.
        Short queries (1-5 words) without descriptive words.
        """
        q = query.strip()
        tokens = q.split()
        
        # Too long for a title
        if len(tokens) > 5:
            return False
        
        # Contains genre/movie words → probably thematic
        if any(w.lower() in self.GENRE_WORDS for w in tokens):
            return False
        
        # Single word that's a genre → not a title
        if len(tokens) == 1 and self._looks_like_genre(query):
            return False
        
        return True
    
    def _looks_like_theme(self, query: str) -> bool:
        """
        STAGE 2: Check if query is thematic/descriptive.
        Contains words like 'movies', 'about', 'like'.
        """
        return any(hint in query.lower() for hint in self.THEMATIC_HINTS)
    
    def _detect_search_mode(self, query: str) -> str:
        """
        SEMANTIC-FIRST architecture. ALL queries go through semantic search.
        Title matching only supplements semantic results — never replaces them.
        """
        # ALL queries → semantic (title/genre matching handled as supplements)
        return "semantic"
        
    def search(self, request: SearchRequest, user_id: Optional[str] = None) -> List[SearchResultItem]:
        """
        SEMANTIC-FIRST search pipeline.
        Step 1: ALWAYS run semantic search (FAISS cosine similarity)
        Step 2: Optionally supplement with title matches (if query looks like a title)
        Step 3: Merge, de-duplicate, return
        """
        base_query = request.base_prompt.strip()
        
        # Check for THEME_EXPANSION mode (alien, robot, etc.)
        parsed = self.prompt_parser.parse(base_query)
        self.last_parsed_intent = parsed
        
        self.last_search_mode = "semantic"
        logger.info(f"[SEMANTIC-FIRST] Query: '{base_query}'")
        
        # STEP 1: ALWAYS semantic search first
        semantic_results = self._search_semantic(request, user_id)
        
        # STEP 2: If query looks like a title, supplement with exact matches
        if self._looks_like_title(base_query) and not self._looks_like_theme(base_query):
            try:
                exact_results = self._search_exact_title(base_query, request)
                if exact_results:
                    # Merge: exact matches that aren't already in semantic go to front
                    seen_ids = {r.content_id for r in semantic_results}
                    new_exact = [r for r in exact_results if r.content_id not in seen_ids]
                    if new_exact:
                        logger.info(f"[SUPPLEMENT] Added {len(new_exact)} title matches to semantic results")
                        semantic_results = new_exact[:3] + semantic_results  # Max 3 title supplements
            except Exception as e:
                logger.warning(f"Title supplement failed (non-critical): {e}")
        
        return semantic_results
    
    def _search_exact_title(self, query: str, request: SearchRequest) -> List[SearchResultItem]:
        """
        4-LAYER INTENT-AWARE SEARCH:
        Layer 1: Fuzzy normalization (vengers → avengers)
        Layer 2: Intent detection (marvel → MCU universe)
        Layer 3: Quality-gated search (rating >= 7.0)
        Layer 4: Intent-aware ranking
        Layer 5: Mood + Genre gates (STRICT AND LOGIC)
        """
        # LAYER 1: Fuzzy normalization
        normalized_query = self.intent_resolver.normalize_query(query)
        if normalized_query != query.lower():
            logger.info(f"[LAYER 1] Fuzzy normalized: '{query}' → '{normalized_query}'")
        
        # LAYER 2: Intent detection
        intent_name, intent_data = self.intent_resolver.detect_intent(normalized_query)
        self.last_detected_intent = intent_name
        
        if intent_data:
            logger.info(f"[LAYER 2] Detected intent: {intent_name} → tags: {intent_data.get('tags', [])}")
            
            # LAYER 3+4: Intent-aware quality search
            tags = intent_data.get("tags", [normalized_query])
            quality_threshold = intent_data.get("quality_threshold", 7.0)
            
            contents = search_by_intent(tags, quality_threshold=quality_threshold, limit=50)
            
            if contents:
                logger.info(f"[LAYER 3] Quality gate passed: {len(contents)} results (rating >= {quality_threshold})")
                
                # LAYER 5: Apply mood + genre gates (STRICT AND LOGIC)
                mood = request.mood
                genres = request.genres
                filtered_contents = []
                for c in contents:
                    if self._passes_mood_gate(c, mood) and self._passes_genre_gate(c, genres):
                        filtered_contents.append(c)
                
                logger.info(f"[LAYER 5] Mood/genre gates: {len(contents)} → {len(filtered_contents)}")
                
                # Convert to SearchResultItems with quality-based scoring
                results = []
                for i, c in enumerate(filtered_contents):
                    # Score based on: position (from rating sort) + rating bonus
                    base_score = 0.90 - (i * 0.02)
                    rating_bonus = (c.rating or 0) / 100  # Small rating bonus
                    score = base_score + rating_bonus
                    
                    results.append(SearchResultItem(
                        content_id=c.content_id,
                        title=c.title,
                        content_type=c.content_type.value,
                        thumbnail_url=c.thumbnail_url,
                        rating=c.rating,
                        score=score,
                        reason=f"Part of {intent_name.replace('_', ' ').title()} • Highly rated ({c.rating:.1f})"
                    ))
                
                if results:
                    return results[:50]
        
        # FALLBACK: Standard title search (no intent detected)
        contents = search_by_title(query, limit=50)
        
        if not contents:
            logger.info(f"[HYBRID] No title match for '{query}', falling back to semantic")
            self.last_search_mode = "semantic (fallback)"
            return self._search_semantic(request, None)
        
        # Apply mood + genre gates (STRICT AND LOGIC)
        mood = request.mood
        genres = request.genres
        filtered_contents = []
        for c in contents:
            if self._passes_mood_gate(c, mood) and self._passes_genre_gate(c, genres):
                filtered_contents.append(c)
        
        logger.info(f"[GATES] Title search: {len(contents)} → {len(filtered_contents)} after mood/genre gates")
        
        if not filtered_contents:
            # If no results pass gates, fallback to semantic
            logger.info(f"[HYBRID] No title results pass mood/genre gates, falling back to semantic")
            self.last_search_mode = "semantic (fallback)"
            return self._search_semantic(request, None)
        
        # Convert to SearchResultItems
        results = []
        for i, c in enumerate(filtered_contents):
            score = 0.95 - (i * 0.02)
            results.append(SearchResultItem(
                content_id=c.content_id,
                title=c.title,
                content_type=c.content_type.value,
                thumbnail_url=c.thumbnail_url,
                rating=c.rating,
                score=score,
                reason=f"Title match for '{query}' • Rated {c.rating:.1f}" if c.rating else f"Title match for '{query}'"
            ))
        
        return results[:50]
    
    def _search_genre_browse(self, genre: str, request: SearchRequest) -> List[SearchResultItem]:
        """MODE 2: Genre browse via SQL with popularity sorting."""
        contents = search_by_genre(genre, limit=50)
        
        if not contents:
            # Fallback to semantic
            logger.info(f"[HYBRID] No genre results for '{genre}', falling back to semantic")
            self.last_search_mode = "semantic (fallback)"
            return self._search_semantic(request, None)
        
        # Apply mood + genre gates (STRICT AND LOGIC)
        mood = request.mood
        genres = request.genres
        filtered_contents = []
        for c in contents:
            if self._passes_mood_gate(c, mood) and self._passes_genre_gate(c, genres):
                filtered_contents.append(c)
        
        logger.info(f"[GATES] Genre browse: {len(contents)} → {len(filtered_contents)} after mood/genre gates")
        
        if not filtered_contents:
            # Fallback to semantic if no results pass gates
            logger.info(f"[HYBRID] No genre results pass mood/genre gates, falling back to semantic")
            self.last_search_mode = "semantic (fallback)"
            return self._search_semantic(request, None)
        
        # Convert to SearchResultItems
        results = []
        for i, c in enumerate(filtered_contents):
            # Popularity-based scoring for genre browse
            pop_score = min(0.9, 0.5 + (c.popularity or 0) / 200)
            results.append(SearchResultItem(
                content_id=c.content_id,
                title=c.title,
                content_type=c.content_type.value,
                thumbnail_url=c.thumbnail_url,
                rating=c.rating,
                score=pop_score,
                reason=f"Popular {genre} content"
            ))
        
        return results[:50]

    def get_similar_content(self, content_id: str, limit: int = 10) -> List[SearchResultItem]:
        """
        Get 'More Like This' recommendations for a specific content ID.
        
        Enhanced multi-dimensional similarity:
        - 40% vector similarity (plot, themes)
        - 25% genre overlap
        - 20% tone similarity (dark/light/intense)
        - 15% narrative style (character-driven, plot-focused)
        """
        # 1. Fetch target content
        targets = get_content_by_ids([content_id])
        if not targets:
            logger.warning(f"Content {content_id} not found for similarity search")
            return []
            
        target = targets[0]
        target_text = f"{target.title} {target.description or ''}"
        
        # 2. Get target's embedding
        if target.embedding_text:
            query_vector = self.embedder.embed_texts([target.embedding_text])[0]
        else:
            query_vector = self.embedder.embed_texts([target_text])[0]
        
        # 3. Lazy load theme library for tone/narrative matching
        theme_library = None
        try:
            from .theme_library import ThemeLibrary
            theme_library = ThemeLibrary()
            theme_library.initialize()
            
            # Pre-compute target's tone and narrative style
            target_tone, target_tone_conf = theme_library.detect_tone(target_text)
            target_narrative, target_narrative_conf = theme_library.detect_narrative_style(target_text)
            logger.debug(f"Target '{target.title}': tone={target_tone}, narrative={target_narrative}")
        except Exception as e:
            logger.warning(f"ThemeLibrary not available for similarity: {e}")
            target_tone = None
            target_narrative = None
              
        # 4. Vector Search - get more candidates for filtering
        distances, candidate_ids = self.vector_store.search(query_vector, k=75)
        
        # 5. Filter and prepare candidates
        valid_indices = [i for i, cid in enumerate(candidate_ids) if cid and cid != content_id]
        candidates = [candidate_ids[i] for i in valid_indices]
        vector_scores = [float(distances[i]) for i in valid_indices]
        
        contents = get_content_by_ids(candidates)
        content_map = {c.content_id: c for c in contents}
        
        # 6. Pre-compute target features
        target_genres = set(g.lower() for g in (target.genres or []))
        
        # 7. Score each candidate with multi-dimensional similarity
        contents_list = []
        scores_list = []
        for i, cid in enumerate(candidates):
            if cid not in content_map:
                continue
                
            c = content_map[cid]
            c_text = f"{c.title} {c.description or ''}"
            
            # --- Component 1: Vector similarity (40%) ---
            vector_sim = vector_scores[i]
            
            # --- Component 2: Genre overlap (25%) ---
            c_genres = set(g.lower() for g in (c.genres or []))
            common_genres = target_genres.intersection(c_genres)
            total_genres = len(target_genres.union(c_genres)) or 1
            genre_score = len(common_genres) / total_genres
            
            # --- Component 3: Tone similarity (20%) ---
            tone_score = 0.5  # Default neutral
            if theme_library and target_tone:
                try:
                    c_tone, _ = theme_library.detect_tone(c_text)
                    if c_tone == target_tone:
                        tone_score = 1.0
                    elif c_tone and target_tone:
                        # Partial matches for similar tones
                        similar_tones = {
                            ("dark", "intense"): 0.7,
                            ("light", "emotional"): 0.6,
                            ("contemplative", "emotional"): 0.7,
                            ("intense", "emotional"): 0.5
                        }
                        pair = tuple(sorted([c_tone, target_tone]))
                        tone_score = similar_tones.get(pair, 0.3)
                except:
                    pass
            
            # --- Component 4: Narrative style similarity (15%) ---
            narrative_score = 0.5  # Default neutral
            if theme_library and target_narrative:
                try:
                    c_narrative, _ = theme_library.detect_narrative_style(c_text)
                    if c_narrative == target_narrative:
                        narrative_score = 1.0
                    elif c_narrative and target_narrative:
                        # Partial matches
                        similar_styles = {
                            ("character_driven", "dialogue_heavy"): 0.7,
                            ("plot_driven", "action_packed"): 0.6,
                            ("visual", "action_packed"): 0.5
                        }
                        pair = tuple(sorted([c_narrative, target_narrative]))
                        narrative_score = similar_styles.get(pair, 0.3)
                except:
                    pass
            
            # --- Weighted combination ---
            # 40% vector + 25% genre + 20% tone + 15% narrative
            final_score = (
                0.40 * vector_sim +
                0.25 * genre_score +
                0.20 * tone_score +
                0.15 * narrative_score
            )
            
            # Bonus for same content type
            if c.content_type == target.content_type:
                final_score += 0.03
            
            # Build reason string
            reason_parts = [f"Similar to {target.title}"]
            if common_genres:
                reason_parts.append(f"shares {', '.join(list(common_genres)[:2])}")
            if theme_library and target_tone and tone_score > 0.6:
                reason_parts.append(f"{target_tone} tone")
                
            contents_list.append(c)
            scores_list.append(final_score)
            
        # 8. Rank and format through universal ranker
        ranked_results = self.ranker.rank_results(
            contents_list,
            scores_list,
            query_hint=""
        )
        
        return ranked_results[:limit]

    def _calculate_ambiguity(self, parsed, query_text: str) -> float:
        """
        Calculate ambiguity score (0.0 = Specific, 1.0 = Ambiguous).
        Used for adaptive personalization.
        """
        # Ambiguous cases:
        # 1. Single genre/theme word ("action", "space")
        if parsed.is_ambiguous or parsed.mode == "THEME":
            return 1.0
            
        # 2. Very short queries (< 3 words)
        tokens = query_text.split()
        if len(tokens) < 3:
            return 0.8
            
        # 3. Story/Entity specific queries are NOT ambiguous
        if parsed.is_story or parsed.mode == "ENTITY":
            return 0.1
            
        # Default
        return 0.5
    
    def _search_semantic(self, request: SearchRequest, user_id: Optional[str] = None) -> List[SearchResultItem]:
        """
        MODE 3: Semantic search with 6-stage prompt understanding.
        Stage 1-2: Parse intent
        Stage 3: High recall FAISS
        Stage 4: Intent filtering
        Stage 5: Quality gate
        Stage 6: Ranking
        """
        # STAGE 1-2: Parse and classify intent
        parsed = self.prompt_parser.parse(request.base_prompt)
        self.last_parsed_intent = parsed
        logger.info(f"[STAGE 1-2] Parsed intent: mode={parsed.mode}, themes={parsed.themes}, entities={parsed.entities}")
        
        # 1. Build Text Query
        query_text = self.prompt_builder.build_query(request)
        
        # INJECTION: If story mode, inject narrative keywords for better recall
        if parsed.is_story:
            query_text += " narrative story plot character processing"
            
        logger.info(f"Generated Query: {query_text}")
        
        # 2. Embed Query
        query_vector = self.embedder.embed_texts([query_text])[0]
        
        # DEBUG LOGGING
        if query_vector.shape != (384,):
            logger.error(f"CRITICAL: Query embedding shape is {query_vector.shape}, expected (384,)")
        else:
            logger.info(f"Query embedding shape: {query_vector.shape}")

        # 3. Personalize Query (Adaptive)
        if user_id:
             # Calculate ambiguity (0.0=specific, 1.0=ambiguous)
             ambiguity = self._calculate_ambiguity(parsed, request.base_prompt)
             query_vector = self.personalization_service.get_personalized_query(query_vector, user_id, ambiguity)
        
        # 4. Vector Search (FAISS)
        # Increased to 200 for broader recall (user request: "more movies")
        distances, content_ids = self.vector_store.search(query_vector, k=200)
        
        # DEBUG LOGGING
        logger.info(f"[SEMANTIC] FAISS returned {len([c for c in content_ids if c])} results")
        
        # Filter out None values and store scores
        valid_indices = [i for i, cid in enumerate(content_ids) if cid is not None]
        candidates_ids = [content_ids[i] for i in valid_indices]
        candidates_scores = [float(distances[i]) for i in valid_indices]
        
        if not candidates_ids:
            logger.info("No results from vector search")
            return []

        # 5. Fetch Content Details
        contents = get_content_by_ids(candidates_ids)
        
        # Build lookup map: content_id → UnifiedContent
        content_map = {c.content_id: c for c in contents}
        
        # Initialize gate tracking
        gate_stats = {"youtube": 0, "quality": 0, "mood": 0, "genre": 0, "theme": 0, "antigravity": 0, "passed": 0}
        sbert_count = len(candidates_ids)
        final_candidates = []
        final_scores = []
        
        # Extract mood and genres from request
        mood = request.mood if hasattr(request, 'mood') and request.mood else None
        
        # Fallback to detected tone in prompt if user didn't explicitly select a mood filter
        if not mood and hasattr(parsed, 'emotional_tone') and parsed.emotional_tone:
            mood = parsed.emotional_tone
            
        genres = request.genres if hasattr(request, 'genres') and request.genres else None
        
        # Story mode / Anti-Gravity detection
        parsed_themes = parsed.themes if hasattr(parsed, 'themes') else []
        is_story_mode = parsed.is_story if hasattr(parsed, 'is_story') else False
        has_antigravity_filters = hasattr(parsed, 'has_antigravity') and parsed.has_antigravity
        
        for cid, score in zip(candidates_ids, candidates_scores):
            if cid in content_map:
                c = content_map[cid]
                
                # GATE 0: EXCLUDE YOUTUBE (ABSOLUTE CONSTRAINT)
                if hasattr(c, 'content_type') and c.content_type and str(c.content_type).lower() in ['youtube', 'short']:
                    gate_stats["youtube"] += 1
                    continue
                
                # GATE 1: QUALITY (rating >= 6.5)
                if not self._passes_quality_gate(c):
                    gate_stats["quality"] += 1
                    continue
                
                # GATE 2: MOOD (allowed genres + no forbidden genres)
                if not self._passes_mood_gate(c, mood):
                    gate_stats["mood"] += 1
                    # Log significant discards for debugging
                    if c.rating and c.rating >= 7.5:
                        logger.debug(f"[MOOD GATE] DISCARDED: {c.title} (rating={c.rating}, genres={c.genres}) - doesn't match mood '{mood}'")
                    continue
                
                # GATE 3: GENRE (user-selected genres)
                if not self._passes_genre_gate(c, genres):
                    gate_stats["genre"] += 1
                    continue
                
                # GATE 4: THEME_EXPANSION (for ambiguous terms like "alien", "robot")
                if parsed.mode == "THEME_EXPANSION" and parsed.is_ambiguous:
                    term = parsed.normalized_query
                    theme_score = self._compute_theme_score(c, term, parsed.expansion_data)
                    threshold = 1.5
                    if parsed.expansion_data and "threshold" in parsed.expansion_data:
                        threshold = parsed.expansion_data["threshold"]
                    
                    if theme_score < threshold:
                        gate_stats["theme"] += 1
                        continue
                
                # GATE 5: Story Intent (for STORY mode)
                if is_story_mode:
                    if not self._matches_story_intent(c, parsed_themes):
                        continue
                
                # GATE 6: ANTI-GRAVITY (Strict AND logic for mood + entity + plot)
                if has_antigravity_filters:
                    ag_result = self._passes_antigravity_filter(c, request.base_prompt)
                    if not ag_result["passed"]:
                        gate_stats["antigravity"] += 1
                        logger.debug(f"[ANTI-GRAVITY] BLOCKED: {c.title} - {ag_result['failed_gate']}: {ag_result['reason']}")
                        continue
                
                # Apply other filters (year, language, etc.)
                if self._apply_filters(c, request.filters):
                    gate_stats["passed"] += 1
                    final_candidates.append(c)
                    final_scores.append(score)
        
        # Update stage counts for debug
        self.last_stage_counts = {
            "sbert": sbert_count,
            "quality_gate": gate_stats["quality"],
            "mood_gate": gate_stats["mood"],
            "genre_gate": gate_stats["genre"],
            "antigravity_gate": gate_stats["antigravity"],
            "final": len(final_candidates)
        }
        logger.info(f"[PIPELINE] SBERT={sbert_count} → Quality={gate_stats['quality']} → Mood={gate_stats['mood']} → Genre={gate_stats['genre']} → AntiGravity={gate_stats['antigravity']} → Final={len(final_candidates)}")
        
        # 7. Rank (Weighted Score) - with mood-aware quality scoring
        detected_concepts = self.ranker.detect_concepts(request.base_prompt)
        if detected_concepts:
            logger.info(f"[COMPOUND] Detected concepts: {detected_concepts}")
            self.last_detected_concepts = detected_concepts
        else:
            self.last_detected_concepts = []
        
        # Pass mood for mood-aware ranking
        mood = request.mood if hasattr(request, 'mood') else None
        if mood:
            logger.info(f"[MOOD] Applied mood filter: {mood}")
        
        ranked_results = self.ranker.rank_results(
            final_candidates,
            final_scores,
            query_hint=query_text,
            detected_concepts=detected_concepts,
            mood=mood
        )
        
        # --- DISCOVERABILITY BOOSTERS (Netflix Architecture) ---
        
        # 1. HIDDEN GEMS: Boost high-quality but low-popularity items
        # Logic: Rating >= 7.5 AND Popularity < Median -> +15% score
        if len(ranked_results) > 10:
            pops = [r.popularity for r in ranked_results if r.popularity]
            if pops:
                median_pop = sorted(pops)[len(pops)//2]
                for r in ranked_results:
                    if r.rating and r.rating >= 7.5 and (r.popularity or 0) < median_pop:
                        old_score = r.score
                        r.score *= 1.15
                        # Add badge/reason if not already there
                        if "Hidden Gem" not in r.reason:
                            r.reason = f"Hidden Gem • {r.reason}"
                        logger.debug(f"[HIDDEN GEM] {r.title}: {old_score:.3f} -> {r.score:.3f}")
                
                # Re-sort after boosting
                ranked_results.sort(key=lambda x: x.score, reverse=True)

        # 2. SERENDIPITY: Inject different genres at fixed positions (5, 10, 15)
        # Logic: Find high-rated items with different genres from top 3 results
        if len(ranked_results) > 20:
            top_genres = set()
            for r in ranked_results[:3]:
                # Extract genre from reason or content override if available
                # Simpler: assume primary genre is first in list (not available here directly, 
                # but we can infer from reason if genre mentioned, or skip complex logic for now)
                pass 
            
            # Simple Serendipity: Take a high-rated item from index 20+ and move to 5, 10
            # Only if it has high rating (> 7.0)
            serendipity_candidates = []
            for i in range(20, len(ranked_results)):
                r = ranked_results[i]
                if r.rating and r.rating >= 7.5:
                    serendipity_candidates.append(i)
            
            # Inject at 5, 10, 15
            injection_points = [5, 10, 15]
            for point in injection_points:
                if serendipity_candidates and point < len(ranked_results):
                    # Pop a candidate
                    cand_idx = serendipity_candidates.pop(0)
                    if cand_idx >= len(ranked_results): continue # Index shifted
                    
                    item = ranked_results.pop(cand_idx)
                    item.reason = f"Spark • {item.reason}"
                    ranked_results.insert(point, item)
                    
                    # Adjust indices for next iteration
                    serendipity_candidates = [x if x < point else x+1 for x in serendipity_candidates]

        # 3. DIVERSITY INJECTION: Prevent genre clustering
        # Logic: Max 3 items of same content type/genre sequence
        # (Simplified to Content Type for now as full objects aren't here)
        final_diverse = []
        type_streak = {"movie": 0, "series": 0}
        overflow = []
        
        for r in ranked_results:
            ctype = r.content_type
            if type_streak.get(ctype, 0) < 4:
                final_diverse.append(r)
                type_streak[ctype] = type_streak.get(ctype, 0) + 1
                # Reset other streak
                other = "series" if ctype == "movie" else "movie"
                type_streak[other] = 0
            else:
                overflow.append(r)
                
        # Append overflow
        ranked_results = final_diverse + overflow

        return ranked_results[:100]

    def _apply_filters(self, content, filters) -> bool:
        if not filters:
            return True
            
        if filters.content_type and content.content_type.value not in filters.content_type:
            return False
            
        if filters.min_year and (content.release_year or 0) < filters.min_year:
            return False

        if filters.max_year and (content.release_year or 0) > filters.max_year:
            return False
            
        if filters.language and content.language != filters.language:
            return False
            
        if filters.min_rating and (content.rating or 0) < filters.min_rating:
            return False
            
        return True

    def get_personal_recommendations(self, seed_ids: List[str], limit: int = 10) -> List[SearchResultItem]:
        """
        Generate recommendations based on a user's watch history (seed_ids).
        Computes the centroid of the seed vectors and finds similar items.
        """
        if not seed_ids:
            return []
            
        # 1. Collect vectors
        vectors = []
        for sid in set(seed_ids):
            v = self.vector_store.get_vector(sid)
            if v is not None:
                vectors.append(v)
                
        if not vectors:
            logger.warning(f"[PERSONAL] No valid vectors found for seeds: {seed_ids}")
            return []
            
        # 2. Compute Centroid
        # shape: (N, 384)
        stacked = np.vstack(vectors)
        centroid = np.mean(stacked, axis=0)
        
        # 3. Normalize Centroid
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm
        else:
            return []
            
        # 4. Search
        # Fetch a significantly larger pool to allow for strict popularity & rating filtering
        search_k = (limit * 5) + len(seed_ids) + 10
        distances, result_ids = self.vector_store.search(centroid, k=search_k)
        
        # 5. Filter and Rank
        seen = set(seed_ids)
        distance_map = {}
        candidate_ids_to_fetch = []

        for idx, cid in enumerate(result_ids):
            if cid and cid not in seen:
                candidate_ids_to_fetch.append(cid)
                distance_map[cid] = float(distances[idx])
        
        if not candidate_ids_to_fetch:
            return []
            
        # 6. Fetch Details
        contents = get_content_by_ids(candidate_ids_to_fetch)
        
        # 7. Apply quality gating (Popularity filter handled here, Rating handled by Ranker)
        final_candidates = []
        final_scores = []
        
        for c in contents:
            # Popularity gate for personalization
            popularity = c.popularity or 0.0
            if popularity < 10.0:
                continue
            
            final_candidates.append(c)
            final_scores.append(distance_map.get(c.content_id, 0.0))
            
        # 8. Route through global ranker to enforce global quality & concept rules
        ranked_results = self.ranker.rank_results(
            final_candidates,
            final_scores,
            query_hint=""
        )
        
        return ranked_results[:limit]
