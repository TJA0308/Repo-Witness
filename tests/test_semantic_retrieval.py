import hashlib
import json
import socket
from pathlib import Path

import pytest

from repo_witness import benchmark
from repo_witness.evidence import MAX_EXCERPT_CHARS
from repo_witness.models import EvidenceSnippet
from repo_witness.retrieval.semantic import TRUNCATION_MARKER
from repo_witness.retrieval import (
    DeterministicFakeEmbeddingProvider,
    EmbeddingProvider,
    InMemoryEmbeddingCache,
    RetrievalStrategy,
    SemanticRetrievalStrategy,
    build_candidates,
    cosine_similarity,
    retrieve_evidence_with_strategy,
)


@pytest.fixture
def semantic_repository(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text(
        "This project schedules deferred background jobs.\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "queue.py").write_text(
        "\n".join(f"# queue line {index}" for index in range(1, 26)) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "notes.md").write_text(
        "Unrelated formatting notes.\n",
        encoding="utf-8",
    )
    return tmp_path


def _strategy():
    return SemanticRetrievalStrategy(DeterministicFakeEmbeddingProvider())


def test_semantic_strategy_satisfies_retrieval_strategy_protocol():
    strategy = _strategy()

    assert isinstance(strategy, RetrievalStrategy)
    assert isinstance(strategy.cache, InMemoryEmbeddingCache)


def test_fake_provider_satisfies_embedding_provider_and_is_deterministic():
    provider = DeterministicFakeEmbeddingProvider()

    assert isinstance(provider, EmbeddingProvider)
    first = provider.embed(["deferred background jobs", "other text"])
    second = provider.embed(["deferred background jobs", "other text"])

    assert first == second
    assert len(first[0]) == provider.dimensions
    assert first[0] != first[1]


def test_candidate_construction_is_deterministic_with_stable_chunk_order(
    semantic_repository,
):
    first = build_candidates(semantic_repository)
    second = build_candidates(semantic_repository)

    assert first == second
    # Files follow the same sorted traversal as the lexical retriever, and every
    # chunk of one file stays contiguous and in ascending line order.
    expected_paths = [
        path.relative_to(semantic_repository).as_posix()
        for path in sorted(semantic_repository.rglob("*"))
        if path.is_file()
    ]
    seen_paths = [*dict.fromkeys(chunk.path for chunk in first)]
    assert seen_paths == expected_paths
    queue_chunks = [chunk for chunk in first if chunk.path == "src/queue.py"]
    starts = [chunk.start_line for chunk in queue_chunks]
    assert starts == sorted(starts)
    assert len(set(starts)) == len(starts)


def test_chunks_preserve_line_number_provenance(semantic_repository):
    lines = (
        (semantic_repository / "src" / "queue.py")
        .read_text(encoding="utf-8")
        .splitlines()
    )

    for chunk in build_candidates(semantic_repository):
        assert 1 <= chunk.start_line <= chunk.end_line
        if chunk.path == "src/queue.py":
            expected = "\n".join(lines[chunk.start_line - 1 : chunk.end_line]).strip()
            assert chunk.text == expected


def test_snippet_excerpt_lines_match_reported_line_range(semantic_repository):
    results = _strategy().retrieve(semantic_repository, "queue line 12", limit=6)

    assert results
    for snippet in results:
        assert isinstance(snippet, EvidenceSnippet)
        file_lines = (
            (semantic_repository / snippet.path).read_text(encoding="utf-8").splitlines()
        )
        first_excerpt_line = snippet.excerpt.splitlines()[0]
        assert (
            first_excerpt_line
            == f"{snippet.start_line}: {file_lines[snippet.start_line - 1]}"
        )
        assert snippet.end_line <= len(file_lines)


def test_cosine_similarity_matches_manual_computation():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([1.0, 1.0], [2.0, 2.0]) == pytest.approx(1.0)
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
    with pytest.raises(ValueError):
        cosine_similarity([1.0], [1.0, 0.0])


def test_ranking_orders_by_descending_similarity(semantic_repository):
    claim = "deferred background jobs"
    results = _strategy().retrieve(semantic_repository, claim, limit=6)

    provider = DeterministicFakeEmbeddingProvider()
    claim_vector = provider.embed([claim])[0]
    chunks = {
        (chunk.path, chunk.start_line): chunk
        for chunk in build_candidates(semantic_repository)
    }
    scores = [
        cosine_similarity(
            claim_vector,
            provider.embed([chunks[(snippet.path, snippet.start_line)].text])[0],
        )
        for snippet in results
    ]

    assert scores == sorted(scores, reverse=True)
    assert results[0].path == "README.md"


def test_ties_break_on_path_then_start_line(tmp_path):
    (tmp_path / "b.txt").write_text("alpha beta\n", encoding="utf-8")
    (tmp_path / "a.txt").write_text("alpha beta\n", encoding="utf-8")
    # Two overlapping windows of c.txt each reduce to the same chunk text, so
    # the three files and both windows tie on similarity.
    (tmp_path / "c.txt").write_text(
        "alpha beta\n" + "\n" * 10 + "alpha beta\n",
        encoding="utf-8",
    )

    results = _strategy().retrieve(tmp_path, "alpha beta", limit=4)

    assert [(snippet.path, snippet.start_line) for snippet in results] == [
        ("a.txt", 1),
        ("b.txt", 1),
        ("c.txt", 1),
        ("c.txt", 6),
    ]


def test_custom_limit_is_respected_exactly(semantic_repository):
    strategy = _strategy()

    assert len(strategy.retrieve(semantic_repository, "queue", limit=2)) == 2
    assert strategy.retrieve(semantic_repository, "queue", limit=0) == []
    unlimited = strategy.retrieve(semantic_repository, "queue", limit=100)
    assert len(unlimited) == len(build_candidates(semantic_repository))


def test_excluded_paths_are_honored_case_insensitively(semantic_repository):
    results = _strategy().retrieve(
        semantic_repository,
        "deferred background jobs",
        limit=6,
        excluded_paths=["src\\QUEUE.py"],
    )

    assert results
    assert all(snippet.path != "src/queue.py" for snippet in results)


def test_originating_readme_is_excluded_from_semantic_evidence(semantic_repository):
    results = _strategy().retrieve(
        semantic_repository,
        "deferred background jobs",
        limit=6,
        excluded_paths=["README.md"],
    )

    assert results
    assert all(snippet.path != "README.md" for snippet in results)


def test_repository_without_eligible_evidence_returns_nothing(tmp_path):
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "empty.py").write_text("\n\n", encoding="utf-8")

    assert build_candidates(tmp_path) == []
    assert _strategy().retrieve(tmp_path, "any claim", limit=6) == []
    assert _strategy().retrieve(tmp_path, "   ", limit=6) == []


