# Repo Witness

Repo Witness is a focused repository claim auditor for OpenAI Build Week's Developer Tools track. Upload a repository ZIP, enter technical claims, and receive evidence-linked verdicts with supporting excerpts and cautious corrected wording.

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

No API key is required. Without `OPENAI_API_KEY`, the app starts in deterministic demo mode. Click **Load sample** to run an audit against the bundled `sample_repo/`, or upload a ZIP and enter one claim per line.

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

The tests cover ZIP safety, filtering, size limits, temporary cleanup, empty claims, deterministic evidence retrieval, and Markdown export.

## Architecture

`repo_witness/ingest.py` validates archive size, rejects traversal and symlinks, limits entries and extracted text, and filters secrets, binaries, dependencies, and build outputs. `repo_witness/evidence.py` deterministically scores repository text and returns at most six small line-numbered snippets. `repo_witness/analyzer.py` either applies deterministic demo heuristics or sends only those snippets to OpenAI and parses a Pydantic `ClaimAudit`. `repo_witness/export.py` creates the evidence-linked Markdown report. `app.py` is the Streamlit deployment entry point.

Repository evidence is kept separate from analysis. Missing evidence is never treated as contradiction.

## Limitations

Demo mode is deterministic but intentionally heuristic: lexical matches can miss synonyms and do not prove runtime or production behavior. The app does not execute uploaded code. Model-assisted classifications can still be wrong and require human review.

Uploads are limited to 25 MB, 5,000 archive entries, 25 MiB of eligible extracted text, and 1 MiB per individual file. Uploaded repositories are processed in a temporary workspace and are not intentionally retained. Cleanup is best-effort, and deployment-provider infrastructure is outside this application's control. In model-assisted mode, only retrieved evidence snippets are sent to OpenAI; demo mode makes no OpenAI API request.

## How Codex with GPT-5.6 was used

Codex with GPT-5.6 was used to design and implement the secure ingestion, evidence retrieval, structured analysis, Streamlit UI, Markdown export, synthetic fixture, and verification workflow. Codex assisted implementation; repository evidence remains the source of truth for every audit.

## License

Repo Witness is open source under the [MIT License](LICENSE).
