"""
Theme Library: Neural Theme Extraction Service
Precomputes embeddings for abstract themes and matches queries to themes.
Enables semantic understanding of queries like "movies about letting go"
"""
import logging
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Abstract theme definitions with related concepts
THEME_DEFINITIONS = {
    # Emotional themes
    "loss": ["loss", "grief", "death", "losing someone", "bereavement", "mourning"],
    "healing": ["healing", "recovery", "overcoming trauma", "getting better", "moving forward"],
    "redemption": ["redemption", "second chance", "making amends", "forgiveness", "atonement"],
    "growth": ["personal growth", "self-discovery", "coming of age", "transformation", "maturity"],
    "letting_go": ["letting go", "moving on", "acceptance", "release", "closure", "goodbye"],
    "hope": ["hope", "optimism", "faith", "believing", "perseverance", "never giving up"],
    "loneliness": ["loneliness", "isolation", "solitude", "alone", "disconnection"],
    "belonging": ["belonging", "finding home", "acceptance", "community", "family bonds"],
    
    # Relationship themes
    "love": ["love", "romance", "passion", "falling in love", "soulmates"],
    "friendship": ["friendship", "loyalty", "companions", "best friends", "brotherhood"],
    "family": ["family", "parent child", "siblings", "relatives", "generational"],
    "betrayal": ["betrayal", "deception", "trust broken", "backstabbing", "treachery"],
    "reconciliation": ["reconciliation", "making up", "reunion", "forgiving", "reconnecting"],
    
    # Life themes
    "identity": ["identity", "who am I", "finding yourself", "self-discovery", "purpose"],
    "freedom": ["freedom", "liberation", "escape", "breaking free", "independence"],
    "sacrifice": ["sacrifice", "giving up", "selfless", "martyrdom", "giving everything"],
    "survival": ["survival", "staying alive", "endurance", "resilience", "against all odds"],
    "justice": ["justice", "fairness", "righting wrongs", "moral", "doing the right thing"],
    "revenge": ["revenge", "vengeance", "payback", "retribution", "getting even"],
    "ambition": ["ambition", "drive", "pursuit of success", "climbing to the top", "dreams"],
    
    # Existential themes
    "mortality": ["mortality", "death", "dying", "life and death", "facing death"],
    "meaning": ["meaning of life", "purpose", "existential", "why we exist", "philosophical"],
    "time": ["time passing", "memories", "nostalgia", "past and present", "fleeting moments"],
    "fate": ["fate", "destiny", "meant to be", "predetermined", "cosmic"],
    "choice": ["choice", "decisions", "crossroads", "free will", "consequences"],
    
    # Adventure themes  
    "journey": ["journey", "quest", "adventure", "expedition", "odyssey"],
    "discovery": ["discovery", "exploration", "finding", "uncovering", "revelation"],
    "challenge": ["challenge", "obstacle", "overcoming", "trial", "test"],
    "heroism": ["heroism", "bravery", "courage", "hero", "saving the day"],
    
    # Social themes
    "power": ["power", "corruption", "authority", "control", "dominance"],
    "class": ["class struggle", "rich and poor", "inequality", "social divide"],
    "truth": ["truth", "honesty", "revealing secrets", "uncovering lies", "transparency"],
    "conformity": ["conformity", "rebellion", "fitting in", "standing out", "individuality"],
    
    # Dark themes
    "obsession": ["obsession", "fixation", "consumed by", "addiction", "compulsion"],
    "madness": ["madness", "insanity", "losing mind", "mental breakdown", "psychological"],
    "fear": ["fear", "terror", "dread", "horror", "facing fears"],
    "guilt": ["guilt", "regret", "remorse", "haunted by past", "shame"],
    "despair": ["despair", "hopelessness", "giving up", "darkness", "depression"]
}

