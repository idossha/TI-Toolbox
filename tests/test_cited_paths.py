"""``dev/check_cited_paths.sh``: every repository path the docs cite resolves (2026-10-22).

What this pins:
- Every rule of the guard, driven from fixture trees built in ``tmp_path``: a stale
  repository path fails (exit 1, ``file:line`` named), a path that resolves passes (exit 0,
  with the number of citations it actually checked), and a guard that could check nothing
  exits 2 rather than 0.
- The repository passes its own guard over its default documents (AGENTS.md,
  docs/dev/TESTING.md, docs/wiki/*.md, agent-plugin/skills/*/SKILL.md).
- With its allowlist emptied, the guard flags the shipped ti-toolbox SKILL.md's ``dev/loader/``
  (a directory this repository never had; ``--dev`` is a loader flag) at the line the file
  itself holds it on.

Where the expected values come from: each fixture is authored here, so every expected
count is the number of citations planted in it; the SKILL.md line is read from the file
on disk, not from the guard.

Reproduce: ``.venv/bin/python -m pytest tests/test_cited_paths.py -q``, or run the guard
directly: ``bash dev/check_cited_paths.sh``.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GUARD = REPO / "dev" / "check_cited_paths.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None, reason="skipping: the guard is a bash script"
)


def _write(root: Path, rel: str, text: str = "x\n") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _run(
    root: Path, *args: str, allowlist: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the guard on *root*; git's upward search stops at the fixture's parent."""
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(root.parent), NO_COLOR="1")
    cmd = ["bash", str(GUARD), "--root", str(root)]
    if allowlist is not None:
        cmd += ["--allowlist", str(allowlist)]
    return subprocess.run(
        [*cmd, *args], capture_output=True, text=True, env=env, cwd=root, timeout=120
    )


def _out(proc: subprocess.CompletedProcess[str]) -> str:
    return proc.stdout + proc.stderr


