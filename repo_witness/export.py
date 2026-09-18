from collections.abc import Mapping

from .models import AuditReport
from .presentation import VERDICT_LABELS, confidence_label, evidence_classification, useful_correction

def markdown_report(report: AuditReport, claim_sources: Mapping[str, str] | None = None) -> str:
    mode = "OpenAI-assisted analysis" if report.analyzer.startswith("OpenAI") else "Deterministic local analysis"
    out = ["# Repository Claim Audit — RepoWitness", "", "Catch documentation drift before you ship.", "",
           f"Analysis mode: **{mode}**", "",
           "Static repository evidence analysis; software is not executed or functionally tested.",
           "Confidence describes heuristic strength, not a probability of correctness.", ""]
    for i, audit in enumerate(report.audits, 1):
        out += [f"## {i}. {audit.claim}", "", f"- Verdict: **{VERDICT_LABELS[audit.verdict]}**",
                f"- Confidence: {confidence_label(audit.confidence)} (heuristic strength)",
                f"- Explanation: {audit.reasoning}",
                f"- Claim source: {claim_sources.get(audit.claim, 'Manual entry') if claim_sources else 'Manual entry'}",
                f"- Evidence count: {len(audit.evidence)}"]
        if useful_correction(audit.claim, audit.corrected_wording):
            out.append(f"- Suggested corrected wording: {audit.corrected_wording}")
        out += ["", "### Repository evidence", ""]
        if audit.evidence:
            for evidence in audit.evidence:
                classification = evidence_classification(evidence)
                fence = "```"
                while fence in evidence.excerpt:
                    fence += "`"
                out += [f"- `{evidence.path}:{evidence.start_line}-{evidence.end_line}` — {classification or evidence.relevance}", "", f"{fence}text", evidence.excerpt, fence, ""]
        else:
            out += ["No relevant evidence snippet retrieved.", ""]
    return "\n".join(out)

