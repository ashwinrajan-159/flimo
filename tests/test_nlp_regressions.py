from unittest.mock import MagicMock, patch

import numpy as np

from src.prompt_parser import PromptParser
from src.schemas import SearchRequest
from src.search_service import SearchService


def test_prompt_parser_does_not_enable_antigravity_for_conversational_query():
    parser = PromptParser()

    with patch.object(parser, "_extract_themes_sbert", return_value=[]):
        parsed = parser.parse("romance movie with action")

    assert parsed.has_antigravity is False
    assert "love" in parsed.themes


def test_prompt_parser_keeps_antigravity_for_ambiguous_single_word_query():
    parser = PromptParser()

    with patch.object(parser, "_extract_themes_sbert", return_value=[]):
        parsed = parser.parse("alien")

    assert parsed.mode == "THEME_EXPANSION"
    assert parsed.has_antigravity is True


def test_semantic_search_keeps_mixed_genre_result_for_natural_language_query():
    with patch("src.search_service.Embedder"), \
         patch("src.search_service.VectorStore"), \
         patch("src.search_service.PersonalizationService"):
        service = SearchService()

    service.embedder = MagicMock()
    service.embedder.embed_texts.return_value = [np.zeros(384)]
    service.vector_store = MagicMock()
    service.vector_store.search.return_value = ([0.95], ["movie_1"])
    service.ranker = MagicMock()
    service.ranker.detect_concepts.return_value = []

    mixed_result = MagicMock()
    mixed_result.content_id = "movie_1"
    mixed_result.title = "Romance Action Movie"
    mixed_result.genres = ["Romance", "Action"]
    mixed_result.rating = 7.8
    mixed_result.description = "A love story with action set pieces."
    mixed_result.content_type = "movie"

    ranked_item = MagicMock()
    ranked_item.content_id = "movie_1"
    ranked_item.title = mixed_result.title
    ranked_item.content_type = "movie"
    ranked_item.thumbnail_url = ""
    ranked_item.rating = mixed_result.rating
    ranked_item.popularity = 10.0
    ranked_item.score = 0.95
    ranked_item.reason = "Matched your query"
    service.ranker.rank_results.return_value = [ranked_item]

    with patch.object(service.prompt_parser, "_extract_themes_sbert", return_value=[]), \
         patch("src.search_service.get_content_by_ids", return_value=[mixed_result]):
        results = service.search(SearchRequest(base_prompt="romance movie with action"))

    assert [item.content_id for item in results] == ["movie_1"]
