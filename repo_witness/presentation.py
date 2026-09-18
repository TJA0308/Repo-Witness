"""Display formatting only; never changes retrieval or verdict results."""

from .models import EvidenceSnippet, Verdict

VERDICT_LABELS = {
    Verdict.VERIFIED: "Verified",
    Verdict.PARTIALLY_VERIFIED: "Partially verified",
    Verdict.CONTRADICTED: "Contradicted",
    Verdict.INSUFFICIENT_EVIDENCE: "Insufficient evidence",
}


def confidence_label(value: float) -> str:
    """Uncalibrated display bands, not probabilities of correctness."""
    return "High" if value >= 0.8 else "Moderate" if value >= 0.5 else "Low"


def useful_correction(claim: str, wording: str) -> bool:
    """Ignore empty wording and changes only to case, spacing, or end punctuation."""
    normalize = lambda text: " ".join(text.split()).casefold().rstrip(".!?")
    return bool(wording.strip()) and normalize(claim) != normalize(wording)


def evidence_classification(evidence: EvidenceSnippet) -> str | None:
    category = evidence.relevance.rsplit("evidence category: ", 1)
    if len(category) != 2:
        return None
    return {
        "supporting": "Supporting", "contradicting": "Contradicting",
        "speculative": "Speculative", "mention_only": "Mention only",
    }.get(category[1].strip())


def visible_evidence(items: list[EvidenceSnippet]) -> list[EvidenceSnippet]:
    """Keep original ranking; hide duplicates with at least 80% range overlap.

    Different known classifications are retained so conflicts remain visible.
    The underlying report and benchmark data are never mutated.
    """
    shown = []
    for item in items:
        duplicate = False
        for previous in shown:
            if item.path != previous.path or evidence_classification(item) != evidence_classification(previous):
                continue
            overlap = max(0, min(item.end_line, previous.end_line) - max(item.start_line, previous.start_line) + 1)
            shorter = min(item.end_line - item.start_line + 1, previous.end_line - previous.start_line + 1)
            if item.excerpt.strip() == previous.excerpt.strip() or overlap / shorter >= 0.8:
                duplicate = True
                break
        if not duplicate:
            shown.append(item)
    return shown
