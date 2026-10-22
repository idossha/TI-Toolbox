#!/usr/bin/env python3
"""Every committed test file is run by something: a CI step, or a named local layer.

A test file nothing runs is worse than no test: it is cited as evidence and protects nothing
(agent-plugin/mcp/test_stdio.py and docs/tests/search-results.test.mjs ran nowhere until
2026-10-22). This lists the tracked test files (``git ls-files``: ``test_*.py``,
``*.test.{ts,tsx,mjs,js}``, ``*.spec.ts``) and requires each to match a runner read from
the files that define what runs:

* pytest: ``testpaths`` in pytest.ini, minus every ``--ignore=`` the CI pytest steps pass;
* vitest: the ``include`` globs in desktop/vitest.config.ts (CI ``desktop-checks``);
* ``unittest discover -s DIR -p PATTERN`` and ``node --test FILE`` steps in
  .circleci/config.yml;
* Playwright's ``testDir`` in desktop/playwright.config.ts (mock server: CircleCI
  ``desktop-e2e-mock``, opt-in with the ``run_e2e_mock`` pipeline parameter; named in the
  table below);
* ``LOCAL_LAYERS``: layers that are local on purpose, each with the job or script that runs
  it.

Exit 0 when every file has a runner, 1 when a file has none (each is named), 2 when the
inventory or a runner definition could not be read. Self-tests:
tests/test_test_inventory_guard.py.
"""

from __future__ import annotations

import configparser
import fnmatch
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TEST_FILE_PATTERNS = (
    "test_*.py",
    "*.test.ts",
    "*.test.tsx",
    "*.test.mjs",
    "*.test.js",
    "*.spec.ts",
)

#: Layers no CI job runs, on purpose, and who runs them instead.
LOCAL_LAYERS: dict[str, str] = {
    "tests/numerical/**": (
        "the image leg: CircleCI `numerical-image` (nightly + build_image) and "
        "dev/verify_release.py `numerical`; host_numerical modules also in build-and-run-tests"
    ),
    "desktop/tests/e2e/real/**": (
        "Playwright --project=real against a live container: dev/verify_release.py `real-e2e`"
    ),
    "tests/smoke/**": "dev/smoke.sh (needs a live tit.server and a real project)",
    "PLAYWRIGHT": (
        "mock-server Playwright: CircleCI desktop-e2e-mock (opt-in: run_e2e_mock) and "
        "dev/verify_release.py `mock-e2e` (npm run e2e:quiet)"
    ),
}


#: Tracked files whose names match a test pattern but that are not tests.
NOT_TESTS: dict[str, str] = {
    "dev/test_inventory_guard.py": "this guard: a script named for what it checks",
}


class CannotCheck(Exception):
    """A runner definition or the inventory could not be read."""


def is_test_file(path: str) -> bool:
    if path in NOT_TESTS:
        return False
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in TEST_FILE_PATTERNS)


def _under(path: str, directory: str) -> bool:
    directory = directory.strip("/").removeprefix("./")
    return directory in ("", ".") or path.startswith(directory + "/")


def _glob(path: str, pattern: str) -> bool:
    """``**`` spans directories, ``*`` stays within one, ``{a,b}`` alternates (vitest style)."""
    alternatives = [pattern]
    while any("{" in p for p in alternatives):
        expanded = []
        for p in alternatives:
            match = re.search(r"\{([^{}]*)\}", p)
            if match is None:
                expanded.append(p)
                continue
            for option in match.group(1).split(","):
                expanded.append(p[: match.start()] + option + p[match.end() :])
        alternatives = expanded
    for p in alternatives:
        regex = re.escape(p).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*")
        regex = regex.replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
        if re.fullmatch(regex, path):
            return True
    return False


def pytest_testpaths(pytest_ini: str) -> list[str]:
    parser = configparser.ConfigParser()
    parser.read_string(pytest_ini)
    try:
        return parser.get("pytest", "testpaths").split()
    except (configparser.Error, KeyError) as exc:
        raise CannotCheck(f"pytest.ini has no [pytest] testpaths: {exc}") from exc


def _ci_commands(ci_yaml: str) -> list[str]:
    """Shell lines of the CI file with backslash continuations joined."""
    return [line.strip() for line in ci_yaml.replace("\\\n", " ").splitlines()]


def ci_pytest_ignores(ci_yaml: str) -> list[str]:
    """Every ``--ignore=`` a CI pytest invocation passes."""
    ignores = []
    for line in _ci_commands(ci_yaml):
        if "-m pytest" in line:
            ignores += re.findall(r"--ignore[= ](\S+)", line)
    return [i.rstrip("/") for i in ignores]


