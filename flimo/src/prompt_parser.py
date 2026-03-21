"""
Prompt Parser: Hybrid Rule + Neural Prompt Understanding System
Stage 0: Entity override (rule-based)
Stage 1: Neural semantic parsing (SBERT themes)
Stage 2: Rule-based reconciliation
Stage 3: Intent classification
"""
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from .intent_resolver import IntentResolver, INTENT_MAP, KNOWN_ENTITIES

# Story structure indicators
STORY_INDICATORS = [
    "searching for", "looking for", "lost", "revenge", "redemption",
    "journey to", "escape from", "fight against", "love story",
    "forbidden", "secret", "hidden", "discovers", "finds out",
    "save", "rescue", "protect", "find my"
]

# Theme keywords (rule-based)
THEME_KEYWORDS = {
    "family": ["father", "mother", "son", "daughter", "parent", "child", "family"],
    "loss": ["lost", "losing", "death", "grief", "mourn"],
    "journey": ["journey", "travel", "quest", "adventure", "voyage"],
    "love": ["love", "romance", "passion", "heart"],
    "revenge": ["revenge", "vengeance", "payback", "retribution"],
    "redemption": ["redemption", "second chance", "forgiveness"],
    "survival": ["survive", "survival", "escape", "hunted"],
    "war": ["war", "battle", "conflict", "military"],
    "space": ["space", "galaxy", "planet", "alien", "cosmos", "interstellar"],
    "supernatural": ["ghost", "vampire", "werewolf", "demon", "supernatural"],
    "crime": ["heist", "robbery", "crime", "mafia", "gangster"]
}

# Emotional tones
EMOTIONAL_TONES = {
    "sad": ["sad", "emotional", "grief", "loss", "tragic", "heartbreaking", "melancholic"],
    "happy": ["happy", "funny", "comedy", "joyful", "uplifting", "feel-good"],
    "dark": ["dark", "gritty", "noir", "psychological", "thriller", "intense"],
    "inspiring": ["inspiring", "motivational", "triumph", "overcome", "heroic"],
    "romantic": ["romantic", "love", "passion"]
}

# AMBIGUOUS TERMS - 3-tier multi-axis semantic modeling
# Each term has subject/event/setting modes for accurate matching
AMBIGUOUS_TERMS = {
    "alien": {
        "modes": {
            "subject": {
                "keywords": ["alien", "extraterrestrial", "creature", "xenomorph", "species"],
                "genres": ["horror", "science fiction"],
                "weight": 1.0
            },
            "event": {
                "keywords": ["contact", "arrival", "invasion", "first contact", "encounter"],
                "genres": ["science fiction", "drama"],
                "weight": 0.8
            },
            "setting": {
                "keywords": ["galaxy", "outer space", "interstellar", "cosmic", "planet"],
                "genres": ["science fiction", "adventure"],
                "weight": 0.6
            }
        },
        "threshold": 1.5  # Minimum score to include
    },
    "robot": {
        "modes": {
            "subject": {
                "keywords": ["robot", "android", "cyborg", "machine", "automaton"],
                "genres": ["science fiction"],
                "weight": 1.0
            },
            "event": {
                "keywords": ["ai", "artificial intelligence", "singularity", "rebellion"],
                "genres": ["science fiction", "thriller"],
                "weight": 0.8
            },
            "setting": {
                "keywords": ["future", "cyberpunk", "dystopia", "tech"],
                "genres": ["science fiction"],
                "weight": 0.6
            }
        },
        "threshold": 1.5
    },
    "zombie": {
        "modes": {
            "subject": {
                "keywords": ["zombie", "undead", "infected", "walker"],
                "genres": ["horror"],
                "weight": 1.0
            },
            "event": {
                "keywords": ["outbreak", "apocalypse", "pandemic", "survival"],
                "genres": ["horror", "thriller"],
                "weight": 0.8
            },
            "setting": {
                "keywords": ["post-apocalyptic", "wasteland"],
                "genres": ["horror"],
                "weight": 0.6
            }
        },
        "threshold": 1.5
    },
    "vampire": {
        "modes": {
            "subject": {
                "keywords": ["vampire", "blood", "immortal", "fangs"],
                "genres": ["horror"],
                "weight": 1.0
            },
            "event": {
                "keywords": ["bite", "transformation", "hunt"],
                "genres": ["horror", "thriller"],
                "weight": 0.8
            },
            "setting": {
                "keywords": ["gothic", "transylvania", "castle"],
                "genres": ["horror"],
                "weight": 0.6
            }
        },
        "threshold": 1.5
    }
}


