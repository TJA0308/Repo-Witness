from .models import AuditReport

def markdown_report(report: AuditReport) -> str:
    out = ["# Repository Claim Audit", "", f"Analyzer: **{report.analyzer}**", ""]
    for i, audit in enumerate(report.audits, 1):
        out += [f"## {i}. {audit.claim}", "", f"- Verdict: **{audit.verdict.value}**", f"- Confidence: {audit.confidence:.0%}", f"- Reasoning: {audit.reasoning}", f"- Suggested wording: {audit.corrected_wording}", "", "### Repository evidence", ""]
        if audit.evidence:
            for evidence in audit.evidence:
                out += [f"- `{evidence.path}:{evidence.start_line}-{evidence.end_line}` — {evidence.relevance}", "", "```text", evidence.excerpt, "```", ""]
        else:
            out += ["No relevant evidence snippet retrieved.", ""]
    return "\n".join(out)

