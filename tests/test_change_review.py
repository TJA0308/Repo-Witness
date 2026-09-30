"""Review signals describe changed retrieved passages, never runtime correctness."""
import pytest

from repo_witness.change_review import compare_claims, markdown_change_review, snapshot_root
from repo_witness.models import Verdict


CLAIM = "Declares requests as a Python dependency."


@pytest.fixture
def snapshots(tmp_path):
    before, after = tmp_path / "before", tmp_path / "after"
    before.mkdir()
    after.mkdir()
    return before, after


def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def test_removed_declaration_flags_deleted_evidence_not_false_claim(snapshots):
    before, after = snapshots
    write(before, "requirements.txt", "requests>=2\n")
    write(after, "requirements.txt", "urllib3>=2\n")
    for root in snapshots:
        write(root, "README.md", CLAIM)
    report = compare_claims(before, after, [CLAIM], {CLAIM: "README.md"})
    item = report.claims[0]
    assert item.status == "REVIEW_NEEDED"
    assert item.before.verdict == Verdict.VERIFIED
    assert item.after.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert item.changes[0].diff == "--- before/requirements.txt\n+++ after/requirements.txt\n@@ -1,1 +1,1 @@\n-requests>=2\n+urllib3>=2"
    assert all(e.path != "README.md" for audit in (item.before, item.after) for e in audit.evidence)
    exported = markdown_change_review(report)
    assert "not that the claim is false" in exported
    assert "requirements.txt:1-1" in exported


@pytest.mark.parametrize("added", [True, False])
def test_added_and_removed_files_retrieve_both_sides(snapshots, added):
    before, after = snapshots
    write(after if added else before, "requirements.txt", "requests>=2\n")
    item = compare_claims(before, after, [CLAIM]).claims[0]
    assert item.status == "REVIEW_NEEDED"
    assert item.changes[0].change == ("added" if added else "removed")


def test_unrelated_file_and_same_file_edit_do_not_flag_import(snapshots):
    before, after = snapshots
    claim = "Imports pytest in Python tests."
    common = "import pytest\n" + "\n" * 15
    write(before, "tests/test_app.py", common + "def test_value():\n    assert 1 == 1\n")
    write(after, "tests/test_app.py", common + "def test_value():\n    assert 2 == 2\n")
    write(before, "notes.txt", "Meeting on Tuesday.")
    write(after, "notes.txt", "Meeting on Wednesday.")
    write(before, "Dockerfile", "FROM python:3.11")
    write(after, "Dockerfile", "FROM python:3.12")
    report = compare_claims(before, after, [claim])
    assert report.changed_file_count == 3
    assert report.claims[0].status == "NO_RETRIEVED_CHANGE"
    assert not report.claims[0].changes


def test_no_retrieved_evidence_is_distinct_from_no_change(snapshots):
    before, after = snapshots
    write(before, "notes.txt", "Hello")
    write(after, "notes.txt", "Goodbye")
    assert compare_claims(before, after, [CLAIM]).claims[0].status == "NO_EVIDENCE"
    for root in snapshots:
        write(root, "requirements.txt", "requests>=2")
    assert compare_claims(before, after, [CLAIM]).claims[0].status == "NO_RETRIEVED_CHANGE"


def test_source_exclusion_survives_edits_and_diffs_are_bounded(snapshots):
    before, after = snapshots
    claim = "Uses widget storage."
    write(before, "README.md", "Uses widget storage before.")
    write(after, "README.md", "Uses widget storage after.")
    assert compare_claims(before, after, [claim], {claim: "README.md"}).claims[0].status == "NO_EVIDENCE"
    write(before, "app.py", "# widget storage\n" + "a = 1\n" * 100)
    write(after, "app.py", "# widget storage replacement\n" + "a = 2\n" * 100)
    item = compare_claims(before, after, [claim], {claim: "README.md"}).claims[0]
    assert item.status == "REVIEW_NEEDED"
    assert item.changes[0].truncated
    assert item.changes[0].diff.endswith("[diff truncated]")
    assert len(item.changes[0].diff) < 4030


def test_comparison_validates_same_claim_limits(snapshots):
    with pytest.raises(ValueError, match="at most 10"):
        compare_claims(*snapshots, [CLAIM] * 11)


def test_wrapper_normalization_and_plain_snapshot(tmp_path):
    wrapper = tmp_path / "repo-commit"
    wrapper.mkdir()
    write(wrapper, "README.md", "Hello")
    assert snapshot_root(tmp_path) == wrapper
    write(tmp_path, "requirements.txt", "requests")
    assert snapshot_root(tmp_path) == tmp_path
