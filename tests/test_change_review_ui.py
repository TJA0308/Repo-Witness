import io
import zipfile
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture
def app(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    root = Path(__file__).parents[1]
    app = AppTest.from_file(str(root / "app.py"), default_timeout=15).run()
    app.radio[0].set_value("Review a code change").run()
    assert not app.exception
    return app


def button(app, label):
    return next(b for b in app.button if b.label == label)


def test_demo_flags_two_claims_and_keeps_unaffected_import(app):
    assert button(app, "Run change review").disabled
    button(app, "Try change-review example").click().run()
    button(app, "Run change review").click().run()
    assert not app.exception
    report = app.session_state["change_report"]
    assert [c.status for c in report.claims] == ["REVIEW_NEEDED", "REVIEW_NEEDED", "NO_RETRIEVED_CHANGE"]
    assert report.changed_file_count == 3
    assert app.get("download_button")[0].proto.url
    app.text_area[0].set_value("Declares urllib3 as a Python dependency.").run()
    assert "change_report" not in app.session_state
    button(app, "Run change review").click().run()
    assert app.session_state["change_report"].claims[0].excluded_document == "README.md"


def test_new_readme_discovery_and_claim_limits(app):
    button(app, "Try change-review example").click().run()
    button(app, "Find claims in newer README").click().run()
    assert not app.exception
    assert app.session_state["change_readme"] == "README.md"
    assert len(app.text_area[0].value.splitlines()) == 3
    app.text_area[0].set_value("\n".join(["Uses pytest"] * 11)).run()
    assert button(app, "Run change review").disabled


def test_worker_example_shows_all_signals_and_switching_clears_results(app):
    from repo_witness.models import Verdict

    button(app, "Try change-review example").click().run()
    button(app, "Run change review").click().run()
    app.selectbox(key="change_example").set_value("Worker service").run()
    assert "change_report" not in app.session_state
    assert app.text_area[0].value == ""
    assert button(app, "Run change review").disabled
    button(app, "Try change-review example").click().run()
    button(app, "Find claims in newer README").click().run()
    assert len(app.text_area[0].value.splitlines()) == 4
    button(app, "Run change review").click().run()
    assert not app.exception
    report = app.session_state["change_report"]
    assert report.changed_file_count == 2
    assert [c.status for c in report.claims] == [
        "REVIEW_NEEDED", "REVIEW_NEEDED", "NO_RETRIEVED_CHANGE", "NO_EVIDENCE",
    ]
    assert [c.before.verdict for c in report.claims] == [
        Verdict.VERIFIED, Verdict.VERIFIED, Verdict.VERIFIED, Verdict.INSUFFICIENT_EVIDENCE,
    ]
    assert [c.after.verdict for c in report.claims] == [
        Verdict.INSUFFICIENT_EVIDENCE, Verdict.INSUFFICIENT_EVIDENCE,
        Verdict.VERIFIED, Verdict.INSUFFICIENT_EVIDENCE,
    ]
    assert "-requires-python = \">=3.10\"" in report.claims[0].changes[0].diff
    assert "-import pytest" in report.claims[1].changes[0].diff
    assert app.get("download_button")[0].proto.url
    root = Path(__file__).parents[1] / "sample_changes/worker"
    for claim in report.claims:
        assert claim.excluded_document == "README.md"
        for side, audit in (("before", claim.before), ("after", claim.after)):
            for snippet in audit.evidence:
                assert snippet.path != "README.md"
                lines = (root / side / snippet.path).read_text().splitlines()
                assert 1 <= snippet.start_line <= snippet.end_line <= len(lines)
                assert snippet.excerpt == "\n".join(
                    f"{i + 1}: {lines[i]}" for i in range(snippet.start_line - 1, snippet.end_line)
                )
    app.selectbox(key="change_example").set_value("API service").run()
    assert "change_report" not in app.session_state
    button(app, "Try change-review example").click().run()
    assert len(app.text_area[0].value.splitlines()) == 3


def test_uploaded_wrapper_snapshots_and_partial_failure_cleanup(app, monkeypatch):
    import streamlit as st
    import repo_witness.change_review_ui as ui
    from streamlit.runtime.uploaded_file_manager import UploadedFile, UploadedFileRec
    from streamlit.proto.Common_pb2 import FileURLs
    def upload(name, payload):
        return UploadedFile(UploadedFileRec(name, name, "application/zip", payload), FileURLs())
    def archive(folder, requirements):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as z:
            z.writestr(folder + "/README.md", "Declares requests as a Python dependency.")
            z.writestr(folder + "/requirements.txt", requirements)
        return data.getvalue()
    uploads = {"change_before_zip": upload("before.zip", archive("repo-old", "requests>=2")),
               "change_after_zip": upload("after.zip", archive("repo-new", "urllib3>=2"))}
    def uploader(*args, **kwargs):
        st.session_state[kwargs["key"]] = uploads[kwargs["key"]]
        return uploads[kwargs["key"]]
    roots = []
    original_extract = ui.extract_repository
    def extract(*args, **kwargs):
        root = original_extract(*args, **kwargs)
        roots.append(root)
        return root
    monkeypatch.setattr(st, "file_uploader", uploader)
    monkeypatch.setattr(ui, "extract_repository", extract)
    app.run()
    button(app, "Find claims in newer README").click().run()
    button(app, "Run change review").click().run()
    assert not app.exception
    assert app.session_state["change_report"].claims[0].changes[0].path == "requirements.txt"
    assert all(not root.exists() for root in roots)
    uploads["change_after_zip"] = upload("invalid.zip", b"bad zip")
    app.run()
    button(app, "Run change review").click().run()
    assert not app.exception
    assert "change_report" not in app.session_state
    assert app.error
    assert all(not root.exists() for root in roots)
