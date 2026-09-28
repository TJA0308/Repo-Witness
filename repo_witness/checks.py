"""Small, explicit checks for facts that can be established from static text.

Only these narrow claim forms can be VERIFIED by the deterministic analyzer.
Other claims still get retrieved evidence and contradiction checks, but keyword
overlap alone cannot verify them. Add a new check only with positive and negative
examples explaining precisely what it establishes.
"""
from __future__ import annotations

import ast
import re
from pathlib import PurePosixPath

from .models import EvidenceSnippet


def bounded_support(claim: str, snippet: EvidenceSnippet) -> bool:
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

    dependency = re.fullmatch(r"declares ([a-z0-9][a-z0-9._-]*) as a python dependency", claim)
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
