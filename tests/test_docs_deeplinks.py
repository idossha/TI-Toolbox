"""Every deep link from the app, the agent plugin and the README names a heading that exists.

What this pins
    The app opens the docs at a section: the Pre-processing (i) panels link to
    ``wiki/pre-processing/#workflow`` and friends, the FastSurfer settings card to
    ``wiki/fastsurfer/#enable-apple-gpu``, the Caps panel to ``wiki/eeg-caps/#apply-a-cap``.
    Renaming a wiki heading silently breaks such a link, and a change under
    ``desktop/src`` never triggers the docs workflow, so this host test runs on every
    CircleCI push. It collects every docs-site URL written in ``desktop/src``,
    ``agent-plugin``, ``README.md``, the release notes and the changelog (literal URLs,
    plus TypeScript ``const`` / Python constant templates such as ``${PRE_DOCS}#workflow``
    resolved from their declarations), maps each to its Markdown source through the
    front-matter ``permalink``, and requires each ``#fragment`` to be a heading id or an
    ``id=""`` in that source. It also checks the ``mirrors `docs/wiki/X.md` "Section"``
    comments in the app name a heading that exists.

Where the expected values come from
    Heading ids are computed by ``docs/tests/check_links.py::heading_ids`` (kramdown's GFM
    rule). Its fixture ids below were produced by real kramdown 2.3.2 with
    kramdown-parser-gfm 1.1.0 (the parser GitHub Pages uses) on 2026-10-22::

        ruby -rkramdown -rkramdown-parser-gfm -e 'puts Kramdown::Document.new(
            File.read(ARGV[0]), input: "GFM").to_html.scan(/<h\\d id="([^"]+)"/)' fixture.md

    and the docs workflow's parity step (``check_links.py --repo``) compares the same
    function with the ids kramdown built for every page of the site (75 pages, 697 ids,
    no difference on 2026-10-22). The known deep links are listed by hand from the
    source files that write them.

Deliberately elsewhere
    Links inside the built site, and absolute URLs against the built site:
    ``tests/test_docs_check_links.py`` and the docs workflow.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"
SITE = "https://idossha.github.io/TI-Toolbox"
SOURCES = (
    "desktop/src",
    "agent-plugin",
    "README.md",
    "docs/releases",
    "docs/dev/CHANGELOG.md",
)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, DOCS / "tests" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


links = _load("check_links")


# ── collecting docs URLs, including template-built ones ─────────────────────

_TS_CONST = re.compile(
    r"\b(?:const|let)\s+([A-Z][A-Z0-9_]*)\s*=\s*([\"`])([^\"`\n]*)\2"
)
_PY_CONST = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=\s*f?\"([^\"\n]*)\"", re.M)
_TS_TEMPLATE = re.compile(r"`\$\{([A-Z][A-Z0-9_]*)\}([^`$]*)`")
_PY_TEMPLATE = re.compile(r"f\"\{([A-Z][A-Z0-9_]*)\}([^\"{]*)\"")
_PLACEHOLDER = re.compile(r"\$?\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _source_files(repo: Path):
    for source in SOURCES:
        root = repo / source
        paths = (
            [root]
            if root.is_file()
            else sorted(root.rglob("*")) if root.is_dir() else []
        )
        for path in paths:
            if path.is_file() and path.suffix in {
                ".ts",
                ".tsx",
                ".py",
                ".md",
                ".json",
                ".js",
            }:
                if "node_modules" not in path.parts:
                    yield path


def _resolve(value: str, constants: dict[str, str], depth: int = 0) -> str | None:
    """Substitute ``${NAME}`` / ``{NAME}`` from *constants*; None if one is unknown."""
    if depth > 5:
        return None
    unknown = [n for n in _PLACEHOLDER.findall(value) if n not in constants]
    if unknown:
        return None
    resolved = _PLACEHOLDER.sub(lambda m: constants[m.group(1)], value)
    return (
        resolved
        if not _PLACEHOLDER.search(resolved)
        else _resolve(resolved, constants, depth + 1)
    )


def collect_docs_links(repo: Path) -> list[tuple[str, str]]:
    """Return ``(file, url)`` for every docs-site URL the sources write."""
    texts = {
        p: p.read_text(encoding="utf-8", errors="ignore") for p in _source_files(repo)
    }
    declared: dict[Path, dict[str, str]] = {}
    shared: dict[str, str] = {}
    for path, text in texts.items():
        pattern = _PY_CONST if path.suffix == ".py" else _TS_CONST
        found = {m.group(1): m.group(m.lastindex) for m in pattern.finditer(text)}
        declared[path] = found
        for name, value in found.items():
            shared.setdefault(name, value)
    collected: list[tuple[str, str]] = []
    for path, text in texts.items():
        rel = path.relative_to(repo).as_posix()
        constants = {**shared, **declared[path]}
        for url in links.docs_urls(text):
            collected.append((rel, url))
        template = _PY_TEMPLATE if path.suffix == ".py" else _TS_TEMPLATE
        candidates = [
            f"${{{n}}}{rest}" if path.suffix != ".py" else f"{{{n}}}{rest}"
            for n, rest in template.findall(text)
        ]
        candidates += [v for v in declared[path].values() if _PLACEHOLDER.search(v)]
        for candidate in candidates:
            url = _resolve(candidate, constants)
            if url and url.startswith(SITE) and not _PLACEHOLDER.search(url):
                collected.append((rel, url.split()[0]))
    return sorted(set(collected))


def deep_link_problems(found: list[tuple[str, str]], docs: Path) -> list[str]:
    """Return the links whose page or ``#fragment`` does not exist in *docs*."""
    pages = links.source_pages(docs)
    anchors: dict[Path, set[str]] = {}
    problems = []
    for rel, url in found:
        if not url.startswith(SITE):
            problems.append(f"{rel}: {url} is not under {SITE}/")
            continue
        parsed = urlparse(url[len(SITE) :] or "/")
        path, fragment = unquote(parsed.path) or "/", unquote(parsed.fragment)
        page = pages.get(path) or pages.get(path + "/")
        if page is None:
            if path.startswith("/api") or (docs / path.lstrip("/")).is_file():
                continue
            problems.append(f"{rel}: {url} -> no page has permalink {path}")
            continue
        if fragment:
            if page not in anchors:
                _meta, body = links.split_front_matter(page.read_text(encoding="utf-8"))
                anchors[page] = links.anchor_ids(body)
            if fragment not in anchors[page]:
                problems.append(
                    f"{rel}: {url} -> no heading '#{fragment}' in "
                    f"{page.relative_to(docs.parent).as_posix()}"
                )
    return problems


