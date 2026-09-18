# RepoWitness

**Catch documentation drift before you ship.**

RepoWitness audits technical README claims against independent code, test, workflow, and configuration evidence, with repository-relative file and line citations.

[![Offline checks](https://github.com/TJA0308/Repo-Witness/actions/workflows/tests.yml/badge.svg)](https://github.com/TJA0308/Repo-Witness/actions/workflows/tests.yml)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Fast-moving and AI-assisted development can leave documentation describing features that were planned, replaced, partially implemented, or removed. RepoWitness helps identify those mismatches before a project is released, submitted, or reviewed. It is a small developer tool for maintainers, students preparing submissions, and developers reviewing a project before sharing it.

This is **static repository evidence analysis**. It does not execute or functionally test the software, and static evidence does not prove runtime correctness. Results are prompts for human review.

## How it works

1. **Add repository:** upload a ZIP or load the safe bundled synthetic example.
2. **Review claims:** discover README suggestions, select them, and edit the claim list; manual entry is also supported.
3. **Inspect audit:** review verdicts, explanations, and collapsible file/line evidence; download a Markdown report.

The application uses deterministic **lexical retrieval**. For an unchanged discovered claim, its originating README is excluded from retrieval so it cannot verify itself. Edited and manual claims have no source mapping; the interface warns when edits lose that exclusion. Documentation and comment mentions alone cannot verify a claim under the local rules.

| Analysis mode | Behavior |
| --- | --- |
| Deterministic local analysis (default) | Fixed rules classify evidence as Supporting, Contradicting, Speculative, or Mention only, then produce a verdict. No API key or model is needed. |
| OpenAI-assisted analysis (optional) | Sends only bounded retrieved snippets for structured analysis; failed requests return insufficient evidence for the affected claim. Uses the same lexical retrieval. |

Verdicts are **Verified**, **Partially verified**, **Contradicted**, and **Insufficient evidence**. Missing evidence is not a contradiction. Confidence labels describe uncalibrated heuristic strength, not probabilities of correctness.

Semantic retrieval exists only for evaluation and is **not enabled in the application**. No hybrid retrieval is implemented. See [architecture and methodology](docs/architecture.md) for details.

## Try the demo

Click **Load sample repository → Find README claims → Run repository audit**. The unchanged bundled example produces:

| README claim | Local verdict |
| --- | --- |
| Uses pytest for automated health-check testing | Verified |
| Includes Docker deployment configuration based on Python 3.11 | Verified |
| Provides a health-check endpoint with production-scale reliability | Partially verified |
| Uses PostgreSQL for persistent health-check storage | Contradicted |
| Publishes signed release artifacts through an automated delivery pipeline | Insufficient evidence |

Open evidence to inspect repository-relative citations. The README is excluded; the reliability claim has limited static support, and the release claim has no independent evidence. Suggested wording appears only when it differs from the claim. The exported report retains verdicts, explanations, source attribution, and evidence paths and line ranges.

## Run locally

Use Python **3.11**:

```bash
git clone https://github.com/TJA0308/Repo-Witness.git
cd Repo-Witness
python -m venv .venv
```

Activate with `.\.venv\Scripts\Activate.ps1` on Windows PowerShell, or `source .venv/bin/activate` on macOS/Linux. Then:

```bash
python -m pip install -r requirements-dev.txt
python -m streamlit run app.py
```

For application-only installation, use `requirements.txt`. No API key is required. To enable optional OpenAI analysis, set `OPENAI_API_KEY` in the environment; `OPENAI_MODEL` optionally overrides the current `gpt-5.1` default. Retrieved snippets leave the host in this mode: review sensitive content before using it. Never commit keys or `.streamlit/secrets.toml`.

### Deploy to Streamlit Community Cloud

After reviewing and merging the changes, select this repository's `main` branch, `app.py`, and Python 3.11 in Community Cloud. It installs `requirements.txt`; the heavy semantic extra is unnecessary. Leave the API key unset for the reproducible local demo, or configure optional root-level `OPENAI_API_KEY` and `OPENAI_MODEL` secrets. Verify the bundled workflow and report download after deployment.

**No live deployment URL is currently documented or verified.** CI checks the app but does not deploy it.

## Tests and benchmarks

```bash
python -m pytest -q --basetemp .pytest-tmp
python -m compileall -q app.py repo_witness tests
python -m repo_witness.benchmark
python -m repo_witness.verdict_benchmark
```

The offline suite covers ingestion, provenance, retrieval parity, verdict safety, model-failure handling, export, and the Streamlit demo workflow. GitHub Actions runs these checks on pushes and pull requests to main using Python 3.11, without API keys or the semantic dependency. Deterministic output guards fail on lexical or verdict benchmark drift. The status badge reflects Actions; it becomes meaningful once this workflow is pushed and runs.

Optional semantic evaluation:

```bash
python -m pip install -r requirements-semantic.txt
python -m repo_witness.benchmark --strategy semantic
```

It uses a local CPU embedding model downloaded on first use. Tests use a fake provider and do not download a model. With the real model already cached, set `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` to evaluate offline.

## What was measured

| Check | Verified result |
| --- | --- |
| Complete offline suite | 207 passing tests |
| Lexical retrieval Recall@3 (production strategy) | 77.8% |
| Semantic retrieval Recall@3 (evaluation-only) | 88.9% |
| Verdict accuracy, before → conservative rules | 38.7% → 83.9% |
| False-verification rate, before → conservative rules | 66.7% → 5.3% |
| Retrieval provenance-exclusion violations | 0 for both strategies |

Retrieval uses **40 synthetic cases** across four small repositories; Recall@3 measures 36 supported cases. Verdict evaluation uses **31 synthetic cases with inline evidence**, independently of retrieval. The verdict dataset and rules share an author, so these results have author bias. Five adversarial failures remain visible. Before/after figures describe the earlier baseline and merged Phase 5 rules; final polish does not change the rules.

Both strategies and the verdict benchmark were run twice before and after polish with identical outputs within this environment. **No real-repository or end-to-end accuracy has been established.** Retrieval recall is not verdict accuracy; higher semantic recall also retrieves plausible snippets for every unsupported fixture claim. Detailed metric definitions, historical results, failure cases, and final verification hashes are in [docs/architecture.md](docs/architecture.md).

## Limits and security boundary

- Lexical matching misses synonyms and can retrieve irrelevant overlap; evidence distributed across files is difficult to rank.
- Local verdict rules can miss paraphrased contradictions, misread nearby negation, and cannot establish absence or broad guarantees. OpenAI-assisted verdicts can also be wrong or unavailable.
- Uploaded code is never imported, built, tested, or executed. Runtime correctness and deployment behavior remain outside the evidence boundary.
- ZIP limits: **25 MiB uploaded**, **25 MiB extracted text**, **1 MiB per file**, **5,000 entries**. Unsafe paths, symlinks, oversized files, common binaries, dependency/build folders, and selected secret-bearing files are skipped. Invalid, empty, or over-limit archives fail with a user-facing message.
- Secret/binary filtering and temporary cleanup are best-effort. Do not upload sensitive repositories; there is no complete secret scanner.
- Synthetic measurements do not establish generalization. Semantic evaluation determinism was checked in one environment, not across machines.

RepoWitness is a review aid for documentation drift, not a guarantee of truth or general code correctness.

## Project map

`app.py` and `styles.css` provide the Streamlit interface. `repo_witness/` contains ZIP intake, claim discovery, lexical retrieval, analysis, verdict rules, display formatting, and export. `sample_repo/` is the safe demo; `benchmarks/` holds synthetic evaluation fixtures; `tests/` contains offline checks. [docs/architecture.md](docs/architecture.md) explains the implementation and tradeoffs.

Available under the [MIT License](LICENSE).
