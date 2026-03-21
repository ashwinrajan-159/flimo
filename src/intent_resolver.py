"""
Intent Resolver: 4-Layer Universal Search System
Layer 1: Fuzzy Intent Normalization
Layer 2: Entity/Franchise Intent Detection
"""
from typing import Dict, List, Tuple, Optional
from difflib import get_close_matches

# LAYER 1: Known entities for fuzzy matching
KNOWN_ENTITIES = {
    # Franchises
    "avengers": ["avengers", "vengers", "avenger", "avangers"],
    "marvel": ["marvel", "marvl", "mcu", "mrvel"],
    "dc": ["dc", "dceu", "dc comics"],
    "batman": ["batman", "batmn", "dark knight"],
    "superman": ["superman", "supermn"],
    "spider-man": ["spider-man", "spiderman", "spider man", "spidey"],
    "star wars": ["star wars", "starwars", "star war"],
    "harry potter": ["harry potter", "harrypotter", "hp"],
    "lord of the rings": ["lord of the rings", "lotr", "rings"],
    "fast and furious": ["fast and furious", "fast furious", "f&f"],
    
    # Themes
    "space": ["space", "spce", "cosmos", "interstellar"],
    "horror": ["horror", "horor", "scary"],
    "comedy": ["comedy", "comdy", "funny"],
    "romance": ["romance", "romanc", "love"],
    "action": ["action", "acton"],
}

# LAYER 2: Intent mapping (entity → SPECIFIC title patterns for DB search)
# These tags are matched against TITLE, not description - for precision
INTENT_MAP = {
    "marvel": {
        "type": "universe",
        # MCU movies + animated series title patterns
        "tags": [
            # Movies
            "avengers", "iron man", "thor", "captain america", 
            "black panther", "guardians of the galaxy", "ant-man", 
            "doctor strange", "black widow", "shang-chi", "eternals",
            "spider-man: homecoming", "spider-man: far from home", "spider-man: no way home",
            "captain marvel", "hulk", "spider-verse",
            # Animated & Series
            "x-men", "what if", "agents of s.h.i.e.l.d", "daredevil", 
            "loki", "wandavision", "moon knight", "ms. marvel", "hawkeye",
            "the spectacular spider-man"
        ],
        "quality_threshold": 7.0
    },
    "avengers": {
        "type": "franchise",
        "tags": ["avengers"],
        "quality_threshold": 7.0
    },
    "dc": {
        "type": "universe",
        "tags": ["batman", "superman", "wonder woman", "justice league", 
                 "aquaman", "flash", "shazam", "joker"],
        "quality_threshold": 7.0
    },
    "batman": {
        "type": "franchise",
        "tags": ["batman", "dark knight"],
        "quality_threshold": 7.0
    },
    "spider-man": {
        "type": "franchise",
        # Specific Spider-Man titles only
        "tags": ["spider-man", "into the spider-verse", "across the spider-verse"],
        "quality_threshold": 7.0
    },
    "star wars": {
        "type": "franchise",
        "tags": ["star wars", "mandalorian", "rogue one", "solo:"],
        "quality_threshold": 7.0
    },
    "harry potter": {
        "type": "franchise",
        "tags": ["harry potter", "fantastic beasts"],
        "quality_threshold": 7.0
    },
    "space": {
        "type": "theme",
        "tags": ["interstellar", "gravity", "martian", "arrival", "moon", "apollo", "2001"],
        "genres": ["science fiction"],
        "quality_threshold": 7.5
    },
    "horror": {
        "type": "theme",
        "tags": ["horror"],
        "genres": ["horror"],
        "quality_threshold": 6.5
    },
    "comedy": {
        "type": "theme",
        "tags": ["comedy"],
        "genres": ["comedy"],
        "quality_threshold": 6.5
    }
}


class IntentResolver:
    """Handles Layer 1 (fuzzy normalization) and Layer 2 (intent detection)"""
    
    def normalize_query(self, query: str) -> str:
        """
        LAYER 1: Fuzzy normalization
        Fixes typos: vengers → avengers, marvl → marvel
        """
        query_lower = query.lower().strip()
        
        # Direct match check
        for canonical, variants in KNOWN_ENTITIES.items():
            if query_lower in variants:
                return canonical
        
        # Fuzzy match if no direct match
        all_variants = []
        variant_to_canonical = {}
        for canonical, variants in KNOWN_ENTITIES.items():
            for v in variants:
                all_variants.append(v)
                variant_to_canonical[v] = canonical
        
        matches = get_close_matches(query_lower, all_variants, n=1, cutoff=0.7)
        if matches:
            return variant_to_canonical[matches[0]]
        
        return query_lower  # Return original if no match
    
    def detect_intent(self, query: str) -> Tuple[Optional[str], Optional[Dict]]:
        """
        LAYER 2: Intent detection
        Returns (intent_name, intent_data) or (None, None)
        """
        normalized = self.normalize_query(query)
        
        if normalized in INTENT_MAP:
            return normalized, INTENT_MAP[normalized]
        
        return None, None
    
    def get_search_tags(self, query: str) -> List[str]:
        """Get all search tags for a query based on intent."""
        intent_name, intent_data = self.detect_intent(query)
        
        if intent_data:
            return intent_data.get("tags", [])
        
        return [query.lower()]
    
    def get_quality_threshold(self, query: str) -> float:
        """Get quality threshold for a query (default 7.0)"""
        intent_name, intent_data = self.detect_intent(query)
        
        if intent_data:
            return intent_data.get("quality_threshold", 7.0)
        
        return 7.0  # Default high quality