def ci_unittest_globs(ci_yaml: str) -> list[str]:
    globs = []
    for line in _ci_commands(ci_yaml):
        match = re.search(r"unittest discover\s+-s\s+(\S+)\s+-p\s+(\S+)", line)
        if match:
            directory, pattern = (shlex.split(g)[0] for g in match.groups())
            globs.append(f"{directory.rstrip('/')}/{pattern}")
    return globs


def ci_node_test_files(ci_yaml: str) -> list[str]:
    files = []
    for line in _ci_commands(ci_yaml):
        match = re.search(r"node --test\s+(.+)$", line)
        if match:
            files += [f for f in shlex.split(match.group(1)) if not f.startswith("-")]
    return files


def vitest_includes(config_ts: str) -> list[str]:
    match = re.search(r"include\s*:\s*\[([^\]]*)\]", config_ts)
    if match is None:
        raise CannotCheck("desktop/vitest.config.ts has no test.include list")
    return ["desktop/" + g for g in re.findall(r"[\"']([^\"']+)[\"']", match.group(1))]


def playwright_test_dir(config_ts: str) -> str:
    match = re.search(r"testDir\s*:\s*[\"']([^\"']+)[\"']", config_ts)
    if match is None:
        raise CannotCheck("desktop/playwright.config.ts has no testDir")
    return "desktop/" + match.group(1).strip("/")


def runners(sources: dict[str, str]) -> list[tuple[str, str]]:
    """``(glob, runner)`` pairs from the runner definitions (keyed by repo path)."""
    ci = sources[".circleci/config.yml"]
    ignores = ci_pytest_ignores(ci)
    found = []
    for path in pytest_testpaths(sources["pytest.ini"]):
        found.append((f"{path.rstrip('/')}/**", "pytest (build-and-run-tests)"))
    found += [
        (g, "vitest (desktop-checks)") for g in vitest_includes(sources["vitest"])
    ]
    found += [(g, "unittest (CircleCI)") for g in ci_unittest_globs(ci)]
    found += [(f, "node --test (CircleCI)") for f in ci_node_test_files(ci)]
    found += [
        (f"{playwright_test_dir(sources['playwright'])}/**", LOCAL_LAYERS["PLAYWRIGHT"])
    ]
    found += [(g, who) for g, who in LOCAL_LAYERS.items() if g != "PLAYWRIGHT"]
    return [(g, who) for g, who in found if g] + [
        (f"!{i}", "ignored by CI pytest") for i in ignores
    ]


def runner_for(path: str, rules: list[tuple[str, str]]) -> str | None:
    """The first runner whose glob matches ``path``; a pytest glob loses to its --ignores."""
    ignored = [g[1:] for g, _ in rules if g.startswith("!")]
    for pattern, who in rules:
        if pattern.startswith("!"):
            continue
        if not _glob(path, pattern):
            continue
        if who.startswith("pytest") and any(_under(path, i) for i in ignored):
            continue
        return who
    return None


def orphans(files: list[str], rules: list[tuple[str, str]]) -> list[str]:
    return [f for f in files if is_test_file(f) and runner_for(f, rules) is None]


def _read(root: Path, relative: str) -> str:
    try:
        return (root / relative).read_text(encoding="utf-8")
    except OSError as exc:
        raise CannotCheck(f"cannot read {relative}: {exc}") from exc


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if args:
        root = Path(args[0]).resolve()
    try:
        listing = subprocess.run(
            ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True
        ).stdout.splitlines()
        tests = [f for f in listing if is_test_file(f)]
        if not tests:
            raise CannotCheck("git ls-files lists no test files; nothing to check")
        rules = runners(
            {
                "pytest.ini": _read(root, "pytest.ini"),
                ".circleci/config.yml": _read(root, ".circleci/config.yml"),
                "vitest": _read(root, "desktop/vitest.config.ts"),
                "playwright": _read(root, "desktop/playwright.config.ts"),
            }
        )
    except (CannotCheck, OSError, subprocess.CalledProcessError) as exc:
        print(f"test_inventory_guard: could not check: {exc}", file=sys.stderr)
        return 2
    missing = orphans(tests, rules)
    print(
        f"test_inventory_guard: {len(tests)} test files, {len(missing)} with no runner"
    )
    for path in missing:
        print(f"  no CI step or local layer runs {path}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
