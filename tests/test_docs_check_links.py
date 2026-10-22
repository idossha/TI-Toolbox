"""Self-test for ``docs/tests/check_links.py``, the built-site link, anchor and URL guard.

What this pins
    That the guard the docs workflow runs after the Jekyll build actually fails red: a
    link to a missing page, an anchor the target page does not carry (``data-id`` is not
    an id), a missing script, stylesheet or frame, an atlas file the atlas browser would
    fetch in vain, a docs URL written in the app with the wrong case, and a page whose
    heading ids differ from what ``heading_ids`` computes from its Markdown. A good tree
    passes; a missing or empty site cannot be checked (exit 2, never a pass).

Where the expected values come from
    The fixture pages are hand-written HTML. The ids on the pre-processing page
    (``workflow``, ``supported-input-formats``, ``head-models-and-atlas-alignment``)
    are copied from a real ``bundle exec jekyll build`` of ``docs/wiki/pre-processing.md``
    (2026-10-22); the replayed broken link is the one the 2026-10-21 audit found in
    ``docs/wiki/analyzer.md`` (``/wiki/pre-processing/#what-changed-from-freesurfer``).

Reproduce on a real build::

    cd docs && bundle exec jekyll build --baseurl /TI-Toolbox \\
        && python3 tests/check_links.py _site --repo ..

Deliberately elsewhere
    Media tags: ``docs/tests/check_assets.py``. Deep links checked without a build:
    ``tests/test_docs_deeplinks.py``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[1] / "docs"
BASE = "/TI-Toolbox"
SITE = "https://idossha.github.io"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, DOCS / "tests" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


links = _load("check_links")

PRE_PROCESSING = (
    '<html data-baseurl="/TI-Toolbox"><body><article class="docs__article">'
    '<h1 class="docs__title">Pre-processing</h1>'
    '<h2 id="workflow">Workflow</h2>'
    '<h2 id="supported-input-formats">Supported input formats</h2>'
    '<h2 id="head-models-and-atlas-alignment">Head models and atlas alignment</h2>'
    '<div data-id="ghost"></div>'
    "</article></body></html>"
)


def _analyzer(extra: str = "") -> str:
    return (
        '<html data-baseurl="/TI-Toolbox"><head>'
        '<link rel="stylesheet" href="/TI-Toolbox/assets/css/site.css">'
        '<link rel="canonical" href="https://idossha.github.io/TI-Toolbox/wiki/analyzer/">'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<script src="/TI-Toolbox/assets/js/toc.js?v=1712"></script>'
        "<script>var s = '<a href=\"/TI-Toolbox/wiki/nowhere/\">'; </script>"
        "</head><body>"
        '<h2 id="results">Results</h2>'
        '<a href="/TI-Toolbox/wiki/pre-processing/#head-models-and-atlas-alignment">atlas</a>'
        '<a href="../pre-processing/#workflow">relative</a>'
        '<a href="#results">here</a>'
        '<a href="https://idossha.github.io/TI-Toolbox/wiki/pre-processing/#workflow">abs</a>'
        '<a href="https://example.org/missing/#nope">external</a>'
        '<a href="mailto:ihaber@wisc.edu">mail</a>'
        '<iframe src="/TI-Toolbox/assets/other/report.html"></iframe>'
        '<!-- <a href="/TI-Toolbox/commented/out/">old</a> -->'
        f"{extra}</body></html>"
    )


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


@pytest.fixture
def site(tmp_path: Path) -> Path:
    root = tmp_path / "_site"
    _write(
        root,
        {
            "index.html": '<html><body><a href="/TI-Toolbox/wiki/analyzer/">go</a></body></html>',
            "wiki/analyzer/index.html": _analyzer(),
            "wiki/pre-processing/index.html": PRE_PROCESSING,
            "assets/css/site.css": "body{}",
            "assets/js/toc.js": "",
            "assets/other/report.html": "<html></html>",
            "assets/atlas/cit168.nii.gz": "x",
            "api/index.html": '<a href="/TI-Toolbox/api/missing/">ignored</a>',
        },
    )
    return root


def _run(site: Path, *extra: str) -> int:
    return links.main([str(site), *extra])


# ── the built-site rules ────────────────────────────────────────────────────


def test_good_site_passes(site, capsys):
    assert _run(site) == 0
    # index, analyzer, pre-processing and the framed report; api/ is MkDocs output.
    assert "4 pages" in capsys.readouterr().out


def test_replayed_old_analyzer_link_to_a_vanished_heading_fails(site, capsys):
    page = site / "wiki/analyzer/index.html"
    page.write_text(
        _analyzer(
            '<a href="/TI-Toolbox/wiki/pre-processing/#what-changed-from-freesurfer">x</a>'
        )
    )
    assert _run(site) == 1
    err = capsys.readouterr().err
    assert "wiki/analyzer/index.html" in err
    assert "/wiki/pre-processing/#what-changed-from-freesurfer" in err
    assert "no id 'what-changed-from-freesurfer'" in err


def test_data_id_is_not_an_anchor(site, capsys):
    (site / "wiki/analyzer/index.html").write_text(
        _analyzer('<a href="/TI-Toolbox/wiki/pre-processing/#ghost">x</a>')
    )
    assert _run(site) == 1
    assert "no id 'ghost'" in capsys.readouterr().err


def test_link_to_a_missing_page_fails(site, capsys):
    (site / "wiki/analyzer/index.html").write_text(
        _analyzer('<a href="/TI-Toolbox/wiki/flex/">x</a>')
    )
    assert _run(site) == 1
    assert (
        "/TI-Toolbox/wiki/flex/ -> no file wiki/flex/index.html"
        in capsys.readouterr().err
    )


@pytest.mark.parametrize(
    "missing, tag",
    [
        ("assets/js/toc.js", "<script>"),
        ("assets/css/site.css", "<link>"),
        ("assets/other/report.html", "<iframe>"),
    ],
)
def test_missing_script_stylesheet_or_frame_fails(site, capsys, missing, tag):
    (site / missing).unlink()
    assert _run(site) == 1
    err = capsys.readouterr().err
    assert tag in err and missing in err


def test_unrendered_liquid_in_a_link_fails(site, capsys):
    (site / "wiki/analyzer/index.html").write_text(
        _analyzer('<a href="{{ site.baseurl }}/wiki/">x</a>')
    )
    assert _run(site) == 1
    assert "unrendered Liquid" in capsys.readouterr().err


def test_missing_or_empty_site_cannot_be_checked(tmp_path, capsys):
    assert _run(tmp_path / "nope") == 2
    (tmp_path / "empty").mkdir()
    assert _run(tmp_path / "empty") == 2


# ── repository rules (--repo) ───────────────────────────────────────────────


@pytest.fixture
def repo(tmp_path: Path, site: Path) -> Path:
    root = tmp_path / "repo"
    _write(
        root,
        {
            "docs/_config.yml": f'baseurl: "{BASE}"\nurl: "{SITE}"\n',
            "docs/_data/atlases.json": json.dumps(
                {"mni": {"template": {"filename": "cit168.nii.gz"}, "atlases": {}}}
            ),
            "docs/wiki/pre-processing.md": (
                "---\npermalink: /wiki/pre-processing/\n---\n\n## Workflow\n\n"
                "## Supported input formats\n\n## Head models and atlas alignment\n"
            ),
            "docs/wiki/analyzer.md": "---\npermalink: /wiki/analyzer/\n---\n\n## Results\n",
            "desktop/src/help.ts": (
                'const DOCS = "https://idossha.github.io/TI-Toolbox/";\n'
                "const PAGE = `https://idossha.github.io/TI-Toolbox/wiki/${slug}/`;\n"
                'const DEEP = "https://idossha.github.io/TI-Toolbox/wiki/pre-processing/#workflow";\n'
            ),
            "tit/x.py": 'URL = f"https://idossha.github.io/TI-Toolbox/releases/v{version}/"\n',
        },
    )
    return root


def test_good_repository_passes(site, repo, capsys):
    assert _run(site, "--repo", str(repo)) == 0
    out = capsys.readouterr().out
    assert "2 repository docs URLs" in out and "2 pages' heading ids" in out


def test_wrong_case_docs_url_in_the_app_fails(site, repo, capsys):
    (repo / "tit" / "init.py").write_text(
        'README = "https://idossha.github.io/TI-toolbox/"\n'
    )
    assert _run(site, "--repo", str(repo)) == 1
    err = capsys.readouterr().err
    assert "tit/init.py: https://idossha.github.io/TI-toolbox/ is not under" in err


def test_app_deep_link_to_a_missing_anchor_fails(site, repo, capsys):
    (repo / "resources" / "x.json").parent.mkdir()
    (repo / "resources" / "x.json").write_text(
        '["https://idossha.github.io/TI-Toolbox/wiki/pre-processing/#apply-a-cap"]'
    )
    assert _run(site, "--repo", str(repo)) == 1
    assert "no id 'apply-a-cap'" in capsys.readouterr().err


def test_atlas_file_missing_from_the_site_fails(site, repo, capsys):
    (site / "assets/atlas/cit168.nii.gz").unlink()
    assert _run(site, "--repo", str(repo)) == 1
    assert "assets/atlas/cit168.nii.gz is not published" in capsys.readouterr().err


def test_unpublished_wiki_permalink_fails(site, repo, capsys):
    (repo / "docs/wiki/jobs.md").write_text(
        "---\npermalink: /wiki/jobs/\n---\n# Jobs\n"
    )
    assert _run(site, "--repo", str(repo)) == 1
    assert "permalink /wiki/jobs/ is not published" in capsys.readouterr().err


def test_heading_ids_that_differ_from_the_build_fail(site, repo, capsys):
    md = repo / "docs/wiki/pre-processing.md"
    md.write_text(md.read_text().replace("## Workflow", "## Work flow"))
    assert _run(site, "--repo", str(repo)) == 1
    err = capsys.readouterr().err
    assert "docs/wiki/pre-processing.md: heading ids differ" in err
    assert "built only: ['workflow']" in err and "computed only: ['work-flow']" in err


def test_repository_with_no_docs_urls_is_not_clean(site, repo, capsys):
    (repo / "desktop/src/help.ts").unlink()
    assert _run(site, "--repo", str(repo)) == 1
    assert "no docs-site URL found" in capsys.readouterr().err


def test_template_urls_are_not_checked_as_literals():
    text = (
        "a `https://idossha.github.io/TI-Toolbox/wiki/${slug}/` "
        'b f"https://idossha.github.io/TI-Toolbox/releases/v{v}/" '
        "c (https://idossha.github.io/TI-Toolbox/installation/#install)."
    )
    assert links.docs_urls(text) == [
        "https://idossha.github.io/TI-Toolbox/installation/#install"
    ]


def test_site_address_matches_the_docs_config():
    config = (DOCS / "_config.yml").read_text(encoding="utf-8")
    assert links.site_address(config) == (SITE, BASE)
