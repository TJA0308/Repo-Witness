import streamlit as st
from repo_witness.analyzer import analyze
from repo_witness.export import markdown_report
from repo_witness.ingest import extract_repository

st.set_page_config(page_title="Repo Witness", page_icon="🔎", layout="wide")
st.title("🔎 Repo Witness")
st.caption("Audit technical claims against the code that actually exists.")
with st.sidebar:
    st.subheader("Safe scan")
    st.write("Text files, tests, CI, Docker, and deployment config are scanned. Secrets, binaries, dependencies, and build outputs are excluded.")
    st.info("No OPENAI_API_KEY? The deterministic demo mode still produces a complete audit.")
upload = st.file_uploader("Repository ZIP", type=["zip"])
claims_text = st.text_area("Technical claims — one per line", height=180, placeholder="Uses pytest for automated testing\nDeploys with Docker\nUses PostgreSQL")
if st.button("Run audit", type="primary"):
    claims = [line.strip() for line in claims_text.splitlines() if line.strip()]
    if not upload:
        st.error("Upload a repository ZIP first.")
    elif not claims:
        st.error("Enter at least one non-empty claim.")
    else:
        try:
            root = extract_repository(upload.getvalue())
            with st.spinner("Retrieving evidence and classifying claims…"):
                report = analyze(root, claims)
            st.session_state["report"] = report
        except Exception as exc:
            st.error(f"Could not scan ZIP: {exc}")
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