# Tone descriptors for content matching
TONE_PROFILES = {
    "dark": {
        "keywords": ["dark", "gritty", "disturbing", "bleak", "noir", "psychological", "twisted"],
        "genres": ["thriller", "horror", "crime", "drama"],
        "avoid_genres": ["comedy", "family", "animation"]
    },
    "light": {
        "keywords": ["light", "fun", "cheerful", "uplifting", "heartwarming", "feel-good"],
        "genres": ["comedy", "family", "animation", "romance"],
        "avoid_genres": ["horror", "thriller", "war"]
    },
    "intense": {
        "keywords": ["intense", "gripping", "edge of seat", "suspenseful", "high stakes"],
        "genres": ["action", "thriller", "war", "crime"],
        "avoid_genres": ["comedy", "family"]
    },
    "contemplative": {
        "keywords": ["contemplative", "slow", "meditative", "philosophical", "thought-provoking"],
        "genres": ["drama", "documentary", "art house"],
        "avoid_genres": ["action", "horror"]
    },
    "emotional": {
        "keywords": ["emotional", "moving", "touching", "tears", "heartbreaking", "bittersweet"],
        "genres": ["drama", "romance", "biography"],
        "avoid_genres": ["horror", "action"]
    }
}

# Narrative style descriptors
NARRATIVE_STYLES = {
    "character_driven": {
        "keywords": ["character study", "personal journey", "intimate", "internal conflict"],
        "description": "Focus on character development and psychology"
    },
    "plot_driven": {
        "keywords": ["twist", "mystery", "puzzle", "revelation", "complex plot"],
        "description": "Focus on story events and plot progression"
    },
    "action_packed": {
        "keywords": ["action", "chase", "fight", "explosion", "spectacle"],
        "description": "Focus on physical action and set pieces"
    },
    "dialogue_heavy": {
        "keywords": ["witty", "conversational", "verbal", "talky", "debate"],
        "description": "Focus on character interaction through dialogue"
    },
    "visual": {
        "keywords": ["visual", "stunning", "beautiful", "aesthetic", "cinematography"],
        "description": "Focus on visual storytelling"
    }
}


@dataclass
class ThemeMatch:
    """Represents a theme match with confidence score"""
    theme: str
    confidence: float
    related_concepts: List[str]


