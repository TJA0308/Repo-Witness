# Architecture

RepoWitness is a static repository evidence review tool. It never executes uploaded code.

## The production path

```mermaid
flowchart LR
    A[Repository ZIP] --> B[Bounded extraction]
    B --> C[README discovery and claim review]
    C --> D[Lexical retrieval]
    D --> E[Static checks and conflict rules]
    E --> F[Cited report]
```

| Module | Responsibility |
| --- | --- |
| `ingest.py` | Limit uploads and extraction; reject escaping paths; skip selected binaries and secrets; clean temporary directories. |
| `readme_claims.py` | Find READMEs, join wrapped prose, and suggest technical sentences or normalized feature bullets. |
| `evidence.py` | Read eligible files once per audit, score matching lines, merge overlapping windows, return at most six excerpts. |
| `checks.py` | Explicit positive checks: Python test imports, requirements declarations, Python Docker base images. |
| `verdicts.py` | Detect possible conflicts and speculation, apply positive checks, aggregate the four verdicts. |
| `analyzer.py` | Validate up to ten claims, reuse the file snapshot, coordinate deterministic or optional model analysis. |
| `models.py` | Pydantic report and citation schemas. |
| `presentation.py` / `export.py` | Format the dashboard and Markdown export. |
| `app.py` | Streamlit session state, user input, discovery, analysis, and cleanup. |

## Retrieval

Tokenization lowercases text and strips sentence-ending periods while keeping version numbers such as `3.11` intact. Each line scores `10 x distinct matching terms + total occurrences`; a `requires-python` line in root `pyproject.toml` gets a 12-point bonus for an explicit Python version claim. Ties sort by path and line number. Matching is lexical substring matching; there is no claim of language understanding.

The analyzer reads eligible files into one dictionary for the audit. Every claim reuses it. There is no persistent index or database. Overlapping same-file windows merge when their combined span is at most ten lines; conflicting text is retained. Up to six excerpts are returned, each capped at 1,200 characters with explicit truncation marking. SQL is eligible. Historical `CHANGELOG.md`, `HISTORY.md`, `CHANGES.md`, and `NEWS.md` are skipped as evidence for the current snapshot. Distributed evidence and synonyms remain weaknesses.

The selected README is excluded for **all claims in its review session**, including edits and additions. This is a document-level exclusion, not a claim that every edited sentence came from that README. Starting a new repository clears the review state. A purely manual session without README discovery has no source exclusion.

## Verdict policy

Keyword overlap can retrieve a candidate but cannot earn verification. `checks.bounded_support` recognizes these claim forms (case-insensitive wording):

- `Imports pytest in Python tests.` Module names can vary. The retrieved window must begin at line one of a Python test file. Python AST parsing checks complete prefixes for a top-level import. It does not import or run the file. Imports in comments, strings, relative imports, and nested conditional imports do not qualify.
- `Declares requests as a Python dependency.` Package names can vary. An uncommented declaration in a requirements text file qualifies. This proves a declaration, not installation or use. Other manifest formats are not supported by this check.
- `Includes Docker configuration based on Python 3.11.` Versions can vary; documented configuration/image wording variants are accepted. A matching Python `FROM` instruction qualifies, not a successful image build or deployment.
- `HTTPX requires Python 3.9+.` A root `pyproject.toml` `requires-python = ">=3.9"` declaration qualifies. Project names and version floors can vary. `Requests officially supports Python 3.10+` is partial: the metadata shows a minimum version, not full compatibility.

An explicit `with production-scale reliability` suffix illustrates a narrow fact plus an unproven guarantee and produces partial verification when the base fact is established. Other compound claims do not silently inherit support for just one component.

Existing negation/rejection rules still detect possible contradictions. They are fallible: nearby negation, comments, and paraphrases can mislead them. Absence claims abstain. Two independent supporting files increase the heuristic confidence label, which is not a probability.

## Optional model analysis

The optional path sends claims and retrieved snippets to the model, retains locally retrieved citations, and returns insufficient evidence on request failure, refusal, or missing structured output. It does **not** use the deterministic positive-check gate and has not been evaluated here. Never describe deterministic benchmark results as model accuracy.

The semantic retriever remains evaluation-only. It uses local embeddings, overlapping text chunks, deterministic cosine ranking, and an in-memory content cache. It is not enabled in the app. Historical semantic measurements predate SQL coverage and are not current comparisons.

## Current evaluation

Reproduce with `python -m repo_witness.benchmark` and `python -m repo_witness.verdict_benchmark`. Committed outputs live in [evaluation](evaluation/).

| Measurement | Before | Current |
| --- | ---: | ---: |
| Lexical Recall@3, 36 supported synthetic cases | 28/36 (77.8%) | 30/36 (83.3%) |
| Verdict accuracy, unchanged 31-case general-claim dataset | 26/31 (83.9%) | 14/31 (45.2%) |
| False verification, 19 cases not labeled VERIFIED | 1/19 (5.3%) | 0/19 (0%) |
| Retrieval source-exclusion violations | 0 | 0 |

**The reduced false verification comes with substantially lower coverage.** The narrower checker abstains on many claims the old dataset expects to verify. The labels are unchanged; these failures remain visible. Zero measured false verification on 19 cases is not a general safety guarantee. No real-repository or end-to-end accuracy claim is established. Regression tests separately exercise complete audits for the supported checks and known false-verification examples.

## Boundaries and remaining work

Uploads and retained extracted text are each capped at 25 MiB; at most 5,000 archive entries and 1 MiB per retained file. These do not bound all decompression work. Secret filename filtering and cleanup are best-effort. Uploaded bytes and reports may remain in session memory. Processing happens on the server. Do not upload sensitive repositories to a public host.

The pinned public-repository smoke test below exposes coverage limits but has no independent verdict labels. Next substantive work should be independently labeled real-repository evaluation and additional narrowly defined checks. Keep each check small enough to explain with a positive and a negative example.

[Historical design and experiments](history/architecture-v1.md) ? [Code walkthrough](how-it-works.md)

## Pinned public repositories

[Click](https://github.com/pallets/click/tree/06b2a678741131fd577ce170e23e5ca0aeba0309), [HTTPX](https://github.com/encode/httpx/tree/b5addb64f0161ff6bfe94c124ef76f6a1fba5254), and [Requests](https://github.com/psf/requests/tree/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60) were audited from pinned ZIPs without executing their code. The extractor proposed 23 claims: 1 verified, 1 partial, 21 insufficient, and 0 contradicted. These are output counts, not accuracy. Source paths and line ranges were checked to exist; only the two version claims received direct positive support from `pyproject.toml`. The other claims need human review or additional bounded checks. See the [saved cases](evaluation/real_repositories.json) and [reproduction steps](evaluation/README.md).
