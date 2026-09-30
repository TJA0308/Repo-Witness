"""Flag edited source passages retrieved for the same claims in two snapshots.

This is a review aid, not semantic impact analysis. Both audits use the existing
deterministic checks; neither uploaded repository is executed.
"""
from __future__ import annotations

import argparse
import difflib
from pathlib import Path

from pydantic import BaseModel, Field

from .analyzer import validate_claims
from .evidence import read_repository, retrieve_evidence
from .ingest import cleanup_repository, extract_repository
from .models import ClaimAudit, EvidenceSnippet
from .verdicts import classify_claim


class EvidenceChange(BaseModel):
    path: str
    change: str
    diff: str
    truncated: bool = False


class ClaimChange(BaseModel):
    claim: str
    excluded_document: str | None = None
    before: ClaimAudit
    after: ClaimAudit
    changes: list[EvidenceChange] = Field(default_factory=list)
    status: str


class ChangeReview(BaseModel):
    changed_file_count: int
    claims: list[ClaimChange]


def snapshot_root(extracted: Path) -> Path:
    """Remove one ZIP wrapper directory, such as a GitHub commit folder."""
    entries = list(extracted.iterdir())
    return entries[0] if len(entries) == 1 and entries[0].is_dir() else extracted


def _overlaps(start: int, end: int, snippets: list[EvidenceSnippet]) -> bool:
    # Opcodes use zero-based, half-open ranges; citations are one-based inclusive.
    for snippet in snippets:
        first, last = snippet.start_line - 1, snippet.end_line
        if start == end:
            if first <= start < last:
                return True
        elif start < last and end > first:
            return True
    return False


def _diff_range(start: int, end: int) -> str:
    return f"{start + 1 if end > start else start},{end - start}"


def changed_passages(path: str, old: list[str], new: list[str],
                     before: list[EvidenceSnippet], after: list[EvidenceSnippet]) -> EvidenceChange | None:
    """Return only diff hunks whose edits intersect a retrieved passage."""
    if old == new:
        return None
    matcher = difflib.SequenceMatcher(a=old, b=new)
    output = []
    for group in matcher.get_grouped_opcodes(n=3):
        relevant = any(tag != "equal" and
                       (_overlaps(i, j, before) or _overlaps(k, l, after))
                       for tag, i, j, k, l in group)
        if not relevant:
            continue
        if not output:
            output = [f"--- before/{path}", f"+++ after/{path}"]
        output.append(f"@@ -{_diff_range(group[0][1], group[-1][2])} +{_diff_range(group[0][3], group[-1][4])} @@")
        for tag, i, j, k, l in group:
            if tag == "equal":
                output.extend(" " + line for line in old[i:j])
            if tag in {"delete", "replace"}:
                output.extend("-" + line for line in old[i:j])
            if tag in {"insert", "replace"}:
                output.extend("+" + line for line in new[k:l])
    if not output:
        return None
    text = "\n".join(output[:80])
    truncated = len(output) > 80 or len(text) > 4000
    if truncated:
        text = text[:4000] + "\n[diff truncated]"
    change = "added" if not old else "removed" if not new else "modified"
    return EvidenceChange(path=path, change=change, diff=text, truncated=truncated)


