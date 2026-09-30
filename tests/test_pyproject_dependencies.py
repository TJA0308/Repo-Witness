"""End-to-end checks of declarations, misleading TOML, citations, and abstentions."""
import pytest

from repo_witness.analyzer import analyze_demo
from repo_witness.evidence import MAX_EXCERPT_CHARS, retrieve_evidence
from repo_witness.export import markdown_report
from repo_witness.models import Verdict
from repo_witness.verdicts import classify_claim


CLAIM = "Declares requests as a Python dependency."


@pytest.mark.parametrize("entry", [
    "requests>=2.0",
    "requests[security]>=2",
    "Requests",
    "requests; python_version < '3.12'",
    "requests @ https://example.org/requests.whl",
])
def test_project_dependencies_are_declarations_not_installation(tmp_path, entry):
    source = '[project]\nname = "example"\ndependencies = [\n  "' + entry + '",\n]\n'
    (tmp_path / "pyproject.toml").write_text(source, encoding="utf-8")
    audit = analyze_demo(tmp_path, [CLAIM]).audits[0]
    assert audit.verdict == Verdict.VERIFIED
    snippet = audit.evidence[0]
    assert (snippet.start_line, snippet.end_line) == (3, 5)
    assert snippet.excerpt == "\n".join(
        f"{i + 1}: {line}" for i, line in enumerate(source.splitlines()) if 2 <= i <= 4
    )
    assert "not successful execution" in audit.reasoning


@pytest.mark.parametrize("source", [
    '[project]\n# dependencies = ["requests"]\ndependencies = []',
    '[project]\ndependencies = ["requests-extra"]',
    '[project.optional-dependencies]\ntest = ["requests"]',
    '[build-system]\nrequires = ["requests"]',
    '[dependency-groups]\ndev = ["requests"]',
    '[tool.poetry.dependencies]\nrequests = {version = "*", optional = true}',
    '[tool.example]\ndependencies = ["requests"]',
    '[project]\ndescription = \'\'\'\ndependencies = ["requests"]\n\'\'\'',
    '[project]\ndependencies = "requests"',
    '[project]\ndependencies = [42]',
    '[project]\ndependencies = ["requests", "broken ???"]',
    '[project]\ndependencies = ["requests"]\ninvalid = [',
    '[project]\ndependencies = ["requests"]\ndynamic = ["dependencies"]',
])
def test_mentions_and_invalid_metadata_do_not_verify(tmp_path, source):
    (tmp_path / "pyproject.toml").write_text(source, encoding="utf-8")
    audit = analyze_demo(tmp_path, [CLAIM]).audits[0]
    assert audit.verdict == Verdict.INSUFFICIENT_EVIDENCE


def test_exact_normalized_name_and_short_package_are_retrieved(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["Foo__bar>=1", "rq"]', encoding="utf-8"
    )
    for name in ("foo.bar", "rq"):
        audit = analyze_demo(tmp_path, [f"Declares {name} as a Python dependency."]).audits[0]
        assert audit.verdict == Verdict.VERIFIED


def test_root_dotted_assignment_and_context_free_excerpt(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        'project.dependencies = ["requests"]', encoding="utf-8"
    )
    audit = analyze_demo(tmp_path, [CLAIM]).audits[0]
    assert audit.verdict == Verdict.VERIFIED
    # Excerpt-only callers cannot establish the full TOML document's validity.
    assert classify_claim(CLAIM, audit.evidence).verdict == Verdict.INSUFFICIENT_EVIDENCE


def test_fake_assignment_in_multiline_string_is_not_cited(tmp_path):
    source = (
        '[tool.example]\ntext = \'\'\'\n[project]\ndependencies = ["requests"]\n\'\'\'\n'
        '[project]\ndependencies = ["requests"]\n'
    )
    (tmp_path / "pyproject.toml").write_text(source, encoding="utf-8")
    audit = analyze_demo(tmp_path, [CLAIM]).audits[0]
    assert audit.verdict == Verdict.VERIFIED
    assert audit.evidence[0].start_line == 7


def test_large_metadata_keeps_a_small_exact_citation(tmp_path):
    source = '[project]\ndescription = "' + "x" * 2000 + '"\ndependencies = ["requests"]'
    (tmp_path / "pyproject.toml").write_text(source, encoding="utf-8")
    for i in range(8):
        (tmp_path / f"noise{i}.txt").write_text(CLAIM * 3, encoding="utf-8")
    audit = analyze_demo(tmp_path, [CLAIM]).audits[0]
    assert audit.verdict == Verdict.VERIFIED
    assert audit.evidence[0].start_line == 3
    assert len(audit.evidence[0].excerpt) <= MAX_EXCERPT_CHARS
    assert len(audit.evidence) <= 6


def test_citation_limit_abstains_instead_of_parsing_a_truncated_array(tmp_path):
    source = '[project]\ndependencies = ["requests",\n' + '"some-package",\n' * 150 + ']'
    (tmp_path / "pyproject.toml").write_text(source, encoding="utf-8")
    assert analyze_demo(tmp_path, [CLAIM]).audits[0].verdict == Verdict.INSUFFICIENT_EVIDENCE


def test_root_scope_exclusion_and_nonpositive_limits(tmp_path):
    nested = tmp_path / "example"
    nested.mkdir()
    source = '[project]\ndependencies = ["requests"]'
    (nested / "pyproject.toml").write_text(source, encoding="utf-8")
    assert analyze_demo(tmp_path, [CLAIM]).audits[0].verdict == Verdict.INSUFFICIENT_EVIDENCE
    (tmp_path / "pyproject.toml").write_text(source, encoding="utf-8")
    audit = analyze_demo(tmp_path, [CLAIM], {CLAIM: "pyproject.toml"}).audits[0]
    assert audit.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert all(e.path != "pyproject.toml" for e in audit.evidence)
    assert retrieve_evidence(tmp_path, CLAIM, limit=0) == []


def test_unresolved_explanations_and_export_are_distinct(tmp_path):
    empty = analyze_demo(tmp_path, [CLAIM])
    assert "No relevant evidence found" in empty.audits[0].reasoning
    assert "No relevant evidence found" in markdown_report(empty)
    (tmp_path / "app.py").write_text("import bcrypt", encoding="utf-8")
    unsupported = analyze_demo(tmp_path, ["Encrypts passwords with bcrypt."])
    assert "outside the supported static checks" in unsupported.audits[0].reasoning
    assert "outside the supported static checks" in markdown_report(unsupported)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["requests-extra"]', encoding="utf-8"
    )
    unmatched = analyze_demo(tmp_path, [CLAIM])
    assert "no matching declaration" in unmatched.audits[0].reasoning
    assert unmatched.audits[0].verdict == Verdict.INSUFFICIENT_EVIDENCE
