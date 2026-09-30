# Five real-repository examples

These are **selected, authored cases**, with labels written before the recorded run. Independent review is pending. They demonstrate the audit flow and its limitations; **3/5 agreement is not a general accuracy estimate**. No downloaded repository code was executed.

Each repository is pinned to a commit. The runner checks the archive SHA-256, review excerpts, actual citation text and ranges, and exclusion of the originating README. Labels and actual results are kept separately.

| Repository | Claim | Expected | Actual |
| --- | --- | --- | --- |
| httpx | Declares httpcore as a Python dependency. | VERIFIED | VERIFIED |
| requests | Requests officially supports Python 3.10+. | PARTIALLY_VERIFIED | PARTIALLY_VERIFIED |
| click | Imports pytest in Python tests. | VERIFIED | INSUFFICIENT_EVIDENCE |
| flask | Flask is quick and easy to get started with. | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE |
| rich | Declares pygments as a Python dependency. | VERIFIED | INSUFFICIENT_EVIDENCE |

## What the mismatches tell us

- **Click:** the test file contains a top-level `import pytest`, but keyword retrieval selected other passages and missed the import. This is a retrieval failure; the claim is not false.
- **Rich:** Poetry declares `pygments`, but the checker only handles requirements files and root `[project].dependencies`. Retrieval also missed the relevant Poetry declaration. This is an unsupported manifest format plus weak retrieval.
- **Flask:** the subjective ease-of-use claim correctly abstains, but the returned snippets are weakly related. Citation correctness does not establish relevance.

The verdict rules were not changed to make these examples pass. There is no contradiction example here; contradiction behavior remains covered by synthetic cases.

## Walk through each case

### httpx

**Claim:** Declares httpcore as a Python dependency.

**Origin:** Authored manifest claim. `README.md` is excluded from retrieval for every case. Other documentation, including translated READMEs, remains eligible; this is source-file exclusion, not repository-wide documentation exclusion.

