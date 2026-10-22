"""Self-tests for dev/test_inventory_guard.py, driven red with a fixture repository.

What this pins
    A planted test file no runner covers exits 1 and is named; a file a CI ``--ignore``
    excludes is an orphan unless a local layer claims it; the runners read from pytest.ini,
    the CI file (unittest discover, node --test), vitest's include globs (``{ts,tsx}``) and
    Playwright's testDir each cover their files; a repository with no test files, or one
    missing a runner definition, exits 2 (could not check); the real repository exits 0.

Where the expectations come from
    The fixture files written below; the guard's rules in its docstring.

Runs under ``python3 -m unittest`` (stdlib only, CI runs it before installing anything) and
under pytest.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "test_inventory_guard", ROOT / "dev" / "test_inventory_guard.py"
)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

PYTEST_INI = "[pytest]\ntestpaths = tests\n"
CI = """jobs:
  python:
    steps:
      - run:
          command: |
            python -m pytest tests/ -q \\
              --ignore=tests/slow --junitxml=x.xml
      - run:
          command: python3 -m unittest discover -s plugin/mcp -p 'test_*.py' -v
      - run:
          command: node --test docs/tests/search.test.mjs
"""
VITEST = (
    'export default defineConfig({ test: { include: ["src/main/**/*.test.ts", '
    '"tests/unit/**/*.test.{ts,tsx}"] } });\n'
)
PLAYWRIGHT = 'export default defineConfig({ testDir: "tests/e2e" });\n'

COVERED = [
    "tests/test_a.py",
    "tests/numerical/test_real.py",
    "plugin/mcp/test_stdio.py",
    "docs/tests/search.test.mjs",
    "desktop/src/main/x.test.ts",
    "desktop/tests/unit/y.test.tsx",
    "desktop/tests/e2e/z.spec.ts",
    "desktop/tests/e2e/real/w.spec.ts",
]


class FixtureRepo:
    """A throwaway git repository with the runner definitions and chosen files staged."""

    def __init__(self, files: list[str], *, omit: tuple[str, ...] = ()):
        self._dir = tempfile.TemporaryDirectory()
        self.root = Path(self._dir.name)
        definitions = {
            "pytest.ini": PYTEST_INI,
            ".circleci/config.yml": CI,
            "desktop/vitest.config.ts": VITEST,
            "desktop/playwright.config.ts": PLAYWRIGHT,
        }
        for path, text in definitions.items():
            if path not in omit:
                self.write(path, text)
        for path in files:
            self.write(path, "# test\n")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)

    def write(self, path: str, text: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def run(self) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = guard.main([str(self.root)])
        return code, out.getvalue(), err.getvalue()

    def close(self) -> None:
        self._dir.cleanup()


class InventoryGuardTests(unittest.TestCase):
    def repo(self, files, **kwargs) -> FixtureRepo:
        repo = FixtureRepo(files, **kwargs)
        self.addCleanup(repo.close)
        return repo

    def test_every_runner_covers_its_files(self):
        code, out, _ = self.repo(COVERED).run()
        self.assertEqual(code, 0, out)
        self.assertIn(f"{len(COVERED)} test files, 0 with no runner", out)

    def test_a_planted_orphan_exits_1_and_is_named(self):
        code, out, _ = self.repo(COVERED + ["tools/test_x.py"]).run()
        self.assertEqual(code, 1)
        self.assertIn("runs tools/test_x.py", out)
        self.assertIn("1 with no runner", out)

    def test_a_ci_ignore_uncovers_a_directory_no_local_layer_claims(self):
        code, out, _ = self.repo(["tests/test_a.py", "tests/slow/test_b.py"]).run()
        self.assertEqual(code, 1)
        self.assertIn("runs tests/slow/test_b.py", out)
        self.assertNotIn("runs tests/test_a.py", out)

    def test_a_desktop_test_outside_the_vitest_globs_is_an_orphan(self):
        code, out, _ = self.repo(COVERED + ["desktop/src/renderer/z.test.js"]).run()
        self.assertEqual(code, 1)
        self.assertIn("runs desktop/src/renderer/z.test.js", out)

    def test_a_repository_without_test_files_cannot_be_checked(self):
        code, _, err = self.repo(["README.md"]).run()
        self.assertEqual(code, 2)
        self.assertIn("no test files", err)

    def test_a_missing_runner_definition_cannot_be_checked(self):
        code, _, err = self.repo(COVERED, omit=("desktop/vitest.config.ts",)).run()
        self.assertEqual(code, 2)
        self.assertIn("vitest.config.ts", err)

    def test_the_globs_follow_vitest_and_ci_semantics(self):
        self.assertTrue(
            guard._glob("tests/unit/a/b.test.tsx", "tests/unit/**/*.test.{ts,tsx}")
        )
        self.assertTrue(
            guard._glob("tests/unit/b.test.ts", "tests/unit/**/*.test.{ts,tsx}")
        )
        self.assertFalse(
            guard._glob("tests/unit/b.test.js", "tests/unit/**/*.test.{ts,tsx}")
        )
        self.assertFalse(
            guard._glob("plugin/mcp/sub/test_x.py", "plugin/mcp/test_*.py")
        )
        self.assertEqual(guard.ci_pytest_ignores(CI), ["tests/slow"])

    def test_the_real_repository_has_a_runner_for_every_test_file(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = guard.main([str(ROOT)])
        self.assertEqual(code, 0, out.getvalue())
        count = int(out.getvalue().split("test_inventory_guard: ")[1].split(" ")[0])
        self.assertGreater(count, 400, out.getvalue())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
