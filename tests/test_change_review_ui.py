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
