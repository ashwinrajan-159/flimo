"""
Prompt Builder: Query Enhancement for Semantic Search
Enhances user queries with mood expansion, narrative context injection,
and optional theme enrichment for improved semantic matching.
"""
import re
import logging
from typing import Optional, List
from .schemas import SearchRequest

logger = logging.getLogger(__name__)

# Mood to semantic expansion mapping
MOOD_MAP = {
    "dark": "dark, intense, psychological, disturbing, suspenseful, noir, gritty",
    "happy": "uplifting, lighthearted, fun, feel good, heartwarming, cheerful",
    "romantic": "romantic, emotional, love story, passionate, intimate",
    "relaxing": "calm, slow paced, soothing, peaceful, meditative",
    "thriller": "suspenseful, mysterious, intense, edge of seat, gripping",
    "motivational": "inspiring, uplifting, personal growth, triumph, perseverance",
    "emotional": "moving, touching, tearjerker, bittersweet, heartbreaking",
    "epic": "grand, spectacular, sweeping, ambitious, larger than life"
}

# Narrative patterns with injection keywords
NARRATIVE_PATTERNS = {
    # Family/relationship patterns
    r"father.*son|mother.*daughter|parent.*child": {
        "keywords": ["family bonds", "generational story", "emotional journey"],
        "context": "character-driven family drama"
    },
    r"searching for|looking for|finding": {
        "keywords": ["quest", "journey", "discovery", "emotional arc"],
        "context": "narrative journey"
    },
    r"love between|falls in love|romance between": {
        "keywords": ["love story", "romantic journey", "emotional connection"],
        "context": "romantic narrative"
    },
    r"revenge|vengeance|payback": {
        "keywords": ["revenge tale", "justice", "moral conflict"],
        "context": "revenge narrative"
    },
    r"escape|running from|fleeing": {
        "keywords": ["escape story", "pursuit", "survival journey"],
        "context": "escape narrative"
    },
    r"overcome|triumph|against all odds": {
        "keywords": ["underdog story", "triumph narrative", "perseverance"],
        "context": "inspirational journey"
    },
    r"secret|hidden|mystery|discover": {
        "keywords": ["mystery plot", "revelation", "uncovering truth"],
        "context": "mystery narrative"
    },
    r"war|battle|soldier|military": {
        "keywords": ["war story", "combat", "sacrifice", "brotherhood"],
        "context": "war narrative"
    },
    r"criminal|heist|robbery|steal": {
        "keywords": ["heist story", "crime plot", "tension"],
        "context": "crime narrative"
    },
    r"survival|survive|apocalypse|disaster": {
        "keywords": ["survival story", "endurance", "resilience"],
        "context": "survival narrative"
    }
}

# Story structure indicators
STORY_INDICATORS = [
    "a story about", "tale of", "journey of", "about a", "follows a",
    "the story of", "chronicles", "depicts", "portrays", "explores"
]


class PromptBuilder:
    """
    Constructs enhanced query strings for semantic search.
    
    Features:
    - Mood expansion: Adds semantic keywords based on mood
    - Narrative injection: Adds story-focused context for narrative queries
    - Theme enrichment: Optionally enriches with detected themes
    """
    
    def __init__(self, theme_library=None):
        """
        Initialize with optional theme library for enrichment.
        """
        self._theme_library = theme_library
        
    @property
    def theme_library(self):
        """Lazy load theme library"""
        if self._theme_library is None:
            try:
                from .theme_library import ThemeLibrary
                self._theme_library = ThemeLibrary()
            except ImportError:
                logger.warning("ThemeLibrary not available")
        return self._theme_library

    def build_query(self, request: SearchRequest, enrich_themes: bool = False) -> str:
        """
        Construct final query string from base prompt, refinements, and mood.
        
        Args:
            request: Search request with base_prompt, refinements, mood
            enrich_themes: Whether to add theme concepts from ThemeLibrary
            
        Returns:
            Enhanced query string for embedding
        """
        base_prompt = request.base_prompt.strip()
        parts = [base_prompt]
        
        # Add Refinements
        if request.refinements:
            parts.extend(request.refinements)
            
        # Add Mood Expansion
        if request.mood and request.mood.lower() in MOOD_MAP:
            parts.append(MOOD_MAP[request.mood.lower()])
            
        # Detect and inject narrative context
        narrative_injection = self._detect_narrative_context(base_prompt)
        if narrative_injection:
            parts.append(narrative_injection)
            logger.debug(f"Narrative injection: {narrative_injection}")
            
        # Optional: Enrich with detected themes
        if enrich_themes and self.theme_library:
            theme_enrichment = self.theme_library.enrich_search_query(base_prompt)
            if theme_enrichment != base_prompt:
                # Extract just the enrichment part
                enrichment_only = theme_enrichment.replace(base_prompt + ", ", "")
                parts.append(enrichment_only)
                logger.debug(f"Theme enrichment: {enrichment_only}")
            
        # Join with commas for semantic separation
        final_query = ", ".join(parts)
        
        return final_query
    
    def _detect_narrative_context(self, query: str) -> Optional[str]:
        """
        Detect if query describes a story/narrative and return injection keywords.
        
        Returns:
            Comma-separated injection keywords or None
        """
        query_lower = query.lower()
        
        # Check for explicit story indicators
        is_story = any(indicator in query_lower for indicator in STORY_INDICATORS)
        
        # Check narrative patterns
        matched_keywords = []
        for pattern, data in NARRATIVE_PATTERNS.items():
            if re.search(pattern, query_lower):
                matched_keywords.extend(data["keywords"])
                
        if is_story or matched_keywords:
            # Add base narrative context
            base_context = ["story", "plot", "character-driven", "emotional arc"]
            
            # Combine with matched keywords (deduplicate)
            all_keywords = list(dict.fromkeys(base_context + matched_keywords))
            
            return ", ".join(all_keywords[:5])  # Limit to top 5
            
        return None
    
    def get_narrative_debug(self, query: str) -> dict:
        """
        Get debug info about narrative detection.
        """
        query_lower = query.lower()
        
        matched_patterns = []
        matched_keywords = []
        
        for pattern, data in NARRATIVE_PATTERNS.items():
            if re.search(pattern, query_lower):
                matched_patterns.append(pattern)
                matched_keywords.extend(data["keywords"])
                
        is_story = any(indicator in query_lower for indicator in STORY_INDICATORS)
        
        injection = self._detect_narrative_context(query)
        
        return {
            "query": query,
            "is_story_query": is_story,
            "matched_patterns": matched_patterns,
            "detected_keywords": matched_keywords,
            "injection": injection
        }

