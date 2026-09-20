"""Self-tests for the canonical-documentation layout guard.

Run with ``python3 -m unittest tests.test_documentation_policy -v``. Fixtures
exercise the path kinds the guard rejects; the final test runs the guard over
this repository so CI cannot pass while the forbidden store is present.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "documentation_policy", REPO_ROOT / "dev" / "documentation_policy.py"
)
assert SPEC and SPEC.loader
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


class DocumentationPolicyTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        (root / "AGENTS.md").write_text("fixture\n")
        (root / "docs").mkdir()
        return temporary, root

    def run_main(self, root: Path) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = policy.main([str(root)])
        return result, output.getvalue()

    def test_absent_path_is_accepted(self) -> None:
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        self.assertEqual(
            self.run_main(root),
            (0, "documentation_policy: canonical documentation layout is clean\n"),
        )

    def test_empty_directory_is_rejected(self) -> None:
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        (root / "docs" / "requirements").mkdir()
        result, output = self.run_main(root)
        self.assertEqual(result, 1)
        self.assertIn("remove docs/requirements", output)

    def test_file_at_forbidden_path_is_rejected(self) -> None:
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        (root / "docs" / "requirements").write_text("not a directory\n")
        self.assertEqual(self.run_main(root)[0], 1)

    @unittest.skipIf(
        os.name == "nt", "symlink creation is not guaranteed on Windows CI"
    )
    def test_symlink_at_forbidden_path_is_rejected(self) -> None:
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        target = root / "elsewhere"
        target.mkdir()
        (root / "docs" / "requirements").symlink_to(target, target_is_directory=True)
        self.assertEqual(self.run_main(root)[0], 1)

    def test_nested_markdown_is_rejected(self) -> None:
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        nested = root / "docs" / "requirements" / "archive"
        nested.mkdir(parents=True)
        (nested / "proposal.md").write_text("temporary intent\n")
        self.assertEqual(self.run_main(root)[0], 1)

    def test_unrelated_requirements_txt_is_accepted(self) -> None:
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        (root / "requirements.txt").write_text("pytest\n")
        self.assertEqual(self.run_main(root)[0], 0)

    def test_invalid_root_returns_two(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result, output = self.run_main(Path(temporary) / "missing")
        self.assertEqual(result, 2)
        self.assertIn("cannot inspect repository root", output)

    def test_repository_obeys_policy(self) -> None:
        self.assertEqual(self.run_main(REPO_ROOT)[0], 0)


if __name__ == "__main__":
    unittest.main()
