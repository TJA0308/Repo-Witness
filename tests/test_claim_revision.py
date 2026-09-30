"""Exercise the revision loop through Streamlit, including provenance and reset."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from repo_witness.models import Verdict


@pytest.fixture
def app(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    root = Path(__file__).parents[1]
    app = AppTest.from_file(str(root / "app.py"), default_timeout=15).run()
    next(b for b in app.button if b.label == "Try sample audit").click().run()
    assert not app.exception
    return app


def test_revision_keeps_original_and_readme_exclusion_and_clears_stale_output(app):
    original = app.session_state["report"].model_dump()
    editor = app.text_input(key="revision_editor_2")
    assert "production-scale" not in editor.value
    app.button(key="revision_button_2").click().run()
    assert not app.exception
    result = app.session_state["revision_result_2"]
    audit = result["report"].audits[0]
    assert audit.verdict == Verdict.VERIFIED
    assert result["sources"] == {audit.claim: "README.md"}
    assert all(e.path != "README.md" for e in audit.evidence)
    assert app.session_state["report"].model_dump() == original
    assert any("Recheck verdict: Verified" in m.value for m in app.markdown)
    assert app.get("download_button")[0].proto.url
    app.text_input(key="revision_editor_2").set_value("Uses PostgreSQL.").run()
    assert "revision_result_2" not in app.session_state
    next(b for b in app.button if b.label == "Load sample repository").click().run()
    assert "revision_result_2" not in app.session_state
    assert "report" not in app.session_state
    assert not app.exception


def test_revision_empty_claim_and_failure_are_recoverable(app, monkeypatch):
    app.text_input(key="revision_editor_0").set_value("   ").run()
    assert app.button(key="revision_button_0").disabled
    app.text_input(key="revision_editor_0").set_value("Imports pytest in Python tests.").run()
    import repo_witness.analyzer as analyzer
    def fail(*args, **kwargs):
        raise RuntimeError("internal private detail")
    monkeypatch.setattr(analyzer, "analyze_demo", fail)
    app.button(key="revision_button_0").click().run()
    assert not app.exception
    assert "error" in app.session_state["revision_result_0"]
    assert all("internal private detail" not in e.value for e in app.error)
    assert "report" in app.session_state


def test_uploaded_snapshot_recheck_preserves_exclusion_and_cleans_extraction(app, monkeypatch):
    import io
    import zipfile
    import streamlit as st
    import repo_witness.ingest as ingest
    from streamlit.runtime.uploaded_file_manager import UploadedFile, UploadedFileRec
    from streamlit.proto.Common_pb2 import FileURLs

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("README.md", "Declares requests as a Python dependency.\nImports pytest in Python tests.\n")
        archive.writestr("pyproject.toml", '[project]\ndependencies = ["requests"]\n')
    uploaded = UploadedFile(UploadedFileRec("snapshot", "repo.zip", "application/zip", buffer.getvalue()), FileURLs())
    def uploader(*args, **kwargs):
        st.session_state[kwargs["key"]] = uploaded
        return uploaded
    roots = []
    extract = ingest.extract_repository
    def record_extract(*args, **kwargs):
        root = extract(*args, **kwargs)
        roots.append(root)
        return root
    monkeypatch.setattr(st, "file_uploader", uploader)
    monkeypatch.setattr(ingest, "extract_repository", record_extract)
    app.session_state["sample_loaded"] = False
    app.run()
    next(b for b in app.button if b.label == "Find README claims").click().run()
    next(b for b in app.button if b.label == "Run repository audit").click().run()
    app.text_input(key="revision_editor_0").set_value("Imports pytest in Python tests.").run()
    app.button(key="revision_button_0").click().run()
    assert not app.exception
    result = app.session_state["revision_result_0"]
    assert result["sources"] == {"Imports pytest in Python tests.": "README.md"}
    assert result["report"].audits[0].verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert all(e.path != "README.md" for e in result["report"].audits[0].evidence)
    assert len(roots) >= 3
    assert all(not root.exists() for root in roots)
