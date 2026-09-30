"""End-to-end regressions for import retrieval and legacy Poetry declarations."""
import pytest

from repo_witness.analyzer import analyze_demo
from repo_witness.evidence import retrieve_evidence
from repo_witness.models import Verdict


IMPORT = "Imports pytest in Python tests."
DEPENDENCY = "Declares requests as a Python dependency."


def test_import_beats_keyword_noise_and_has_exact_header(tmp_path):
    (tmp_path / "tests").mkdir()
    source = 'from __future__ import annotations\n\nimport os\n\nimport pytest\n\ndef test_it():\n    pass\n'
    (tmp_path / "tests/test_basic.py").write_text(source, encoding="utf-8")
    for i in range(8):
        (tmp_path / f"noise{i}.md").write_text(IMPORT * 3, encoding="utf-8")
    audit = analyze_demo(tmp_path, [IMPORT]).audits[0]
    assert audit.verdict == Verdict.VERIFIED
    snippet = audit.evidence[0]
    assert (snippet.path, snippet.start_line, snippet.end_line) == ("tests/test_basic.py", 1, 5)
    assert snippet.excerpt == "\n".join(f"{i + 1}: {line}" for i, line in enumerate(source.splitlines()[:5]))
    assert len(audit.evidence) <= 6
    assert len(retrieve_evidence(tmp_path, IMPORT, limit=1)) == 1
    assert analyze_demo(tmp_path, [IMPORT], {IMPORT: "tests/test_basic.py"}).audits[0].verdict != Verdict.VERIFIED


@pytest.mark.parametrize("source", [
    '# import pytest\n',
    'text = "import pytest"\n',
    'text = """\nimport pytest\n"""\n',
    'if False:\n    import pytest\n',
    'def test_it():\n    import pytest\n',
    'from . import pytest\n',
    'import pytest_extra\n',
    'import pytest\ninvalid = [\n',
    '# header\n' * 41 + 'import pytest\n',
])
def test_import_lookalikes_and_unbounded_headers_abstain(tmp_path, source):
    (tmp_path / "test_app.py").write_text(source, encoding="utf-8")
    assert analyze_demo(tmp_path, [IMPORT]).audits[0].verdict == Verdict.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize("entry", [
    'requests = "^2.0"',
    'requests = {version = "^2.0", optional = false}',
    'requests = {git = "https://example.org/requests.git"}',
    'requests = {path = "../requests"}',
    '"Requests" = {url = "https://example.org/requests.whl"}',
])
def test_poetry_main_dependency_is_verified_without_installing(tmp_path, entry):
    source = '[tool.poetry.dependencies]\npython = ">=3.9"\n' + entry
    (tmp_path / "pyproject.toml").write_text(source, encoding="utf-8")
    audit = analyze_demo(tmp_path, [DEPENDENCY]).audits[0]
    assert audit.verdict == Verdict.VERIFIED
    assert audit.evidence[0].start_line == audit.evidence[0].end_line == 3
    assert audit.evidence[0].excerpt == f"3: {entry}"
    assert analyze_demo(tmp_path, [DEPENDENCY], {DEPENDENCY: "pyproject.toml"}).audits[0].verdict == Verdict.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize("source", [
    '[tool.poetry.dev-dependencies]\nrequests = "*"',
    '[tool.poetry.group.test.dependencies]\nrequests = "*"',
    '[tool.poetry.dependencies]\nrequests = {version = "*", optional = true}',
    '[tool.poetry.dependencies]\nrequests = 42',
    '[tool.poetry.dependencies]\nrequests = {version = 42}',
    '[tool.poetry.dependencies]\nrequests = ""',
    '[tool.poetry.dependencies]\nrequests-extra = "*"',
    '[tool.poetry]\ntext = \'\'\'\n[tool.poetry.dependencies]\nrequests = "*"\n\'\'\'',
    '[tool.poetry.dependencies]\nrequests = "*"\ninvalid = [',
    '[project]\ndependencies = []\n[tool.poetry.dependencies]\nrequests = "*"',
    '[project]\ndynamic = ["dependencies"]\n[tool.poetry.dependencies]\nrequests = "*"',
])
def test_poetry_wrong_groups_invalid_or_conflicting_metadata_abstain(tmp_path, source):
    (tmp_path / "pyproject.toml").write_text(source, encoding="utf-8")
    assert analyze_demo(tmp_path, [DEPENDENCY]).audits[0].verdict == Verdict.INSUFFICIENT_EVIDENCE


def test_poetry_string_decoy_is_not_cited_and_python_key_is_not_a_package(tmp_path):
    source = ('[tool.example]\ntext = \'\'\'\nrequests = "*"\n\'\'\'\n'
              '[tool.poetry.dependencies]\nrequests = "*"\npython = ">=3.9"')
    (tmp_path / "pyproject.toml").write_text(source, encoding="utf-8")
    audit = analyze_demo(tmp_path, [DEPENDENCY]).audits[0]
    assert audit.verdict == Verdict.VERIFIED
    assert audit.evidence[0].start_line == 6
    assert analyze_demo(tmp_path, ["Declares python as a Python dependency."]).audits[0].verdict == Verdict.INSUFFICIENT_EVIDENCE
