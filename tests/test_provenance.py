import sys
from pathlib import Path
from types import SimpleNamespace

from repo_witness.analyzer import (
    EVIDENCE_DELIMITER,
    MODEL_ERROR_REASON,
    MODEL_REFUSAL_REASON,
    MODEL_UNPARSED_REASON,
    OPENAI_TIMEOUT_SECONDS,
    UNTRUSTED_EVIDENCE_NOTICE,
    analyze_demo,
    analyze_openai,
)
from repo_witness.export import markdown_report
from repo_witness.models import ClaimAudit, Verdict
from repo_witness.readme_claims import discover_readmes, extract_candidate_claims


def test_originating_readme_cannot_verify_its_own_claim(tmp_path):
    claim = "Publishes signed release artifacts through an automated pipeline."
    (tmp_path / "README.md").write_text(f"# Features\n\n- {claim}\n", encoding="utf-8")
    report = analyze_demo(tmp_path, [claim], claim_sources={claim: "README.md"})
    audit = report.audits[0]
    assert audit.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert audit.evidence == []


def test_independent_source_code_can_verify_discovered_claim(tmp_path):
    claim = "Uses pytest for automated testing."
    (tmp_path / "README.md").write_text(f"- {claim}\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text("import pytest\n", encoding="utf-8")
    audit = analyze_demo(tmp_path, [claim], {claim: "README.md"}).audits[0]
    assert audit.verdict == Verdict.VERIFIED
    assert [evidence.path for evidence in audit.evidence] == ["test_app.py"]


def test_independent_configuration_can_verify_discovered_claim(tmp_path):
    claim = "Includes Docker configuration based on Python 3.11."
    (tmp_path / "README.md").write_text(f"- {claim}\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM python:3.11-slim\n", encoding="utf-8")
    audit = analyze_demo(tmp_path, [claim], {claim: "README.md"}).audits[0]
    assert audit.verdict == Verdict.VERIFIED
    assert {evidence.path for evidence in audit.evidence} == {"Dockerfile"}


def test_manual_claim_supported_only_by_documentation_is_insufficient(tmp_path):
    """A manual claim keeps its retrieved evidence, but prose alone cannot verify it."""
    claim = "Uses pytest for automated testing."
    (tmp_path / "README.md").write_text(f"- {claim}\n", encoding="utf-8")
    audit = analyze_demo(tmp_path, [claim]).audits[0]
    assert audit.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert audit.evidence[0].path == "README.md"
    assert audit.evidence[0].relevance.endswith("evidence category: mention_only")


def test_export_and_evidence_keep_relative_paths_without_source_proof(tmp_path):
    claim = "Publishes signed release artifacts through an automated pipeline."
    (tmp_path / "README.md").write_text(f"- {claim}\n", encoding="utf-8")
    report = analyze_demo(tmp_path, [claim], {claim: "README.md"})
    assert all(not Path(evidence.path).is_absolute() for audit in report.audits for evidence in audit.evidence)
    exported = markdown_report(report)
    assert "`README.md:" not in exported
    assert "No relevant evidence snippet retrieved." in exported


def test_bundled_sample_provenance_verdicts():
    sample_root = Path(__file__).parents[1] / "sample_repo"
    document = discover_readmes(sample_root)[0]
    claims = extract_candidate_claims(document.text)
    report = analyze_demo(sample_root, claims, {claim: document.path for claim in claims})
    assert [audit.verdict for audit in report.audits] == [
        Verdict.VERIFIED,
        Verdict.VERIFIED,
        Verdict.PARTIALLY_VERIFIED,
        Verdict.CONTRADICTED,
        Verdict.INSUFFICIENT_EVIDENCE,
    ]
    assert all(evidence.path != document.path for audit in report.audits for evidence in audit.evidence)


def test_model_assisted_path_does_not_classify_without_independent_evidence(tmp_path, monkeypatch):
    claim = "Publishes signed release artifacts through an automated pipeline."
    (tmp_path / "README.md").write_text(f"- {claim}\n", encoding="utf-8")

    class Responses:
        def parse(self, **kwargs):
            raise AssertionError("The model must not classify a claim with no independent evidence")

    client = SimpleNamespace(responses=Responses())
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=lambda **kwargs: client))
    audit = analyze_openai(tmp_path, [claim], claim_sources={claim: "README.md"}).audits[0]
    assert audit.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert audit.evidence == []


