# Pinned public-repository smoke test

For five manually reasoned examples with expected and actual verdicts, see
[the authored walkthrough](authored-cases.md). Those selected cases are separate
from this unlabeled smoke test; independent review is still pending.

This is an audit of three public project snapshots. It checks whether discovery,
retrieval, citations, and the verdict rules run on repositories outside the
synthetic fixtures. It is **not an accuracy estimate**: the 23 claims have no
independent verdict labels, and no code was executed.

| Repository | Commit | Suggested claims | Verified | Partial | Contradicted | Insufficient |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [Click](https://github.com/pallets/click/tree/06b2a678741131fd577ce170e23e5ca0aeba0309) | `06b2a67` | 3 | 0 | 0 | 0 | 3 |
| [HTTPX](https://github.com/encode/httpx/tree/b5addb64f0161ff6bfe94c124ef76f6a1fba5254) | `b5addb6` | 10 | 1 | 0 | 0 | 9 |
| [Requests](https://github.com/psf/requests/tree/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60) | `611c616` | 10 | 0 | 1 | 0 | 9 |

The version claims provide the clearest examples. HTTPX's README says it
requires Python 3.9+, and root `pyproject.toml` declares `requires-python =
">=3.9"`. RepoWitness verifies the **declared minimum**. Requests says it
"officially supports Python 3.10+"; its metadata declares `>=3.10`, but that
does not establish full support, so RepoWitness marks the claim partial.

The other claims mostly describe runtime features that the current static
checks cannot establish. Those abstentions are visible in the saved
[case results](real_repositories.json). The source files and cited line ranges
were validated against each extracted snapshot. That check establishes citation
existence, not whether every cited excerpt is relevant. A sample review found
plausible but weak documentation excerpts among the top results. Historical
changelogs and history files are excluded from current evidence.

The first run exposed false contradictions: nearby "not" in examples about
HTTP/2 response versioning, Requests' timeout defaults, and invalid bare URLs
was being read as a rejection of unrelated feature claims. The new rule
requires a direct rejection of the claim term. The observed cases now abstain,
while explicit lines such as "does not use PostgreSQL" still contradict.

## Reproduce

Download the three exact commit archives into one temporary directory. On
PowerShell:

```powershell
$archiveDir = Join-Path $env:TEMP 'repo-witness-eval'
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
curl.exe -L -f -o (Join-Path $archiveDir 'click.zip') 'https://codeload.github.com/pallets/click/zip/06b2a678741131fd577ce170e23e5ca0aeba0309'
curl.exe -L -f -o (Join-Path $archiveDir 'httpx.zip') 'https://codeload.github.com/encode/httpx/zip/b5addb64f0161ff6bfe94c124ef76f6a1fba5254'
curl.exe -L -f -o (Join-Path $archiveDir 'requests.zip') 'https://codeload.github.com/psf/requests/zip/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60'
python -m repo_witness.real_evaluation $archiveDir
```

Run from the project root after installing `requirements.txt`. The evaluator
uses the same bounded ZIP extraction, README discovery, retrieval, and
deterministic analyzer as the app. It validates citation paths and line ranges,
prints JSON, and cleans its temporary extraction. It never runs repository
code. The saved JSON includes the SHA-256 of each downloaded archive; compare
those values if a newly downloaded archive produces different output.

For a proper accuracy estimate, the next dataset needs independent reviewers
to label claims and citations before changing the rules. Keep that dataset
separate from the current synthetic development cases.
