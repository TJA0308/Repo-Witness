"""Small, explicit checks for facts that can be established from static text.

Only these narrow claim forms can be VERIFIED by the deterministic analyzer.
Other claims still get retrieved evidence and contradiction checks, but keyword
overlap alone cannot verify them. Add a new check only with positive and negative
examples explaining precisely what it establishes.
"""
from __future__ import annotations

import ast
import re
import tomllib
from collections.abc import Mapping
from pathlib import PurePosixPath

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from .models import EvidenceSnippet

DEPENDENCY_CLAIM = re.compile(r"declares ([a-z0-9][a-z0-9._-]*) as a python dependency", re.I)


def pyproject_dependency_evidence(claim: str, lines: list[str]) -> EvidenceSnippet | None:
    """Parse root project dependencies and locate their complete source assignment.

    Parsing prefixes locates the assignment without mistaking text inside a TOML
    multiline string or an unrelated table for the project dependency list.
    A declaration too large for a 1,200-character citation stays unresolved.
    """
    match = DEPENDENCY_CLAIM.fullmatch(claim.strip().rstrip("."))
    if not match:
        return None
    try:
        document = tomllib.loads("\n".join(lines))
        project = document.get("project")
        if not isinstance(project, dict) or "dependencies" in project.get("dynamic", []):
            return None
        dependencies = project.get("dependencies")
        if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
            return None
        names = {canonicalize_name(Requirement(item).name) for item in dependencies}
    except (tomllib.TOMLDecodeError, InvalidRequirement, TypeError):
        return None
    if canonicalize_name(match.group(1)) not in names:
        return None
    for start, line in enumerate(lines):
        if not re.match(r'^\s*(?:project\.)?dependencies\s*=', line):
            continue
        try:
            before = tomllib.loads("\n".join(lines[:start])).get("project", {})
        except tomllib.TOMLDecodeError:
            continue
        if not isinstance(before, dict) or "dependencies" in before:
            continue
        for end in range(start + 1, min(len(lines), start + 40) + 1):
            excerpt = "\n".join(f"{i + 1}: {lines[i]}" for i in range(start, end))
            if len(excerpt) > 1200:
                break
            try:
                after = tomllib.loads("\n".join(lines[:end])).get("project", {})
            except tomllib.TOMLDecodeError:
                continue
            if isinstance(after, dict) and after.get("dependencies") == dependencies:
                return EvidenceSnippet(
                    path="pyproject.toml", start_line=start + 1, end_line=end,
                    excerpt=excerpt,
                    relevance="Parsed root project.dependencies; exact normalized package name",
                )
            break
    return None


def supports_claim_form(claim: str) -> bool:
    """Whether the deterministic checker has a rule for this sentence form."""
    text = claim.strip().rstrip(".").lower()
    return bool(
        DEPENDENCY_CLAIM.fullmatch(text)
        or re.fullmatch(r"imports ([a-z_]\w*(?:\.[a-z_]\w*)*) in python tests", text)
        or re.fullmatch(r"(?:[a-z0-9_-]+\s+)?(?:requires|officially supports) python (\d+\.\d+)\+", text)
        or re.fullmatch(
            r"(?:includes (?:a )?docker (?:deployment configuration|configuration|image)|"
            r"uses a docker base image) based on python (\d+\.\d+(?:\.\d+)?)", text,
        )
    )


def bounded_support(
    claim: str, snippet: EvidenceSnippet,
    repository_files: Mapping[str, list[str]] | None = None,
) -> bool:
    claim = claim.strip().rstrip(".").lower()
    path = PurePosixPath(snippet.path.replace("\\", "/").lower())
    text = "\n".join(re.sub(r"^\s*\d+:\s?", "", line) for line in snippet.excerpt.splitlines())

    # A FROM instruction establishes a base image, not successful deployment.
    docker = re.fullmatch(
        r"(?:includes (?:a )?docker (?:deployment configuration|configuration|image)|"
        r"uses a docker base image) based on python (\d+\.\d+(?:\.\d+)?)", claim,
    )
    if docker and path.name == "dockerfile":
        version = re.escape(docker.group(1))
        return bool(re.search(rf"^FROM\s+python:{version}(?:-[\w.-]+)?(?:\s+AS\s+\w+)?\s*$", text, re.M | re.I))

    python_version = re.fullmatch(
        r"(?:[a-z0-9_-]+\s+)?(?:requires|officially supports) python (\d+\.\d+)\+", claim
    )
    if python_version and snippet.path.casefold() == "pyproject.toml":
        version = re.escape(python_version.group(1))
        return bool(re.search(rf'^requires-python\s*=\s*["\']>=\s*{version}(?:["\',\s]|$)', text, re.M | re.I))

    dependency = DEPENDENCY_CLAIM.fullmatch(claim)
    if dependency and snippet.path == "pyproject.toml" and repository_files is not None:
        declaration = pyproject_dependency_evidence(claim, repository_files.get("pyproject.toml", []))
        return bool(declaration and snippet.start_line == declaration.start_line
                    and snippet.end_line == declaration.end_line and snippet.excerpt == declaration.excerpt)
    if dependency and re.fullmatch(r"requirements(?:[-_.][\w.-]+)?\.txt", path.name):
        package = dependency.group(1).replace("-", "_").replace(".", "_")
        for line in text.splitlines():
            entry = re.match(r"^\s*([a-z0-9][a-z0-9._-]*)(?:\[[\w,.-]+\])?\s*(?:[<>=!~;@]|$)", line, re.I)
            if entry and entry.group(1).lower().replace("-", "_").replace(".", "_") == package:
                return True

    # Parse Python syntax instead of counting strings or comments as imports.
    imported = re.fullmatch(r"imports ([a-z_]\w*(?:\.[a-z_]\w*)*) in python tests", claim)
    if imported and path.suffix == ".py":
        module = imported.group(1)
        is_test = path.name.startswith("test_") or path.stem.endswith("_test") or "tests" in path.parts
        if not is_test or snippet.start_line != 1:
            return False
        # A retrieved window can end halfway through a function. Parse complete
        # prefixes from the file's beginning, never a line of unknown context.
        lines = text.splitlines()
        for end in range(1, len(lines) + 1):
            try:
                tree = ast.parse("\n".join(lines[:end]))
            except (SyntaxError, ValueError):
                continue
            # Only top-level imports: `if False: import pytest` is not enough.
            if any(
                isinstance(node, ast.Import) and any(alias.name.lower() == module for alias in node.names)
                or isinstance(node, ast.ImportFrom) and (node.module or "").lower() == module and node.level == 0
                for node in tree.body
            ):
                return True
    return False
