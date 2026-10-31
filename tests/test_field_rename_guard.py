"""Retired field and metric names stay retired outside the history files (2026-10-30).

What this pins (docs/dev/DECISIONS.md, 2026-10-30 "field renames and display labels"):
``hf_sar`` became ``hf_rms`` (a different quantity: sqrt(hf_power), not 2 * hf_power), the
analyzer's ``hf_focality`` / ``rms_focality`` became ``hf_peak_focality`` / ``hf_rms_focality``,
and the Ex/mEx and group-summary columns ``HF_Focality`` / ``RMS_Focality`` became
``HFpeak_Focality`` / ``HFrms_Focality``. None of the old spellings may appear in code, tests,
docs, the wiki, the agent plugin, examples or notebooks; the history files keep them:
``docs/dev/CHANGELOG.md``, ``docs/dev/DECISIONS.md``, ``docs/releases/`` and the contract
change log ``contracts/CHANGES.md``.

Where the expectations come from: the tracked tree read off disk (``git ls-files``). Each rule
is also driven red on a planted file in ``tmp_path``.

Reproduce: ``.venv/bin/python -m pytest tests/test_field_rename_guard.py -q``.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: A retired spelling, never part of a longer identifier (``hf_rms_focality`` is not ``rms_focality``).
#: An escaped ``\_`` too: KaTeX writes ``\mathrm{hf\_sar}``.
RETIRED = re.compile(
    r"hf\\?_sar|HF_SAR|(?<![A-Za-z_\\])(?:rms\\?_focality|hf\\?_focality)"
    r"|HF\\?_Focality|RMS\\?_Focality"
)

#: The history files, which name what changed and so keep the old spellings.
HISTORY = ("docs/dev/CHANGELOG.md", "docs/dev/DECISIONS.md", "contracts/CHANGES.md")
HISTORY_DIRS = ("docs/releases/",)


#: The one reader of the old Ex/mEx column, which says in the report that it was renamed, and
#: its test.
LEGACY_READERS = (
    "tit/reporting/generators/ex_search.py",
    "tests/test_ex_carrier_focality.py",
)


def allowed(path: str) -> bool:
    return (
        path in HISTORY
        or path in LEGACY_READERS
        or path.startswith(HISTORY_DIRS)
        or path == "tests/test_field_rename_guard.py"
    )


def violations(root: Path, paths: list[str]) -> list[str]:
    """``path:line: match`` for every retired spelling in a non-history text file."""
    out = []
    for rel in paths:
        if allowed(rel):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue  # binary, or deleted in the working tree
        for number, line in enumerate(text.splitlines(), start=1):
            match = RETIRED.search(line)
            if match:
                out.append(f"{rel}:{number}: {match.group(0)}")
    return out


#: The old surface layout (2026-10-30, "one central surface mesh per run"): nothing the toolbox
#: ships writes or reads these, except the producer that copies an old run's ``TI_normal``.
RETIRED_LAYOUT = re.compile(r"_normal\.msh|msh2cortex|surface_overlays")
#: Shipped code and user docs; tests and the dev docs model and describe old runs.
LAYOUT_SCOPE = (
    "tit/",
    "desktop/src/",
    "agent-plugin/",
    "docs/wiki/",
    "docs/api_mkdocs/",
)
#: The one reader of an old run's ``<sim>_normal.msh``: the copy into the rebuilt surface.
LAYOUT_ALLOWED = ("tit/volume_fields.py",)


def layout_violations(root: Path, paths: list[str]) -> list[str]:
    """``path:line: match`` for the retired surface layout in shipped code and user docs."""
    out = []
    for rel in paths:
        if not rel.startswith(LAYOUT_SCOPE) or rel in LAYOUT_ALLOWED:
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            match = RETIRED_LAYOUT.search(line)
            if match:
                out.append(f"{rel}:{number}: {match.group(0)}")
    return out


def tracked() -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert len(listed) > 1000, "the tree has files to check"
    return listed


def test_no_retired_field_or_metric_name_outside_the_history_files() -> None:
    found = violations(REPO, tracked())
    assert not found, "\n".join(found[:50])


def test_each_retired_spelling_is_caught(tmp_path: Path) -> None:
    lines = [
        "x = 'hf_sar'",
        "FIELD_HF_SAR",
        "r.rms_focality",
        "hf_focality_50_area",
        "row['HF_Focality']",
        "RMS_Focality",
        r"$$\mathrm{hf\_sar}$$",
    ]
    (tmp_path / "a.py").write_text("\n".join(lines))
    assert len(violations(tmp_path, ["a.py"])) == len(lines)


def test_the_new_names_and_the_history_files_pass(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "hf_rms hf_peak_focality hf_rms_focality hf_peak_focality_50_area "
        "HFpeak_Focality HFrms_Focality TI_Selectivity"
    )
    (tmp_path / "docs/dev").mkdir(parents=True)
    (tmp_path / "docs/dev/CHANGELOG.md").write_text("hf_sar was renamed hf_rms")
    assert violations(tmp_path, ["a.py", "docs/dev/CHANGELOG.md"]) == []


def test_no_retired_surface_layout_in_shipped_code_or_user_docs() -> None:
    found = layout_violations(REPO, tracked())
    assert not found, "\n".join(found[:50])


def test_the_retired_layout_rule_is_caught_and_its_allowlist_kept(
    tmp_path: Path,
) -> None:
    for rel in ("tit/a.py", "docs/wiki/b.md", "tit/volume_fields.py", "tests/c.py"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("M_normal.msh\nmsh2cortex\nTI/surface_overlays/\n")
    found = layout_violations(
        tmp_path, ["tit/a.py", "docs/wiki/b.md", "tit/volume_fields.py", "tests/c.py"]
    )
    assert len(found) == 6 and all(
        f.startswith(("tit/a.py", "docs/wiki/b.md")) for f in found
    )
