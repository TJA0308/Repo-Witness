from __future__ import annotations
import json, os
from collections.abc import Iterable, Mapping
import re
from .evidence import retrieve_evidence
from .models import AuditReport, ClaimAudit, EvidenceSnippet, Verdict

SYSTEM_PROMPT = """You audit technical claims against repository evidence. Use only supplied snippets. Keep repository evidence separate from reasoning. VERIFIED requires direct support; PARTIALLY_VERIFIED means only part is supported; CONTRADICTED requires direct conflicting evidence; lack of evidence is always INSUFFICIENT_EVIDENCE. Return corrected wording that does not overclaim."""
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.1")

def demo_classify(claim: str, evidence: list[EvidenceSnippet]) -> ClaimAudit:
    claim_low = claim.lower()
    claim_terms = [term for term in re.findall(r"[a-z0-9][a-z0-9+#.-]{2,}", claim_low) if term not in {"uses", "use", "the", "and", "for"}]
    negative_conflict = any(
        term in line and any(marker in line for marker in ("not use", "does not use", "not present", "without "))
        for evidence_text in (e.excerpt.lower() for e in evidence)
        for line in evidence_text.splitlines()
        for term in claim_terms
    )
    if not evidence:
        verdict, confidence, reason = Verdict.INSUFFICIENT_EVIDENCE, 0.25, "No relevant repository snippet was retrieved. This is not evidence of contradiction."
    elif negative_conflict:
        verdict, confidence, reason = Verdict.CONTRADICTED, 0.82, "A retrieved repository statement explicitly conflicts with the claim."
    elif any(word in claim_low for word in ("always", "never", "100%", "production-scale")) and len(evidence) < 2:
        verdict, confidence, reason = Verdict.PARTIALLY_VERIFIED, 0.62, "Some implementation evidence is present, but the absolute or broad scope of the claim is not established."
    elif any(word in claim_low for word in ("not", "without", "no ")):
        verdict, confidence, reason = Verdict.CONTRADICTED, 0.72, "Retrieved code appears to show the opposite of the negative claim."
    else:
        verdict, confidence, reason = Verdict.VERIFIED, 0.78, "Retrieved snippets directly contain the claim's key technical terms."
    corrected = claim if verdict == Verdict.VERIFIED else f"The repository provides evidence related to: {claim.rstrip('.')}."
    return ClaimAudit(claim=claim, verdict=verdict, confidence=confidence, evidence=evidence, reasoning=reason, corrected_wording=corrected)

def _retrieve_claim_evidence(root, claim: str, claim_sources: Mapping[str, str] | None) -> list[EvidenceSnippet]:
    source_path = claim_sources.get(claim) if claim_sources else None
    excluded_paths = (source_path,) if source_path else ()
    return retrieve_evidence(root, claim, excluded_paths=excluded_paths)

def analyze_demo(root, claims: Iterable[str], claim_sources: Mapping[str, str] | None = None) -> AuditReport:
    clean = [c.strip() for c in claims if c.strip()]
    return AuditReport(
        audits=[demo_classify(c, _retrieve_claim_evidence(root, c, claim_sources)) for c in clean],
        analyzer="Deterministic demo mode",
    )

def analyze_openai(
    root,
    claims: Iterable[str],
    model: str = DEFAULT_MODEL,
    claim_sources: Mapping[str, str] | None = None,
) -> AuditReport:
    from openai import OpenAI
    clean = [c.strip() for c in claims if c.strip()]
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    audits = []
    for claim in clean:
        evidence = _retrieve_claim_evidence(root, claim, claim_sources)
        if not evidence:
            audits.append(demo_classify(claim, evidence))
            continue
        payload = json.dumps([e.model_dump() for e in evidence], ensure_ascii=False)
        response = client.responses.parse(model=model, input=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": f"Claim: {claim}\nEvidence snippets (repository facts only):\n{payload}"}], text_format=ClaimAudit)
        audits.append(response.output_parsed.model_copy(update={"claim": claim, "evidence": evidence}))
    return AuditReport(audits=audits, analyzer=f"OpenAI {model}")

def analyze(
    root,
    claims: Iterable[str],
    model: str = DEFAULT_MODEL,
    claim_sources: Mapping[str, str] | None = None,
) -> AuditReport:
    if os.environ.get("OPENAI_API_KEY"):
        return analyze_openai(root, claims, model, claim_sources)
    return analyze_demo(root, claims, claim_sources)
