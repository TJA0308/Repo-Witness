# Repository Claim Audit — RepoWitness

Catch documentation drift before you ship.

Analysis mode: **Deterministic local analysis**

Static repository evidence analysis; software is not executed or functionally tested.
Confidence describes heuristic strength, not a probability of correctness.

## 1. Imports pytest in Python tests.

- Verdict: **Verified**
- Confidence: Moderate (heuristic strength)
- Explanation: A supported static check found the stated import, dependency declaration, Docker base-image instruction, or declared Python version floor. This establishes a fact about repository text, not successful execution or deployment.
- Excluded review document: README.md
- Evidence count: 5

### Repository evidence

- `.github/workflows/test.yml:1-3` — Mention only

```text
1: name: tests
2: on: [push]
3: jobs:
```

- `.github/workflows/test.yml:6-10` — Mention only

```text
6:     steps:
7:       - uses: actions/checkout@v4
8:       - run: pip install pytest
9:       - run: pytest
10:
```

- `Dockerfile:1-4` — Mention only

```text
1: FROM python:3.11-slim
2: COPY . /app
3: CMD ["python", "-m", "app"]
4:
```

- `app.py:1-3` — Mention only

```text
1: """Synthetic app: pytest-backed and Dockerized."""
2:
3: STORAGE_POLICY = "This service does not use PostgreSQL; health data exists only in memory."
```

- `tests/test_app.py:1-3` — Supporting

```text
1: import pytest
2: from app import healthcheck
3: def test_healthcheck():
```

## 2. Includes Docker deployment configuration based on Python 3.11.

- Verdict: **Verified**
- Confidence: Moderate (heuristic strength)
- Explanation: A supported static check found the stated import, dependency declaration, Docker base-image instruction, or declared Python version floor. This establishes a fact about repository text, not successful execution or deployment.
- Excluded review document: README.md
- Evidence count: 2

### Repository evidence

- `Dockerfile:1-4` — Supporting

```text
1: FROM python:3.11-slim
2: COPY . /app
3: CMD ["python", "-m", "app"]
4:
```

- `app.py:1-3` — Mention only

```text
1: """Synthetic app: pytest-backed and Dockerized."""
2:
3: STORAGE_POLICY = "This service does not use PostgreSQL; health data exists only in memory."
```

## 3. Includes Docker configuration based on Python 3.11 with production-scale reliability.

- Verdict: **Partially verified**
- Confidence: Moderate (heuristic strength)
- Explanation: A bounded repository fact was found, but the claim's absolute or broad scope is not established by static evidence.
- Excluded review document: README.md
- Evidence count: 2
- Suggested corrected wording: Includes Docker configuration based on Python 3.11 with production-scale reliability, though the retrieved evidence does not establish its full scope.

### Repository evidence

- `Dockerfile:1-4` — Supporting

```text
1: FROM python:3.11-slim
2: COPY . /app
3: CMD ["python", "-m", "app"]
4:
```

- `app.py:1-3` — Mention only

```text
1: """Synthetic app: pytest-backed and Dockerized."""
2:
3: STORAGE_POLICY = "This service does not use PostgreSQL; health data exists only in memory."
```

## 4. Uses PostgreSQL for persistent health-check storage.

- Verdict: **Contradicted**
- Confidence: Moderate (heuristic strength)
- Explanation: A retrieved repository statement negates the claim or records the claimed approach as one that was not taken.
- Excluded review document: README.md
- Evidence count: 1
- Suggested corrected wording: Repository evidence conflicts with this claim; resolve the conflict before restating: Uses PostgreSQL for persistent health-check storage.

### Repository evidence

- `app.py:1-6` — Contradicting

```text
1: """Synthetic app: pytest-backed and Dockerized."""
2:
3: STORAGE_POLICY = "This service does not use PostgreSQL; health data exists only in memory."
4: HEALTH_CHECK_ENDPOINT = "health-check"
5:
6: def healthcheck():
```

## 5. Publishes signed release artifacts through an automated delivery pipeline.

- Verdict: **Insufficient evidence**
- Confidence: Low (heuristic strength)
- Explanation: No relevant evidence found: no repository snippet was retrieved. Try a more specific claim or inspect the repository manually. This is not evidence of contradiction.
- Excluded review document: README.md
- Evidence count: 0
- Suggested corrected wording: Publishes signed release artifacts through an automated delivery pipeline — not established by the retrieved repository evidence.

### Repository evidence

No relevant evidence snippet retrieved.
