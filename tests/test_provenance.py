import sys
from pathlib import Path
from types import SimpleNamespace

from repo_witness.analyzer import analyze_demo, analyze_openai
from repo_witness.export import markdown_report
from repo_witness.models import Verdict
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


def test_manual_claims_keep_existing_behavior(tmp_path):
    claim = "Uses pytest for automated testing."
    (tmp_path / "README.md").write_text(f"- {claim}\n", encoding="utf-8")
    audit = analyze_demo(tmp_path, [claim]).audits[0]
    assert audit.verdict == Verdict.VERIFIED
    assert audit.evidence[0].path == "README.md"


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