_MIRROR = re.compile(r"mirrors\s+`?(docs/wiki/[\w.-]+\.md)`?\s+\"([^\"]+)\"")


def mirror_comments(repo: Path) -> list[tuple[str, str, str]]:
    """Return ``(file, markdown path, section)`` for each "mirrors" comment in the app."""
    found = []
    for path in sorted((repo / "desktop" / "src").rglob("*.ts*")):
        for md, section in _MIRROR.findall(path.read_text(encoding="utf-8")):
            found.append((path.relative_to(repo).as_posix(), md, section))
    return found


def mirror_problems(mirrors: list[tuple[str, str, str]], docs: Path) -> list[str]:
    """Return the comments whose section is not a heading of the named page."""
    problems = []
    for rel, md, section in mirrors:
        source = docs.parent / md
        if not source.is_file():
            problems.append(f"{rel}: mirrors {md}, which does not exist")
            continue
        _meta, body = links.split_front_matter(source.read_text(encoding="utf-8"))
        wanted = links.heading_ids(f"## {section}\n")[0]
        if wanted not in links.heading_ids(body):
            problems.append(f'{rel}: mirrors {md} "{section}", no such heading')
    return problems


# ── kramdown's id rule ──────────────────────────────────────────────────────

FIXTURE = """# Getting Started

## Install (macOS & Linux)

## Install (macOS & Linux)

## `run_simulation()` arguments

## Apply a cap {#custom-anchor}

## What's new -- v3.1?

### Step 1: Pre-processing

Setext Title
============

## Getting Started

```bash
## not a heading
```

<div id="raw-anchor"></div>

## [Link text](https://example.org) here

## Ünïcode héadïng

## `--dev` and `snake_case` flags ##

## A *bold* _choice_ & <span class="pill">Latest</span>
"""

# Produced by real kramdown + kramdown-parser-gfm from FIXTURE (see the header).
KRAMDOWN_IDS = [
    "getting-started",
    "install-macos--linux",
    "install-macos--linux-1",
    "run_simulation-arguments",
    "custom-anchor",
    "whats-new--v31",
    "step-1-pre-processing",
    "setext-title",
    "getting-started-1",
    "link-text-here",
    "ünïcode-héadïng",
    "--dev-and-snake_case-flags",
    "a-bold-choice--latest",
]


def test_heading_ids_follow_kramdown_gfm():
    assert links.heading_ids(FIXTURE) == KRAMDOWN_IDS


def test_raw_ids_are_anchors_but_code_blocks_are_not_headings():
    anchors = links.anchor_ids(FIXTURE)
    assert "raw-anchor" in anchors
    assert "not-a-heading" not in anchors


# ── this repository ─────────────────────────────────────────────────────────

