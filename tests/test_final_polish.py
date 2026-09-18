"""User-visible workflow and deterministic regression guards, entirely offline."""
import hashlib
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from repo_witness.benchmark import format_results, run_benchmark
from repo_witness.export import markdown_report
from repo_witness.models import EvidenceSnippet, Verdict
from repo_witness.presentation import visible_evidence
from repo_witness.verdict_benchmark import run_verdict_benchmark

ROOT = Path(__file__).parents[1]


@pytest.fixture
def app(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=15).run()


def button(app, label):
    return next(item for item in app.button if item.label == label)


def load_demo(app):
    button(app, "Load sample repository").click().run()
    button(app, "Find README claims").click().run()
    return app


def test_bundled_demo_interface_and_export(app, monkeypatch):
    from streamlit.runtime.memory_media_file_storage import MemoryMediaFileStorage
    stored = {}
    original_load = MemoryMediaFileStorage.load_and_get_id
    def capture_download(storage, *args, **kwargs):
        stored["storage"] = storage
        return original_load(storage, *args, **kwargs)
    monkeypatch.setattr(MemoryMediaFileStorage, "load_and_get_id", capture_download)
    assert not app.exception
    assert button(app, "Run repository audit").disabled
    load_demo(app)
    button(app, "Run repository audit").click().run()
    assert not app.exception
    report = app.session_state["report"]
    assert [audit.verdict for audit in report.audits] == [
        Verdict.VERIFIED, Verdict.VERIFIED, Verdict.PARTIALLY_VERIFIED,
        Verdict.CONTRADICTED, Verdict.INSUFFICIENT_EVIDENCE,
    ]
    assert [(m.label, m.value) for m in app.metric if m.label in
            ("Verified", "Partially verified", "Contradicted", "Insufficient evidence")] == [
        ("Verified", "2"), ("Partially verified", "1"),
        ("Contradicted", "1"), ("Insufficient evidence", "1")]
    sources = app.session_state["report_claim_sources"]
    exported = markdown_report(report, sources)
    assert "Confidence describes heuristic strength" in exported
    assert "Suggested corrected wording" in exported
    assert app.get("download_button")[0].proto.url
    url = app.get("download_button")[0].proto.url
    downloaded = stored["storage"].get_file(url.rsplit("/", 1)[1])
    assert downloaded.content.decode("utf-8") == exported
    assert downloaded.filename == "repo-witness-audit.md"
    for audit in report.audits:
        assert sources[audit.claim] == "README.md"
        for evidence in audit.evidence:
            assert evidence.path != "README.md"
            assert not Path(evidence.path).is_absolute()
            assert f"{evidence.path}:{evidence.start_line}-{evidence.end_line}" in exported
            assert evidence.end_line <= len((ROOT / "sample_repo" / evidence.path).read_text().splitlines())
        citations = [f"{e.path}:{e.start_line}-{e.end_line}" for e in visible_evidence(audit.evidence)]
        assert len(citations) == len(set(citations))
    assert str(ROOT) not in exported
    assert "repo-witness-" not in exported
    assert len(app.info) == 3
    assert exported.count("Suggested corrected wording") == 3


def test_editor_changes_clear_report_and_preserve_only_exact_sources(app):
    load_demo(app)
    original = app.text_area[0].value.splitlines()
    button(app, "Run repository audit").click().run()
    app.text_area[0].set_value(original[0] + "\nUses pytest and provides a manual claim.").run()
    assert "report" not in app.session_state
    assert any("source mapping" in item.value for item in app.warning)
    button(app, "Run repository audit").click().run()
    assert app.session_state["report_claim_sources"] == {original[0]: "README.md"}
    assert not app.exception


def test_selection_is_explicit_and_repository_reset_clears_claims(app):
    load_demo(app)
    before = app.text_area[0].value
    app.multiselect[0].set_value([app.multiselect[0].options[0]]).run()
    assert app.text_area[0].value == before
    button(app, "Use selected claims").click().run()
    assert len(app.text_area[0].value.splitlines()) == 1
    button(app, "Load sample repository").click().run()
    assert app.text_area[0].value == ""
    assert button(app, "Run repository audit").disabled
    assert not app.exception


@pytest.mark.parametrize("kind", ["no_readme", "no_claims"])
def test_empty_discovery_states(app, monkeypatch, kind):
    import repo_witness.readme_claims as discovery
    if kind == "no_readme":
        monkeypatch.setattr(discovery, "discover_readmes", lambda root: [])
    else:
        monkeypatch.setattr(discovery, "extract_candidate_claims", lambda text: [])
    load_demo(app)
    assert app.session_state["discovery_status"] == kind
    assert not app.exception
    assert button(app, "Run repository audit").disabled


def test_openai_failure_visible_without_network(app, monkeypatch):
    import repo_witness.analyzer as analyzer
    from repo_witness.verdicts import insufficient_audit
    monkeypatch.setenv("OPENAI_API_KEY", "fake-test-key")
    monkeypatch.setattr(analyzer, "_model_claim_audit", lambda client, model, claim, evidence:
                        insufficient_audit(claim, evidence, analyzer.MODEL_ERROR_REASON))
    load_demo(app)
    button(app, "Run repository audit").click().run()
    assert not app.exception
    assert any("OpenAI analysis failed" in item.value for item in app.warning)
    assert all(a.verdict == Verdict.INSUFFICIENT_EVIDENCE for a in app.session_state["report"].audits)


def test_invalid_zip_discovery_and_audit_are_recoverable(app, monkeypatch):
    import streamlit as st
    from streamlit.runtime.uploaded_file_manager import UploadedFile, UploadedFileRec
    from streamlit.proto.Common_pb2 import FileURLs
    uploaded = UploadedFile(
        UploadedFileRec("invalid", "invalid.zip", "application/zip", b"not a zip"), FileURLs())
    # AppTest cannot operate the uploader. Inject its return value at that boundary.
    def uploader(*args, **kwargs):
        st.session_state[kwargs["key"]] = uploaded
        return uploaded
    monkeypatch.setattr(st, "file_uploader", uploader)
    app.run()
    button(app, "Find README claims").click().run()
    assert not app.exception
    assert any("Rejected ZIP" in item.value for item in app.error)
    app.text_area[0].set_value("Uses pytest").run()
    button(app, "Run repository audit").click().run()
    assert not app.exception
    assert any("Rejected ZIP" in item.value for item in app.error)
    assert "report" not in app.session_state


def test_presentation_deduplication_retains_conflicts_and_original_report():
    first = EvidenceSnippet(path="app.py", start_line=1, end_line=10,
                            excerpt="code", relevance="evidence category: supporting")
    overlap = first.model_copy(update={"start_line": 2, "excerpt": "overlap"})
    conflict = overlap.model_copy(update={"relevance": "evidence category: contradicting"})
    separate = first.model_copy(update={"start_line": 20, "end_line": 22, "excerpt": "different"})
    items = [first, overlap, conflict, separate]
    assert visible_evidence(items) == [first, conflict, separate]
    assert len(items) == 4


def test_deterministic_benchmark_guards():
    lexical = format_results(run_benchmark()).encode()
    assert hashlib.sha256(lexical).hexdigest() == "ed2933432a61b51fc34553360852d4032b94c73884d5cef9b34d3422a6a1eb2b"
    verdict = format_results(run_verdict_benchmark()).encode()
    assert hashlib.sha256(verdict).hexdigest() == "314028531c9e73052bcfd91638c773f40cadb484e01e21a0971aa4d32c82ac2e"
