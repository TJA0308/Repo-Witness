# Repo Witness

Repo Witness is a tightly scoped repository claim auditor for Build Week's Developer Tools track. Upload a ZIP, enter one technical claim per line, and get evidence-linked verdicts plus cautious corrected wording.

## Setup
```bash
python -m venv .venv
.venv\Scripts\activate  # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```
Set `OPENAI_API_KEY` to enable the OpenAI adapter. Without it, the app uses deterministic demo mode. The adapter defaults to `gpt-5.1`; change the model in code if your account uses another structured-output-capable model.

## Architecture
`ingest.py` validates ZIP size, rejects traversal and symlinks, limits individual files, filters secrets/binaries/dependencies/build outputs, and extracts only eligible text. `evidence.py` performs deterministic term scoring and returns at most six small line-numbered snippets. `analyzer.py` sends only those snippets to OpenAI and parses a Pydantic `ClaimAudit`; demo mode uses the same evidence boundary. `export.py` renders evidence-linked Markdown. `app.py` provides the Streamlit UI.

Evidence is repository fact; reasoning, confidence, verdict, and corrected wording are model/demo analysis. Missing evidence is never treated as contradiction.

## Testing and fixture
Run `python -m pytest -q`. `sample_repo/` is a small synthetic repository with pytest, Docker, CI, and deliberately absent PostgreSQL/Kubernetes evidence. To make a ZIP on your machine, compress that directory and upload it.

## Limitations
This MVP uses lexical retrieval rather than semantic search, does not execute code, cannot prove runtime or production behavior, and may miss claims expressed with unusual vocabulary. ZIPs are capped at 25 MiB and files at 1 MiB. The OpenAI path makes one request per claim; API failures are surfaced rather than silently relabeled.

## How Codex with GPT-5.6 was used
Codex with GPT-5.6 was used to design the vertical slice, implement the secure ingestion/retrieval/analyzer/UI/export layers, create the synthetic fixture, and run the test and smoke-test workflow. The model is an implementation assistant; repository evidence remains the source of truth for each audit.
