import pytest

from repo_witness.models import EvidenceSnippet, Verdict
from repo_witness.verdicts import (
    CONTRADICTING,
    MENTION_ONLY,
    SPECULATIVE,
    SUPPORTING,
    aggregate_outcome,
    annotate_evidence,
    categorize_snippet,
    claim_terms,
    classify_claim,
    corrected_wording,
    has_scope_word,
    insufficient_audit,
    is_absence_claim,
    line_context,
    strip_line_prefix,
)


def _snippet(path, excerpt, start_line=1, relevance=""):
    lines = excerpt.splitlines() or [""]
    return EvidenceSnippet(
        path=path,
        start_line=start_line,
        end_line=start_line + len(lines) - 1,
        excerpt=excerpt,
        relevance=relevance,
    )


def _numbered(path, *lines, relevance=""):
    excerpt = "\n".join(f"{index}: {line}" for index, line in enumerate(lines, 1))
    return _snippet(path, excerpt, relevance=relevance)


def test_claim_terms_strip_trailing_punctuation_that_the_retriever_keeps():
    assert claim_terms("Streams events through Kafka.") == ["streams", "events", "through", "kafka"]
    assert "3.11" in claim_terms("Builds on Python 3.11.")
    assert claim_terms("Uses the API for testing") == ["api", "testing"]


def test_line_context_strips_the_excerpt_line_number_prefix_before_detecting_comments():
    assert strip_line_prefix("12: # TODO: add postgres") == "# TODO: add postgres"
    assert line_context("src/db.py", strip_line_prefix("12: # TODO: add postgres")) == "comment"
    # Without stripping, every line starts with a digit and can never look like a comment.
    assert line_context("src/db.py", "12: # TODO: add postgres") == "code"


@pytest.mark.parametrize(
    ("path", "line", "expected"),
    [
        ("src/app.py", "value = 1", "code"),
        ("src/app.py", "# a comment", "comment"),
        ("docs/guide.md", "Some prose about Redis.", "prose"),
        ("Dockerfile", "FROM python:3.11-slim", "config"),
        ("config/celery.toml", "[celery]", "config"),
        ("Makefile", "lint:", "config"),
        ("tests/test_auth.py", "import pytest", "test"),
        ("src/auth_test.py", "import pytest", "test"),
        ("spec/login.py", "import pytest", "test"),
    ],
)
def test_line_context_classifies_paths_suffixes_and_comment_lines(path, line, expected):
    assert line_context(path, line) == expected


def test_negated_claim_term_inside_a_python_string_literal_is_contradicting():
    snippet = _numbered(
        "src/storage.py",
        'STORAGE_POLICY = "This service does not use PostgreSQL; records live in memory."',
    )
    assert categorize_snippet("Uses PostgreSQL for storage.", snippet) == CONTRADICTING


def test_negation_is_detected_when_the_cue_follows_the_claim_term():
    snippet = _numbered("src/upload.py", "# FIXME: ClamAV scanning is not yet wired up.")
    assert categorize_snippet("Validates uploads with ClamAV.", snippet) == CONTRADICTING


def test_negation_cues_beyond_the_proximity_window_are_not_treated_as_contradictions():
    snippet = _numbered(
        "src/cache.py",
        "# Redis was the original plan for this subsystem, but it is not used today.",
    )
    assert categorize_snippet("Uses Redis for caching.", snippet) == MENTION_ONLY


def test_rejection_words_are_ignored_outside_prose_and_comment_lines():
    code = _numbered("src/config.py", 'SELECTED_FIELDS = ["redis", "host"]')
    comment = _numbered("src/cache.py", "# We evaluated Redis and picked Memcached.")
    assert categorize_snippet("Uses Redis for caching.", code) == SUPPORTING
    assert categorize_snippet("Uses Redis for caching.", comment) == CONTRADICTING


def test_speculative_words_are_ignored_outside_prose_and_comment_lines():
    code = _numbered("src/planner.py", "consider_postgresql = True")
    comment = _numbered("src/db.py", "# TODO: consider PostgreSQL someday")
    assert categorize_snippet("Uses PostgreSQL for storage.", code) == SUPPORTING
    assert categorize_snippet("Uses PostgreSQL for storage.", comment) == SPECULATIVE


@pytest.mark.parametrize(
    ("claim", "path", "line"),
    [
        ("Provides type annotations for public functions.", "src/introspect.py", "annotations = hints()"),
        ("Includes notification support via email.", "src/notify.py", 'notification_queue = Queue("email")'),
        ("Supports Notion export.", "src/export.py", "def export_to_notion(doc):"),
        ("Runs on the Mono runtime.", "src/runtime.py", "mono_runtime = MonoRuntime()"),
    ],
)
def test_claim_words_containing_negation_substrings_are_never_contradicted(claim, path, line):
    audit = classify_claim(claim, [_numbered(path, line)])
    assert audit.verdict == Verdict.VERIFIED


def test_word_boundaries_allow_underscores_so_identifiers_still_count_as_evidence():
    snippet = _numbered("src/app.py", 'HEALTH_CHECK_ENDPOINT = "health-check"')
    assert categorize_snippet("Provides a health-check endpoint.", snippet) == SUPPORTING
    unrelated = _numbered("src/app.py", "monolith_mode = True")
    assert categorize_snippet("Runs on the Mono runtime.", unrelated) == MENTION_ONLY


