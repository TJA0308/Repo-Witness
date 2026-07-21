import io, zipfile
from pathlib import Path
import pytest
from repo_witness.analyzer import analyze_demo
from repo_witness.evidence import retrieve_evidence
from repo_witness.export import markdown_report
from repo_witness.ingest import MAX_FILE_BYTES, MAX_TOTAL_EXTRACTED_BYTES, cleanup_repository, extract_repository, safe_member_path, should_ignore

def make_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items(): z.writestr(name, data)
    return buf.getvalue()

def test_zip_rejects_traversal(tmp_path):
    assert safe_member_path("../escape.txt") is None
    assert safe_member_path("/absolute.txt") is None
    out = tmp_path / "out"
    extract_repository(make_zip({"../escape.txt": "bad", "safe.py": "print('ok')"}), out)
    assert (out / "safe.py").exists() and not (tmp_path / "escape.txt").exists()

def test_filtering():
    assert should_ignore(Path("node_modules/pkg/index.js"))
    assert should_ignore(Path(".env"))
    assert not should_ignore(Path("src/app.py"))

def test_oversized_file_is_not_ingested(tmp_path):
    with pytest.raises(ValueError, match="No eligible"):
        extract_repository(make_zip({"huge.txt": b"a" * (MAX_FILE_BYTES + 1)}), tmp_path / "out")

def test_total_extracted_size_limit(tmp_path):
    entries = {f"file_{index}.txt": b"a" * MAX_FILE_BYTES for index in range(26)}
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(name, data)
    with pytest.raises(ValueError, match="total extracted-size"):
        extract_repository(archive.getvalue(), tmp_path / "out")

def test_cleanup_repository(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "app.py").write_text("print('ok')", encoding="utf-8")
    cleanup_repository(root)
    assert not root.exists()

def test_empty_claims_and_evidence(tmp_path):
    (tmp_path / "app.py").write_text("import pytest\n", encoding="utf-8")
    assert analyze_demo(tmp_path, ["", "  "]).audits == []
    assert retrieve_evidence(tmp_path, "Uses PostgreSQL") == []

def test_evidence_retrieval(tmp_path):
    (tmp_path / "tests.py").write_text("import pytest\ndef test_login():\n    assert True\n", encoding="utf-8")
    found = retrieve_evidence(tmp_path, "uses pytest")
    assert found and found[0].path == "tests.py" and "pytest" in found[0].excerpt

def test_markdown_export(tmp_path):
    (tmp_path / "app.py").write_text("import pytest\n", encoding="utf-8")
    md = markdown_report(analyze_demo(tmp_path, ["Uses pytest"]))
    assert "# Repository Claim Audit" in md and "app.py:1-1" in md