def _install_fake_openai(monkeypatch, parse, captured_client_kwargs=None):
    class Responses:
        def parse(self, **kwargs):
            return parse(**kwargs)

    client = SimpleNamespace(responses=Responses())

    def build_client(**kwargs):
        if captured_client_kwargs is not None:
            captured_client_kwargs.update(kwargs)
        return client

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=build_client))
    return client


def _two_claim_repository(tmp_path):
    (tmp_path / "test_app.py").write_text("import pytest\n", encoding="utf-8")
    (tmp_path / "cache.py").write_text("redis_client = Redis()\n", encoding="utf-8")
    return ["Uses pytest for automated testing.", "Uses Redis for caching."]


def _model_audit(claim):
    return ClaimAudit(
        claim="ignored",
        verdict=Verdict.VERIFIED,
        confidence=0.9,
        evidence=[],
        reasoning="model reasoning",
        corrected_wording=claim,
    )


def test_model_assisted_success_keeps_locally_retrieved_evidence_and_the_model_verdict(
    tmp_path, monkeypatch
):
    claim = "Uses pytest for automated testing."
    (tmp_path / "test_app.py").write_text("import pytest\n", encoding="utf-8")
    _install_fake_openai(
        monkeypatch,
        lambda **kwargs: SimpleNamespace(output_parsed=_model_audit(claim), output=[]),
    )

    audit = analyze_openai(tmp_path, [claim]).audits[0]

    assert audit.verdict == Verdict.VERIFIED
    assert audit.reasoning == "model reasoning"
    assert audit.claim == claim
    assert [item.path for item in audit.evidence] == ["test_app.py"]


def test_model_failure_degrades_one_claim_without_discarding_the_other_audits(
    tmp_path, monkeypatch
):
    claims = _two_claim_repository(tmp_path)
    calls = []

    def parse(**kwargs):
        calls.append(kwargs)
        if len(calls) == 2:
            raise RuntimeError("connection reset")
        return SimpleNamespace(output_parsed=_model_audit(claims[0]), output=[])

    _install_fake_openai(monkeypatch, parse)
    audits = analyze_openai(tmp_path, claims).audits

    assert len(audits) == 2
    assert audits[0].verdict == Verdict.VERIFIED
    assert audits[1].verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert audits[1].reasoning == MODEL_ERROR_REASON
    assert audits[1].evidence, "a degraded claim keeps the evidence that was retrieved for it"


def test_missing_structured_output_degrades_to_insufficient_evidence(tmp_path, monkeypatch):
    claim = "Uses pytest for automated testing."
    (tmp_path / "test_app.py").write_text("import pytest\n", encoding="utf-8")
    _install_fake_openai(
        monkeypatch, lambda **kwargs: SimpleNamespace(output_parsed=None, output=[])
    )

    audit = analyze_openai(tmp_path, [claim]).audits[0]

    assert audit.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert audit.reasoning == MODEL_UNPARSED_REASON


def test_model_refusal_is_reported_as_a_refusal_rather_than_a_parse_failure(
    tmp_path, monkeypatch
):
    claim = "Uses pytest for automated testing."
    (tmp_path / "test_app.py").write_text("import pytest\n", encoding="utf-8")
    refusal = SimpleNamespace(content=[SimpleNamespace(type="refusal")])
    _install_fake_openai(
        monkeypatch,
        lambda **kwargs: SimpleNamespace(output_parsed=None, output=[refusal]),
    )

    audit = analyze_openai(tmp_path, [claim]).audits[0]

    assert audit.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert audit.reasoning == MODEL_REFUSAL_REASON


def test_repository_evidence_is_delimited_as_untrusted_data_and_the_client_has_a_timeout(
    tmp_path, monkeypatch
):
    claim = "Uses pytest for automated testing."
    (tmp_path / "test_app.py").write_text("import pytest\n", encoding="utf-8")
    client_kwargs = {}
    parsed = []

    def parse(**kwargs):
        parsed.append(kwargs)
        return SimpleNamespace(output_parsed=_model_audit(claim), output=[])

    _install_fake_openai(monkeypatch, parse, client_kwargs)
    analyze_openai(tmp_path, [claim])

    assert client_kwargs["timeout"] == OPENAI_TIMEOUT_SECONDS
    user_message = parsed[0]["input"][1]["content"]
    assert user_message.count(EVIDENCE_DELIMITER) == 2
    assert UNTRUSTED_EVIDENCE_NOTICE in user_message
    assert user_message.index(UNTRUSTED_EVIDENCE_NOTICE) < user_message.index(EVIDENCE_DELIMITER)
