import os
from html import escape
from pathlib import Path

import streamlit as st

from repo_witness.analyzer import analyze
from repo_witness.export import markdown_report
from repo_witness.ingest import cleanup_repository, extract_repository
from repo_witness.models import Verdict


APP_ROOT = Path(__file__).parent
SAMPLE_CLAIMS = [
    "Uses pytest for automated testing",
    "Includes Docker deployment configuration",
    "Uses PostgreSQL for persistent storage",
    "Deploys to Kubernetes",
]
VERDICT_UI = {
    Verdict.VERIFIED: ("Verified", "verified"),
    Verdict.PARTIALLY_VERIFIED: ("Partially verified", "partial"),
    Verdict.CONTRADICTED: ("Contradicted", "contradicted"),
    Verdict.INSUFFICIENT_EVIDENCE: ("Insufficient evidence", "insufficient"),
}


def load_styles() -> None:
    stylesheet = (APP_ROOT / "styles.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{stylesheet}</style>", unsafe_allow_html=True)


def run_repository_audit(root: Path, claims: list[str]):
    status = st.status("Scanning repository and collecting evidence…", expanded=True)
    try:
        report = analyze(root, claims)
        status.update(label="Audit complete", state="complete", expanded=False)
        return report
    except Exception:
        status.update(label="Audit could not be completed", state="error", expanded=False)
        raise


def render_header() -> None:
    model = os.environ.get("OPENAI_MODEL", "gpt-5.1")
    mode = f"Model-assisted · {escape(model)}" if os.environ.get("OPENAI_API_KEY") else "Deterministic demo"
    st.markdown(
        f"""
        <header class="rw-header">
          <div class="rw-brand-lockup">
            <div class="rw-mark" aria-hidden="true">⌕</div>
            <div>
              <div class="rw-title-row">
                <h1>RepoWitness</h1>
                <span class="rw-mode-badge">{mode}</span>
              </div>
              <p class="rw-tagline">Verify what your repository can actually prove.</p>
            </div>
          </div>
          <p class="rw-supporting">Audit technical claims against source code, tests, CI workflows, and deployment configuration.</p>
        </header>
        """,
        unsafe_allow_html=True,
    )