def test_binary_and_ignored_content_is_never_processed(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "vendor.py").write_text("alpha\n", encoding="utf-8")
    (tmp_path / "binary.py").write_bytes(b"alpha\x00beta\n")
    (tmp_path / "keep.py").write_text("alpha\n", encoding="utf-8")

    paths = {chunk.path for chunk in build_candidates(tmp_path)}

    assert paths == {"keep.py"}


def test_provider_errors_are_not_silently_hidden(semantic_repository):
    class FailingProvider:
        model_id = "failing/provider"

        def embed(self, texts):
            raise RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        SemanticRetrievalStrategy(FailingProvider()).retrieve(
            semantic_repository,
            "claim",
            limit=3,
        )


def test_provider_returning_wrong_vector_count_raises():
    class ShortProvider:
        model_id = "short/provider"

        def embed(self, texts):
            return []

    with pytest.raises(ValueError):
        InMemoryEmbeddingCache(ShortProvider()).embed(["a"])


def test_embedding_cache_reuses_vectors_for_repeated_text():
    calls = []

    class CountingProvider:
        model_id = "counting/provider"

        def embed(self, texts):
            calls.append(list(texts))
            return DeterministicFakeEmbeddingProvider().embed(texts)

    cache = InMemoryEmbeddingCache(CountingProvider())
    first = cache.embed(["alpha", "beta", "alpha"])
    second = cache.embed(["alpha", "beta"])

    assert calls == [["alpha", "beta"]]
    assert first[0] == first[2] == second[0]
    assert cache.misses == 2
    assert cache.hits == 3