def test_a_contradicting_line_outranks_a_supporting_line_in_the_same_excerpt():
    snippet = _numbered(
        "src/app.py",
        'STORAGE_POLICY = "This service does not use PostgreSQL; data is in memory."',
        'HEALTH_CHECK_ENDPOINT = "health-check"',
    )
    claim = "Uses PostgreSQL for persistent health-check storage."
    assert categorize_snippet(claim, snippet) == CONTRADICTING


def test_snippets_without_a_word_boundary_term_match_are_mention_only():
    snippet = _numbered("src/other.py", "unrelated = compute()")
    assert categorize_snippet("Uses Kafka for streaming.", snippet) == MENTION_ONLY


def test_absence_claims_are_detected_by_word_not_by_substring():
    assert is_absence_claim("Does not collect user analytics.")
    assert is_absence_claim("Runs without a database.")
    assert not is_absence_claim("Provides type annotations for public functions.")
    assert not is_absence_claim("Supports Notion export.")
    assert not is_absence_claim("Runs on the Mono runtime.")


def test_scope_words_are_detected_without_matching_inside_longer_words():
    assert has_scope_word("Provides production-scale reliability.")
    assert has_scope_word("Retries all failed jobs.")
    assert not has_scope_word("Provides a fallback handler.")


@pytest.mark.parametrize(
    ("claim", "categories", "outcome"),
    [
        ("Uses Kafka.", [], "no_evidence"),
        ("Does not use Kafka.", [SUPPORTING], "absence_claim"),
        ("Uses Kafka.", [CONTRADICTING, SUPPORTING], "mixed"),
        ("Uses Kafka.", [CONTRADICTING, MENTION_ONLY], "contradicted"),
        ("Uses Kafka for all events.", [SUPPORTING], "scoped_support"),
        ("Uses Kafka.", [SUPPORTING], "supported"),
        ("Uses Kafka.", [SPECULATIVE, MENTION_ONLY], "weak_evidence"),
    ],
)
def test_aggregation_precedence_maps_categories_to_documented_outcomes(claim, categories, outcome):
    assert aggregate_outcome(claim, categories) == outcome


def test_absence_claims_return_insufficient_evidence_with_an_unprovable_absence_reason():
    audit = classify_claim("Does not collect user analytics.", [_numbered("src/app.py", "TELEMETRY = False")])
    assert audit.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert "cannot be established" in audit.reasoning


def test_no_evidence_returns_insufficient_evidence_and_denies_being_a_contradiction():
    audit = classify_claim("Uses Kafka for streaming.", [])
    assert audit.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert "not evidence of contradiction" in audit.reasoning


def test_only_documentation_or_planned_evidence_returns_insufficient_evidence():
    prose = classify_claim("Publishes signed releases.", [_numbered("README.md", "- Publishes signed releases.")])
    planned = classify_claim("Uses PostgreSQL.", [_numbered("src/db.py", "# TODO: consider PostgreSQL")])
    assert prose.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert planned.verdict == Verdict.INSUFFICIENT_EVIDENCE


def test_evidence_category_is_appended_to_the_existing_relevance_string():
    original = _numbered("tests/test_a.py", "import pytest", relevance="Matched: pytest; score 11")
    audit = classify_claim("Uses pytest for testing.", [original])
    assert audit.evidence[0].relevance == "Matched: pytest; score 11; evidence category: supporting"


def test_category_is_the_whole_relevance_string_when_the_retriever_supplied_none():
    annotated = annotate_evidence([_numbered("src/a.py", "x = 1")], [MENTION_ONLY])
    assert annotated[0].relevance == "evidence category: mention_only"


def test_classification_returns_copies_and_never_mutates_the_retrieved_snippets():
    original = _numbered("tests/test_a.py", "import pytest", relevance="Matched: pytest; score 11")
    classify_claim("Uses pytest for testing.", [original])
    assert original.relevance == "Matched: pytest; score 11"


def test_confidence_comes_from_the_outcome_table_and_rises_only_when_corroborated():
    single = classify_claim("Uses pytest for testing.", [_numbered("tests/test_a.py", "import pytest")])
    corroborated = classify_claim(
        "Uses pytest for testing.",
        [_numbered("tests/test_a.py", "import pytest"), _numbered("ci.yml", "- run: pytest")],
    )
    assert single.confidence == 0.70
    assert corroborated.confidence == 0.80
    assert classify_claim("Uses Kafka.", []).confidence == 0.20


def test_corrected_wording_repeats_the_claim_only_when_the_verdict_is_verified():
    claim = "Uses pytest for testing."
    assert corrected_wording(claim, Verdict.VERIFIED) == claim
    assert corrected_wording(claim, Verdict.CONTRADICTED).startswith("Repository evidence conflicts")
    assert claim.rstrip(".") in corrected_wording(claim, Verdict.PARTIALLY_VERIFIED)
    assert "not established" in corrected_wording(claim, Verdict.INSUFFICIENT_EVIDENCE)


def test_contradicted_wording_does_not_describe_the_repository_as_supporting_the_claim():
    audit = classify_claim(
        "Uses PostgreSQL for storage.",
        [_numbered("src/db.py", 'POLICY = "does not use PostgreSQL"')],
    )
    assert audit.verdict == Verdict.CONTRADICTED
    assert "provides evidence related to" not in audit.corrected_wording


def test_insufficient_audit_bypasses_the_rule_classifier_and_keeps_the_evidence():
    evidence = [_numbered("tests/test_a.py", "import pytest")]
    audit = insufficient_audit("Uses pytest for testing.", evidence, "model unavailable")
    assert audit.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert audit.reasoning == "model unavailable"
    assert [item.path for item in audit.evidence] == ["tests/test_a.py"]
