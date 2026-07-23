# Repo Witness

Repo Witness is a focused repository claim auditor for OpenAI Build Week's Developer Tools track. Upload a repository ZIP, discover candidate technical claims from its README or enter claims manually, and receive evidence-linked verdicts with supporting excerpts and cautious corrected wording.

## Supported platforms

Repo Witness targets Python 3.11 and runs on Windows, macOS, Linux, and Streamlit Community Cloud. It uses `pathlib` and standard-library ZIP handling; no machine-specific paths or external system packages are required.

## Installation

```bash
python -m venv .venv
pip install -r requirements-dev.txt
```

Activate the environment on Windows with `.venv\Scripts\activate`, or on macOS/Linux with `source .venv/bin/activate`.

## Run locally

```bash
streamlit run app.py
```

No API key is required. Without `OPENAI_API_KEY`, the app starts in deterministic demo mode. Click **Load sample repository**, then **Find README claims**, to review suggestions from the bundled `sample_repo/`. You can also upload a ZIP and enter claims manually.

## README claim discovery

After uploading or loading a repository, click **Find README claims**. Repo Witness prefers a root-level `README.md`, `README.rst`, `README.txt`, or `README`, and offers a selector when several are available. It deterministically suggests concise implementation-oriented statements while excluding headings, badges, code fences, commands, URLs, contribution text, license text, and obvious duplicates. Claim discovery makes no OpenAI API request.

Discovered claims are suggestions, not verdicts. Select the useful suggestions, apply them to the editable claim list, add or remove wording as needed, and run the audit only after review. Manual claim entry remains available throughout; no discovered claim is audited automatically.

## Optional OpenAI mode

Set `OPENAI_API_KEY` to enable model-assisted analysis. Set `OPENAI_MODEL` to choose the model; the default is `gpt-5.1`.

PowerShell:

```powershell
$env:OPENAI_API_KEY="your-key"
$env:OPENAI_MODEL="gpt-5.1"
streamlit run app.py
```

macOS/Linux:

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_MODEL="gpt-5.1"
streamlit run app.py
```

For Streamlit Community Cloud, add these values as root-level secrets in the app's Advanced settings. Never commit API keys or `.streamlit/secrets.toml`.

## Testing

Install development dependencies, then run the documented suite:

```bash
python -m pytest -q --basetemp .pytest-tmp
```

The tests cover ZIP safety, filtering, size limits, temporary cleanup, README discovery and extraction, empty claims, deterministic evidence retrieval, manual claims, the bundled sample, and Markdown export.

## Evaluation

RepoWitness includes a deterministic synthetic evaluation of the production lexical evidence retriever. See the [lexical retrieval benchmark](#lexical-retrieval-benchmark) for the command, metrics, and limitations.

## Lexical retrieval benchmark

The checked-in benchmark measures whether the existing lexical evidence retriever returns an expected repository-relative file for 12 synthetic claims. It reports Hit Rate / Recall@1, Recall@3, Recall@5, mean reciprocal rank (MRR), the number of evaluated cases, and the first expected snippet rank for each case. A rank is the one-based position of the first retrieved snippet from any expected file; an unretrieved expected file has a `null` rank.

The dataset includes direct lexical matches, a synonym case, irrelevant distractors, and README provenance exclusions. Its files are small synthetic fixtures under `benchmarks/lexical_evidence/`; it uses no private or downloaded repository and requires no API key.

Run it from the repository root:

```bash
python -m repo_witness.benchmark
```

Current checked-in results, measured with that command, are 12 evaluated cases, Hit Rate / Recall@1 `0.75`, Recall@3 `0.9166666666666666`, Recall@5 `0.9166666666666666`, and MRR `0.8333333333333334`. The complete command output includes every case's rank and retrieved repository-relative paths.

This small synthetic benchmark checks deterministic lexical ranking and source exclusion only. It does not demonstrate semantic understanding, generalize to arbitrary repositories, prove that retrieved text supports a claim, validate verdict quality, or establish runtime behavior. In particular, synonym phrasing can be missed.

## Architecture

RepoWitness separates untrusted repository ingestion, claim provenance, bounded lexical retrieval, structured analysis, and presentation. See the [technical architecture](docs/architecture.md) for the verified system flow, component map, trust boundaries, exact security controls, analysis modes, design decisions, benchmark context, and limitations.

Repository evidence is kept separate from analysis. Missing evidence is never treated as contradiction.

### Evidence authority and provenance

For README-discovered claims, the selected README is tracked as the **claim source** and excluded from supporting **repository evidence**. A claim source explains what the project asserts; it cannot prove that assertion. Implementation verdicts require independent technical artifacts such as source code, tests, dependency manifests, CI workflows, Docker or deployment configuration, migrations, schemas, infrastructure-as-code, or executable configuration. When no independent evidence remains, the verdict is `INSUFFICIENT_EVIDENCE`.

General documentation, project descriptions, comments, and unexecuted examples are contextual and lower-authority than implementation artifacts. Repo Witness displays the originating README path separately and never includes that file as evidence for its discovered claim.

## Limitations

README discovery is deterministic and heuristic, not semantic understanding or universal Markdown parsing. It intentionally favors a few explicit implementation statements and may miss claims, especially when prose spans several lines or uses unusual wording. Originating README statements are excluded from implementation evidence, but users must still review the authority and relevance of every independent snippet.

Demo mode is deterministic but intentionally heuristic: lexical matches can miss synonyms and do not prove runtime or production behavior. The app does not execute uploaded code. Model-assisted classifications can still be wrong and require human review.

Uploads are limited to 25 MB, 5,000 archive entries, 25 MiB of eligible extracted text, and 1 MiB per individual file. Uploaded repositories are processed in a temporary workspace and are not intentionally retained. Cleanup is best-effort, and deployment-provider infrastructure is outside this application's control. In model-assisted mode, only retrieved evidence snippets are sent to OpenAI; demo mode makes no OpenAI API request.

## How Codex with GPT-5.6 was used

Codex with GPT-5.6 was used to design and implement the secure ingestion, evidence retrieval, structured analysis, Streamlit UI, Markdown export, synthetic fixture, and verification workflow. Codex assisted implementation; repository evidence remains the source of truth for every audit.

## License

Repo Witness is open source under the [MIT License](LICENSE).
