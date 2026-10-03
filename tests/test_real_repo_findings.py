"""Small reproductions of failures observed in three pinned public repositories."""
import pytest

from repo_witness.analyzer import analyze_demo
from repo_witness.models import EvidenceSnippet, Verdict
from repo_witness.readme_claims import extract_candidate_claims
from repo_witness.verdicts import classify_claim


def _snippet(path: str, line: str) -> EvidenceSnippet:
    return EvidenceSnippet(path=path, start_line=1, end_line=1, excerpt=f"1: {line}")


def test_wrapped_readme_and_feature_bullets_are_complete_suggestions():
    readme = """# Example

The project aims to make it easy to
implement an intended API.

## Features

- Automatic help page generation
- HTTP/1.1 and HTTP/2 support

## Donate

Our group develops and supports tools.
"""
    assert extract_candidate_claims(readme) == [
        "Provides automatic help page generation.",
        "Supports HTTP/1.1 and HTTP/2.",
    ]


def test_version_claim_uses_manifest_and_keeps_broad_scope_partial(tmp_path):
    (tmp_path / "README.md").write_text("HTTPX requires Python 3.9+.\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "httpx"\nrequires-python = ">=3.9"\n', encoding="utf-8"
    )
    supported = analyze_demo(tmp_path, ["HTTPX requires Python 3.9+."],
                             {"HTTPX requires Python 3.9+.": "README.md"}).audits[0]
    assert supported.verdict == Verdict.VERIFIED
    assert supported.evidence[0].path == "pyproject.toml"
    broader = analyze_demo(tmp_path, ["HTTPX officially supports Python 3.9+."],
                           {"HTTPX officially supports Python 3.9+.": "README.md"}).audits[0]
    assert broader.verdict == Verdict.PARTIALLY_VERIFIED


def test_other_project_version_does_not_verify(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.10"\n', encoding="utf-8"
    )
    audit = analyze_demo(tmp_path, ["Requires Python 3.9+."]).audits[0]
    assert audit.verdict == Verdict.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize("source", [
    '[tool.example]\nrequires-python = ">=3.9"',
    '[project]\ndescription = \'\'\'\nrequires-python = ">=3.9"\n\'\'\'\nrequires-python = ">=3.12"',
    '[project]\nrequires-python = ">=3.9"\ninvalid = [',
    '[project]\nrequires-python = ">=3.9"\ndynamic = ["requires-python"]',
    '[project]\nrequires-python = ">=3.9,>=3.12"',
    '[project]\nrequires-python = ">=3.9,<3.8"',
    '[project]\nrequires-python = ">=3.9,!=3.9"',
    '[project]\nrequires-python = ">=3.9,broken"',
])
def test_misleading_or_invalid_python_metadata_never_verifies(tmp_path, source):
    (tmp_path / "pyproject.toml").write_text(source, encoding="utf-8")
    audit = analyze_demo(tmp_path, ["Requires Python 3.9+."]).audits[0]
    assert audit.verdict not in {Verdict.VERIFIED, Verdict.PARTIALLY_VERIFIED}


@pytest.mark.parametrize("source", [
    '[project]\nrequires-python = ">=3.9"',
    '[project]\nrequires-python = ">=3.9,<4"',
    'project.requires-python = ">=3.9"',
])
def test_python_minimum_requires_full_metadata_and_real_citation(tmp_path, source):
    (tmp_path / "pyproject.toml").write_text(source, encoding="utf-8")
    audit = analyze_demo(tmp_path, ["Requires Python 3.9+."]).audits[0]
    assert audit.verdict == Verdict.VERIFIED
    # A window alone cannot establish its TOML table or full document validity.
    assert classify_claim(audit.claim, audit.evidence).verdict != Verdict.VERIFIED


def test_unrelated_negation_in_real_documentation_is_not_a_contradiction():
    cases = [
        ("Supports HTTP/1.1 and HTTP/2.", "docs/advanced/extensions.md",
         "When using HTTP/2 there is no further response versioning included in the protocol."),
        ("Supports strict timeouts everywhere.", "docs/compatibility.md",
         "HTTPX defaults to including timeouts, while Requests has no timeouts by default."),
        ("Supports international domains and URLs.", "src/requests/models.py",
         "# Bare domains aren't valid URLs."),
        ("Supports automatic help page generation.", "docs/documentation.md",
         "A parameter merely named help does not disable the default help parameter."),
    ]
    for claim, path, line in cases:
        assert classify_claim(claim, [_snippet(path, line)]).verdict != Verdict.CONTRADICTED


def test_direct_conflicts_still_surface():
    assert classify_claim("Uses PostgreSQL for storage.", [
        _snippet("src/storage.py", "# This service does not use PostgreSQL."),
    ]).verdict == Verdict.CONTRADICTED
    assert classify_claim("Sends telemetry to an external collector.", [
        _snippet("src/app.py", "# This build does not send telemetry anywhere."),
    ]).verdict == Verdict.CONTRADICTED
    assert classify_claim("Uses SQLite for local storage.", [
        _snippet("src/config.py", '# sqlite was dropped in v2'),
    ]).verdict == Verdict.CONTRADICTED
