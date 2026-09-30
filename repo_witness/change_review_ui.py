"""Small Streamlit form for the two-snapshot documentation review."""
from contextlib import contextmanager
from pathlib import Path

import streamlit as st

from .analyzer import MAX_AUDIT_CLAIMS, MAX_CLAIM_CHARS
from .change_review import compare_claims, markdown_change_review, snapshot_root
from .ingest import cleanup_repository, extract_repository
from .readme_claims import discover_readmes, extract_candidate_claims


def clear_change_result() -> None:
    st.session_state.pop("change_report", None)
    st.session_state.pop("change_error", None)


def change_upload_changed() -> None:
    st.session_state["change_demo"] = False
    clear_change_result()
    st.session_state["change_editor"] = ""
    st.session_state.pop("change_documents", None)
    st.session_state.pop("change_readme", None)


def load_change_demo() -> None:
    clear_change_result()
    st.session_state["change_demo"] = True
    st.session_state.pop("change_documents", None)
    st.session_state["change_readme"] = "README.md"
    st.session_state["change_editor"] = "\n".join([
        "Declares requests as a Python dependency.",
        "Includes Docker configuration based on Python 3.11.",
        "Imports pytest in Python tests.",
    ])


@contextmanager
def snapshot_pair(app_root: Path):
    temporary = []
    try:
        if st.session_state.get("change_demo"):
            yield app_root / "sample_changes/before", app_root / "sample_changes/after"
        else:
            for key in ("change_before_zip", "change_after_zip"):
                upload = st.session_state.get(key)
                if upload is None:
                    raise ValueError("Both snapshots are required")
                temporary.append(extract_repository(upload.getvalue()))
            yield snapshot_root(temporary[0]), snapshot_root(temporary[1])
    finally:
        for root in temporary:
            cleanup_repository(root)


def select_change_readme() -> None:
    clear_change_result()
    documents = st.session_state.get("change_documents", {})
    source = st.session_state.get("change_readme")
    st.session_state["change_editor"] = "\n".join(documents.get(source, []))


def discover_change_claims(app_root: Path) -> None:
    clear_change_result()
    try:
        with snapshot_pair(app_root) as (_, after):
            documents = discover_readmes(after)
            st.session_state["change_documents"] = {
                document.path: extract_candidate_claims(document.text) for document in documents
            }
            st.session_state["change_readme"] = documents[0].path if documents else None
            select_change_readme()
    except Exception:
        st.session_state["change_error"] = "Could not read the snapshots. Check that both ZIPs contain eligible text within the upload limits."


def render_change_review(app_root: Path) -> None:
    st.markdown("## Review documentation after a code change")
    st.caption("Compare the same claims against before and after snapshots. A flag means an edit overlaps retrieved evidence; review the diff to decide whether the wording needs updating.")
    st.button("Try change-review example", on_click=load_change_demo)
    columns = st.columns(2)
    with columns[0]:
        st.file_uploader("Before repository ZIP", type=["zip"], key="change_before_zip", on_change=change_upload_changed)
    with columns[1]:
        st.file_uploader("After repository ZIP", type=["zip"], key="change_after_zip", on_change=change_upload_changed)
    st.caption("Each ZIP: 25 MiB uploaded/extracted text, 5,000 entries, 1 MiB per file. Use snapshots of the same repository. One ZIP wrapper directory is removed so commit folder names do not create false changes.")
    st.caption("Processing happens on the server; do not upload sensitive repositories. Temporary extraction is cleaned after each comparison. Change review uses deterministic local checks, with no AI API request.")
    demo = st.session_state.get("change_demo", False)
    ready = demo or bool(st.session_state.get("change_before_zip") and st.session_state.get("change_after_zip"))
    if demo:
        st.info("Synthetic example loaded: a dependency is removed, a Docker base version changes, and a test import stays unchanged.")
    st.button("Find claims in newer README", on_click=discover_change_claims, args=(app_root,), disabled=not ready)
    documents = st.session_state.get("change_documents")
    if documents is not None:
        if len(documents) > 1:
            st.selectbox("README to review", list(documents), key="change_readme", on_change=select_change_readme)
        elif not documents:
            st.info("No README found. You can enter claims manually.")
        if documents and not st.session_state.get("change_editor", "").strip():
            st.info("No claims were suggested. Enter the claims you want to review.")
    source = st.session_state.get("change_readme")
    st.caption(f"Review document excluded in both snapshots: {source}" if source else "Manual entry: no review document excluded.")
    text = st.text_area("Claims to compare", key="change_editor", height=160, on_change=clear_change_result,
                        placeholder="One claim per line")
    claims = [line.strip() for line in text.splitlines() if line.strip()]
    within_limits = len(claims) <= MAX_AUDIT_CLAIMS and all(len(c) <= MAX_CLAIM_CHARS for c in claims)
    if not within_limits:
        st.warning("Use at most 10 claims, with no more than 300 characters per claim.")
    if st.button("Run change review", type="primary", disabled=not (ready and claims and within_limits)):
        clear_change_result()
        try:
            with st.spinner("Comparing source passages…"):
                with snapshot_pair(app_root) as (before, after):
                    st.session_state["change_report"] = compare_claims(
                        before, after, claims, {claim: source for claim in claims} if source else None)
        except Exception:
            st.session_state["change_error"] = "Change review could not complete. Check both ZIPs and the displayed limits, then retry."
    if st.session_state.get("change_error"):
        st.error(st.session_state["change_error"])
    report = st.session_state.get("change_report")
    if report is None:
        return
    flagged = sum(bool(item.changes) for item in report.claims)
    st.markdown("### Change review results")
    metrics = st.columns(3)
    metrics[0].metric("Claims to review", flagged)
    metrics[1].metric("Claims compared", len(report.claims))
    metrics[2].metric("Changed text files", report.changed_file_count)
    st.caption("No flagged change does not establish that a claim is unaffected or correct. Retrieval can miss relevant code; context edits can produce extra flags. Renames appear as removal and addition.")
    labels = {"REVIEW_NEEDED": "Review needed · retrieved evidence changed",
              "NO_RETRIEVED_CHANGE": "No change found in retrieved evidence",
              "NO_EVIDENCE": "No evidence retrieved in either snapshot"}
    for item in report.claims:
        with st.container(border=True):
            st.markdown(f"#### {item.claim}")
            st.write(labels[item.status])
            st.caption(f"Before: {item.before.verdict.value} → After: {item.after.verdict.value}. These verdicts are separate from the change-review signal.")
            for change in item.changes:
                st.code(f"{change.path} · {change.change}", language=None)
                st.code(change.diff, language="diff")
            with st.expander("Inspect before and after evidence"):
                sides = st.columns(2)
                for column, label, audit in zip(sides, ("Before", "After"), (item.before, item.after)):
                    with column:
                        st.markdown(f"**{label}**")
                        st.write(audit.reasoning)
                        if not audit.evidence:
                            st.caption("No evidence retrieved.")
                        for snippet in audit.evidence:
                            st.code(f"{snippet.path}:{snippet.start_line}-{snippet.end_line}", language=None)
                            st.code(snippet.excerpt, language="text")
    st.download_button("Download change review", markdown_change_review(report), "repo-witness-change-review.md", "text/markdown")