# Written by hand from the files that hold them (stepInfo.tsx, SurferSettingsCard.tsx,
# caps/index.tsx, the 3.x release notes and the changelog).
KNOWN_DEEP_LINKS = {
    "/wiki/pre-processing/#workflow",
    "/wiki/pre-processing/#supported-input-formats",
    "/wiki/pre-processing/#head-models-and-atlas-alignment",
    "/wiki/fastsurfer/#fastsurfer-segmentation",
    "/wiki/fastsurfer/#enable-apple-gpu",
    "/wiki/fastsurfer/#permissions",
    "/wiki/eeg-caps/#apply-a-cap",
    "/wiki/eeg-caps/#inspect-a-net",
    "/wiki/simulator/#carrier-only-control",
    "/installation/#install",
    "/wiki/ai-assistant/#approving-a-plan",
}


@pytest.fixture(scope="module")
def found() -> list[tuple[str, str]]:
    return collect_docs_links(REPO)


def test_the_known_deep_links_are_collected(found):
    urls = {url[len(SITE) :] for _rel, url in found}
    assert KNOWN_DEEP_LINKS <= urls, sorted(KNOWN_DEEP_LINKS - urls)
    app = {url for rel, url in found if rel.startswith("desktop/src") and "#" in url}
    assert len(app) >= 8


def test_every_deep_link_names_an_existing_heading(found):
    assert deep_link_problems(found, DOCS) == []


def test_mirror_comments_name_existing_headings():
    mirrors = mirror_comments(REPO)
    assert {(m[1], m[2]) for m in mirrors} >= {
        ("docs/wiki/eeg-caps.md", "Apply a cap"),
        ("docs/wiki/eeg-caps.md", "Inspect a net"),
    }
    assert mirror_problems(mirrors, DOCS) == []


def test_template_constants_resolve_like_the_app(tmp_path):
    src = tmp_path / "desktop" / "src"
    src.mkdir(parents=True)
    (src / "a.ts").write_text(
        'export const DOCS_SITE = "https://idossha.github.io/TI-Toolbox/";\n'
        "const PRE = `${DOCS_SITE}wiki/pre-processing/`;\n"
        "const x = { docsHref: `${PRE}#workflow` };\n"
        "const y = `${DOCS_SITE}wiki/${slug}/`;\n"
    )
    (src / "b.tsx").write_text(
        'import { DOCS_SITE } from "./a";\nconst WIKI = `${DOCS_SITE}wiki/eeg-caps/`;\n'
        "<ReadMore href={`${WIKI}#apply-a-cap`} />\n"
    )
    urls = {url for _rel, url in collect_docs_links(tmp_path)}
    assert urls == {
        "https://idossha.github.io/TI-Toolbox/",
        "https://idossha.github.io/TI-Toolbox/wiki/pre-processing/",
        "https://idossha.github.io/TI-Toolbox/wiki/pre-processing/#workflow",
        "https://idossha.github.io/TI-Toolbox/wiki/eeg-caps/",
        "https://idossha.github.io/TI-Toolbox/wiki/eeg-caps/#apply-a-cap",
    }


def _docs_copy(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    for sub in ("wiki", "releases"):
        shutil.copytree(DOCS / sub, docs / sub)
    (docs / "dev").mkdir()
    shutil.copy(DOCS / "dev" / "CHANGELOG.md", docs / "dev" / "CHANGELOG.md")
    shutil.copy(DOCS / "index.md", docs / "index.md")
    (docs / "assets").symlink_to(DOCS / "assets")
    return docs


def test_renaming_a_linked_heading_fails(tmp_path, found):
    docs = _docs_copy(tmp_path)
    assert deep_link_problems(found, docs) == []
    caps = docs / "wiki" / "eeg-caps.md"
    text = caps.read_text(encoding="utf-8")
    assert "\n## Apply a cap\n" in text
    caps.write_text(text.replace("\n## Apply a cap\n", "\n## Apply an EEG cap\n"))
    problems = deep_link_problems(found, docs)
    assert problems and all("#apply-a-cap" in p for p in problems)
    assert any(
        p.startswith("desktop/src/renderer/pages/panels/caps/index.tsx")
        for p in problems
    )
    assert mirror_problems(mirror_comments(REPO), docs) == [
        "desktop/src/renderer/pages/panels/caps/model.ts: mirrors docs/wiki/eeg-caps.md "
        '"Apply a cap", no such heading'
    ]


def test_wrong_case_site_url_is_reported(tmp_path):
    problems = deep_link_problems(
        [("x.ts", "https://idossha.github.io/TI-toolbox/wiki/eeg-caps/")], DOCS
    )
    assert problems == [
        "x.ts: https://idossha.github.io/TI-toolbox/wiki/eeg-caps/ is not under "
        "https://idossha.github.io/TI-Toolbox/"
    ]
