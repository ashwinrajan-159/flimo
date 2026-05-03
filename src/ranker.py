from typing import List, Dict, Set
import datetime
from .schemas import SearchResultItem
from .models import UnifiedContent

# Compound intent detection keywords
COMPOUND_KEYWORDS = {
    "space": ["space", "galaxy", "cosmic", "interstellar", "star wars", "trek", "alien", "planet"],
    "robot": ["robot", "android", "ai", "mech", "droid", "cyborg", "machine", "automaton"],
    "horror": ["horror", "scary", "fear", "terror", "haunted", "demon"],
    "comedy": ["comedy", "funny", "humor", "laugh", "hilarious"],
    "romance": ["romance", "love", "romantic", "relationship"],
    "war": ["war", "battle", "military", "soldier", "combat"],
    "superhero": ["superhero", "marvel", "dc", "avengers", "batman", "superman"],
    "mystery": ["mystery", "detective", "crime", "investigation"],
    "fantasy": ["fantasy", "magic", "wizard", "dragon", "mythical"],
    "action": ["action", "explosions", "fight", "martial arts", "furious"],
    "drama": ["drama", "dramatic"],
    "sci-fi": ["sci-fi", "science fiction", "scifi", "futuristic"],
    "thriller": ["thriller", "suspense", "tense", "psychological"],
    "animation": ["animation", "animated", "cartoon", "anime"],
    "family": ["family", "parent", "child", "kids", "children"],
    "documentary": ["documentary", "docuseries", "real life"]
}

# Concept -> genre/keyword mapping for content matching
CONCEPT_CONTENT_MATCH = {
    "space": ["science fiction", "sci-fi", "space", "alien"],
    "robot": ["robot", "ai", "android", "droid", "cyborg"],
    "horror": ["horror", "thriller"],
    "comedy": ["comedy"],
    "romance": ["romance", "drama"],
    "war": ["war", "action"],
    "superhero": ["action", "adventure", "superhero"],
    "mystery": ["mystery", "crime", "thriller"],
    "fantasy": ["fantasy", "adventure"],
    "action": ["action", "adventure"],
    "drama": ["drama"],
    "sci-fi": ["science fiction", "sci-fi"],
    "thriller": ["thriller", "horror", "mystery"],
    "animation": ["animation", "family"],
    "family": ["family", "animation", "comedy"],
    "documentary": ["documentary", "history"]
}

# Role-based concept classification (theme > entity > tone)
CONCEPT_ROLES = {
    "space": "theme",
    "war": "theme",
    "fantasy": "theme",
    "robot": "entity",
    "superhero": "entity",
    "mystery": "entity",
    "horror": "tone",
    "comedy": "tone",
    "romance": "tone"
}

ROLE_WEIGHTS = {
    "theme": 1.0,
    "entity": 0.8,
    "tone": 0.6
}

# Negative intent keywords
NEGATIVE_KEYWORDS = ["not", "no", "without", "exclude", "except"]

# STORY ARCHETYPES - Narrative intent patterns
STORY_ARCHETYPES = {
    "parent_searching_child": {
        "phrases": [
            "father searching for son", "parent looking for child", 
            "searching for my son", "lost child", "rescue my child",
            "find my daughter", "father saves son", "mother searching",
            "parent rescue", "save my child"
        ],
        "themes": ["family", "journey", "rescue", "love", "adventure"],
        "boost_genres": ["animation", "adventure", "drama", "family"],
        "literal_words": ["father", "son", "daughter", "mother", "parent", "child"]
    },
    "redemption_story": {
        "phrases": [
            "second chance", "redemption arc", "making things right",
            "atoning for sins", "criminal goes straight", "changed man"
        ],
        "themes": ["redemption", "change", "forgiveness", "growth"],
        "boost_genres": ["drama", "crime", "thriller"],
        "literal_words": ["redemption", "forgive", "atone"]
    },
    "underdog_triumph": {
        "phrases": [
            "underdog wins", "nobody to somebody", "against all odds",
            "unexpected hero", "zero to hero", "rags to riches"
        ],
        "themes": ["triumph", "perseverance", "success", "sports", "competition"],
        "boost_genres": ["sports", "drama", "comedy", "biography"],
        "literal_words": ["underdog", "winner", "loser"]
    },
    "forbidden_love": {
        "phrases": [
            "forbidden love", "love across boundaries", "secret romance",
            "love that cannot be", "star crossed lovers", "impossible love"
        ],
        "themes": ["love", "tragedy", "romance", "sacrifice"],
        "boost_genres": ["romance", "drama"],
        "literal_words": ["forbidden", "secret"]
    },
    "revenge_story": {
        "phrases": [
            "seeking revenge", "vengeance", "getting even",
            "avenge my family", "payback", "retribution"
        ],
        "themes": ["revenge", "justice", "action", "thriller"],
        "boost_genres": ["action", "thriller", "crime"],
        "literal_words": ["revenge", "avenge"]
    }
}

