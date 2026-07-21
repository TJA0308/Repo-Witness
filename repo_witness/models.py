from enum import Enum
from pydantic import BaseModel, Field

class Verdict(str, Enum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

class EvidenceSnippet(BaseModel):
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    excerpt: str
    relevance: str = ""

class ClaimAudit(BaseModel):
    claim: str
    verdict: Verdict
    confidence: float = Field(ge=0, le=1)
    evidence: list[EvidenceSnippet] = Field(default_factory=list)
    reasoning: str
    corrected_wording: str

class AuditReport(BaseModel):
    audits: list[ClaimAudit]
    analyzer: str

