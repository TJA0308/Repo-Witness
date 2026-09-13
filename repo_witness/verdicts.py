"""Deterministic evidence classification and verdict aggregation.

Retrieval finds text that is *about* a claim. It does not establish that the text
*supports* the claim. This module is the separation between those two ideas: it
sorts retrieved snippets into evidence categories and aggregates them into one of
the four existing verdicts.

It is a conservative rule baseline, not natural-language entailment. Everything
here is regular expressions over lines. There is no model, no embedding, and no
network call. When the evidence is ambiguous the rules prefer
``INSUFFICIENT_EVIDENCE`` over ``VERIFIED``, because a false verification is the
failure this project exists to prevent.

The claim tokenizer deliberately does not import ``repo_witness.evidence._terms``.
That retriever is frozen and its tokenizer keeps trailing punctuation, so a claim
ending "... uses Kafka." yields the term ``kafka.`` and can never match ``Kafka``
in a file. Classification strips that punctuation instead. Both tokenizers are
small and are allowed to diverge; the retriever's behavior is unchanged.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from .models import ClaimAudit, EvidenceSnippet, Verdict

SUPPORTING = "supporting"
CONTRADICTING = "contradicting"
SPECULATIVE = "speculative"
MENTION_ONLY = "mention_only"
EVIDENCE_CATEGORIES = (SUPPORTING, CONTRADICTING, SPECULATIVE, MENTION_ONLY)
# Highest precedence first. A snippet takes the strongest category any of its
# lines produced, so one contradicting line outweighs a supporting line beside it.
_CATEGORY_PRECEDENCE = (CONTRADICTING, SUPPORTING, SPECULATIVE, MENTION_ONLY)

LINE_CONTEXTS = ("code", "comment", "config", "prose", "test")
_NATURAL_LANGUAGE_CONTEXTS = frozenset({"prose", "comment"})
_IMPLEMENTATION_CONTEXTS = frozenset({"code", "config", "test"})

# Retrieval renders every excerpt line as "{number}: {text}" (evidence.py and
# retrieval/semantic.py both do this). Without stripping that prefix no line can
# ever look like a comment, and a line number could be mistaken for a claim term.
_LINE_PREFIX = re.compile(r"^\s*\d+:\s?")
_COMMENT_LINE = re.compile(r"^\s*(#|//|/\*|\*|<!--|--\s|;)")

_PROSE_SUFFIXES = frozenset({".md", ".txt", ".rst"})
_CONFIG_SUFFIXES = frozenset({".yml", ".yaml", ".toml", ".ini", ".cfg", ".json"})
_CONFIG_NAMES = frozenset({"dockerfile", "makefile"})
_TEST_SEGMENTS = frozenset({"test", "tests", "testing", "spec", "specs", "__tests__"})

_TERM_PATTERN = re.compile(r"[a-z0-9][a-z0-9+#.-]{2,}")
_TERM_STOP_WORDS = frozenset({"uses", "use", "the", "and", "for", "with", "has"})

_NEGATION_CUES = (
    "not", "never", "no", "without", "cannot", "lacks", "lacking",
    "doesn't", "does not", "don't", "isn't", "aren't", "won't",
)
# Rejection language is natural language. Restricting these cues to prose and
# comments is what stops ``SELECTED_FIELDS = [...]`` or ``deprecated=True`` in
# ordinary code from reading as a rejection of the claim.
_REJECTION_CUES = (
    "instead of", "in favor of", "in favour of", "rather than", "rejected",
    "evaluated", "deprecated", "replaced", "migrated", "moved away",
    "decided against", "chose", "chosen", "selected",
)
_SPECULATIVE_CUES = (
    "todo", "fixme", "planned", "planning", "roadmap", "someday", "eventually",
    "in the future", "might", "may want", "consider", "considering",
    "not yet", "coming soon", "proposed", "proposal", "future work", "wip",
)
# Scope words describe reach or guarantees that static evidence cannot establish.
# "never" is absent on purpose: it makes a claim an absence claim, which is
# checked earlier and outranks this list.
_SCOPE_WORDS = ("always", "100%", "production-scale", "fully", "every", "all")

_NEGATION_WINDOW_WORDS = 3
_NEGATION_ALTERNATION = "|".join(re.escape(cue) for cue in _NEGATION_CUES)
_REJECTION_PATTERN = re.compile(
    "|".join(rf"\b{re.escape(cue)}\b" for cue in _REJECTION_CUES)
)
_SPECULATIVE_PATTERN = re.compile(
    "|".join(rf"\b{re.escape(cue)}\b" for cue in _SPECULATIVE_CUES)
)
_SCOPE_PATTERN = re.compile(
    "|".join(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])" for word in _SCOPE_WORDS)
)
_ABSENCE_PATTERN = re.compile(
    "|".join(rf"\b{re.escape(cue)}\b" for cue in _NEGATION_CUES)
)

_TERM_CACHE: dict[str, re.Pattern[str]] = {}
_NEGATED_TERM_CACHE: dict[str, re.Pattern[str]] = {}

# Outcome -> (verdict, confidence, reasoning). Confidence values are fixed labels
# of rule strength. They are not calibrated probabilities; nothing in this
# repository estimates a probability.
REASON_NO_EVIDENCE = (
    "No relevant repository snippet was retrieved. This is not evidence of contradiction."
)
REASON_ABSENCE = (
    "This claim asserts an absence. Bounded lexical retrieval can only show what a "
    "repository contains, never that something is missing, so the absence cannot be "
    "established from the retrieved evidence."
)
REASON_WEAK = (
    "The retrieved evidence only mentions the claim's terms in documentation, comments, "
    "or planned work. Mentioning a technology is not the same as using it."
)
REASON_CONTRADICTED = (
    "A retrieved repository statement negates the claim or records the claimed approach "
    "as one that was not taken."
)
REASON_MIXED = (
    "The retrieved evidence both supports and contradicts parts of this claim, so only "
    "part of it is established."
)
REASON_SCOPED = (
    "Implementation evidence was found, but the claim's absolute or broad scope is not "
    "established by static evidence."
)
REASON_SUPPORTED = (
    "Retrieved code, configuration, or test evidence uses the claim's key technical terms "
    "in an implementation context."
)

OUTCOMES: dict[str, tuple[Verdict, float, str]] = {
    "no_evidence": (Verdict.INSUFFICIENT_EVIDENCE, 0.20, REASON_NO_EVIDENCE),
    "absence_claim": (Verdict.INSUFFICIENT_EVIDENCE, 0.20, REASON_ABSENCE),
    "weak_evidence": (Verdict.INSUFFICIENT_EVIDENCE, 0.30, REASON_WEAK),
    "contradicted": (Verdict.CONTRADICTED, 0.70, REASON_CONTRADICTED),
    "mixed": (Verdict.PARTIALLY_VERIFIED, 0.55, REASON_MIXED),
    "scoped_support": (Verdict.PARTIALLY_VERIFIED, 0.55, REASON_SCOPED),
    "supported": (Verdict.VERIFIED, 0.70, REASON_SUPPORTED),
}
CORROBORATED_CONFIDENCE = 0.80


def _boundary(term: str) -> re.Pattern[str]:
    """Match a term on its own, allowing `_` and punctuation at its edges.

    The boundary class excludes the underscore on purpose, so ``endpoint`` still
    matches inside ``HEALTH_CHECK_ENDPOINT`` while ``not`` never matches inside
    ``annotations`` and ``mono`` never matches inside ``monolith``. ``\\b`` is
    unusable here because terms legitimately contain ``+ # . -``.
    """
    pattern = _TERM_CACHE.get(term)
    if pattern is None:
        pattern = re.compile(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])")
        _TERM_CACHE[term] = pattern
    return pattern


def _negated(term: str) -> re.Pattern[str]:
    """Match a negation cue within a few words on either side of the term."""
    pattern = _NEGATED_TERM_CACHE.get(term)
    if pattern is None:
        escaped = re.escape(term)
        gap = rf"(?:\W+\w+){{0,{_NEGATION_WINDOW_WORDS}}}\W+"
        pattern = re.compile(
            rf"\b(?:{_NEGATION_ALTERNATION})\b{gap}(?<![a-z0-9]){escaped}(?![a-z0-9])"
            rf"|(?<![a-z0-9]){escaped}(?![a-z0-9]){gap}\b(?:{_NEGATION_ALTERNATION})\b"
        )
        _NEGATED_TERM_CACHE[term] = pattern
    return pattern


def claim_terms(claim: str) -> list[str]:
    terms = []
    for raw in _TERM_PATTERN.findall(claim.lower()):
        term = raw.strip(".,;:!?")
        if len(term) >= 3 and term not in _TERM_STOP_WORDS and term not in terms:
            terms.append(term)
    return terms


def is_absence_claim(claim: str) -> bool:
    return bool(_ABSENCE_PATTERN.search(claim.lower()))


def has_scope_word(claim: str) -> bool:
    return bool(_SCOPE_PATTERN.search(claim.lower()))


def strip_line_prefix(line: str) -> str:
    return _LINE_PREFIX.sub("", line, count=1)


def line_context(path: str, line: str) -> str:
    """Classify one already-prefix-stripped excerpt line by where it lives."""
    if _COMMENT_LINE.match(line):
        return "comment"
    normalized = path.replace("\\", "/").casefold()
    parts = normalized.split("/")
    name = parts[-1] if parts else normalized
    suffix = name[name.rfind(".") :] if "." in name else ""
    if suffix in _PROSE_SUFFIXES:
        return "prose"
    stem = name[: -len(suffix)] if suffix else name
    if set(parts[:-1]) & _TEST_SEGMENTS or stem.startswith("test_") or stem.endswith("_test"):
        return "test"
    if suffix in _CONFIG_SUFFIXES or name in _CONFIG_NAMES:
        return "config"
    return "code"


def categorize_snippet(claim: str, snippet: EvidenceSnippet) -> str:
    terms = claim_terms(claim)
    if not terms:
        return MENTION_ONLY
    found: set[str] = set()
    for raw_line in snippet.excerpt.splitlines():
        line = strip_line_prefix(raw_line)
        low = line.lower()
        hits = [term for term in terms if _boundary(term).search(low)]
        if not hits:
            continue
        context = line_context(snippet.path, line)
        natural = context in _NATURAL_LANGUAGE_CONTEXTS
        if any(_negated(term).search(low) for term in hits):
            found.add(CONTRADICTING)
        elif natural and _REJECTION_PATTERN.search(low):
            found.add(CONTRADICTING)
        elif natural and _SPECULATIVE_PATTERN.search(low):
            found.add(SPECULATIVE)
        elif context in _IMPLEMENTATION_CONTEXTS:
            found.add(SUPPORTING)
        else:
            found.add(MENTION_ONLY)
    for category in _CATEGORY_PRECEDENCE:
        if category in found:
            return category
    return MENTION_ONLY


def categorize_evidence(claim: str, evidence: Sequence[EvidenceSnippet]) -> list[str]:
    return [categorize_snippet(claim, snippet) for snippet in evidence]


def annotate_evidence(
    evidence: Sequence[EvidenceSnippet], categories: Sequence[str]
) -> list[EvidenceSnippet]:
    """Return copies carrying the category, leaving the caller's snippets untouched.

    The category is appended to the existing free-text ``relevance`` rather than
    added as a model field, so no public schema changes and the retriever's own
    relevance string stays exactly as its characterization tests pin it.
    """
    annotated = []
    for snippet, category in zip(evidence, categories):
        suffix = f"evidence category: {category}"
        relevance = f"{snippet.relevance}; {suffix}" if snippet.relevance else suffix
        annotated.append(snippet.model_copy(update={"relevance": relevance}))
    return annotated


def aggregate_outcome(claim: str, categories: Sequence[str]) -> str:
    """Reduce snippet categories to one outcome key.

    Absence is tested before emptiness so an absence claim always explains itself
    as unprovable rather than as a retrieval miss. Both return the same verdict.
    """
    if is_absence_claim(claim):
        return "absence_claim"
    if not categories:
        return "no_evidence"
    contradicting = CONTRADICTING in categories
    supporting = SUPPORTING in categories
    if contradicting and supporting:
        return "mixed"
    if contradicting:
        return "contradicted"
    if supporting and has_scope_word(claim):
        return "scoped_support"
    if supporting:
        return "supported"
    return "weak_evidence"


def corrected_wording(claim: str, verdict: Verdict) -> str:
    stem = claim.rstrip(" .")
    if verdict == Verdict.VERIFIED:
        return claim
    if verdict == Verdict.CONTRADICTED:
        return (
            "Repository evidence conflicts with this claim; resolve the conflict "
            f"before restating: {stem}."
        )
    if verdict == Verdict.PARTIALLY_VERIFIED:
        return f"{stem}, though the retrieved evidence does not establish its full scope."
    return f"{stem} — not established by the retrieved repository evidence."


def classify_claim(claim: str, evidence: Sequence[EvidenceSnippet]) -> ClaimAudit:
    categories = categorize_evidence(claim, evidence)
    outcome = aggregate_outcome(claim, categories)
    verdict, confidence, reasoning = OUTCOMES[outcome]
    if outcome == "supported":
        supporting_files = {
            snippet.path
            for snippet, category in zip(evidence, categories)
            if category == SUPPORTING
        }
        if len(supporting_files) >= 2:
            confidence = CORROBORATED_CONFIDENCE
    return ClaimAudit(
        claim=claim,
        verdict=verdict,
        confidence=confidence,
        evidence=annotate_evidence(evidence, categories),
        reasoning=reasoning,
        corrected_wording=corrected_wording(claim, verdict),
    )


def insufficient_audit(
    claim: str, evidence: Sequence[EvidenceSnippet], reasoning: str
) -> ClaimAudit:
    """Build an insufficient-evidence audit without running the rule classifier.

    Used when an analysis mode could not reach a conclusion at all. Routing such a
    failure back through ``classify_claim`` would let regex heuristics publish a
    verdict under another analyzer's name.
    """
    return ClaimAudit(
        claim=claim,
        verdict=Verdict.INSUFFICIENT_EVIDENCE,
        confidence=OUTCOMES["no_evidence"][1],
        evidence=list(evidence),
        reasoning=reasoning,
        corrected_wording=corrected_wording(claim, Verdict.INSUFFICIENT_EVIDENCE),
    )