@pytest.fixture
def empty_allowlist(tmp_path: Path) -> Path:
    path = tmp_path / "allow.txt"
    path.write_text("# nothing allowed\n")
    return path


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A small repository: top-level tit/, dev/, tests/, docs/ and desktop/."""
    root = tmp_path / "repo"
    _write(root, "tit/calc.py")
    _write(root, "tit/sim/config.py")
    _write(root, "dev/smoke.sh")
    _write(root, "tests/test_a.py")
    _write(root, "desktop/tests/e2e/real/sim.spec.ts")
    _write(root, "docs/dev/TESTING.md", "# Testing\n")
    _write(root, "docs/README.md", "# Docs\n")
    return root


# ── exit 0: every repository citation resolves ─────────────────────────────


def test_resolving_citations_pass_and_are_counted(tree, empty_allowlist):
    _write(
        tree,
        "AGENTS.md",
        "Run `dev/smoke.sh`; the config is `tit/sim/config.py`.\n"
        "See [testing](docs/dev/TESTING.md).\n",
    )
    proc = _run(tree, allowlist=empty_allowlist)
    assert proc.returncode == 0, _out(proc)
    # Two default documents: AGENTS.md and the fixture's docs/dev/TESTING.md (no citations).
    assert "3 cited path(s) in 2 document(s) resolve" in proc.stdout


def test_a_module_path_resolves_to_its_py_file(tree, empty_allowlist):
    _write(tree, "AGENTS.md", "Numerics live in `tit/calc` and `tit/nothere`.\n")
    proc = _run(tree, allowlist=empty_allowlist)
    assert proc.returncode == 1
    assert "AGENTS.md:1: path does not resolve: tit/nothere" in proc.stderr
    assert "tit/calc\n" not in proc.stderr
    assert "1 of 2 cited path(s) do not resolve" in proc.stderr


def test_a_directory_cited_by_its_tail_resolves(tree, empty_allowlist):
    _write(
        tree,
        "AGENTS.md",
        "Real specs are in `tests/e2e/real`.\nMissing ones in `tests/e2e/gone`.\n",
    )
    proc = _run(tree, allowlist=empty_allowlist)
    assert proc.returncode == 1
    assert "AGENTS.md:2: path does not resolve: tests/e2e/gone" in proc.stderr
    assert "tests/e2e/real" not in proc.stderr


def test_user_project_paths_are_not_repository_citations(tree, empty_allowlist):
    _write(
        tree,
        "docs/wiki/guide.md",
        "Copy scans to `sourcedata/sub-01/T1w/`; results land in "
        "`derivatives/SimNIBS/sub-01/` with `analysis.json`.\n"
        "The tests are in `tests/test_a.py`.\n",
    )
    proc = _run(tree, "docs/wiki/guide.md", allowlist=empty_allowlist)
    assert proc.returncode == 0, _out(proc)
    # Only tests/test_a.py cites this tree; the three user paths were never counted.
    assert "1 cited path(s) in 1 document(s) resolve" in proc.stdout


def test_a_gitignored_output_directory_is_described_not_cited(tree, empty_allowlist):
    _write(tree, "AGENTS.md", "The build writes `desktop/out`.\n")
    # A checkout: the guard then lists the tree with `git ls-files`, so the files are added.
    subprocess.run(["git", "init", "-q", str(tree)], check=True)
    subprocess.run(["git", "-C", str(tree), "add", "."], check=True)
    proc = _run(tree, allowlist=empty_allowlist)
    assert proc.returncode == 1
    assert "path does not resolve: desktop/out" in proc.stderr
    _write(tree, "desktop/.gitignore", "out/\n")
    proc = _run(tree, allowlist=empty_allowlist)
    assert proc.returncode == 0, _out(proc)


# ── exit 1: a stale citation ───────────────────────────────────────────────


def test_a_stale_repository_path_fails_naming_file_and_line(tree, empty_allowlist):
    _write(
        tree,
        "agent-plugin/skills/x/SKILL.md",
        "# Skill\n\nThe dev overrides live in `dev/loader/`.\n",
    )
    proc = _run(tree, allowlist=empty_allowlist)
    assert proc.returncode == 1
    assert (
        "agent-plugin/skills/x/SKILL.md:3: path does not resolve: dev/loader/"
        in proc.stderr
    )


def test_a_bare_document_name_must_exist_somewhere(tree, empty_allowlist):
    _write(tree, "AGENTS.md", "Read `README.md`, then `RELEASE.md` section B.\n")
    proc = _run(tree, allowlist=empty_allowlist)
    assert proc.returncode == 1
    assert "AGENTS.md:1: path does not resolve: RELEASE.md" in proc.stderr
    assert "README.md" not in proc.stderr


def test_a_glob_must_match_something(tree, empty_allowlist):
    _write(tree, "AGENTS.md", "Sources: `tit/*.py`.\nNever cite `tit/gui/**`.\n")
    proc = _run(tree, allowlist=empty_allowlist)
    assert proc.returncode == 1
    assert "AGENTS.md:2: path matches nothing: tit/gui/**" in proc.stderr
    assert "tit/*.py" not in proc.stderr


def test_a_link_is_strict_where_a_backticked_path_is_lenient(tree, empty_allowlist):
    # `e2e/real/sim.spec.ts` is the tail of a real file, which a backticked path may be,
    # but a renderer resolves a link from the citing file or the root only.
    _write(
        tree,
        "AGENTS.md",
        "The [spec](tests/e2e/real/sim.spec.ts) and [docs](docs/README.md).\n",
    )
    proc = _run(tree, allowlist=empty_allowlist)
    assert proc.returncode == 1
    assert (
        "AGENTS.md:1: link does not resolve: tests/e2e/real/sim.spec.ts" in proc.stderr
    )
    assert "docs/README.md" not in proc.stderr


# ── the allowlist ──────────────────────────────────────────────────────────


def test_a_scoped_allowlist_entry_covers_only_its_file(tree, tmp_path):
    _write(tree, "AGENTS.md", "Old: `dev/loader/`.\n")
    _write(tree, "docs/wiki/a.md", "Old: `dev/loader/`.\n")
    allow = tmp_path / "scoped.txt"
    allow.write_text("# stale, owned elsewhere\ndev/loader/ docs/wiki/a.md\n")
    proc = _run(tree, "AGENTS.md", "docs/wiki/a.md", allowlist=allow)
    assert proc.returncode == 1
    assert "AGENTS.md:1: path does not resolve: dev/loader/" in proc.stderr
    assert "docs/wiki/a.md" not in proc.stderr


def test_an_unscoped_allowlist_glob_covers_every_file(tree, tmp_path):
    _write(tree, "AGENTS.md", "Pages: `docs/releases/vX.Y.Z.md`.\n")
    allow = tmp_path / "glob.txt"
    allow.write_text("*vX.Y.Z*\n")
    proc = _run(tree, allowlist=allow)
    assert proc.returncode == 0, _out(proc)


# ── exit 2: nothing could be checked ───────────────────────────────────────


def test_no_documents_at_all_is_not_a_pass(tmp_path, empty_allowlist):
    root = tmp_path / "bare"
    _write(root, "README.md", "# Nothing for the guard\n")
    proc = _run(root, allowlist=empty_allowlist)
    assert proc.returncode == 2
    assert "no documents found" in proc.stderr


def test_a_named_document_that_is_missing_is_not_a_pass(tree, empty_allowlist):
    proc = _run(tree, "docs/wiki/missing.md", allowlist=empty_allowlist)
    assert proc.returncode == 2
    assert "docs/wiki/missing.md does not exist" in proc.stderr


def test_documents_citing_no_repository_path_are_not_a_pass(tree, empty_allowlist):
    _write(
        tree,
        "AGENTS.md",
        "Put scans in `sourcedata/`, keep `~/.config/x.json`, see "
        "[site](https://example.org/) and `<your-file>.py`.\n",
    )
    proc = _run(tree, allowlist=empty_allowlist)
    assert proc.returncode == 2
    assert "cite no repository path" in proc.stderr
    proc = _run(tree, "--allow-empty", allowlist=empty_allowlist)
    assert proc.returncode == 0, _out(proc)


# ── the repository itself ──────────────────────────────────────────────────


def _run_repo(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(GUARD), *args],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=300,
    )


@pytest.mark.skipif(
    not (REPO / ".git").exists(), reason="skipping: needs the git checkout's file list"
)
def test_the_repository_passes_its_own_guard():
    proc = _run_repo()
    assert proc.returncode == 0, _out(proc)
    count = int(re.search(r"ok -- (\d+) cited path", proc.stdout).group(1))
    # The guarded documents cite hundreds of repository paths; a count near zero means the
    # repository-citation filter stopped recognising them.
    assert count > 100, proc.stdout


@pytest.mark.skipif(
    not (REPO / ".git").exists(), reason="skipping: needs the git checkout's file list"
)
def test_without_its_allowlist_the_guard_flags_the_shipped_skill_dev_loader(tmp_path):
    skill = REPO / "agent-plugin" / "skills" / "ti-toolbox" / "SKILL.md"
    lines = [
        i
        for i, line in enumerate(skill.read_text().splitlines(), start=1)
        if "`dev/loader/`" in line
    ]
    if not lines:
        pytest.skip("skipping: the shipped SKILL.md no longer cites dev/loader/")
    assert not (REPO / "dev" / "loader").exists()
    allow = tmp_path / "none.txt"
    allow.write_text("")
    proc = _run_repo("--allowlist", str(allow))
    assert proc.returncode == 1
    for line in lines:
        assert (
            f"agent-plugin/skills/ti-toolbox/SKILL.md:{line}: path does not resolve: "
            "dev/loader/" in proc.stderr
        )