@dataclass
class ParsedIntent:
    """Structured representation of parsed query intent with confidence"""
    mode: str  # ENTITY, THEME, STORY, MIXED, THEME_EXPANSION
    themes: List[str]
    entities: List[str]
    emotional_tone: Optional[str]
    is_story: bool
    story_confidence: float
    raw_query: str
    normalized_query: str
    is_ambiguous: bool = False  # True for aliens, robot, etc.
    expansion_data: Optional[Dict] = None  # Keywords for theme expansion
    has_antigravity: bool = False  # Enable Anti-Gravity strict filters


class PromptParser:
    """
    Hybrid Rule + Neural Prompt Understanding System
    Combines rule-based intent gating with semantic parsing.
    """
    
    def __init__(self):
        self.intent_resolver = IntentResolver()
        self._embedder = None  # Lazy load for SBERT

    @staticmethod
    def _contains_term(query: str, term: str) -> bool:
        """
        Match terms using word boundaries so "ai" does not match "maid"
        and "war" does not match "reward".
        """
        normalized_query = f" {query.lower()} "
        normalized_term = term.lower().strip()
        if not normalized_term:
            return False

        if " " in normalized_term:
            return normalized_term in normalized_query

        return re.search(rf"\b{re.escape(normalized_term)}\b", query.lower()) is not None

    def _should_enable_antigravity(self, query: str, mode: str, matched_terms: List[str]) -> bool:
        """
        Anti-gravity is useful for short, ambiguous prompts like "alien" or
        "space adventure", but it is too strict for conversational NL prompts.
        """
        if mode == "THEME_EXPANSION":
            return True

        tokens = re.findall(r"\b\w+\b", query.lower())
        connective_words = {"with", "and", "or", "but", "about", "like", "for", "that"}
        if any(token in connective_words for token in tokens):
            return False

        return len(tokens) <= 2 and len(set(matched_terms)) == 1
    
    @property
    def embedder(self):
        """Lazy load embedder for SBERT-based theme extraction"""
        if self._embedder is None:
            try:
                from .embedder import Embedder
                self._embedder = Embedder()
            except Exception:
                self._embedder = None
        return self._embedder
    
    def parse(self, query: str) -> ParsedIntent:
        """
        Full hybrid parsing pipeline:
        Stage 0: Entity override
        Stage 1: Neural + rule theme extraction
        Stage 2: Reconciliation
        Stage 3: Classification
        """
        # Normalize query ONCE (moved up from loop)
        q = query.lower().strip()
        normalized = self.intent_resolver.normalize_query(q)
        
        # Stage 0: Entity override (fastest path)
        entities = self._detect_entities(normalized, q)
        
        # Stage 1: Theme extraction (rule-based, SBERT hook ready)
        rule_themes = self._extract_themes_rule(q)
        sbert_themes = self._extract_themes_sbert(q)  # Optional neural
        
        # Stage 2: Reconciliation - union of rule + neural themes
        themes = list(set(rule_themes + sbert_themes))
        
        # Detect emotional tone
        emotion = self._detect_emotion(q)
        
        # Detect story structure with confidence
        is_story, story_confidence = self._detect_story_structure(q)
        
        # Stage 3: Classify intent type
        mode = self._classify_intent_type(q, themes, entities, is_story)
        
        # Check for AMBIGUOUS single-word queries (alien, robot, etc.)
        is_ambiguous = False
        expansion_data = None
        tokens = q.split()
        
        if len(tokens) == 1 and q in AMBIGUOUS_TERMS:
            is_ambiguous = True
            expansion_data = AMBIGUOUS_TERMS[q]
            mode = "THEME_EXPANSION"  # Override to theme expansion mode
            
        # Anti-Gravity detection (Enable filters for space, alien, robot, magic, war, love, adventure)
        antigravity_keywords = ["space", "alien", "robot", "magic", "war", "love", "romance", "adventure"]
        matched_antigravity_terms = [kw for kw in antigravity_keywords if self._contains_term(q, kw)]
        has_antigravity = self._should_enable_antigravity(q, mode, matched_antigravity_terms)
        
        return ParsedIntent(
            mode=mode,
            themes=themes,
            entities=entities,
            emotional_tone=emotion,
            is_story=is_story,
            story_confidence=story_confidence,
            raw_query=query,
            normalized_query=normalized,
            is_ambiguous=is_ambiguous,
            expansion_data=expansion_data,
            has_antigravity=has_antigravity
        )
    
    def _extract_themes_rule(self, query: str) -> List[str]:
        """Rule-based theme extraction"""
        found_themes = []
        for theme, keywords in THEME_KEYWORDS.items():
            if any(self._contains_term(query, kw) for kw in keywords):
                found_themes.append(theme)
        return found_themes
    
    # Canonical descriptions for neural theme matching
    THEME_DEFINITIONS = {
        "family": "movies about family relationships, parenting, father son bonding, mother daughter, siblings",
        "loss": "movies about grief, death, losing a loved one, mourning, tragedy",
        "journey": "movies about a long journey, road trip, quest, adventure to a new place",
        "love": "movies about romance, falling in love, relationships, dating, marriage, heartbreak",
        "revenge": "movies about seeking revenge, vengeance, getting even, retribution, payback",
        "redemption": "movies about redemption, forgiveness, second chances, atoning for past mistakes",
        "survival": "movies about survival, trapped, disaster, staying alive against odds",
        "war": "movies about war, combat, soldiers, military, battles, army",
        "space": "movies about space travel, astronauts, universe, galaxy, planets, aliens",
        "supernatural": "movies about ghosts, spirits, paranormal, haunting, demons, vampires",
        "crime": "movies about criminals, heists, gangsters, mafia, robbery, police investigation",
        "underdog": "movies about underdogs, against all odds, training, competition, winning from behind",
        "friendship": "movies about friends, buddies, friendship, loyal companions",
        "growing_up": "movies about coming of age, growing up, teenagers, school life, puberty",
        "isolation": "movies about loneliness, isolation, being alone, castaway, solitude"
    }

    def _extract_themes_sbert(self, query: str) -> List[str]:
        """
        SBERT-based theme extraction.
        Compares query embedding with cached theme embeddings.
        """
        if not self.embedder:
            return []
            
        try:
            # Lazy load theme embeddings
            if not hasattr(self, '_theme_embeddings'):
                import numpy as np
                self._theme_keys = list(self.THEME_DEFINITIONS.keys())
                descriptions = [self.THEME_DEFINITIONS[k] for k in self._theme_keys]
                self._theme_embeddings = self.embedder.embed_texts(descriptions)
                
            # Embed query
            query_vec = self.embedder.embed_texts([query])[0]
            
            # Compute cosine similarity (dot product of normalized vectors)
            # shape: (num_themes,)
            scores = np.dot(self._theme_embeddings, query_vec)
            
            # Threshold: 0.45 is usually good for SBERT semantic match
            matched_themes = []
            for idx, score in enumerate(scores):
                if score > 0.45:
                    matched_themes.append(self._theme_keys[idx])
                    
            return matched_themes
            
        except Exception as e:
            # Fail silently to fallback to rules
            return []
    
    def _detect_entities(self, normalized: str, raw_query: str) -> List[str]:
        """Detect franchise/universe entities (uses pre-normalized query)"""
        entities = []
        
        # Check if normalized matches a known entity
        if normalized in KNOWN_ENTITIES:
            entities.append(normalized)
        
        # Check raw query for entity keywords
        for entity in KNOWN_ENTITIES.keys():
            if entity in raw_query and entity not in entities:
                entities.append(entity)
        
        # Check intent resolver
        intent_name, _ = self.intent_resolver.detect_intent(raw_query)
        if intent_name and intent_name not in entities:
            entities.append(intent_name)
        
        return entities
    
    def _detect_emotion(self, query: str) -> Optional[str]:
        """Detect emotional tone"""
        for emotion, keywords in EMOTIONAL_TONES.items():
            if any(self._contains_term(query, kw) for kw in keywords):
                return emotion
        return None
    
    def _detect_story_structure(self, query: str) -> Tuple[bool, float]:
        """
        Detect if query describes a story/narrative with confidence score.
        Returns (is_story, confidence)
        """
        matches = sum(1 for ind in STORY_INDICATORS if self._contains_term(query, ind))
        
        # Calculate confidence based on matches
        if matches == 0:
            return False, 0.0
        elif matches == 1:
            return True, 0.6
        elif matches == 2:
            return True, 0.8
        else:
            return True, 0.95
    
    def _classify_intent_type(self, query: str, themes: List[str], 
                               entities: List[str], is_story: bool) -> str:
        """
        Stage 3: Classify intent into ENTITY/THEME/STORY/MIXED
        Priority: ENTITY (if franchise) > STORY (if narrative) > MIXED > THEME
        """
        # Entity mode: direct franchise/universe reference
        if entities and not is_story and len(themes) <= 1:
            return "ENTITY"
        
        # Story mode: narrative structure detected
        if is_story:
            return "STORY"
        
        # Mixed mode: multiple themes + entity or emotion
        if len(themes) >= 2 or (themes and entities):
            return "MIXED"
        
        # Theme mode: single concept
        return "THEME"
    
    def to_debug_dict(self, parsed: ParsedIntent) -> Dict:
        """Convert ParsedIntent to debug output"""
        return {
            "mode": parsed.mode,
            "themes": parsed.themes,
            "entities": parsed.entities,
            "emotional_tone": parsed.emotional_tone,
            "is_story": parsed.is_story,
            "story_confidence": parsed.story_confidence,
            "normalized_query": parsed.normalized_query
        }