def test_embedding_cache_invalidates_when_content_changes():
    provider = DeterministicFakeEmbeddingProvider()
    cache = InMemoryEmbeddingCache(provider)

    original = cache.embed(["alpha content"])[0]
    changed = cache.embed(["beta content"])[0]

    assert original != changed
    assert changed == provider.embed(["beta content"])[0]


def test_repeated_retrieval_in_one_process_reuses_embeddings(semantic_repository):
    calls = []

    class CountingProvider:
        model_id = "counting/provider"

        def embed(self, texts):
            calls.append(list(texts))
            return DeterministicFakeEmbeddingProvider().embed(texts)

    strategy = SemanticRetrievalStrategy(CountingProvider())
    first = strategy.retrieve(semantic_repository, "deferred background jobs", limit=3)
    misses_after_first = strategy.cache.misses
    second = strategy.retrieve(semantic_repository, "deferred background jobs", limit=3)

    assert [snippet.model_dump() for snippet in first] == [
        snippet.model_dump() for snippet in second
    ]
    # The second retrieval embeds nothing: every text is already cached.
    assert strategy.cache.misses == misses_after_first
    assert sum(len(call) for call in calls) == misses_after_first


def test_provider_failure_does_not_poison_the_cache():
    class FlakyProvider:
        model_id = "flaky/provider"

        def __init__(self):
            self.fail = True

        def embed(self, texts):
            if self.fail:
                raise RuntimeError("provider unavailable")
            return DeterministicFakeEmbeddingProvider().embed(texts)

    provider = FlakyProvider()
    cache = InMemoryEmbeddingCache(provider)

    with pytest.raises(RuntimeError):
        cache.embed(["alpha"])
    assert cache._entries == {}

    provider.fail = False
    recovered = cache.embed(["alpha"])

    assert recovered == DeterministicFakeEmbeddingProvider().embed(["alpha"])


def test_cache_does_not_carry_across_processes_or_instances():
    """The cache is process-local: a new instance starts empty."""
    first = InMemoryEmbeddingCache(DeterministicFakeEmbeddingProvider())
    first.embed(["alpha"])
    second = InMemoryEmbeddingCache(DeterministicFakeEmbeddingProvider())

    assert first.misses == 1
    assert second._entries == {}
    assert second.hits == 0 and second.misses == 0


def test_overlapping_chunks_report_truthful_non_identical_ranges(semantic_repository):
    chunks = [
        chunk for chunk in build_candidates(semantic_repository)
        if chunk.path == "src/queue.py"
    ]

    assert len(chunks) > 1
    # Windows overlap, but each range is distinct and describes its own lines.
    assert len({(chunk.start_line, chunk.end_line) for chunk in chunks}) == len(chunks)
    assert any(
        later.start_line <= earlier.end_line
        for earlier, later in zip(chunks, chunks[1:])
    )


def test_long_lines_mark_excerpt_truncation_explicitly(tmp_path):
    wide_line = "x" * 400 + " alpha"
    (tmp_path / "wide.py").write_text(
        "\n".join(wide_line for _ in range(10)) + "\n",
        encoding="utf-8",
    )

    snippet = _strategy().retrieve(tmp_path, "alpha", limit=1)[0]

    assert len(snippet.excerpt) <= MAX_EXCERPT_CHARS
    assert snippet.excerpt.endswith(TRUNCATION_MARKER)
    assert snippet.end_line > snippet.start_line


