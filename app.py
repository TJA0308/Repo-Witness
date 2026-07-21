import os
from pathlib import Path

import streamlit as st

from repo_witness.analyzer import analyze
from repo_witness.export import markdown_report
from repo_witness.ingest import cleanup_repository, extract_repository


st.set_page_config(page_title="Repo Witness", page_icon="🔎", layout="wide")
st.markdown(
    """
    <style>
    .rw-badge { background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 999px; color: #3730a3; display: inline-block; font-size: .82rem; margin-top: .7rem; padding: .35rem .7rem; }
    div.stButton > button[kind="primary"] { background-color: #4f46e5; border-color: #4f46e5; }
    div.stButton > button[kind="primary"]:hover { background-color: #4338ca; border-color: #4338ca; }
    </style>
    """,
    unsafe_allow_html=True,
)

title_col, badge_col = st.columns([3, 2])
with title_col:
    st.title("🔎 Repo Witness")
with badge_col:
    if os.environ.get("OPENAI_API_KEY"):
        configured_model = os.environ.get("OPENAI_MODEL", "gpt-5.1")
        st.markdown(f'<div class="rw-badge">Model-assisted analysis · {configured_model}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="rw-badge">Demo mode · deterministic analysis</div>', unsafe_allow_html=True)
st.caption("Audit technical claims against the code that actually exists.")

with st.sidebar:
    st.subheader("Safe scan")
    st.write("Text files, tests, CI, Docker, and deployment config are scanned. Secrets, binaries, dependencies, and build outputs are excluded.")
    st.info("No API key required. Demo mode provides a deterministic repository audit; model-assisted analysis is optional.")
    st.caption("Uploaded repositories are processed in a temporary workspace and are not intentionally retained.")

upload = st.file_uploader(
    "Repository ZIP",
    type=["zip"],
    help="25 MB upload limit. The scanner accepts up to 25 MiB of extracted text across at most 5,000 archive entries; individual files over 1 MiB are skipped.",
)
claims_text = st.text_area(
    "Technical claims — one per line",
    height=180,
    placeholder="Uses pytest for automated testing\nIncludes Docker deployment configuration\nUses PostgreSQL for persistent storage",
)
claims = [line.strip() for line in claims_text.splitlines() if line.strip()]
run_audit = st.button("Run audit", type="primary", disabled=not upload or not claims)
load_sample = st.button("Load sample")
if not upload or not claims:
    st.caption("Upload a ZIP and enter at least one non-empty claim to enable Run audit.")

if run_audit or load_sample:
    root = None
    try:
        if load_sample:
            root = Path(__file__).parent / "sample_repo"
            claims = [
                "Uses pytest for automated testing",
                "Includes Docker deployment configuration",
                "Uses PostgreSQL for persistent storage",
                "Deploys to Kubernetes",
            ]
        else:
            root = extract_repository(upload.getvalue())
        with st.spinner("Retrieving evidence and classifying claims…"):
            report = analyze(root, claims)
        st.session_state["report"] = report
    except Exception as exc:
        st.error(f"Could not scan ZIP: {exc}")
    finally:
        if root is not None and upload is not None and not load_sample:
            cleanup_repository(root)

report = st.session_state.get("report")
if report:
    st.success(f"Audit complete · {report.analyzer}")
    for audit in report.audits:
        with st.container(border=True):
            st.subheader(audit.claim)
            st.metric("Verdict", audit.verdict.value, f"{audit.confidence:.0%} confidence")
            st.write(audit.reasoning)
            st.write("**Suggested wording:**", audit.corrected_wording)
            for evidence in audit.evidence:
                st.code(evidence.excerpt, language="text")
                st.caption(f"{evidence.path}:{evidence.start_line}-{evidence.end_line} · {evidence.relevance}")
    st.download_button("Export Markdown report", markdown_report(report), "repo-witness-audit.md", "text/markdown")
