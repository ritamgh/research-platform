"""Minimal evaluator tests — all offline, no API keys needed."""
from unittest.mock import MagicMock, patch

import pytest


def _run(outputs: dict) -> MagicMock:
    r = MagicMock()
    r.outputs = outputs
    return r


def _example(inputs: dict, outputs: dict, metadata: dict | None = None) -> MagicMock:
    e = MagicMock()
    e.inputs = inputs
    e.outputs = outputs
    e.metadata = metadata or {}
    return e


# --- Faithfulness ---

class TestFaithfulnessEvaluator:
    def test_direct_route_empty_context_returns_skip(self):
        from evals.evaluators.faithfulness import faithfulness_evaluator
        run = _run({"answer": "Paris is the capital.", "retrieved_context": []})
        example = _example({"query": "Capital of France?"}, {}, metadata={"route_type": "direct"})
        result = faithfulness_evaluator(run, example)
        assert result["key"] == "faithfulness"
        assert result["score"] == 1.0
        assert "skip" in result["comment"]

    def test_non_direct_empty_context_returns_zero(self):
        from evals.evaluators.faithfulness import faithfulness_evaluator
        run = _run({"answer": "Some answer.", "retrieved_context": []})
        example = _example({"query": "q"}, {}, metadata={"route_type": "web_only"})
        result = faithfulness_evaluator(run, example)
        assert result["score"] == 0.0
        assert "retrieval_failure" in result["comment"]

    def test_unknown_route_empty_context_returns_zero(self):
        from evals.evaluators.faithfulness import faithfulness_evaluator
        run = _run({"answer": "Some answer.", "retrieved_context": []})
        example = _example({"query": "q"}, {}, metadata={})
        result = faithfulness_evaluator(run, example)
        assert result["score"] == 0.0

    def test_empty_answer_returns_zero(self):
        from evals.evaluators.faithfulness import faithfulness_evaluator
        run = _run({"answer": "", "retrieved_context": ["some context"]})
        example = _example({"query": "q"}, {})
        result = faithfulness_evaluator(run, example)
        assert result["score"] == 0.0

    def test_error_run_returns_none_score(self):
        from evals.evaluators.faithfulness import faithfulness_evaluator
        run = _run({"answer": "", "retrieved_context": [], "error": "http_504"})
        example = _example({"query": "q"}, {})
        result = faithfulness_evaluator(run, example)
        assert result["score"] is None
        assert "skipped" in result["comment"]

    def test_calls_judge_when_context_present(self):
        from evals.evaluators import faithfulness
        mock_result = {"score": 0.9, "reasoning": "well supported"}
        with patch.object(faithfulness, "judge", return_value=mock_result) as mock_judge:
            run = _run({"answer": "Some answer.", "retrieved_context": ["context text"]})
            example = _example({"query": "q"}, {}, metadata={"route_type": "web_only"})
            result = faithfulness.faithfulness_evaluator(run, example)
        mock_judge.assert_called_once()
        assert result["score"] == 0.9


# --- Relevance ---

class TestRelevanceEvaluator:
    def test_empty_answer_returns_zero(self):
        from evals.evaluators.relevance import relevance_evaluator
        run = _run({"answer": ""})
        example = _example({"query": "q"}, {"required_topics": ["topic"]})
        result = relevance_evaluator(run, example)
        assert result["score"] == 0.0

    def test_error_run_returns_none_score(self):
        from evals.evaluators.relevance import relevance_evaluator
        run = _run({"answer": "", "error": "connect_error"})
        example = _example({"query": "q"}, {})
        result = relevance_evaluator(run, example)
        assert result["score"] is None

    def test_full_topic_coverage_boosts_score(self):
        from evals.evaluators import relevance
        with patch.object(relevance, "judge", return_value={"score": 1.0, "reasoning": "good"}):
            run = _run({"answer": "RAG stands for Retrieval-Augmented Generation"})
            example = _example({"query": "What is RAG?"}, {"required_topics": ["RAG", "Retrieval-Augmented Generation"]})
            result = relevance.relevance_evaluator(run, example)
        assert result["score"] == 1.0

    def test_zero_topic_coverage_lowers_score(self):
        from evals.evaluators import relevance
        with patch.object(relevance, "judge", return_value={"score": 1.0, "reasoning": "good"}):
            run = _run({"answer": "Completely unrelated answer"})
            example = _example({"query": "q"}, {"required_topics": ["missing", "topics"]})
            result = relevance.relevance_evaluator(run, example)
        # 0.7 * 1.0 + 0.3 * 0.0 = 0.7
        assert result["score"] == pytest.approx(0.7)


# --- Citation Accuracy ---

class TestCitationAccuracyEvaluator:
    def test_min_sources_zero_returns_one(self):
        from evals.evaluators.citation_accuracy import citation_accuracy_evaluator
        run = _run({"answer": "2 + 2 = 4"})
        example = _example({"query": "q"}, {"min_sources": 0})
        result = citation_accuracy_evaluator(run, example)
        assert result["score"] == 1.0

    def test_empty_answer_returns_zero(self):
        from evals.evaluators.citation_accuracy import citation_accuracy_evaluator
        run = _run({"answer": ""})
        example = _example({"query": "q"}, {"min_sources": 1})
        result = citation_accuracy_evaluator(run, example)
        assert result["score"] == 0.0

    def test_error_run_returns_none_score(self):
        from evals.evaluators.citation_accuracy import citation_accuracy_evaluator
        run = _run({"answer": "", "error": "http_500"})
        example = _example({"query": "q"}, {"min_sources": 1})
        result = citation_accuracy_evaluator(run, example)
        assert result["score"] is None

    def test_url_citation_detected(self):
        from evals.evaluators import citation_accuracy
        with patch.object(citation_accuracy, "judge", return_value={"score": 0.8, "reasoning": "ok"}):
            run = _run({"answer": "See https://example.com for details."})
            example = _example({"query": "q"}, {"min_sources": 1})
            result = citation_accuracy.citation_accuracy_evaluator(run, example)
        # count_score=1.0, llm=0.8 → 0.5*1.0 + 0.5*0.8 = 0.9
        assert result["score"] == pytest.approx(0.9)


# --- Dataset loader ---

class TestDatasetLoader:
    def test_loads_25_examples(self):
        from evals.dataset_loader import load_local_dataset
        data = load_local_dataset()
        assert len(data) == 25

    def test_all_entries_have_required_keys(self):
        from evals.dataset_loader import load_local_dataset
        data = load_local_dataset()
        for entry in data:
            assert "id" in entry
            assert "inputs" in entry
            assert "outputs" in entry
            assert "query" in entry["inputs"]
            assert "min_sources" in entry["outputs"]

    def test_route_types_cover_all_categories(self):
        from evals.dataset_loader import load_local_dataset
        data = load_local_dataset()
        route_types = {e["route_type"] for e in data}
        assert route_types == {"web_only", "rag_only", "both", "direct"}


# --- Async helper ---

class TestRunAsyncInSync:
    def test_works_outside_event_loop(self):
        from agents.web_research.agent import _run_async_in_sync

        async def _coro():
            return 42

        assert _run_async_in_sync(_coro()) == 42

    def test_works_inside_running_loop(self):
        import asyncio
        from agents.web_research.agent import _run_async_in_sync

        async def _outer():
            async def _inner():
                return 99
            return _run_async_in_sync(_inner())

        assert asyncio.run(_outer()) == 99
