# Understand RepoWitness in one walkthrough

Start the app, click **Try sample audit**, and open the evidence for “Imports pytest in Python tests.”

## Follow the data

1. `app.try_sample_audit()` loads `sample_repo`, discovers the README claims, and passes them to the same audit function used by uploads. Uploads first go through `ingest.extract_repository()` and are cleaned in a `finally` block.
2. `readme_claims.extract_candidate_claims()` finds short technical sentences. The user can edit them; discovery is a suggestion, not a verdict.
3. `app.current_claim_sources()` excludes the selected README for every claim in that review. The README cannot establish its own statement, even after editing.
4. `analyzer.analyze_demo()` validates the claim limits and calls `evidence.read_repository()` once. Think of the result as `{relative_path: [lines]}`.
5. `evidence.retrieve_evidence()` scores lines containing claim terms, sorts them, and returns bounded `EvidenceSnippet` objects. Each has a path, line range, text, and ranking explanation.
6. `verdicts.classify_claim()` checks possible contradictions and asks `checks.bounded_support()` whether an explicit positive check establishes the narrow claim. The Python import check parses syntax; it does not execute Python.
7. The result is a `ClaimAudit`: claim, verdict, heuristic confidence, evidence, reasoning, and corrected wording. Several audits form an `AuditReport`.
8. `app.render_results()` displays the report. `export.markdown_report()` serializes it for download. Presentation does not change verdicts.

## Three distinctions to explain

**Retrieval vs verification:** `passwords = {}` is relevant to a password claim, but it cannot establish bcrypt encryption. Retrieval finds candidates; a check determines whether they establish the stated fact.

**Declared vs working:** a requirements line establishes a declared dependency. It does not prove the package is installed, used, or functioning. Similarly, a Docker base-image instruction does not establish deployment.

**No evidence vs false:** if the checker does not support a claim form or cannot find evidence, it abstains. A contradiction requires a conflicting statement, although the current text rules can still misread it.

## Interview explanation

> I built a tool for reviewing README claims against repository evidence. It reads an uploaded snapshot without running the code, excludes the README under review, retrieves matching excerpts, and produces cited verdicts. I found that keyword overlap could falsely verify behavioral claims, so I restricted positive verdicts to explicit static checks. On the unchanged small benchmark, false verification fell from 1/19 to 0/19, but accuracy fell because the narrower checker abstains more often. I report both numbers and would next label real repository cases independently.

## Why the design stays small

- Streamlit handles the UI and session state; no separate frontend or backend service.
- A dictionary caches files within one audit; no database or vector service.
- Four explicit check families are easier to inspect than a growing generic keyword classifier.
- `ast.parse` inspects Python syntax without importing uploaded code.
- The optional model path is separate and has separate failure behavior.
- Tests cover observed failures and workflows. Passing tests does not establish general accuracy.

## Before extending a check

Write down the exact fact it establishes, a positive example, and a deceptive negative example. Implement it in `checks.py`, test through `analyze_demo()`, and rerun both benchmarks. Do not change benchmark labels merely to improve the score.

## Follow a pyproject dependency claim

For `Declares requests as a Python dependency.`, the flow is:

1. Parse the complete root `pyproject.toml` from the existing file snapshot with Python's built-in `tomllib`.
2. Read only `project.dependencies`. Parse each requirement with `packaging.Requirement` and compare normalized package names exactly. `requests-extra` does not match `requests`.
3. Locate where that dependency list first appears in parsed source prefixes. This avoids citing a fake assignment inside a multiline description or an unrelated tool table.
4. Return the complete assignment as a bounded citation. The classifier rechecks it against the same full source before allowing verification; a context-free excerpt alone cannot establish which TOML table it belongs to.

This establishes a declared dependency, including conditional declarations. It does not establish that a package is installed or used. Optional extras, build dependencies, and Poetry tables are outside this check. A very large assignment or unsupported key spelling stays unresolved.

The additional `packaging` library handles Python requirement syntax; no custom dependency grammar or package installation is involved. The parser itself does not execute repository code.

## Explain an unresolved result

- **No relevant evidence found:** retrieval returned no snippets. Try a more specific claim or inspect the repository.
- **Claim form outside supported checks:** related text exists, but the checker has no rule for that sentence. Review the evidence manually or write a narrow factual claim.
- **Supported check found no matching declaration:** the rule exists, but the available source does not establish the claim. This can include a different value, invalid metadata, or an incomplete citation.

None of these outcomes establishes that the original claim is false. Absence claims and model request failures keep their own specific explanations.
