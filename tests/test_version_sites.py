"""Every stamped release literal in the checkout names one release, and the bump script moves all.

A partial bump ships a loader that downloads one release's compose file while the app refreshes
another's image (``dev/update/build_plan.py`` checks only compose and the wheel fallback). The
expected release is read from ``version.py`` (public release metadata, which a development bump
leaves alone), cross-checked against the runtime version in ``desktop/package.json``,
``desktop/package-lock.json`` and ``tit/__init__.py``; Python sites are read with :mod:`ast`, the
others by locating each literal with a pattern that must match exactly once.

The second test runs ``update_version`` on copies of the live files (never the checkout) and
checks every site moved to the new release and nothing else in those files changed, so a site
reformatted out of the bump script's patterns fails here instead of shipping stale (2026-10-22).
It runs on the files as checked out and on a development-stamped copy (``X.Y.Z-dev.N`` runtime
beside the last release, docs/dev/RELEASING.md), each file compared with its own pre-bump value.
Run: python -m pytest tests/test_version_sites.py -q. Release mechanics: docs/dev/RELEASING.md.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Non-Python sites: (file, pattern whose one group is the stamped tag, what it is).
TAG_SITES = [
    (
        "docker-compose.yml",
        r"image: idossha/ti-toolbox:\$\{TIT_IMAGE_TAG:-([^}]+)\}",
        "compose image default",
    ),
    (
        "tit/launch.py",
        r'refresh and image == "idossha/ti-toolbox:([^"]+)"',
        "Python launcher refresh literal",
    ),
    (
        "desktop/src/main/stack.ts",
        r'plan\.image === "idossha/ti-toolbox:([^"]+)"',
        "desktop refresh literal",
    ),
    (
        "loader.sh",
        r'\[ "\$image" = idossha/ti-toolbox:(\S+) \]',
        "bash loader refresh literal",
    ),
    (
        "loader.sh",
        r"\$\{TIT_SOURCE_REF:-refs/tags/([^}]+)\}",
        "bash loader source tag",
    ),
    (
        "container/blueprint/apptainer.def",
        r"(?m)^From: idossha/ti-toolbox:(\S+)$",
        "Apptainer base image",
    ),
    (
        "resources/dataset_descriptions/simnibs.dataset_description.json",
        r'"Tag": "idossha/ti-toolbox:(v[^"]+)"',
        "SimNIBS derivative container tag",
    ),
    ("README.md", r"The current release is \*\*([^*]+)\*\*", "README current release"),
]

#: Every file update_version stamps on a stable bump.
STAMPED_FILES = [
    "version.py",
    "README.md",
    "docker-compose.yml",
    "tit/launch.py",
    "loader.sh",
    "loader.py",
    "container/blueprint/apptainer.def",
    "desktop/src/main/stack.ts",
    "desktop/package.json",
    "tit/__init__.py",
    "CITATION.cff",
    *sorted(
        str(p.relative_to(ROOT))
        for p in (ROOT / "resources/dataset_descriptions").glob("*.json")
    ),
]


def _assigned(tree: ast.Module, name: str) -> ast.expr:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return node.value
    raise AssertionError(f"no top-level {name} assignment")


def _one(text: str, pattern: str, what: str) -> str:
    found = re.findall(pattern, text)
    assert len(found) == 1, f"{what}: expected exactly one site, found {found}"
    return found[0]


def read_sites(root: Path) -> dict[str, str]:
    """``{what: value}`` for every stamped site under *root*, each read independently."""
    sites: dict[str, str] = {}
    for rel, pattern, what in TAG_SITES:
        sites[what] = _one((root / rel).read_text(encoding="utf-8"), pattern, what)

    launch = ast.parse((root / "tit/launch.py").read_text(encoding="utf-8"))
    spec = _assigned(launch, "BUILTIN_SPEC")
    image = next(k.value.value for k in spec.keywords if k.arg == "image")
    sites["wheel fallback image default"] = _one(
        image, r"^idossha/ti-toolbox:\$\{TIT_IMAGE_TAG:-([^}]+)\}$", "BUILTIN_SPEC"
    )
    loader = ast.parse((root / "loader.py").read_text(encoding="utf-8"))
    sites["standalone loader release tag"] = ast.literal_eval(
        _assigned(loader, "RELEASE_TAG")
    )
    metadata = ast.parse((root / "version.py").read_text(encoding="utf-8"))
    core = ast.literal_eval(_assigned(metadata, "DOCKER_IMAGES"))["core"]["tag"]
    sites["version.py core image"] = _one(
        core, r"^idossha/ti-toolbox:(.+)$", "core tag"
    )
    sites["version.py TI_CSC_INFO"] = (
        "v" + ast.literal_eval(_assigned(metadata, "TI_CSC_INFO"))["version"]
    )
    sites["CITATION.cff"] = "v" + _one(
        (root / "CITATION.cff").read_text(encoding="utf-8"),
        r"(?m)^version: (\S+)$",
        "CITATION version",
    )
    return sites


def read_versions(root: Path) -> dict[str, str]:
    """The release (version.py) and the three runtime version sites."""
    package = json.loads((root / "desktop/package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "desktop/package-lock.json").read_text(encoding="utf-8"))
    tit_init = ast.parse((root / "tit/__init__.py").read_text(encoding="utf-8"))
    metadata = ast.parse((root / "version.py").read_text(encoding="utf-8"))
    return {
        "release": ast.literal_eval(_assigned(metadata, "__version__")),
        "desktop/package.json": package["version"],
        "desktop/package-lock.json": lock["version"],
        "desktop/package-lock.json root package": lock["packages"][""]["version"],
        "tit.__version__": ast.literal_eval(_assigned(tit_init, "__version__")),
    }


def _core(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("-", 1)[0].split("."))


def test_every_stamped_site_names_the_release():
    versions = read_versions(ROOT)
    release = versions.pop("release")
    runtime = set(versions.values())
    assert len(runtime) == 1, f"runtime versions disagree: {versions}"
    (runtime_version,) = runtime
    if "-" in runtime_version:
        # A development stamp (X.Y.Z-dev.N) keeps every release site on the last release.
        assert _core(runtime_version) >= _core(release), (runtime_version, release)
    else:
        assert runtime_version == release, (runtime_version, release)

    sites = read_sites(ROOT)
    stale = {what: tag for what, tag in sites.items() if tag != f"v{release}"}
    assert not stale, f"sites not on v{release}: {stale}"
    assert len(sites) == len(TAG_SITES) + 5


def test_the_launcher_default_image_is_the_release_image(monkeypatch):
    from tit import launch

    release = read_versions(ROOT)["release"]
    monkeypatch.delenv("TIT_IMAGE_TAG", raising=False)
    assert launch.default_image() == f"idossha/ti-toolbox:v{release}"
    monkeypatch.setattr(launch, "compose_path", lambda: None)  # an installed wheel
    assert launch.default_image() == f"idossha/ti-toolbox:v{release}"


def _load_update_version():
    spec = importlib.util.spec_from_file_location(
        "update_version_under_test", ROOT / "dev/update/update_version.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _undated(text: str) -> str:
    """Drop the lines a bump legitimately re-dates (version.py release_date, CITATION date)."""
    return re.sub(r'(?m)^.*("release_date": |date-released: ).*\n', "", text)


#: Files holding the runtime version: a development bump moves them and leaves the release sites.
RUNTIME_FILES = {"desktop/package.json", "tit/__init__.py"}


def _next_dev(release: str) -> str:
    """The development stamp RELEASING.md describes for the release after *release*."""
    major, minor, patch = release.split(".")
    return f"{major}.{minor}.{int(patch) + 1}-dev.1"


@pytest.mark.parametrize(
    "dev_stamped", [False, True], ids=["as-checked-out", "dev-stamped"]
)
def test_update_version_moves_every_live_site_and_nothing_else(
    tmp_path, monkeypatch, dev_stamped
):
    """A stable bump of copies of the live files moves every site and nothing else.

    Each file is compared with its own pre-bump value: the runtime files (package.json, lock,
    ``tit/__init__.py``) with the runtime version, every other site with version.py's release, so
    a development-stamped checkout (``X.Y.Z-dev.N`` beside release ``X.Y.Z-1``) passes too. The
    dev-stamped case makes that state on the copies with the development bump first, whatever the
    checkout holds.
    """
    new = "9.8.7"
    files = [*STAMPED_FILES, "desktop/package-lock.json"]
    for rel in files:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
        assert new not in target.read_text(encoding="utf-8"), rel
    monkeypatch.chdir(tmp_path)
    update = _load_update_version()
    if dev_stamped:
        release = read_versions(tmp_path)["release"]
        update.update_development_version(_next_dev(release))
        runtime = {k: v for k, v in read_versions(tmp_path).items() if k != "release"}
        assert set(runtime.values()) == {_next_dev(release)}, runtime
        assert read_sites(tmp_path) == read_sites(ROOT)
    before = {rel: (tmp_path / rel).read_text(encoding="utf-8") for rel in files}
    pre = read_versions(tmp_path)
    old_release, old_runtime = pre["release"], pre["desktop/package.json"]

    update.update_version(new)

    assert os.getcwd() == str(tmp_path)
    versions = read_versions(tmp_path)
    assert set(versions.values()) == {new}, versions
    sites = read_sites(tmp_path)
    assert sites == {what: f"v{new}" for what in sites}, sites
    for rel in STAMPED_FILES:
        old = old_runtime if rel in RUNTIME_FILES else old_release
        after = (tmp_path / rel).read_text(encoding="utf-8")
        assert _undated(after.replace(new, old)) == _undated(before[rel]), rel
    lock_before = json.loads(before["desktop/package-lock.json"])
    lock_after = json.loads((tmp_path / "desktop/package-lock.json").read_text())
    lock_after["version"] = lock_after["packages"][""]["version"] = old_runtime
    assert lock_after == lock_before


@pytest.mark.parametrize("what", [what for _, _, what in TAG_SITES])
def test_a_site_left_behind_is_named(tmp_path, what):
    """The reader itself: one stale site among copies of the live files is the one reported."""
    release = read_versions(ROOT)["release"]
    for rel in STAMPED_FILES:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
    rel, pattern, _ = next(site for site in TAG_SITES if site[2] == what)
    path = tmp_path / rel
    text = path.read_text(encoding="utf-8")
    match = re.search(pattern, text)
    path.write_text(
        text[: match.start(1)] + "v0.0.1" + text[match.end(1) :], encoding="utf-8"
    )
    sites = read_sites(tmp_path)
    assert {w: t for w, t in sites.items() if t != f"v{release}"} == {what: "v0.0.1"}