def test_relevance_records_similarity_and_model_without_false_metadata(
    semantic_repository,
):
    snippet = _strategy().retrieve(semantic_repository, "deferred background jobs", limit=1)[0]

    assert snippet.relevance.startswith("Semantic cosine similarity ")
    assert "fake/deterministic-hashing-v1" in snippet.relevance
    assert not Path(snippet.path).is_absolute()
    assert snippet.path == Path(snippet.path).as_posix()


def test_cache_key_separates_providers():
    left = InMemoryEmbeddingCache(DeterministicFakeEmbeddingProvider("model/a"))
    right = InMemoryEmbeddingCache(DeterministicFakeEmbeddingProvider("model/b"))

    assert left._key("text") != right._key("text")
    assert left._key("text")[1] == hashlib.sha256(b"text").hexdigest()


def test_strategy_entry_point_accepts_semantic_strategy(semantic_repository):
    results = retrieve_evidence_with_strategy(
        _strategy(),
        semantic_repository,
        "deferred background jobs",
        limit=2,
    )

    assert len(results) == 2
    assert all(isinstance(snippet, EvidenceSnippet) for snippet in results)


def test_benchmark_default_remains_lexical(monkeypatch):
    assert benchmark.build_strategy("lexical", "unused") is None

    used_strategies = []

    def fake_run(dataset, repository, strategy):
        used_strategies.append(strategy)
        return {"metrics": {}, "cases": []}

    monkeypatch.setattr(benchmark, "run_benchmark", fake_run)

    assert benchmark.main([]) == 0
    assert used_strategies == [None]


def test_benchmark_rejects_unknown_strategy():
    with pytest.raises(ValueError, match="Unknown retrieval strategy"):
        benchmark.build_strategy("hybrid", "unused")


def test_benchmark_runs_with_an_explicit_semantic_strategy(tmp_path):
    repository_root = tmp_path / "repositories"
    fixture = repository_root / "fixture"
    fixture.mkdir(parents=True)
    (fixture / "README.md").write_text("Claims a task queue.\n", encoding="utf-8")
    (fixture / "expected.py").write_text("celery task queue worker\n", encoding="utf-8")
    (fixture / "noise.py").write_text("unrelated formatting helper\n", encoding="utf-8")
    dataset = tmp_path / "cases.json"
    dataset.write_text(
        json.dumps(
            {
                "version": 2,
                "cases": [
                    {
                        "id": "queue-case",
                        "repository": "fixture",
                        "claim": "celery task queue worker",
                        "expected_paths": ["expected.py"],
                        "excluded_source_paths": ["README.md"],
                        "case_tags": ["exact-lexical"],
                        "supported": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    results = benchmark.run_benchmark(dataset, repository_root, _strategy())
    repeated = benchmark.run_benchmark(dataset, repository_root, _strategy())

    assert benchmark.format_results(results) == benchmark.format_results(repeated)
    assert results["cases"][0]["retrieved_paths"][0] == "expected.py"
    assert results["metrics"]["provenance_exclusion_violations"] == 0
    assert "README.md" not in results["cases"][0]["retrieved_paths"]


def test_lexical_benchmark_output_is_unchanged_by_the_semantic_addition():
    default_output = benchmark.format_results(benchmark.run_benchmark())
    explicit_lexical = benchmark.format_results(
        benchmark.run_benchmark(strategy=benchmark.build_strategy("lexical", "unused"))
    )

    assert default_output == explicit_lexical
    metrics = json.loads(default_output)["metrics"]
    assert metrics["evaluated_cases"] == 36
    assert metrics["provenance_exclusion_violations"] == 0
    assert metrics["hit_rate_recall_at_1"] == pytest.approx(0.5277777777777778)
    assert metrics["mean_reciprocal_rank"] == pytest.approx(0.6513888888888889)


def test_semantic_unit_tests_require_no_network(monkeypatch, semantic_repository):
    def blocked(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)

    assert _strategy().retrieve(semantic_repository, "deferred background jobs", limit=3)
