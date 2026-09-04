"""Parity between lexical and semantic candidate discovery.

``repo_witness.evidence`` and ``repo_witness.retrieval.candidates`` duplicate
their file-eligibility rules, because sharing the code would require editing the
frozen lexical retriever. These tests pin that duplication: they prove the two
agree on the checked-in fixtures, and they pin the three checks that are
deliberately stricter on the semantic side so neither can drift unnoticed.
"""

from pathlib import Path

import pytest

from repo_witness.benchmark import DEFAULT_REPOSITORY
from repo_witness.evidence import TEXT_EXTENSIONS
from repo_witness.ingest import MAX_FILE_BYTES
from repo_witness.retrieval.candidates import EXTENSIONLESS_NAMES, build_candidates

PROJECT_ROOT = Path(__file__).parents[1]
FIXTURE_ROOTS = [PROJECT_ROOT / "sample_repo", *sorted(DEFAULT_REPOSITORY.iterdir())]


def lexical_eligible_paths(root, excluded_paths=()):
    """Re-derive lexical file eligibility from `retrieve_evidence`'s own rules.

    This mirrors `repo_witness/evidence.py` lines 25-30 without importing private
    helpers, so a change to the lexical rules surfaces here as a parity failure.
    """
    excluded = {path.replace("\\", "/").casefold() for path in excluded_paths}
    paths = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if (
            path.suffix.lower() not in TEXT_EXTENSIONS
            and path.name.lower() not in EXTENSIONLESS_NAMES
        ):
            continue
        relative = path.relative_to(root).as_posix()
        if relative.casefold() in excluded:
            continue
        paths.append(relative)
    return paths


def semantic_eligible_paths(root, excluded_paths=()):
    return [*dict.fromkeys(chunk.path for chunk in build_candidates(root, excluded_paths))]


@pytest.mark.parametrize("root", FIXTURE_ROOTS, ids=lambda root: root.name)
def test_fixtures_agree_on_file_eligibility(root):
    assert semantic_eligible_paths(root) == lexical_eligible_paths(root)


@pytest.mark.parametrize("root", FIXTURE_ROOTS, ids=lambda root: root.name)
def test_fixtures_agree_on_exclusions(root):
    eligible = lexical_eligible_paths(root)
    assert eligible, "fixture must contain eligible files"
    excluded = [eligible[0].replace("/", "\\").upper()]

    lexical = lexical_eligible_paths(root, excluded)
    semantic = semantic_eligible_paths(root, excluded)

    assert semantic == lexical
    assert eligible[0] not in semantic


@pytest.mark.parametrize(
    "extension",
    sorted(TEXT_EXTENSIONS),
)
def test_every_supported_extension_is_eligible_for_both(tmp_path, extension):
    (tmp_path / f"file{extension}").write_text("alpha beta gamma\n", encoding="utf-8")

    assert semantic_eligible_paths(tmp_path) == lexical_eligible_paths(tmp_path)
    assert semantic_eligible_paths(tmp_path) == [f"file{extension}"]


@pytest.mark.parametrize("name", sorted(EXTENSIONLESS_NAMES))
def test_extensionless_names_are_eligible_for_both(tmp_path, name):
    (tmp_path / name.capitalize()).write_text("FROM python\n", encoding="utf-8")

    assert semantic_eligible_paths(tmp_path) == lexical_eligible_paths(tmp_path)


def test_unsupported_extension_is_ineligible_for_both(tmp_path):
    (tmp_path / "events.sql").write_text("CREATE TABLE events (id INT);\n", encoding="utf-8")

    assert lexical_eligible_paths(tmp_path) == []
    assert semantic_eligible_paths(tmp_path) == []


def test_semantic_is_deliberately_stricter_on_ignored_paths(tmp_path):
    """Documented divergence: ingestion already removes these before retrieval."""
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "vendor.py").write_text("alpha\n", encoding="utf-8")
    (tmp_path / "keep.py").write_text("alpha\n", encoding="utf-8")

    assert "node_modules/vendor.py" in lexical_eligible_paths(tmp_path)
    assert semantic_eligible_paths(tmp_path) == ["keep.py"]


def test_semantic_is_deliberately_stricter_on_binary_content(tmp_path):
    (tmp_path / "binary.py").write_bytes(b"alpha\x00beta\n")
    (tmp_path / "keep.py").write_text("alpha\n", encoding="utf-8")

    assert "binary.py" in lexical_eligible_paths(tmp_path)
    assert semantic_eligible_paths(tmp_path) == ["keep.py"]


def test_semantic_is_deliberately_stricter_on_oversized_files(tmp_path):
    (tmp_path / "huge.py").write_text("a" * (MAX_FILE_BYTES + 1), encoding="utf-8")
    (tmp_path / "keep.py").write_text("alpha\n", encoding="utf-8")

    assert "huge.py" in lexical_eligible_paths(tmp_path)
    assert semantic_eligible_paths(tmp_path) == ["keep.py"]


def test_both_decode_invalid_utf8_leniently_rather_than_skipping(tmp_path):
    (tmp_path / "latin.py").write_bytes(b"caf\xe9 worker\n")

    assert semantic_eligible_paths(tmp_path) == lexical_eligible_paths(tmp_path) == [
        "latin.py"
    ]
