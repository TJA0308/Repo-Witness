from pathlib import Path

from repo_witness.analyzer import analyze_demo
from repo_witness.readme_claims import discover_readmes, extract_candidate_claims


def test_root_readme_is_preferred_over_nested_readme(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("Nested", encoding="utf-8")
    (tmp_path / "README.md").write_text("Root", encoding="utf-8")
    documents = discover_readmes(tmp_path)
    assert [document.path for document in documents] == ["README.md", "docs/README.md"]


def test_readme_names_are_case_insensitive_and_multiple_are_returned(tmp_path):
    (tmp_path / "README.RST").write_text("Root", encoding="utf-8")
    (tmp_path / "guide").mkdir()
    (tmp_path / "guide" / "readme.TXT").write_text("Guide", encoding="utf-8")
    assert [document.path for document in discover_readmes(tmp_path)] == ["README.RST", "guide/readme.TXT"]


def test_discovery_skips_ignored_and_binary_readmes(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "README.md").write_text("Uses a dependency.", encoding="utf-8")
    (tmp_path / "README.txt").write_bytes(b"binary\x00content")
    assert discover_readmes(tmp_path) == []


def test_extractor_excludes_headings_badges_commands_fences_and_tables():
    text = """# Features
[![Build](https://example.com/badge.svg)](https://example.com)
pip install repo-witness
```python
app.run()
```
| Feature | Status |
| --- | --- |
## Architecture
- Uses pytest for automated testing.
- Includes Docker deployment configuration.
"""
    assert extract_candidate_claims(text) == [
        "Uses pytest for automated testing.",
        "Includes Docker deployment configuration.",
    ]


def test_extractor_keeps_useful_claims_and_removes_near_duplicates():
    text = """## Features
- Provides deterministic repository audits without requiring an API key.
- Provides deterministic repository auditing without an API key.
- Supports Markdown report exports with repository-relative evidence paths.
Our revolutionary developer experience changes everything.
"""
    claims = extract_candidate_claims(text)
    assert len(claims) == 2
    assert claims[0].startswith("Provides deterministic")
    assert claims[1].startswith("Supports Markdown")


def test_empty_and_missing_readme_behavior(tmp_path):
    assert discover_readmes(tmp_path) == []
    assert extract_candidate_claims("") == []
    assert extract_candidate_claims("```markdown\nUses Redis for caching.\n") == []
    (tmp_path / "README").write_text("# Empty\n", encoding="utf-8")
    documents = discover_readmes(tmp_path)
    assert len(documents) == 1
    assert extract_candidate_claims(documents[0].text) == []


def test_bundled_sample_readme_discovers_claims():
    sample_root = Path(__file__).parents[1] / "sample_repo"
    documents = discover_readmes(sample_root)
    claims = extract_candidate_claims(documents[0].text)
    assert len(claims) >= 4
    assert any("pytest" in claim.lower() for claim in claims)
    assert any("Docker" in claim for claim in claims)


def test_manual_claim_workflow_remains_functional(tmp_path):
    (tmp_path / "app.py").write_text("import pytest\n", encoding="utf-8")
    report = analyze_demo(tmp_path, ["Uses pytest for testing"])
    assert len(report.audits) == 1
    assert report.audits[0].claim == "Uses pytest for testing"
