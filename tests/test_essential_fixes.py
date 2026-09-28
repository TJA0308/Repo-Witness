"""Regression examples for the concrete failures found during project review."""
from pathlib import Path

import pytest

from repo_witness.analyzer import analyze_demo, validate_claims
from repo_witness.evidence import retrieve_evidence
from repo_witness.models import EvidenceSnippet, Verdict
from repo_witness.verdicts import classify_claim


@pytest.mark.parametrize(("claim", "code"), [
    ("Uses PostgreSQL for durable storage.", "storage = {}"),
    ("Encrypts passwords with bcrypt.", "passwords = {}"),
    ("Uses Redis caching.", "redis_enabled = False"),
    ("Encrypts passwords with bcrypt.", "import bcrypt"),
    ("Uses pytest for automated testing.", "import pytest"),
])
def test_keyword_or_import_does_not_verify_behavior(tmp_path, claim, code):
    (tmp_path / "app.py").write_text(code, encoding="utf-8")
    audit = analyze_demo(tmp_path, [claim]).audits[0]
    assert audit.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert audit.evidence


@pytest.mark.parametrize(("code", "expected"), [
    ("import pytest", Verdict.VERIFIED),
    ("from pytest import fixture", Verdict.VERIFIED),
    ('text = "import pytest"', Verdict.INSUFFICIENT_EVIDENCE),
    ('"""\nimport pytest\n"""', Verdict.INSUFFICIENT_EVIDENCE),
    ("# import pytest", Verdict.INSUFFICIENT_EVIDENCE),
    ("if False:\n    import pytest", Verdict.INSUFFICIENT_EVIDENCE),
    ("from .pytest import fake", Verdict.INSUFFICIENT_EVIDENCE),
])
def test_pytest_import_check_uses_syntax(tmp_path, code, expected):
    (tmp_path / "test_app.py").write_text(code, encoding="utf-8")
    assert analyze_demo(tmp_path, ["Imports pytest in Python tests."]).audits[0].verdict == expected


@pytest.mark.parametrize(("claim", "code", "expected"), [
    ("Includes Docker configuration based on Python 3.11.", "FROM python:3.11-slim", Verdict.VERIFIED),
    ("Includes Docker configuration based on Python 3.11.", "FROM python:3.12", Verdict.INSUFFICIENT_EVIDENCE),
    ("Includes Docker configuration based on Python 3.11.", "# FROM python:3.11", Verdict.INSUFFICIENT_EVIDENCE),
    ("Includes Docker configuration based on Python 3.11 and encrypts passwords.", "FROM python:3.11", Verdict.INSUFFICIENT_EVIDENCE),
    ("Includes Docker configuration based on Python 3.11 with production-scale reliability.", "FROM python:3.11", Verdict.PARTIALLY_VERIFIED),
])
def test_docker_check_is_version_and_scope_specific(tmp_path, claim, code, expected):
    (tmp_path / "Dockerfile").write_text(code, encoding="utf-8")
    assert analyze_demo(tmp_path, [claim]).audits[0].verdict == expected


def test_import_window_of_unknown_context_cannot_verify():
    snippet = EvidenceSnippet(path="test_app.py", start_line=20, end_line=20, excerpt="20: import pytest")
    assert classify_claim("Imports pytest in Python tests.", [snippet]).verdict == Verdict.INSUFFICIENT_EVIDENCE


def test_punctuation_sql_and_nonpositive_limit(tmp_path):
    (tmp_path / "events.sql").write_text("CREATE TABLE kafka (id INT);", encoding="utf-8")
    assert retrieve_evidence(tmp_path, "Uses Kafka.")[0].path == "events.sql"
    assert retrieve_evidence(tmp_path, "Uses Kafka.", limit=0) == []
    assert retrieve_evidence(tmp_path, "Uses Kafka.", limit=-1) == []


def test_overlapping_windows_retain_conflicting_text(tmp_path):
    (tmp_path / "app.py").write_text('redis = object()\n# Redis is not used\n', encoding="utf-8")
    evidence = retrieve_evidence(tmp_path, "Uses Redis.")
    assert len(evidence) == 1
    assert "redis = object()" in evidence[0].excerpt
    assert "Redis is not used" in evidence[0].excerpt


def test_repository_is_read_once_for_multiple_claims(tmp_path, monkeypatch):
    source = tmp_path / "test_app.py"
    source.write_text("import pytest", encoding="utf-8")
    reads = []
    original = Path.read_text
    def read(path, *args, **kwargs):
        reads.append(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read)
    analyze_demo(tmp_path, ["Imports pytest in Python tests.", "Uses pytest for testing."])
    assert reads == [source]


def test_claim_limits_are_enforced_before_repository_reads(tmp_path):
    with pytest.raises(ValueError, match="10 claims"):
        analyze_demo(tmp_path, ["claim"] * 11)
    with pytest.raises(ValueError, match="300 characters"):
        validate_claims(["a" * 301])
    assert validate_claims([" ", " claim "]) == ["claim"]


@pytest.mark.parametrize(("entry", "expected"), [
    ("requests>=2.0", Verdict.VERIFIED),
    ("requests[security]>=2", Verdict.VERIFIED),
    ("# requests>=2", Verdict.INSUFFICIENT_EVIDENCE),
    ("requests-extra>=2", Verdict.INSUFFICIENT_EVIDENCE),
    ("-r requests.txt", Verdict.INSUFFICIENT_EVIDENCE),
])
def test_dependency_declaration_is_specific_and_not_a_comment(tmp_path, entry, expected):
    (tmp_path / "requirements.txt").write_text(entry, encoding="utf-8")
    audit = analyze_demo(tmp_path, ["Declares requests as a Python dependency."]).audits[0]
    assert audit.verdict == expected


def test_import_check_accepts_other_module_names(tmp_path):
    (tmp_path / "test_app.py").write_text("import unittest", encoding="utf-8")
    assert analyze_demo(tmp_path, ["Imports unittest in Python tests."]).audits[0].verdict == Verdict.VERIFIED
