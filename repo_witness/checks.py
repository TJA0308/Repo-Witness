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
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version

from .models import EvidenceSnippet

DEPENDENCY_CLAIM = re.compile(r"declares ([a-z0-9][a-z0-9._-]*) as a python dependency", re.I)
IMPORT_CLAIM = re.compile(r"imports ([a-z_]\w*(?:\.[a-z_]\w*)*) in python tests", re.I)


def python_test_import_evidence(claim: str, path: str, lines: list[str]) -> EvidenceSnippet | None:
    """Find a top-level import in valid Python, then cite its bounded header.

    Parsing the entire file prevents a window inside a string, function or
    conditional from masquerading as an unconditional module import.
    """
    match = IMPORT_CLAIM.fullmatch(claim.strip().rstrip("."))
    source_path = PurePosixPath(path)
    is_test = source_path.name.startswith("test_") or source_path.stem.endswith("_test") or "tests" in source_path.parts
    if not match or source_path.suffix != ".py" or not is_test:
        return None
    try:
        tree = ast.parse("\n".join(lines))
    except (SyntaxError, ValueError):
        return None
    module = match.group(1)
    for node in tree.body:
        found = (
            isinstance(node, ast.Import) and any(alias.name == module for alias in node.names)
            or isinstance(node, ast.ImportFrom) and node.module == module and node.level == 0
        )
        if not found:
            continue
        end = node.end_lineno
        excerpt = "\n".join(f"{i + 1}: {line}" for i, line in enumerate(lines[:end]))
        if end <= 40 and len(excerpt) <= 1200:
            return EvidenceSnippet(path=path, start_line=1, end_line=end, excerpt=excerpt,
                                   relevance="Parsed top-level Python test import; exact module name")
    return None


def _poetry_dependencies(document: dict) -> dict:
    tool = document.get("tool", {})
    poetry = tool.get("poetry", {}) if isinstance(tool, dict) else {}
    dependencies = poetry.get("dependencies", {}) if isinstance(poetry, dict) else {}
    return dependencies if isinstance(dependencies, dict) else {}


def poetry_dependency_evidence(claim: str, lines: list[str], document: dict) -> EvidenceSnippet | None:
    """Read legacy Poetry main dependencies; optional and development groups abstain.

    Only ordinary string entries or tables with a version/path/git/url source
    qualify. Values are declarations, not evaluated version constraints.
    """
    package = DEPENDENCY_CLAIM.fullmatch(claim.strip().rstrip("."))
    if not package or canonicalize_name(package.group(1)) == "python":
        return None
    entries = _poetry_dependencies(document)
    matches = [(key, value) for key, value in entries.items()
               if canonicalize_name(key) == canonicalize_name(package.group(1))]
    if len(matches) != 1:
        return None
    key, value = matches[0]
    if isinstance(value, str):
        valid = bool(value.strip())
    elif isinstance(value, dict):
        valid = value.get("optional", False) is False and any(
            isinstance(value.get(field), str) and value[field].strip()
            for field in ("version", "path", "git", "url")
        )
    else:
        valid = False
    if not valid:
        return None
    spellings = (key, f'"{key}"', f"'{key}'")
    assignment = re.compile(r"^\s*(?:" + "|".join(re.escape(item) for item in spellings) + r")\s*=")
    for start, line in enumerate(lines):
        if not assignment.match(line):
            continue
        try:
            before = tomllib.loads("\n".join(lines[:start]))
        except tomllib.TOMLDecodeError:
            continue
        if key in _poetry_dependencies(before):
            continue
        for end in range(start + 1, min(len(lines), start + 40) + 1):
            excerpt = "\n".join(f"{i + 1}: {lines[i]}" for i in range(start, end))
            if len(excerpt) > 1200:
                break
            try:
                after = tomllib.loads("\n".join(lines[:end]))
            except tomllib.TOMLDecodeError:
                continue
            if _poetry_dependencies(after).get(key) == value:
                return EvidenceSnippet(path="pyproject.toml", start_line=start + 1,
                                       end_line=end, excerpt=excerpt,
                                       relevance="Parsed root tool.poetry.dependencies; exact normalized package name")
            break
    return None


def pyproject_dependency_evidence(claim: str, lines: list[str]) -> EvidenceSnippet | None:
    """Parse root project or legacy Poetry dependencies and cite their assignment.

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
        if project is None or isinstance(project, dict) and "dependencies" not in project and "dependencies" not in project.get("dynamic", []):
            return poetry_dependency_evidence(claim, lines, document)
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
    original_claim = claim
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
    if python_version and snippet.path == "pyproject.toml":
        if repository_files is None:
            return False
        lines = repository_files.get("pyproject.toml", [])
        try:
            project = tomllib.loads("\n".join(lines)).get("project", {})
            if not isinstance(project, dict) or "requires-python" in project.get("dynamic", []):
                return False
            value = project.get("requires-python")
            if not isinstance(value, str):
                return False
            specifiers = SpecifierSet(value)
            minimum = Version(python_version.group(1))
            if not any(item.operator == ">=" and Version(item.version) == minimum for item in specifiers):
                return False
            # A higher or strict lower bound cannot establish this minimum.
            if any(item.operator not in {">=", "<", "<=", "!="}
                   or item.operator == ">=" and Version(item.version) != minimum for item in specifiers):
                return False
            if not specifiers.contains(minimum, prereleases=True):
                return False
        except (tomllib.TOMLDecodeError, InvalidSpecifier, ValueError, TypeError):
            return False
        # Locate the real assignment using parsed prefixes. Text inside a
        # multiline string or another table never changes project metadata.
        for index in range(max(0, snippet.start_line - 1), min(len(lines), snippet.end_line)):
            if not re.match(r'^\s*(?:project\.)?requires-python\s*=', lines[index]):
                continue
            try:
                before = tomllib.loads("\n".join(lines[:index])).get("project", {})
                after = tomllib.loads("\n".join(lines[:index + 1])).get("project", {})
            except tomllib.TOMLDecodeError:
                continue
            if (isinstance(before, dict) and "requires-python" not in before
                    and isinstance(after, dict) and after.get("requires-python") == value
                    and f"{index + 1}: {lines[index]}" in snippet.excerpt.splitlines()):
                return True
        return False

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
        if repository_files is not None:
            declaration = python_test_import_evidence(
                original_claim, snippet.path, repository_files.get(snippet.path, [])
            )
            return bool(declaration and snippet.start_line == declaration.start_line
                        and snippet.end_line == declaration.end_line and snippet.excerpt == declaration.excerpt)
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
