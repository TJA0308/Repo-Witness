from repo_witness.evidence import _terms, retrieve_evidence


def test_tokenization_normalizes_case_length_characters_and_exact_stop_words():
    claim = (
        "THE and WITH Uses HAS for a an go API C++ F#lang ASP.NET "
        "node_js foo-bar use using"
    )

    assert _terms(claim) == [
        "api",
        "c++",
        "f#lang",
        "asp.net",
        "node_js",
        "foo-bar",
        "use",
        "using",
    ]


def test_substring_matching_is_directional_and_does_not_normalize_processes(tmp_path):
    source = tmp_path / "worker.txt"
    source.write_text("the worker will process tasks\n", encoding="utf-8")

    assert retrieve_evidence(tmp_path, "Processes deferred jobs") == []
    assert retrieve_evidence(tmp_path, "Process deferred jobs")

    source.write_text("the worker processes tasks\n", encoding="utf-8")

    assert retrieve_evidence(tmp_path, "Process deferred jobs")
    assert retrieve_evidence(tmp_path, "Processes deferred jobs")


def test_scoring_favors_distinct_coverage_over_repeated_occurrences(tmp_path):
    (tmp_path / "coverage.txt").write_text("alpha beta\n", encoding="utf-8")
    (tmp_path / "repeated.txt").write_text(
        "alpha alpha alpha alpha alpha\n",
        encoding="utf-8",
    )

    evidence = retrieve_evidence(tmp_path, "alpha beta")

    assert [item.path for item in evidence] == ["coverage.txt", "repeated.txt"]
    assert [item.relevance for item in evidence] == [
        "Matched: alpha, beta; score 22",
        "Matched: alpha; score 15",
    ]


def test_ordering_uses_score_then_path_then_matching_line(tmp_path):
    (tmp_path / "z_high.txt").write_text("alpha beta\n", encoding="utf-8")
    (tmp_path / "a_tie.txt").write_text(
        "alpha\none\ntwo\nthree\nfour\nalpha\n",
        encoding="utf-8",
    )
    (tmp_path / "b_tie.txt").write_text("alpha\n", encoding="utf-8")

    evidence = retrieve_evidence(tmp_path, "alpha beta")

    assert [item.path for item in evidence] == [
        "z_high.txt",
        "a_tie.txt",
        "a_tie.txt",
        "b_tie.txt",
    ]
    assert [item.start_line for item in evidence] == [1, 1, 4, 1]
    assert [item.relevance for item in evidence] == [
        "Matched: alpha, beta; score 22",
        "Matched: alpha; score 11",
        "Matched: alpha; score 11",
        "Matched: alpha; score 11",
    ]


def test_separate_matching_lines_in_one_file_occupy_separate_ranks(tmp_path):
    (tmp_path / "repeated.txt").write_text(
        "alpha\ncontext one\ncontext two\ncontext three\ncontext four\nalpha\n",
        encoding="utf-8",
    )

    evidence = retrieve_evidence(tmp_path, "alpha")

    assert len(evidence) == 2
    assert [item.path for item in evidence] == ["repeated.txt", "repeated.txt"]
    assert [item.start_line for item in evidence] == [1, 4]
    assert all(item.relevance == "Matched: alpha; score 11" for item in evidence)


def test_filename_terms_do_not_create_evidence(tmp_path):
    (tmp_path / "postgresql_database.py").write_text(
        'print("hello")\n',
        encoding="utf-8",
    )

    assert retrieve_evidence(tmp_path, "Uses PostgreSQL database") == []


def test_provenance_exclusion_normalizes_slashes_and_case(tmp_path):
    docs = tmp_path / "Docs"
    docs.mkdir()
    source = tmp_path / "src"
    source.mkdir()
    (docs / "README.md").write_text("alpha implementation\n", encoding="utf-8")
    (source / "app.py").write_text("alpha implementation\n", encoding="utf-8")

    evidence = retrieve_evidence(
        tmp_path,
        "alpha implementation",
        excluded_paths=[r"docs\readme.MD"],
    )

    assert [item.path for item in evidence] == ["src/app.py"]
    assert all(item.path.casefold() != "docs/readme.md" for item in evidence)


def test_complete_lexical_output_compatibility_fixture(tmp_path):
    (tmp_path / "a.py").write_text(
        "header\nalpha beta\ncontext\n",
        encoding="utf-8",
    )
    (tmp_path / "b.txt").write_text(
        "alpha alpha\nbeta\n",
        encoding="utf-8",
    )
    (tmp_path / "notes.md").write_text("alpha\n", encoding="utf-8")

    serialized = [
        item.model_dump()
        for item in retrieve_evidence(tmp_path, "Uses ALPHA beta")
    ]

    assert serialized == [
        {
            "path": "a.py",
            "start_line": 1,
            "end_line": 3,
            "excerpt": "1: header\n2: alpha beta\n3: context",
            "relevance": "Matched: alpha, beta; score 22",
        },
        {
            "path": "b.txt",
            "start_line": 1,
            "end_line": 2,
            "excerpt": "1: alpha alpha\n2: beta",
            "relevance": "Matched: alpha; score 12",
        },
        {
            "path": "b.txt",
            "start_line": 1,
            "end_line": 2,
            "excerpt": "1: alpha alpha\n2: beta",
            "relevance": "Matched: beta; score 11",
        },
        {
            "path": "notes.md",
            "start_line": 1,
            "end_line": 1,
            "excerpt": "1: alpha",
            "relevance": "Matched: alpha; score 11",
        },
    ]