def compare_claims(before_root: Path, after_root: Path, claims: list[str],
                   claim_sources: dict[str, str] | None = None) -> ChangeReview:
    clean = validate_claims(claims)
    old_files, new_files = read_repository(before_root), read_repository(after_root)
    changed = {path for path in old_files.keys() | new_files.keys()
               if old_files.get(path) != new_files.get(path)}
    reviews = []
    for claim in clean:
        source = (claim_sources or {}).get(claim)
        exclusions = [source] if source else []
        old_evidence = retrieve_evidence(before_root, claim, excluded_paths=exclusions, repository_files=old_files)
        new_evidence = retrieve_evidence(after_root, claim, excluded_paths=exclusions, repository_files=new_files)
        old_audit = classify_claim(claim, old_evidence, repository_files=old_files)
        new_audit = classify_claim(claim, new_evidence, repository_files=new_files)
        # A narrow fact should track its supporting passages rather than noise
        # sharing broad words such as "Python". If support disappears on one
        # side, keep that side's candidates only from the supporting file paths.
        old_support = [s for s in old_audit.evidence if s.relevance.endswith("evidence category: supporting")]
        new_support = [s for s in new_audit.evidence if s.relevance.endswith("evidence category: supporting")]
        support_paths = {s.path for s in old_support + new_support}
        if support_paths:
            old_evidence = old_support or [s for s in old_evidence if s.path in support_paths]
            new_evidence = new_support or [s for s in new_evidence if s.path in support_paths]
        paths = {snippet.path for snippet in old_evidence + new_evidence} & changed
        passages = []
        for path in sorted(paths):
            result = changed_passages(path, old_files.get(path, []), new_files.get(path, []),
                                      [s for s in old_evidence if s.path == path],
                                      [s for s in new_evidence if s.path == path])
            if result:
                # Distinguish an empty existing file from a missing file.
                result.change = "added" if path not in old_files else "removed" if path not in new_files else "modified"
                passages.append(result)
        status = "REVIEW_NEEDED" if passages else "NO_RETRIEVED_CHANGE" if old_evidence or new_evidence else "NO_EVIDENCE"
        reviews.append(ClaimChange(claim=claim, excluded_document=source,
                                   before=old_audit, after=new_audit,
                                   changes=passages, status=status))
    return ChangeReview(changed_file_count=len(changed), claims=reviews)


def markdown_change_review(report: ChangeReview) -> str:
    out = ["# Documentation change review — RepoWitness", "",
           "Review signals from two text snapshots; repository code is never executed.",
           "A flag means an edit overlaps retrieved evidence, not that the claim is false.",
           "No flagged change does not establish that a claim is unaffected or correct.", "",
           f"Changed eligible text files: {report.changed_file_count}", ""]
    for item in report.claims:
        out += [f"## {item.claim}", "", f"- Review signal: {item.status}",
                f"- Excluded document in both snapshots: {item.excluded_document or 'None (manual entry)'}",
                f"- Before verdict: {item.before.verdict.value}", f"- After verdict: {item.after.verdict.value}", ""]
        for change in item.changes:
            fence = "```"
            while fence in change.diff:
                fence += "`"
            out += [f"### {change.path} ({change.change})", "", f"{fence}diff", change.diff, fence, ""]
        for label, audit in (("Before", item.before), ("After", item.after)):
            out += [f"### {label} evidence", "", audit.reasoning, ""]
            for snippet in audit.evidence:
                fence = "```"
                while fence in snippet.excerpt:
                    fence += "`"
                out += [f"{snippet.path}:{snippet.start_line}-{snippet.end_line}", "", f"{fence}text", snippet.excerpt, fence, ""]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path, help="Before repository ZIP")
    parser.add_argument("--after", required=True, type=Path, help="After repository ZIP")
    parser.add_argument("--claim", action="append", required=True, help="Repeat for up to ten claims")
    parser.add_argument("--readme", default="README.md", help="Relative README path excluded in both snapshots")
    parser.add_argument("--output", type=Path, help="Save UTF-8 Markdown")
    args = parser.parse_args()
    roots = []
    try:
        for archive in (args.before, args.after):
            roots.append(extract_repository(archive.read_bytes()))
        report = compare_claims(snapshot_root(roots[0]), snapshot_root(roots[1]), args.claim,
                                {claim.strip(): args.readme for claim in args.claim})
        text = markdown_change_review(report)
        if args.output:
            args.output.write_text(text, encoding="utf-8")
        else:
            print(text)
    finally:
        for root in roots:
            cleanup_repository(root)


if __name__ == "__main__":
    main()