# MOOD PROFILES - Emotional constraints per mood (STRICT AND LOGIC)
# "allowed" = content MUST have one of these genres
# "forbidden" = content with these genres is DISCARDED
MOOD_PROFILE = {
    "happy": {
        "allowed": ["comedy", "family", "animation", "adventure"],
        "forbidden": ["horror", "thriller", "war", "crime"],
        "tone_keywords": ["uplifting", "fun", "joy", "heartwarming", "feel-good"]
    },
    "sad": {
        "allowed": ["drama"],
        "forbidden": ["comedy", "animation", "action", "horror", "thriller"],
        "tone_keywords": ["loss", "emotional", "journey", "grief", "tragedy"]
    },
    "dark": {
        "allowed": ["horror", "thriller", "crime", "mystery"],
        "forbidden": ["comedy", "family", "animation"],
        "tone_keywords": ["dark", "psychological", "intense", "gritty"]
    },
    "romantic": {
        "allowed": ["romance", "drama"],
        "forbidden": ["horror", "war", "action"],
        "tone_keywords": ["love", "relationship", "passion"]
    },
    "epic": {
        "allowed": ["action", "adventure", "science fiction", "fantasy", "war"],
        "forbidden": ["comedy", "romance"],
        "tone_keywords": ["heroic", "large-scale", "grand", "legendary"]
    },
    "emotional": {
        "allowed": ["drama", "romance"],
        "forbidden": ["comedy", "action", "horror", "thriller"],
        "tone_keywords": ["moving", "touching", "relationships", "heartfelt"]
    },
    "inspiring": {
        "allowed": ["biography", "sports", "drama", "documentary"],
        "forbidden": ["horror", "thriller", "crime"],
        "tone_keywords": ["triumph", "perseverance", "success", "overcome", "uplifting"]
    },
    "thoughtful": {
        "allowed": ["drama", "mystery", "documentary", "biography"],
        "forbidden": ["action", "horror", "comedy"],
        "tone_keywords": ["thought-provoking", "philosophical", "deep"]
    },
    "chill": {
        "allowed": ["documentary", "family", "animation", "comedy"],
        "forbidden": ["thriller", "action", "horror"],
        "tone_keywords": ["relaxing", "easy", "calm"]
    }
}

# HARD QUALITY GATE - Movies below this are DISCARDED (not just penalized)
MIN_RATING = 7.0


