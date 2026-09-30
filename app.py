import os
import re
import zipfile
from html import escape
from pathlib import Path

import streamlit as st

from repo_witness.analyzer import analyze, MAX_AUDIT_CLAIMS, MAX_CLAIM_CHARS
from repo_witness.export import markdown_report
from repo_witness.ingest import cleanup_repository, extract_repository
from repo_witness.models import Verdict
from repo_witness.presentation import confidence_label, evidence_classification, useful_correction, visible_evidence
from repo_witness.readme_claims import discover_readmes, extract_candidate_claims


APP_ROOT = Path(__file__).parent
VERDICT_UI = {
    Verdict.VERIFIED: ("Verified", "verified"),
    Verdict.PARTIALLY_VERIFIED: ("Partially verified", "partial"),
    Verdict.CONTRADICTED: ("Contradicted", "contradicted"),
    Verdict.INSUFFICIENT_EVIDENCE: ("Insufficient evidence", "insufficient"),
}


def repository_error_message(error: Exception) -> str:
    if isinstance(error, zipfile.BadZipFile):
        return "Rejected ZIP: this file is invalid or damaged. Create a new repository ZIP and retry."
    safe_messages = (
        "Upload exceeds 25 MiB limit", "ZIP contains too many files",
        "Repository exceeds 25 MiB total extracted-size limit",
        "No eligible text files found in repository", "ZIP path escapes extraction directory",
        "Use at most 10 claims per audit", "Keep each claim within 300 characters",
    )
    if isinstance(error, ValueError) and str(error) in safe_messages:
        return f"Rejected ZIP: {error}. Check the displayed limits; unsafe or excluded files are skipped."
    return "Repository audit failed. Check that the ZIP is valid and contains eligible text files within the displayed limits, then retry."


def load_styles() -> None:
    stylesheet = (APP_ROOT / "styles.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{stylesheet}</style>", unsafe_allow_html=True)


def run_repository_audit(root: Path, claims: list[str], claim_sources: dict[str, str] | None = None):
    status = st.status("Scanning repository and collecting evidence…", expanded=True)
    try:
        report = analyze(root, claims, claim_sources=claim_sources)
        status.update(label="Audit complete", state="complete", expanded=False)
        return report
    except Exception:
        status.update(label="Audit could not be completed", state="error", expanded=False)
        raise


def render_header() -> None:
    model = os.environ.get("OPENAI_MODEL", "gpt-5.1")
    mode = f"OpenAI-assisted analysis · {escape(model)}" if os.environ.get("OPENAI_API_KEY") else "Deterministic analysis · No external AI API"
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
              <p class="rw-tagline">Catch documentation drift before you ship.</p>
            </div>
          </div>
        </header>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Static repository evidence analysis: RepoWitness does not execute or functionally test the software.")