def render_workflow() -> None:
    st.markdown(
        """
        <div class="rw-workflow" aria-label="Audit workflow">
          <div class="rw-step"><span>1</span><strong>Add repository</strong></div>
          <div class="rw-step-line" aria-hidden="true"></div>
          <div class="rw-step"><span>2</span><strong>Enter claims</strong></div>
          <div class="rw-step-line" aria-hidden="true"></div>
          <div class="rw-step"><span>3</span><strong>Review evidence</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_results(report) -> None:
    counts = {verdict: 0 for verdict in Verdict}
    for audit in report.audits:
        counts[audit.verdict] += 1

    st.markdown('<div class="rw-section-heading"><span>Audit results</span><h2>Evidence dashboard</h2></div>', unsafe_allow_html=True)
    metric_columns = st.columns(5)
    metric_columns[0].metric("Total claims", len(report.audits))
    metric_columns[1].metric("Verified", counts[Verdict.VERIFIED])
    metric_columns[2].metric("Partial", counts[Verdict.PARTIALLY_VERIFIED])
    metric_columns[3].metric("Contradicted", counts[Verdict.CONTRADICTED])
    metric_columns[4].metric("Insufficient", counts[Verdict.INSUFFICIENT_EVIDENCE])

    st.caption(f"Analysis mode: {report.analyzer}")
    for audit in report.audits:
        status_text, status_class = VERDICT_UI[audit.verdict]
        with st.container(border=True):
            status_col, confidence_col = st.columns([4, 1])
            with status_col:
                st.markdown(f'<span class="rw-verdict rw-verdict-{status_class}">{status_text}</span>', unsafe_allow_html=True)
                st.markdown(f"### {audit.claim}")
            with confidence_col:
                st.metric("Confidence", f"{audit.confidence:.0%}")

            st.markdown("**Analysis conclusion**")
            st.write(audit.reasoning)
            st.markdown("**Suggested corrected wording**")
            st.info(audit.corrected_wording)

            evidence_count = len(audit.evidence)
            with st.expander(f"Repository evidence · {evidence_count} item{'s' if evidence_count != 1 else ''}"):
                if not audit.evidence:
                    st.caption("No relevant repository evidence was retrieved for this claim.")
                for index, evidence in enumerate(audit.evidence):
                    if index:
                        st.divider()
                    location = f"{evidence.path}:{evidence.start_line}-{evidence.end_line}"
                    st.code(location, language=None)
                    if evidence.relevance:
                        st.caption(f"Relevance · {evidence.relevance}")
                    st.code(evidence.excerpt, language="text")

    with st.container(border=True):
        st.markdown("### Export audit")
        st.caption("Download the complete verdicts, corrected wording, and line-linked evidence as Markdown.")
        st.download_button(
            "Download Markdown report",
            markdown_report(report),
            "repo-witness-audit.md",
            "text/markdown",
            use_container_width=True,
        )

    with st.expander("Limitations"):
        st.write(
            "Deterministic demo mode uses lexical evidence retrieval and fixed heuristics. It can miss synonyms, cannot prove runtime behavior, and should not replace human review. Uploaded code is inspected as text and is never executed."
        )


st.set_page_config(
    page_title="RepoWitness · Repository claim auditor",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="collapsed",
)
load_styles()
render_header()
render_workflow()

repository_col, claims_col = st.columns(2, gap="large")
with repository_col:
    with st.container(border=True):
        st.markdown('<div class="rw-card-kicker">Step 1</div>', unsafe_allow_html=True)
        st.markdown("## Repository")
        st.caption("Upload the repository snapshot you want to audit.")
        upload = st.file_uploader("Repository ZIP", type=["zip"])
        st.caption("25 MB archive · 25 MiB extracted text · 5,000 entries · 1 MiB per file")
        st.markdown(
            '<div class="rw-note"><strong>Safe scan</strong><br>Source, tests, CI, Docker, and deployment configuration are inspected. Dependencies, build outputs, binaries, secrets, and Git metadata are excluded.</div>',
            unsafe_allow_html=True,
        )
        st.caption("Uploaded repositories are processed in a temporary workspace and are not intentionally retained.")
        load_sample = st.button(
            "Load sample repository",
            help="Run the audit against the bundled synthetic repository.",
            use_container_width=True,
        )

with claims_col:
    with st.container(border=True):
        st.markdown('<div class="rw-card-kicker">Step 2</div>', unsafe_allow_html=True)
        st.markdown("## Technical claims")
        st.caption("Enter one claim per line. Be specific about technologies and behavior.")
        claims_text = st.text_area(
            "Claims to audit",
            height=220,
            placeholder="Uses pytest for automated testing\nIncludes Docker deployment configuration\nUses PostgreSQL for persistent storage",
        )
        claims = [line.strip() for line in claims_text.splitlines() if line.strip()]
        count_col, example_col = st.columns([1, 2])
        count_col.metric("Claims", len(claims))
        example_col.caption("Examples: test automation, CI enforcement, storage, deployment, security controls")

can_run = upload is not None and bool(claims)
run_audit = st.button(
    "Run repository audit",
    type="primary",
    disabled=not can_run,
    use_container_width=True,
)
if not can_run:
    st.caption("Add a repository ZIP and at least one non-empty claim to run an audit, or load the sample repository above.")

if run_audit or load_sample:
    root = None
    try:
        if load_sample:
            root = APP_ROOT / "sample_repo"
            active_claims = SAMPLE_CLAIMS
        else:
            root = extract_repository(upload.getvalue())
            active_claims = claims
        st.session_state["report"] = run_repository_audit(root, active_claims)
    except Exception as exc:
        st.error(f"Could not scan repository: {exc}")
    finally:
        if root is not None and not load_sample:
            cleanup_repository(root)

report = st.session_state.get("report")
if report:
    render_results(report)
