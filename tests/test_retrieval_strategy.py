from pathlib import Path

import pytest

from repo_witness.evidence import retrieve_evidence
from repo_witness.models import EvidenceSnippet
from repo_witness.retrieval import (
    LexicalRetrievalStrategy,
    RetrievalStrategy,
    retrieve_evidence_with_strategy,
)


def _serialized(evidence):
    return [snippet.model_dump() for snippet in evidence]


@pytest.fixture
def retrieval_repository(tmp_path):
    (tmp_path / "Docs").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "Docs" / "README.md").write_text(
        "Alpha beta documentation\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "app.py").write_text(
        "ALPHA beta implementation\n"
        "alpha worker implementation\n"
        "beta service implementation\n",
        encoding="utf-8",
    )
    return tmp_path


def test_lexical_strategy_default_output_matches_original(retrieval_repository):
    strategy = LexicalRetrievalStrategy()

    original = retrieve_evidence(retrieval_repository, "Uses alpha beta")
    adapted = strategy.retrieve(retrieval_repository, "Uses alpha beta")

    assert _serialized(adapted) == _serialized(original)


def test_lexical_strategy_custom_limit_matches_original(retrieval_repository):
    strategy = LexicalRetrievalStrategy()

    original = retrieve_evidence(
        retrieval_repository,
        "Uses alpha beta",
        limit=1,
    )
    adapted = strategy.retrieve(
        retrieval_repository,
        "Uses alpha beta",
        limit=1,
    )

    assert _serialized(adapted) == _serialized(original)
    assert len(adapted) == 1


def test_lexical_strategy_exclusion_normalization_matches_original(
    retrieval_repository,
):
    strategy = LexicalRetrievalStrategy()
    excluded_paths = ["docs\\readme.MD"]

    original = retrieve_evidence(
        retrieval_repository,
        "Uses alpha beta",
        excluded_paths=excluded_paths,
    )
    adapted = strategy.retrieve(
        retrieval_repository,
        "Uses alpha beta",
        excluded_paths=excluded_paths,
    )

    assert _serialized(adapted) == _serialized(original)
    assert all(snippet.path != "Docs/README.md" for snippet in adapted)


def test_lexical_strategy_zero_result_matches_original(retrieval_repository):
    strategy = LexicalRetrievalStrategy()

    original = retrieve_evidence(retrieval_repository, "unmatched qwerty")
    adapted = strategy.retrieve(retrieval_repository, "unmatched qwerty")

    assert adapted == original == []


def test_strategy_entry_point_forwards_arguments_and_accepts_fake_strategy(
    tmp_path,
):
    expected = [
        EvidenceSnippet(
            path="src/example.py",
            start_line=2,
            end_line=4,
            excerpt="2: example",
            relevance="fixture",
        )
    ]
    calls = []

    class FakeStrategy:
        def retrieve(self, root, claim, limit, excluded_paths=None):
            calls.append((root, claim, limit, excluded_paths))
            return expected

    strategy = FakeStrategy()
    excluded_paths = ("README.md",)

    result = retrieve_evidence_with_strategy(
        strategy,
        tmp_path,
        "Example claim",
        limit=3,
        excluded_paths=excluded_paths,
    )

    assert isinstance(strategy, RetrievalStrategy)
    assert result is expected
    assert calls == [(tmp_path, "Example claim", 3, excluded_paths)]
    assert isinstance(result[0], EvidenceSnippet)


def test_lexical_strategy_delegates_to_original_function(monkeypatch, tmp_path):
    expected = [
        EvidenceSnippet(
            path="src/example.py",
            start_line=1,
            end_line=1,
            excerpt="1: example",
            relevance="fixture",
        )
    ]
    calls = []

    def fake_retrieve(root, claim, limit, excluded_paths):
        calls.append((root, claim, limit, excluded_paths))
        return expected

    monkeypatch.setattr(
        "repo_witness.retrieval.lexical.retrieve_evidence",
        fake_retrieve,
    )
    excluded_paths = ["README.md"]

    result = LexicalRetrievalStrategy().retrieve(
        tmp_path,
        "Example claim",
        limit=2,
        excluded_paths=excluded_paths,
    )

    assert result is expected
    assert calls == [(tmp_path, "Example claim", 2, excluded_paths)]