class Ranker:
    # 5-Part Personalization Formula Weights
    W_LIKE = 0.40   # Similarity to Liked content
    W_SAVE = 0.20   # Similarity to Saved content
    W_HIST = 0.15   # Similarity to Watch History
    W_COMM = 0.15   # Community Relevance (genre/topic overlap)
    W_POP  = 0.10   # General Popularity

    def __init__(self):
        pass

    def detect_concepts(self, query: str) -> List[str]:
        """Detect compound concepts in query."""
        matched = []
        query_lower = query.lower()
        for concept, keywords in COMPOUND_KEYWORDS.items():
            # Skip if this is a negative intent
            is_negative = any(f"{neg} {kw}" in query_lower for neg in NEGATIVE_KEYWORDS for kw in keywords)
            if is_negative:
                continue
            if any(kw in query_lower for kw in keywords):
                matched.append(concept)
        return matched

    def detect_negative_concepts(self, query: str) -> Set[str]:
        """Detect negative intents like 'not horror', 'no romance'."""
        q = query.lower()
        negatives = set()
        for concept, keywords in COMPOUND_KEYWORDS.items():
            for kw in keywords:
                for neg in NEGATIVE_KEYWORDS:
                    if f"{neg} {kw}" in q:
                        negatives.add(concept)
                        break
        return negatives

    def detect_story_archetype(self, query: str) -> tuple:
        """
        Detect if query matches a story archetype.
        Returns: (archetype_name, archetype_data) or (None, None)
        """
        q = query.lower()
        for archetype, data in STORY_ARCHETYPES.items():
            for phrase in data["phrases"]:
                if phrase in q:
                    return archetype, data
        return None, None

    def _content_matches_archetype(self, content: UnifiedContent, archetype_data: dict) -> float:
        """
        Score how well content matches a story archetype.
        Returns: 0.0 to 1.0 match score
        """
        score = 0.0
        desc_lower = (content.description or "").lower()
        content_genres_lower = [g.lower() for g in content.genres]
        
        Themes = archetype_data.get("themes", [])
        theme_matches = sum(1 for t in Themes if t in desc_lower)
        if Themes:
            score += (theme_matches / len(Themes)) * 0.4
        
        boost_genres = archetype_data.get("boost_genres", [])
        genre_matches = sum(1 for g in boost_genres if any(g in cg for cg in content_genres_lower))
        if boost_genres:
            score += (genre_matches / len(boost_genres)) * 0.4
        
        if any(g in content_genres_lower for g in ["family", "animation", "adventure"]):
            score += 0.2
        
        return min(1.0, score)

    def _has_literal_word_in_title(self, content: UnifiedContent, archetype_data: dict) -> bool:
        """Check if content title contains literal words that should be de-emphasized."""
        literal_words = archetype_data.get("literal_words", [])
        title_lower = content.title.lower()
        return any(w in title_lower for w in literal_words)

    def _content_matches_concept(self, content: UnifiedContent, concept: str) -> bool:
        """Check if content matches a concept via genres or description."""
        if concept not in CONCEPT_CONTENT_MATCH:
            return False
        
        match_keywords = CONCEPT_CONTENT_MATCH[concept]
        content_genres_lower = [g.lower() for g in content.genres]
        for kw in match_keywords:
            if any(kw in g for g in content_genres_lower):
                return True
        
        desc_lower = (content.description or "").lower()
        for kw in match_keywords:
            if kw in desc_lower:
                return True
        
        return False

    def _concept_match_score(self, content: UnifiedContent, concept: str) -> float:
        """Returns 1.0 for match, 0.0 for no match."""
        return 1.0 if self._content_matches_concept(content, concept) else 0.0

    def rank_results(self, contents: List[UnifiedContent], similarities: List[float], 
                     query_hint: str = "", detected_concepts: List[str] = None,
                     mood: str = None, 
                     personalization_signals: Dict[str, float] = None) -> List[SearchResultItem]:
        """
        Rank results with the 5-part formula:
        FINAL_SCORE = (Like * 0.40) + (Saved * 0.20) + (Hist * 0.15) + (Comm * 0.15) + (Pop * 0.10)
        
        similarities: List of float, conceptually representing "Relevance" (often used as Like/Saved proxy in simple search).
        personalization_signals: Dict mapping content_id -> { 'like_sim': float, 'save_sim': float, 'hist_sim': float, 'comm_score': float }
        """
        if not contents:
            return []

        if detected_concepts is None:
            detected_concepts = []

        negative_concepts = self.detect_negative_concepts(query_hint)

        # Normalize Features
        max_pop = max((c.popularity or 0) for c in contents) if contents else 1
        current_year = datetime.datetime.now().year
        
        ranked_items = []
        
        for content, base_sim in zip(contents, similarities):
            cid = content.content_id
            
            # HARD QUALITY GATE
            if content.rating is not None and content.rating < MIN_RATING:
                continue
                
            # TAG MATCHING GATE
            if detected_concepts:
                has_match = any(self._content_matches_concept(content, concept) for concept in detected_concepts)
                if not has_match:
                    continue

            # Extract Signals (default to base_sim if explicit signal missing, implies general relevance)
            # In a full vector system, we'd have separate distance metrics. 
            # Here we approximate: if personalization_signals is None, we fall back to generic ranking.
            
            if personalization_signals and cid in personalization_signals:
                signals = personalization_signals[cid]
                like_sim = signals.get('like_sim', 0.0)
                save_sim = signals.get('save_sim', 0.0)
                hist_sim = signals.get('hist_sim', 0.0)
                comm_score = signals.get('comm_score', 0.0)
            else:
                # Fallback for generic search
                like_sim = base_sim 
                save_sim = base_sim * 0.5
                hist_sim = 0.0
                comm_score = 0.0

            # ===== SIGNAL 1: LIKE SIMILARITY (40%) =====
            s1 = self.W_LIKE * like_sim
            
            # ===== SIGNAL 2: SAVED SIMILARITY (20%) =====
            s2 = self.W_SAVE * save_sim
            
            # ===== SIGNAL 3: HISTORY SIMILARITY (15%) =====
            s3 = self.W_HIST * hist_sim
            
            # ===== SIGNAL 4: COMMUNITY RELEVANCE (15%) =====
            s4 = self.W_COMM * comm_score

            # ===== SIGNAL 5: POPULARITY (10%) =====
            pop_norm = (content.popularity or 0) / max_pop if max_pop > 0 else 0
            s5 = self.W_POP * pop_norm
            
            # ===== COMPUTE FINAL SCORE =====
            final_score = s1 + s2 + s3 + s4 + s5
            
            # ===== BOOSTS (Recency, Mood, Concepts) applied ON TOP to refine ordering =====
            
            # Recency Boost (Classic logic: newer is slightly better for recs unless specified)
            year = content.release_year or 2000
            years_old = max(0, current_year - year)
            recency_score = max(0.1, 1.0 - (years_old / 20.0))
            final_score += 0.1 * recency_score # Add small boost

            # Concept Boosts
            if detected_concepts:
                for concept in detected_concepts:
                    if self._content_matches_concept(content, concept):
                        role = CONCEPT_ROLES.get(concept, "entity")
                        final_score += 0.05 * ROLE_WEIGHTS[role]

            # Archetype Boost
            archetype_name, archetype_data = self.detect_story_archetype(query_hint)
            if archetype_data:
                arch_match = self._content_matches_archetype(content, archetype_data)
                if arch_match > 0:
                    final_score += 0.08 * arch_match
            
            # Mood Boost
            mood_matched = False
            if mood and mood.lower() in MOOD_PROFILE:
                profile = MOOD_PROFILE[mood.lower()]
                content_genres_lower = [g.lower() for g in content.genres]
                for g in profile.get("allowed", []):
                    if any(g in cg for cg in content_genres_lower):
                        final_score += 0.05
                        mood_matched = True
                        break

            # Negative Penalties
            for neg in negative_concepts:
                if self._content_matches_concept(content, neg):
                    final_score -= 0.25

            # Reason Generation
            reason_parts = []
            if like_sim > 0.7: reason_parts.append("Matches your taste")
            if comm_score > 0.6: reason_parts.append("Trending in your communities")
            if save_sim > 0.7: reason_parts.append("Similar to watchlist")
            if mood_matched: reason_parts.append(f"Fits {mood} mood")
            
            ranked_items.append(SearchResultItem(
                content_id=content.content_id,
                title=content.title,
                content_type=content.content_type.value,
                thumbnail_url=content.thumbnail_url,
                rating=content.rating,
                popularity=content.popularity,
                score=final_score,
                reason=" • ".join(reason_parts) or "Recommended for you"
            ))
            
        ranked_items.sort(key=lambda x: x.score, reverse=True)
        return ranked_items
