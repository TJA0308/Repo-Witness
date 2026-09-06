<div align="center">

# Repo Witness

### Provenance-aware technical claim auditing for software repositories

Repo Witness checks claims from project documentation or manual input against
independent, repository-relative evidence—without executing uploaded code.

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.40%2B-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-E92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![Tests](https://img.shields.io/badge/Tests-126%20passing-2EA44F?logo=pytest&logoColor=white)](#testing)
[![Benchmark](https://img.shields.io/badge/Benchmark-40%20cases-6F42C1)](#retrieval-evaluation)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[Quick start](#quick-start) ·
[How it works](#how-it-works) ·
[Architecture](docs/architecture.md) ·
[Evaluation](#retrieval-evaluation) ·
[Security](#security-boundary)

</div>

## Overview

Repository documentation can drift away from implementation. Repo Witness keeps
those two sources separate:

- A README or manually entered statement is treated as a **claim**.
- Source code, tests, manifests, workflows, and configuration are treated as
  potential **independent evidence**.
- The originating README is excluded from evidence retrieval for claims
  discovered from that README.
- Missing evidence produces `INSUFFICIENT_EVIDENCE`; it is not automatically
  treated as a contradiction.

The result is an evidence-linked audit that remains reviewable by a human.

## What it provides

| Capability | Current behavior |
| --- | --- |
| Safe repository intake | Accepts repository ZIPs through bounded extraction and filtering. |
| Claim discovery | Deterministically suggests implementation-oriented README statements for user review. |
| Manual claims | Supports editable, manually entered technical claims. |
| Provenance tracking | Retains the originating README path and excludes it from independent evidence. |
| Evidence retrieval | Uses deterministic lexical ranking over eligible repository text files. |
| Experimental retrieval | Provides an evaluation-only semantic strategy using local embeddings, not used in production. |
| Analysis | Runs in deterministic demo mode or optional OpenAI-assisted mode. |
| Structured results | Validates verdicts and evidence with existing Pydantic models. |
| Export | Produces a repository-relative Markdown audit report. |
| Evaluation | Includes a deterministic 40-case synthetic retrieval benchmark, runnable against either strategy. |

Every production path continues to use the original lexical retriever. A
semantic retrieval strategy exists behind an internal strategy seam for
evaluation only; it is not wired into the application, and hybrid retrieval is
not implemented.

## How it works

```text
Repository ZIP
    ↓
Safe extraction and filtering
    ↓
README claim discovery or manual claim entry
    ↓
Provenance-aware lexical evidence retrieval
    ↓
Deterministic or OpenAI-assisted analysis
    ↓
Pydantic-validated verdict
    ↓
Streamlit results and Markdown export
```

For the verified component map, trust boundaries, controls, and full Mermaid
flowchart, see [docs/architecture.md](docs/architecture.md).

## Quick start

Repo Witness targets Python 3.11 and runs on Windows, macOS, Linux, and
Streamlit Community Cloud.

```bash
git clone https://github.com/TJA0308/Repo-Witness.git
cd Repo-Witness
python -m venv .venv
pip install -r requirements-dev.txt
```

Activate the virtual environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS or Linux
source .venv/bin/activate
```

Start the application:

```bash
streamlit run app.py
```

No API key is required. Select **Load sample repository**, then
**Find README claims**, to try the deterministic workflow with the bundled
synthetic fixture.

The application needs nothing beyond `requirements-dev.txt`. The optional
semantic evaluation extra is installed separately and only when you want to run
that benchmark:

```bash
pip install -r requirements-semantic.txt
```

## Analysis modes

| Mode | Activation | Behavior |
| --- | --- | --- |
| Deterministic demo | Default when no API key is present | Uses fixed, reproducible heuristics over retrieved lexical evidence. |
| OpenAI-assisted | Set `OPENAI_API_KEY` | Requests a structured `ClaimAudit` using only the bounded evidence candidates. |

Set the optional model explicitly with `OPENAI_MODEL`; the current default is
`gpt-5.1`.

```powershell
# Windows PowerShell
$env:OPENAI_API_KEY="your-key"
$env:OPENAI_MODEL="gpt-5.1"
streamlit run app.py
```

```bash
# macOS or Linux
export OPENAI_API_KEY="your-key"
export OPENAI_MODEL="gpt-5.1"
streamlit run app.py
```

For Streamlit Community Cloud, configure these as root-level secrets. Never
commit API keys or `.streamlit/secrets.toml`.

Both analysis modes require human review. Deterministic verdicts are heuristic,
and model-assisted verdicts can be wrong.

## Retrieval evaluation

The checked-in benchmark evaluates retrieval on 40 claims across four small
synthetic repositories. The default run uses the unchanged production lexical
retriever and requires no network access or API key.

```bash
python -m repo_witness.benchmark
```

A strategy can be selected explicitly. Semantic evaluation needs the optional
extra above, and downloads a small embedding model once on first use:

```bash
python -m repo_witness.benchmark --strategy semantic
```

Lexical is the default, no strategy silently falls back to another, and the
benchmark cases and labels are identical for both.

### Lexical baseline and semantic comparison

| Metric | Lexical (production) | Semantic (experimental) |
| --- | ---: | ---: |
| Total cases | 40 | 40 |
| Recall@1 | 52.8% | 69.4% |
| Recall@3 | 77.8% | 88.9% |
| Recall@5 | 83.3% | 91.7% |
| Mean reciprocal rank | 0.651 | 0.788 |
| Synonym Recall@3 | 33.3% | 66.7% |
| Paraphrase Recall@3 | 55.6% | 66.7% |
| Provenance-exclusion violations | 0 | 0 |
| Unsupported-claim retrieval@3 | 50.0% | 100.0% |

Semantic ranking improved every recall and MRR figure on these fixtures, and
provenance-exclusion violations stayed at zero for both. Precision moved the
other way: semantic retrieval applies no acceptance threshold, so a claim the
repository does not support now always receives topically plausible evidence.
That is why lexical remains the production default.

Of the 40 cases, 36 supported cases contribute to ordinary Recall and MRR;
four unsupported cases are measured separately. The dataset includes exact
matches, synonyms, paraphrases, distractors, multiple valid paths, distributed
evidence, provenance exclusions, unsupported claims, and one separately tagged
ineligible-extension case.

This is a small synthetic benchmark. It characterizes retrieval ranking
behavior only. It does not demonstrate evidence entailment, verdict accuracy,
runtime behavior, or real-world generalization, and a higher Recall@K does not
mean better verdict accuracy.
See the [full metric definitions and category results](docs/architecture.md#retrieval-benchmark).

## Security boundary

Uploaded repositories are untrusted. Repo Witness inspects eligible text but
does not import, build, test, invoke, or otherwise execute uploaded code.

Current ingestion limits:

| Control | Limit |
| --- | ---: |
| Uploaded ZIP | 25 MiB |
| Total eligible extracted data | 25 MiB |
| Individual file | 1 MiB |
| Archive entries | 5,000 |

Extraction rejects or skips unsafe paths, symbolic links, oversized files,
configured dependency/build directories, common binary formats, and selected
secret-bearing names and extensions. These controls reduce risk but do not
provide complete secret or binary detection. Temporary cleanup is best-effort,
and hosting-provider infrastructure remains outside the application boundary.

## Project layout

```text
Repo-Witness/
├── app.py                         # Streamlit application
├── repo_witness/
│   ├── analyzer.py                # Analysis orchestration
│   ├── benchmark.py               # Deterministic retrieval evaluation
│   ├── evidence.py                # Production lexical retriever
│   ├── ingest.py                  # Safe ZIP extraction and filtering
│   ├── models.py                  # Pydantic result models
│   ├── readme_claims.py           # README discovery and claim suggestions
│   └── retrieval/                 # Strategy seam: lexical adapter,
│                                  #   experimental semantic strategy,
│                                  #   embedding providers and cache
├── benchmarks/lexical_evidence/   # Synthetic evaluation data
├── docs/architecture.md           # Architecture and trust boundaries
├── requirements-semantic.txt      # Optional semantic evaluation extra
├── sample_repo/                   # Bundled synthetic repository
└── tests/                         # Automated test suite
```

## Testing

Install development dependencies, then run:

```bash
python -m pytest -q --basetemp .pytest-tmp
```

The current suite contains 126 passing tests covering ingestion safety, size
limits, cleanup, README discovery, lexical characterization, claim provenance,
analysis behavior, Markdown export, benchmark validation, metrics, deterministic
output, retrieval-strategy parity, semantic candidate construction and ranking,
embedding-cache behavior, and lexical-versus-semantic file-eligibility parity.

Semantic tests use a deterministic fake embedding provider, so the suite runs
offline and never downloads a model.

## Known limitations

- Lexical matching can miss synonyms and retrieve irrelevant lexical overlap.
- Evidence distributed across multiple files is difficult to rank within a
  small candidate limit.
- Deterministic demo verdicts are heuristic.
- Model-assisted analysis depends on API and model availability.
- Secret detection and temporary cleanup are best-effort.
- Uploaded code is never executed, so runtime and deployment behavior remain
  outside the proof boundary.
- The retrieval benchmark is synthetic and has not established real-world
  generalization.
- Semantic retrieval is experimental and evaluation-only. It applies no
  acceptance threshold, so unsupported claims still receive plausible-looking
  evidence, and semantic similarity is topical rather than evidential.
- Retrieval metrics measure ranking, not verdict correctness. Evidence
  classification remains future work.
- Semantic determinism was verified in a single environment; cross-machine
  byte-identical output is not guaranteed.

## License

Repo Witness is available under the [MIT License](LICENSE).