class ThemeLibrary:
    """
    Neural theme extraction service using SBERT embeddings.
    Precomputes theme embeddings at startup for fast similarity matching.
    """
    
    def __init__(self, embedder=None):
        """
        Initialize with optional embedder (lazy load if not provided).
        """
        self._embedder = embedder
        self._theme_embeddings: Dict[str, np.ndarray] = {}
        self._tone_embeddings: Dict[str, np.ndarray] = {}
        self._narrative_embeddings: Dict[str, np.ndarray] = {}
        self._initialized = False
        
    @property
    def embedder(self):
        """Lazy load embedder"""
        if self._embedder is None:
            from .embedder import Embedder
            self._embedder = Embedder()
        return self._embedder
    
    def initialize(self):
        """Precompute all theme embeddings"""
        if self._initialized:
            return
            
        logger.info("Initializing ThemeLibrary with precomputed embeddings...")
        
        # Compute theme embeddings
        for theme, concepts in THEME_DEFINITIONS.items():
            # Create rich text representation
            theme_text = f"{theme}: {', '.join(concepts)}"
            embedding = self.embedder.embed_texts([theme_text])[0]
            self._theme_embeddings[theme] = embedding
            
        # Compute tone embeddings
        for tone, profile in TONE_PROFILES.items():
            tone_text = f"{tone}: {', '.join(profile['keywords'])}"
            embedding = self.embedder.embed_texts([tone_text])[0]
            self._tone_embeddings[tone] = embedding
            
        # Compute narrative style embeddings
        for style, profile in NARRATIVE_STYLES.items():
            style_text = f"{style}: {profile['description']}. {', '.join(profile['keywords'])}"
            embedding = self.embedder.embed_texts([style_text])[0]
            self._narrative_embeddings[style] = embedding
            
        self._initialized = True
        logger.info(f"ThemeLibrary initialized with {len(self._theme_embeddings)} themes, "
                   f"{len(self._tone_embeddings)} tones, {len(self._narrative_embeddings)} narrative styles")
    
    def match_themes(self, query: str, top_k: int = 5, threshold: float = 0.3) -> List[ThemeMatch]:
        """
        Match query against theme library using cosine similarity.
        
        Args:
            query: User search query
            top_k: Maximum themes to return
            threshold: Minimum similarity threshold
            
        Returns:
            List of ThemeMatch objects sorted by confidence
        """
        self.initialize()
        
        # Embed query
        query_embedding = self.embedder.embed_texts([query])[0]
        
        # Calculate similarities
        matches = []
        for theme, theme_embedding in self._theme_embeddings.items():
            # Cosine similarity (embeddings are normalized)
            similarity = float(np.dot(query_embedding, theme_embedding))
            
            if similarity >= threshold:
                matches.append(ThemeMatch(
                    theme=theme,
                    confidence=similarity,
                    related_concepts=THEME_DEFINITIONS[theme][:3]  # Top 3 concepts
                ))
        
        # Sort by confidence
        matches.sort(key=lambda x: x.confidence, reverse=True)
        
        return matches[:top_k]
    
    def detect_tone(self, text: str) -> Tuple[str, float]:
        """
        Detect the dominant tone of content text.
        
        Returns:
            Tuple of (tone_name, confidence)
        """
        self.initialize()
        
        text_embedding = self.embedder.embed_texts([text])[0]
        
        best_tone = None
        best_score = -1
        
        for tone, tone_embedding in self._tone_embeddings.items():
            similarity = float(np.dot(text_embedding, tone_embedding))
            if similarity > best_score:
                best_score = similarity
                best_tone = tone
                
        return best_tone, best_score
    
    def detect_narrative_style(self, text: str) -> Tuple[str, float]:
        """
        Detect the narrative style of content.
        
        Returns:
            Tuple of (style_name, confidence)
        """
        self.initialize()
        
        text_embedding = self.embedder.embed_texts([text])[0]
        
        best_style = None
        best_score = -1
        
        for style, style_embedding in self._narrative_embeddings.items():
            similarity = float(np.dot(text_embedding, style_embedding))
            if similarity > best_score:
                best_score = similarity
                best_style = style
                
        return best_style, best_score
    
    def get_tone_profile(self, tone: str) -> Optional[Dict]:
        """Get full profile for a tone"""
        return TONE_PROFILES.get(tone)
    
    def get_narrative_profile(self, style: str) -> Optional[Dict]:
        """Get full profile for a narrative style"""
        return NARRATIVE_STYLES.get(style)
    
    def compare_content_similarity(self, text1: str, text2: str) -> Dict[str, float]:
        """
        Compare two content descriptions for multi-dimensional similarity.
        
        Returns:
            Dict with semantic, tone, and narrative similarity scores
        """
        self.initialize()
        
        # Semantic similarity
        emb1 = self.embedder.embed_texts([text1])[0]
        emb2 = self.embedder.embed_texts([text2])[0]
        semantic_sim = float(np.dot(emb1, emb2))
        
        # Tone similarity
        tone1, _ = self.detect_tone(text1)
        tone2, _ = self.detect_tone(text2)
        tone_sim = 1.0 if tone1 == tone2 else 0.3
        
        # Narrative style similarity
        style1, _ = self.detect_narrative_style(text1)
        style2, _ = self.detect_narrative_style(text2)
        narrative_sim = 1.0 if style1 == style2 else 0.3
        
        return {
            "semantic": semantic_sim,
            "tone": tone_sim,
            "narrative": narrative_sim,
            "combined": 0.5 * semantic_sim + 0.3 * tone_sim + 0.2 * narrative_sim
        }
    
    def enrich_search_query(self, query: str) -> str:
        """
        Enrich a search query with detected theme concepts.
        Useful for improving semantic search recall.
        """
        matches = self.match_themes(query, top_k=3, threshold=0.35)
        
        if not matches:
            return query
            
        # Add top theme concepts to query
        enrichment_terms = []
        for match in matches[:2]:  # Top 2 themes
            enrichment_terms.extend(match.related_concepts[:2])
            
        if enrichment_terms:
            enriched = f"{query}, {', '.join(enrichment_terms)}"
            logger.debug(f"Enriched query: '{query}' → '{enriched}'")
            return enriched
            
        return query
