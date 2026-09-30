import hashlib
import io
import json
import zipfile

import pytest

from repo_witness.authored_evaluation import evaluate, validate_excerpt


def test_citation_validation_checks_text_and_repository_boundary(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "test.py").write_text("import pytest\n", encoding="utf-8")
    citation = {"path": "test.py", "start_line": 1, "end_line": 1,
                "excerpt": "1: import pytest"}
    validate_excerpt(root, citation, numbered=True)
    with pytest.raises(ValueError, match="differs"):
        validate_excerpt(root, {**citation, "excerpt": "1: import requests"}, numbered=True)
    with pytest.raises(ValueError, match="range"):
        validate_excerpt(root, {**citation, "end_line": 2}, numbered=True)
    with pytest.raises(ValueError, match="escapes"):
        validate_excerpt(root, {**citation, "path": "../outside.py"}, numbered=True)


def test_evaluation_retains_mismatch_and_rejects_changed_archive(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("fixture-abc/pyproject.toml", '[project]\nrequires-python = ">=3.9"\n')
    data = buffer.getvalue()
    archive_path = tmp_path / "fixture.zip"
    archive_path.write_bytes(data)
    case = {"id": "fixture", "repository": "fixture", "commit": "abc",
            "archive_sha256": hashlib.sha256(data).hexdigest(),
            "claim": "Fixture requires Python 3.9+.", "excluded_path": "README.md",
            "expected_verdict": "INSUFFICIENT_EVIDENCE",
            "review_source": {"path": "pyproject.toml", "start_line": 2, "end_line": 2,
                              "excerpt": 'requires-python = ">=3.9"'}}
    labels = tmp_path / "cases.json"
    labels.write_text(json.dumps({"label_status": "test", "cases": [case]}), encoding="utf-8")
    result = evaluate(tmp_path, labels)
    assert result["agreement"] == {"matching": 0, "total": 1}
    assert result["cases"][0]["actual"]["verdict"] == "VERIFIED"
    archive_path.write_bytes(data + b"modified")
    with pytest.raises(ValueError, match="hash"):
        evaluate(tmp_path, labels)