**Review source:** [pyproject.toml:30-35](https://github.com/encode/httpx/blob/b5addb64f0161ff6bfe94c124ef76f6a1fba5254/pyproject.toml#L30-L35)

```text
dependencies = [
    "certifi",
    "httpcore==1.*",
    "anyio",
    "idna",
]
```

**Expected:** `VERIFIED`. The project.dependencies array declares httpcore==1.*. This establishes a declaration, not successful installation or runtime use.

**Actual:** `VERIFIED`. A supported static check found the stated import, dependency declaration, Docker base-image instruction, or declared Python version floor. This establishes a fact about repository text, not successful execution or deployment.

<details>
<summary>Inspect the actual retrieved evidence</summary>

[pyproject.toml:30-35](https://github.com/encode/httpx/blob/b5addb64f0161ff6bfe94c124ef76f6a1fba5254/pyproject.toml#L30-L35)

```text
30: dependencies = [
31:     "certifi",
32:     "httpcore==1.*",
33:     "anyio",
34:     "idna",
35: ]
```

[docs/async.md:24-28](https://github.com/encode/httpx/blob/b5addb64f0161ff6bfe94c124ef76f6a1fba5254/docs/async.md#L24-L28)

```text
24:
25: !!! tip
26:     Use [IPython](https://ipython.readthedocs.io/en/stable/) or Python 3.9+ with `python -m asyncio` to try this code interactively, as they support executing `async`/`await` expressions in the console.
27:
28: ## API Differences
```

[.github/workflows/test-suite.yml:10-14](https://github.com/encode/httpx/blob/b5addb64f0161ff6bfe94c124ef76f6a1fba5254/.github/workflows/test-suite.yml#L10-L14)

```text
10: jobs:
11:   tests:
12:     name: "Python ${{ matrix.python-version }}"
13:     runs-on: "ubuntu-latest"
14:
```

[.github/workflows/test-suite.yml:21-25](https://github.com/encode/httpx/blob/b5addb64f0161ff6bfe94c124ef76f6a1fba5254/.github/workflows/test-suite.yml#L21-L25)

```text
21:       - uses: "actions/setup-python@v6"
22:         with:
23:           python-version: "${{ matrix.python-version }}"
24:           allow-prereleases: true
25:       - name: "Install dependencies"
```

[docs/advanced/authentication.md:83-87](https://github.com/encode/httpx/blob/b5addb64f0161ff6bfe94c124ef76f6a1fba5254/docs/advanced/authentication.md#L83-L87)

```text
83: ```
84:
85: The `NetRCAuth()` class uses [the `netrc.netrc()` function from the Python standard library](https://docs.python.org/3/library/netrc.html). See the documentation there for more details on exceptions that may be raised if the `.netrc` file is not found, or cannot be parsed.
86:
87: ## Custom authentication schemes
```

[docs/advanced/extensions.md:3-7](https://github.com/encode/httpx/blob/b5addb64f0161ff6bfe94c124ef76f6a1fba5254/docs/advanced/extensions.md#L3-L7)

```text
3: Request and response extensions provide a untyped space where additional information may be added.
4:
5: Extensions should be used for features that may not be available on all transports, and that do not fit neatly into [the simplified request/response model](https://www.encode.io/httpcore/extensions/) that the underlying `httpcore` package uses as its API.
6:
7: Several extensions are supported on the request:
```

</details>

### requests

**Claim:** Requests officially supports Python 3.10+.

**Origin:** Literal README.md:38. `README.md` is excluded from retrieval for every case. Other documentation, including translated READMEs, remains eligible; this is source-file exclusion, not repository-wide documentation exclusion.

**Review source:** [pyproject.toml:17-17](https://github.com/psf/requests/blob/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60/pyproject.toml#L17-L17)

```text
requires-python = ">=3.10"
```

**Expected:** `PARTIALLY_VERIFIED`. requires-python establishes the declared minimum. Official support across Python versions requires broader evidence than this static declaration.

**Actual:** `PARTIALLY_VERIFIED`. A bounded repository fact was found, but the claim's absolute or broad scope is not established by static evidence.

<details>
<summary>Inspect the actual retrieved evidence</summary>

[pyproject.toml:15-19](https://github.com/psf/requests/blob/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60/pyproject.toml#L15-L19)

```text
15:     {name = "Nate Prewitt", email="nate.prewitt@gmail.com"}
16: ]
17: requires-python = ">=3.10"
18: dependencies = [
19:     "charset_normalizer>=2,<4",
```

[setup.py:2-6](https://github.com/psf/requests/blob/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60/setup.py#L2-L6)

```text
2:
3: if sys.version_info < (3, 10):  # noqa: UP036
4:     sys.stderr.write("Requests requires Python 3.10 or later.\n")
5:     sys.exit(1)
6:
```

[.github/CONTRIBUTING.md:13-17](https://github.com/psf/requests/blob/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60/.github/CONTRIBUTING.md#L13-L17)

```text
13: not use it to ask questions about how to use Requests. These questions should
14: instead be directed to [Stack Overflow](https://stackoverflow.com/). Make sure
15: that your question is tagged with the `python-requests` tag when asking it on
16: Stack Overflow, to ensure that it is answered promptly and accurately.
17:
```

[.github/ISSUE_TEMPLATE.md:18-22](https://github.com/psf/requests/blob/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60/.github/ISSUE_TEMPLATE.md#L18-L22)

```text
18: ## System Information
19:
20:     $ python -m requests.help
21:
22: ```
```

[.github/ISSUE_TEMPLATE/Bug_report.md:24-28](https://github.com/psf/requests/blob/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60/.github/ISSUE_TEMPLATE/Bug_report.md#L24-L28)

```text
24: ## System Information
25:
26:     $ python -m requests.help
27:
28: ```json
```

[.github/ISSUE_TEMPLATE/Custom.md:8-10](https://github.com/psf/requests/blob/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60/.github/ISSUE_TEMPLATE/Custom.md#L8-L10)

```text
8: ---
9:
10: Please refer to our [Stack Overflow tag](https://stackoverflow.com/questions/tagged/python-requests) for guidance.
```

</details>

### click

**Claim:** Imports pytest in Python tests.

**Origin:** Authored test import claim. `README.md` is excluded from retrieval for every case. Other documentation, including translated READMEs, remains eligible; this is source-file exclusion, not repository-wide documentation exclusion.

**Review source:** [tests/test_basic.py:1-9](https://github.com/pallets/click/blob/06b2a678741131fd577ce170e23e5ca0aeba0309/tests/test_basic.py#L1-L9)

```text
from __future__ import annotations

import enum
import os

import pytest

import click
from click._utils import UNSET
```

**Expected:** `VERIFIED`. A top-level import pytest appears in a Python test file. This does not establish that the tests pass.

**Actual:** `INSUFFICIENT_EVIDENCE`. Related evidence found, but the supported static check found no matching declaration. The source may contain only a mention, a different value, invalid syntax, or an incomplete excerpt. This does not establish that the claim is false.

<details>
<summary>Inspect the actual retrieved evidence</summary>

[docs/upgrade-guides.md:16-20](https://github.com/pallets/click/blob/06b2a678741131fd577ce170e23e5ca0aeba0309/docs/upgrade-guides.md#L16-L20)

```text
16: - A parameter name that is not a valid Python identifier, or that is a [Python keyword](https://docs.python.org/3/reference/lexical_analysis.html#keywords), is deprecated and raises `TypeError` in 9.0. [`str.isidentifier()`](https://docs.python.org/3/library/stdtypes.html#str.isidentifier) decides the first case, so `click.argument("0foo")` fails it. It accepts a keyword, so `click.option("--from")` names a parameter `from`, which no callback can declare. [Soft keywords](https://docs.python.org/3/reference/lexical_analysis.html#soft-keywords) such as `match` and `type` are contextual and unaffected, and `--True` and `--None` lower case out of the keyword set. To migrate, pass an explicit name (`click.option("--from", "source")`, `click.option("--0-file", "zero_file")`). An argument takes one declaration and has no explicit-name channel, so rename it and pass `metavar` to keep its old display (`click.argument("zero_file", metavar="0-FILE")`). See [#3827](https://github.com/pallets/click/pull/3827) and [#3866](https://github.com/pallets/click/pull/3866).
17: - An option name written as a Python identifier is deprecated when it is not already lower cased: `clic
[excerpt truncated]
```

[docs/testing.md:15-19](https://github.com/pallets/click/blob/06b2a678741131fd577ce170e23e5ca0aeba0309/docs/testing.md#L15-L19)

```text
15: ```
16:
17: The examples use [pytest](https://docs.pytest.org/en/stable/) style tests.
18:
19: ```{contents}
```

[docs/complex.md:232-236](https://github.com/pallets/click/blob/06b2a678741131fd577ce170e23e5ca0aeba0309/docs/complex.md#L232-L236)

```text
232:
233: ```{warning}
234: Lazy loading of python code can result in hard to track down bugs, circular imports
235: in order-dependent codebases, and other surprising behaviors. It is recommended that
236: this technique only be used in concert with testing which will at least run the
```

[src/click/core.py:2493-2497](https://github.com/pallets/click/blob/06b2a678741131fd577ce170e23e5ca0aeba0309/src/click/core.py#L2493-L2497)

```text
2493:
2494:         Both imports are local because neither :mod:`keyword` nor
2495:         :mod:`warnings` is on the allow-list ``tests/test_imports.py`` holds
2496:         Click's import footprint to.
2497:
```

[src/click/testing.py:749-753](https://github.com/pallets/click/blob/06b2a678741131fd577ce170e23e5ca0aeba0309/src/click/testing.py#L749-L753)

```text
749:
750:         .. warning::
751:             This helper predates Python 3 and modern pytest, and is not
752:             thread-safe: it relies on :func:`os.chdir`, which mutates
753:             process-global state, and :meth:`invoke` swaps the
```

[tests/test_arguments.py:195-199](https://github.com/pallets/click/blob/06b2a678741131fd577ce170e23e5ca0aeba0309/tests/test_arguments.py#L195-L199)

```text
195:         click.Argument([])
196:
197:     with pytest.warns(DeprecationWarning, match="not a valid Python identifier"):
198:         assert click.Argument([], expose_value=False).name == ""
199:
```

</details>

### flask

**Claim:** Flask is quick and easy to get started with.

**Origin:** Paraphrase of README.md:5-7. `README.md` is excluded from retrieval for every case. Other documentation, including translated READMEs, remains eligible; this is source-file exclusion, not repository-wide documentation exclusion.

**Review source:** [pyproject.toml:1-5](https://github.com/pallets/flask/blob/d73fa1cdcbd8b1465c151db8924ba58b1dd14e35/pyproject.toml#L1-L5)

```text
[project]
name = "Flask"
version = "3.2.0.dev"
description = "A simple framework for building complex web applications."
readme = "README.md"
```

**Expected:** `INSUFFICIENT_EVIDENCE`. Quick and easy is subjective and depends on the user and task. The package description is context, not proof; the originating README is excluded.

**Actual:** `INSUFFICIENT_EVIDENCE`. Related evidence found, but this claim form is outside the supported static checks. Review the cited lines manually or use a narrow claim such as 'Declares requests as a Python dependency.'

<details>
<summary>Inspect the actual retrieved evidence</summary>

[tests/test_basic.py:504-508](https://github.com/pallets/flask/blob/d73fa1cdcbd8b1465c151db8924ba58b1dd14e35/tests/test_basic.py#L504-L508)

```text
504:     @app.route("/bump")
505:     def bump():
506:         rv = flask.session["foo"] = flask.session.get("foo", 0) + 1
507:         flask.session.permanent = is_permanent
508:         return str(rv)
```

[tests/test_json.py:31-35](https://github.com/pallets/flask/blob/d73fa1cdcbd8b1465c151db8924ba58b1dd14e35/tests/test_json.py#L31-L35)

```text
31:     @app.route("/json", methods=["POST"])
32:     def return_json():
33:         return flask.jsonify(foo=str(flask.request.get_json()))
34:
35:     rv = client.post("/json", data="malformed", content_type="application/json")
```

[tests/test_json.py:248-252](https://github.com/pallets/flask/blob/d73fa1cdcbd8b1465c151db8924ba58b1dd14e35/tests/test_json.py#L248-L252)

```text
248:     @app.route("/", methods=["POST"])
249:     def index():
250:         return flask.json.dumps(flask.request.get_json()["x"])
251:
252:     rv = client.post(
```

[docs/conf.py:8-12](https://github.com/pallets/flask/blob/d73fa1cdcbd8b1465c151db8924ba58b1dd14e35/docs/conf.py#L8-L12)

```text
8: copyright = "2010 Pallets"
9: author = "Pallets"
10: release, version = get_version("Flask")
11:
12: # General --------------------------------------------------------------
```

[examples/tutorial/tests/conftest.py:5-9](https://github.com/pallets/flask/blob/d73fa1cdcbd8b1465c151db8924ba58b1dd14e35/examples/tutorial/tests/conftest.py#L5-L9)

```text
5:
6: from flaskr import create_app
7: from flaskr.db import get_db
8: from flaskr.db import init_db
9:
```

[examples/tutorial/tests/test_auth.py:3-7](https://github.com/pallets/flask/blob/d73fa1cdcbd8b1465c151db8924ba58b1dd14e35/examples/tutorial/tests/test_auth.py#L3-L7)

```text
3: from flask import session
4:
5: from flaskr.db import get_db
6:
7:
```

</details>

### rich

**Claim:** Declares pygments as a Python dependency.

**Origin:** Authored Poetry manifest claim. `README.md` is excluded from retrieval for every case. Other documentation, including translated READMEs, remains eligible; this is source-file exclusion, not repository-wide documentation exclusion.

**Review source:** [pyproject.toml:29-33](https://github.com/Textualize/rich/blob/9d8f9a372cc5916fd4781fec207ced7ddac2f08f/pyproject.toml#L29-L33)

```text
[tool.poetry.dependencies]
python = ">=3.9.0"
pygments = "^2.13.0"
ipywidgets = { version = ">=7.5.1,<9", optional = true }
markdown-it-py = ">=2.2.0"
```

**Expected:** `VERIFIED`. The tool.poetry.dependencies table declares pygments ^2.13.0. A manual static review can verify the declaration even though the current checker does not support Poetry.

**Actual:** `INSUFFICIENT_EVIDENCE`. Related evidence found, but the supported static check found no matching declaration. The source may contain only a mention, a different value, invalid syntax, or an incomplete excerpt. This does not establish that the claim is false.

<details>
<summary>Inspect the actual retrieved evidence</summary>

[pyproject.toml:58-62](https://github.com/Textualize/rich/blob/9d8f9a372cc5916fd4781fec207ced7ddac2f08f/pyproject.toml#L58-L62)

```text
58:
59: [[tool.mypy.overrides]]
60: module = ["pygments.*", "IPython.*", "ipywidgets.*"]
61: ignore_missing_imports = true
62:
```

[tests/test_syntax.py:6-10](https://github.com/Textualize/rich/blob/9d8f9a372cc5916fd4781fec207ced7ddac2f08f/tests/test_syntax.py#L6-L10)

```text
6:
7: import pytest
8: from pygments.lexers import PythonLexer
9:
10: from rich.console import Console
```

[rich/syntax.py:60-64](https://github.com/Textualize/rich/blob/9d8f9a372cc5916fd4781fec207ced7ddac2f08f/rich/syntax.py#L60-L64)

```text
60: DEFAULT_THEME = "monokai"
61:
62: # The following styles are based on https://github.com/pygments/pygments/blob/master/pygments/formatters/terminal.py
63: # A few modifications were made
64:
```

[.github/workflows/pythonpackage.yml:18-25](https://github.com/Textualize/rich/blob/9d8f9a372cc5916fd4781fec207ced7ddac2f08f/.github/workflows/pythonpackage.yml#L18-L25)

```text
18:     steps:
19:       - uses: actions/checkout@v4
20:       - name: Set up Python ${{ matrix.python-version }}
21:         uses: actions/setup-python@v5
22:         with:
23:           python-version: ${{ matrix.python-version }}
24:           allow-prereleases: true
25:       - name: Install and configure Poetry
```

[FAQ.md:6-10](https://github.com/Textualize/rich/blob/9d8f9a372cc5916fd4781fec207ced7ddac2f08f/FAQ.md#L6-L10)

```text
6: - [Incorrect highlights in printed output](#incorrect-highlights-in-printed-output)
7: - [Natively inserted ANSI escape sequence characters break alignment of Panel.](#natively-inserted-ansi-escape-sequence-characters-break-alignment-of-panel)
8: - [python -m rich.spinner shows extra lines.](#python--m-richspinner-shows-extra-lines)
9: - [Rich is automatically installing traceback handler.](#rich-is-automatically-installing-traceback-handler)
10: - [Strange colors in console output.](#strange-colors-in-console-output)
```

[README.cn.md:366-370](https://github.com/Textualize/rich/blob/9d8f9a372cc5916fd4781fec207ced7ddac2f08f/README.cn.md#L366-L370)

```text
366: <summary>语法高亮（Syntax Highlighting）</summary>
367:
368: Rich 使用[pygments](https://pygments.org/)库来实现[语法高亮显示](https://rich.readthedocs.io/en/latest/syntax.html)。用法类似于渲染 markdown。构造一个`Syntax`对象并将其打印到控制台。下面是一个例子：
369:
370: ```python
```

</details>

## Reproduce

From the project root, after installing `requirements.txt`:

```powershell
$archiveDir = Join-Path $env:TEMP 'repo-witness-authored-cases'
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
curl.exe -L -f -o (Join-Path $archiveDir 'httpx.zip') 'https://codeload.github.com/encode/httpx/zip/b5addb64f0161ff6bfe94c124ef76f6a1fba5254'
curl.exe -L -f -o (Join-Path $archiveDir 'requests.zip') 'https://codeload.github.com/psf/requests/zip/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60'
curl.exe -L -f -o (Join-Path $archiveDir 'click.zip') 'https://codeload.github.com/pallets/click/zip/06b2a678741131fd577ce170e23e5ca0aeba0309'
curl.exe -L -f -o (Join-Path $archiveDir 'flask.zip') 'https://codeload.github.com/pallets/flask/zip/d73fa1cdcbd8b1465c151db8924ba58b1dd14e35'
curl.exe -L -f -o (Join-Path $archiveDir 'rich.zip') 'https://codeload.github.com/Textualize/rich/zip/9d8f9a372cc5916fd4781fec207ced7ddac2f08f'
python -m repo_witness.authored_evaluation $archiveDir --output docs/evaluation/authored_cases.json
```

The runner rejects archive hash differences instead of silently evaluating a different snapshot. It uses the same bounded ZIP ingestion, retrieval and deterministic analyzer as the app, and cleans its temporary extraction.

[Authored labels](../../benchmarks/real_repository_cases/cases.json) ? [Saved results](authored_cases.json) ? [Runner](../../repo_witness/authored_evaluation.py)

## How to explain this in an interview

> I built a static claim auditor that retrieves repository evidence and applies narrow, explainable checks. I tried five pinned real repositories and recorded both successes and failures. It verifies declarations rather than runtime behavior. A missed import showed that retrieval can lose the right evidence; a Poetry dependency showed a format coverage gap. The examples are authored demonstrations, and independent evaluation is still future work.