def render_workflow() -> None:
    st.markdown(
        """
        <div class="rw-workflow" aria-label="Audit workflow">
          <div class="rw-step"><span>1</span><strong>Add repository</strong></div>
          <div class="rw-step-line" aria-hidden="true"></div>
          <div class="rw-step"><span>2</span><strong>Review claims</strong></div>
          <div class="rw-step-line" aria-hidden="true"></div>
          <div class="rw-step"><span>3</span><strong>Inspect audit</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_results(report, claim_sources: dict[str, str] | None = None) -> None:
    counts = {verdict: 0 for verdict in Verdict}
    for audit in report.audits:
        counts[audit.verdict] += 1

    st.markdown('<div class="rw-section-heading"><span>Audit results</span><h2>Evidence dashboard</h2></div>', unsafe_allow_html=True)
    metric_columns = st.columns(4)
    for column, verdict in zip(metric_columns, Verdict):
        column.metric(VERDICT_UI[verdict][0], counts[verdict])

    mode = "OpenAI-assisted analysis" if report.analyzer.startswith("OpenAI") else "Deterministic local analysis"
    st.caption(f"Analysis mode: {mode}. Confidence is heuristic strength, not a probability of correctness.")
    st.success(f"Audit complete — {len(report.audits)} claims reviewed.")
    for audit_index, audit in enumerate(report.audits):
        status_text, status_class = VERDICT_UI[audit.verdict]
        with st.container(border=True):
            status_col, confidence_col = st.columns([4, 1])
            with status_col:
                st.markdown(f'<span class="rw-verdict rw-verdict-{status_class}">{status_text}</span>', unsafe_allow_html=True)
                st.markdown(f"### {audit.claim}")
                source_path = claim_sources.get(audit.claim) if claim_sources else None
                st.caption(f"Excluded review document · {source_path}" if source_path else "Manual entry · no review document excluded")
            with confidence_col:
                st.metric("Confidence", confidence_label(audit.confidence))

            st.markdown("**Analysis conclusion**")
            st.write(audit.reasoning)
            if useful_correction(audit.claim, audit.corrected_wording):
                st.markdown("**Suggested corrected wording**")
                st.info(audit.corrected_wording)
            if audit.verdict == Verdict.INSUFFICIENT_EVIDENCE:
                st.caption("Insufficient evidence does not establish that the claim is false.")
            if report.analyzer.startswith("OpenAI") and any(phrase in audit.reasoning for phrase in ("did not complete", "declined to classify", "no structured verdict")):
                st.warning("OpenAI analysis failed or returned no verdict for this claim. Review the evidence or retry.")

            presented = visible_evidence(audit.evidence)
            evidence_count = len(presented)
            st.caption(f"Evidence · {evidence_count} distinct excerpt{'s' if evidence_count != 1 else ''}")
            with st.expander(f"Repository evidence · {evidence_count} item{'s' if evidence_count != 1 else ''}"):
                if evidence_count < len(audit.evidence):
                    st.caption("Repeated or substantially overlapping excerpts are hidden in this view.")
                if not audit.evidence:
                    st.caption("No relevant repository evidence was retrieved for this claim.")
                for index, evidence in enumerate(presented):
                    if index:
                        st.divider()
                    st.code(f"{evidence.path}:{evidence.start_line}-{evidence.end_line}", language=None)
                    classification = evidence_classification(evidence)
                    if classification:
                        st.caption(f"Evidence classification · {classification}")
                    if evidence.relevance:
                        st.caption(f"Relevance · {evidence.relevance}")
                    st.code(evidence.excerpt, language="text")

            render_claim_revision(audit, audit_index, source_path)

    with st.container(border=True):
        st.markdown("### Export audit")
        st.caption("Download the complete verdicts, corrected wording, and line-linked evidence as Markdown.")
        st.download_button(
            "Download Markdown report",
            markdown_report(report, claim_sources),
            "repo-witness-audit.md",
            "text/markdown",
            use_container_width=True,
        )

    with st.expander("Limitations"):
        st.write(
            "Deterministic local analysis uses lexical evidence retrieval and fixed rules that sort each snippet into supporting, contradicting, speculative, or mention-only evidence. Those rules can miss paraphrased contradictions and misread nearby negation. Retrieval can miss synonyms; OpenAI-assisted verdicts can also be wrong. Static evidence does not prove runtime correctness. Every verdict needs human review. Semantic retrieval is evaluation-only and is not enabled in this application."
        )


def clear_discovery_state() -> None:
    for key in (
        "readme_claims_by_path",
        "selected_readme_path",
        "discovered_claims",
        "selected_suggestions",
        "discovery_status",
        "discovery_error",
        "claims_source_path",
    ):
        st.session_state.pop(key, None)


def uploaded_repository_changed() -> None:
    st.session_state["sample_loaded"] = False
    clear_discovery_state()
    st.session_state["claims_editor"] = ""
    clear_report()


def load_sample_repository() -> None:
    st.session_state["sample_loaded"] = True
    clear_discovery_state()
    st.session_state["claims_editor"] = ""
    clear_report()


def try_sample_audit() -> None:
    """One-click demo using the same discovery and analysis as uploaded projects."""
    load_sample_repository()
    discover_repository_claims()
    st.session_state["run_sample_after_render"] = bool(st.session_state.get("discovered_claims"))


def acquire_repository() -> tuple[Path | None, bool]:
    if st.session_state.get("sample_loaded"):
        return APP_ROOT / "sample_repo", False
    upload = st.session_state.get("repository_zip")
    if upload is None:
        return None, False
    return extract_repository(upload.getvalue()), True


def set_claims_for_selected_readme() -> None:
    clear_report()
    selected_path = st.session_state.get("selected_readme_path")
    claims_by_path = st.session_state.get("readme_claims_by_path", {})
    claims = list(claims_by_path.get(selected_path, []))
    st.session_state["discovered_claims"] = claims
    st.session_state["selected_suggestions"] = claims
    st.session_state["claims_editor"] = "\n".join(claims)
    st.session_state["claims_source_path"] = selected_path
    st.session_state["discovery_status"] = "ready" if claims else "no_claims"


def discover_repository_claims() -> None:
    root = None
    temporary = False
    clear_discovery_state()
    clear_report()
    try:
        root, temporary = acquire_repository()
        if root is None:
            st.session_state["discovery_status"] = "no_repository"
            return
        documents = discover_readmes(root)
        if not documents:
            st.session_state["discovery_status"] = "no_readme"
            return
        st.session_state["readme_claims_by_path"] = {
            document.path: extract_candidate_claims(document.text) for document in documents
        }
        st.session_state["selected_readme_path"] = documents[0].path
        set_claims_for_selected_readme()
    except Exception as exc:
        st.session_state["discovery_status"] = "error"
        st.session_state["discovery_error"] = repository_error_message(exc)
    finally:
        if temporary and root is not None:
            cleanup_repository(root)


def apply_selected_suggestions() -> None:
    selected = st.session_state.get("selected_suggestions", [])
    st.session_state["claims_editor"] = "\n".join(selected)
    st.session_state["claims_source_path"] = st.session_state.get("selected_readme_path")
    clear_report()


def current_claim_sources(claims: list[str]) -> dict[str, str]:
    source = st.session_state.get("claims_source_path")
    # The entire editor belongs to the selected README review. Keep its exclusion
    # after edits and additions; do not infer provenance by comparing claim text.
    return {claim: source for claim in claims if source}


def clear_report() -> None:
    st.session_state.pop("report", None)
    st.session_state.pop("report_claim_sources", None)
    clear_revision_state()


def clear_revision_state() -> None:
    for key in list(st.session_state):
        if key.startswith("revision_"):
            st.session_state.pop(key, None)


def recheck_claim(editor_key: str, result_key: str, source_path: str | None) -> None:
    """Audit one edit without replacing the original report or losing provenance."""
    st.session_state.pop(result_key, None)
    claim = st.session_state[editor_key].strip()
    if not claim or len(claim) > MAX_CLAIM_CHARS:
        st.session_state[result_key] = {"error": "Enter a claim with 1 to 300 characters."}
        return
    root, temporary = None, False
    try:
        root, temporary = acquire_repository()
        if root is None:
            raise ValueError("No repository is available to audit")
        sources = {claim: source_path} if source_path else {}
        report = run_repository_audit(root, [claim], sources)
        st.session_state[result_key] = {"report": report, "sources": sources}
    except Exception as exc:
        st.session_state[result_key] = {"error": repository_error_message(exc)}
    finally:
        if temporary and root is not None:
            cleanup_repository(root)


def render_claim_revision(audit, index: int, source_path: str | None) -> None:
    editor_key, result_key = f"revision_editor_{index}", f"revision_result_{index}"
    suggestion = audit.claim
    if audit.verdict == Verdict.PARTIALLY_VERIFIED:
        suggestion = re.sub(r" with production-scale reliability\.?$", ".", suggestion, flags=re.I)
        suggestion = re.sub(r"officially supports Python", "requires Python", suggestion, flags=re.I)
    with st.expander("Revise and recheck this claim"):
        st.caption("Edit the claim to state a fact the cited source can establish. Rechecking keeps the original audit above; improved wording still needs evidence.")
        revised = st.text_input(
            "Revised claim", value=suggestion, key=editor_key, max_chars=MAX_CLAIM_CHARS,
            on_change=st.session_state.pop, args=(result_key, None),
        )
        st.caption(f"Review document remains excluded: {source_path}" if source_path else "Manual entry: no review document excluded.")
        st.button("Recheck revised claim", key=f"revision_button_{index}",
                  disabled=not revised.strip(), on_click=recheck_claim,
                  args=(editor_key, result_key, source_path), use_container_width=True)
        result = st.session_state.get(result_key)
        if not result:
            return
        if "error" in result:
            st.error(result["error"])
            return
        revised_report = result["report"]
        revised_audit = revised_report.audits[0]
        st.markdown(f"**Recheck verdict: {VERDICT_UI[revised_audit.verdict][0]}**")
        st.write(revised_audit.claim)
        st.write(revised_audit.reasoning)
        st.caption(f"Analysis mode: {revised_report.analyzer}. Confidence is heuristic, not a probability.")
        if revised_audit.verdict == Verdict.INSUFFICIENT_EVIDENCE:
            st.caption("Insufficient evidence does not establish that the revised claim is false.")
        for evidence in visible_evidence(revised_audit.evidence):
            st.code(f"{evidence.path}:{evidence.start_line}-{evidence.end_line}", language=None)
            st.code(evidence.excerpt, language="text")
        st.download_button("Download recheck report", markdown_report(revised_report, result["sources"]),
                           "repo-witness-recheck.md", "text/markdown", key=f"revision_export_{index}")


def render_claim_review() -> None:
    status = st.session_state.get("discovery_status")
    if not status:
        return
    with st.container(border=True):
        st.markdown('<div class="rw-card-kicker">Review</div>', unsafe_allow_html=True)
        st.markdown("## README claim suggestions")
        if status == "no_repository":
            st.warning("Add a repository before discovering README claims.")
            return
        if status == "no_readme":
            st.info("No README file was found in the safely ingested repository.")
            return
        if status == "error":
            message = st.session_state.get("discovery_error", "Unknown error")
            st.error(f"README discovery could not be completed: {message}")
            return

        claims_by_path = st.session_state.get("readme_claims_by_path", {})
        paths = list(claims_by_path)
        if len(paths) > 1:
            st.selectbox(
                "README source",
                paths,
                key="selected_readme_path",
                on_change=set_claims_for_selected_readme,
                help="Root-level README files are preferred by default.",
            )
            st.caption(f"Found {len(paths)} README files. Select the source you want to review.")
        elif paths:
            st.caption(f"README source · {paths[0]}")

        st.caption("Select suggestions, then use the button to replace the editor contents. Edits in the editor are the claims that will be audited.")
        discovered = st.session_state.get("discovered_claims", [])
        if not discovered:
            st.warning("No defensible technical claims were discovered in the selected README. You can still enter claims manually.")
            return
        selected = st.multiselect(
            "Select suggested claims",
            options=discovered,
            key="selected_suggestions",
            help="Selection changes take effect only when you click Use selected claims. This replaces manual edits.",
        )
        action_col, count_col = st.columns([2, 1])
        action_col.button(
            "Use selected claims" if selected else "Clear claim list",
            on_click=apply_selected_suggestions,
            use_container_width=True,
        )
        count_col.metric("Selected", len(selected))
        if not selected:
            st.caption("Clear the claim list, or continue with manual claim entry.")


st.set_page_config(
    page_title="RepoWitness · Repository claim auditor",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="collapsed",
)
load_styles()
render_header()
render_workflow()
st.caption("Fast-moving and AI-assisted development can leave README claims describing planned, replaced, partial, or removed features. Review those claims before release, submission, or project review.")

st.session_state.setdefault("sample_loaded", False)
st.session_state.setdefault("claims_editor", "")

with st.expander("How the audit works · supported checks and limits"):
    st.markdown("""
1. **Read text.** Extract eligible files from the ZIP; never execute repository code.
2. **Review claims.** Discover README suggestions or enter your own. The selected README stays excluded after edits.
3. **Find evidence.** Rank matching lines and combine overlapping excerpts, retaining file and line citations.
4. **Check the claim.** Deterministic verification supports these narrow forms:
   - `Imports pytest in Python tests.` — a parsed top-level import with a bounded test-file header citation.
   - `Declares requests as a Python dependency.` — an entry in a requirements text file or root `pyproject.toml` under `[project].dependencies` or legacy `[tool.poetry.dependencies]` (non-optional).
   - `Includes Docker configuration based on Python 3.11.` — a matching `FROM` instruction.
   - `HTTPX requires Python 3.9+.` - a matching Python version floor in `pyproject.toml`.

Module names, dependency names, and Python versions can vary. Other wording or broader behavior claims
may return **insufficient evidence**, even when the feature exists. Contradictions use fallible text rules.
Confidence labels are heuristic, not probabilities. Optional model analysis has different behavior.
""")
st.button("Try sample audit", on_click=try_sample_audit, help="Discover and audit five synthetic claims in one click.")

repository_col, claims_col = st.columns(2, gap="large")
with repository_col:
    with st.container(border=True):
        st.markdown('<div class="rw-card-kicker">Step 1</div>', unsafe_allow_html=True)
        st.markdown("## Repository")
        st.caption("Upload the repository snapshot you want to audit.")
        upload = st.file_uploader(
            "Repository ZIP",
            type=["zip"],
            key="repository_zip",
            on_change=uploaded_repository_changed,
        )
        st.caption("25 MiB ZIP · 25 MiB extracted text · 5,000 entries · 1 MiB per file")
        st.markdown(
            '<div class="rw-note"><strong>Text-only scan</strong><br>Unsafe paths, symlinks, oversized files, common binaries, dependency/build folders, and selected secret-bearing files are skipped. Secret filtering is best-effort; do not upload sensitive repositories.</div>',
            unsafe_allow_html=True,
        )
        st.caption("Uploaded repositories are processed in a temporary workspace and are not intentionally retained.")
        st.button(
            "Load sample repository",
            on_click=load_sample_repository,
            help="Safe example: a bundled synthetic repository with all four verdicts. No code is executed.",
            use_container_width=True,
        )
        if st.session_state.get("sample_loaded"):
            st.success("Safe example loaded — bundled synthetic repository.")
        elif upload is None:
            st.caption("No repository yet. Upload a ZIP or load the safe example.")
        source_ready = st.session_state.get("sample_loaded") or upload is not None
        st.button(
            "Find README claims",
            on_click=discover_repository_claims,
            disabled=not source_ready,
            use_container_width=True,
        )

with claims_col:
    with st.container(border=True):
        st.markdown('<div class="rw-card-kicker">Step 2</div>', unsafe_allow_html=True)
        st.markdown("## Technical claims")
        st.caption("One claim per line · up to 10 claims · 300 characters each")
        claims_text = st.text_area(
            "Claims to audit",
            height=220,
            key="claims_editor",
            on_change=clear_report,
            placeholder="Enter one technical claim per line…",
        )
        claims = [line.strip() for line in claims_text.splitlines() if line.strip()]
        if st.session_state.get("claims_source_path"):
            st.caption(f"Review document excluded from evidence: {st.session_state['claims_source_path']}. This also applies to edited and added claims.")
        count_col, example_col = st.columns([1, 2])
        count_col.metric("Claims", len(claims))
        example_col.caption("Start with a narrow fact: a dependency declaration, a test import, or a Docker base image.")

render_claim_review()

source_ready = st.session_state.get("sample_loaded") or upload is not None
claims_within_limits = len(claims) <= MAX_AUDIT_CLAIMS and all(len(claim) <= MAX_CLAIM_CHARS for claim in claims)
if not claims_within_limits:
    st.warning("Use at most 10 claims, with no more than 300 characters per claim.")
can_run = source_ready and bool(claims) and claims_within_limits
run_audit = st.button(
    "Run repository audit",
    type="primary",
    disabled=not can_run,
    use_container_width=True,
)
if not can_run:
    st.caption("Add a repository and at least one user-approved claim to run an audit.")

auto_run_sample = st.session_state.pop("run_sample_after_render", False)
if run_audit or auto_run_sample:
    clear_revision_state()
    root = None
    temporary = False
    try:
        root, temporary = acquire_repository()
        if root is None:
            raise ValueError("No repository is available to audit")
        claim_sources = current_claim_sources(claims)
        st.session_state["report"] = run_repository_audit(root, claims, claim_sources)
        st.session_state["report_claim_sources"] = claim_sources
    except Exception as exc:
        clear_report()
        st.error(repository_error_message(exc))
    finally:
        if temporary and root is not None:
            cleanup_repository(root)

report = st.session_state.get("report")
if report:
    render_results(report, st.session_state.get("report_claim_sources", {}))
