"""A new project's README and dataset_description.json link to the live docs site.

What this pins
    Every project used to be created with ``https://idossha.github.io/TI-toolbox/``
    (lower-case ``t``) in its README and, through the root template, in
    ``dataset_description.json`` ``ReferencesAndLinks``. GitHub Pages paths are
    case-sensitive: that URL is a 404 (Dataset 000's description carries it). Both
    writers of a project root are exercised: ``initialize_project_structure`` (README
    and the initializer's description) and ``ensure_dataset_descriptions(["root"])``
    (the template the pre-processing pipeline copies when the file is missing).

Where the expected values come from
    The docs site is ``url`` + ``baseurl`` in ``docs/_config.yml`` (the spec
    ``desktop/tests/unit/help-docs.test.ts`` applies to the app's ``DOCS_SITE``); the
    repository is ``github.com/idossha/TI-Toolbox``, the spelling of
    ``docs/_config.yml``'s baseurl. Nothing is read from the writers under test.

Deliberately elsewhere
    The built-site link guard (``docs/tests/check_links.py --repo``) resolves every
    docs URL written in ``tit/`` and ``resources/`` against the built site.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tit.pre.utils import ensure_dataset_descriptions
from tit.project_init.initializer import initialize_project_structure

REPO = Path(__file__).resolve().parents[1]


def _docs_site() -> str:
    config = (REPO / "docs" / "_config.yml").read_text(encoding="utf-8")
    url = re.search(r'^url:\s*"([^"]+)"', config, re.M).group(1)
    baseurl = re.search(r'^baseurl:\s*"([^"]+)"', config, re.M).group(1)
    return f"{url}{baseurl}/"


def _check_links(text: str) -> tuple[list[str], list[str]]:
    """Return (docs URLs, problems) for the idossha links in *text*."""
    site = _docs_site()
    repo_name = site.rstrip("/").rsplit("/", 1)[1]
    problems = []
    docs = re.findall(r"https?://idossha\.github\.io/[^\s\"'),]*", text)
    for url in docs:
        if not url.startswith(site):
            problems.append(f"{url} is not under {site}")
    for url in re.findall(r"https?://github\.com/idossha/[^\s\"'),/]*", text):
        if url.rsplit("/", 1)[1] != repo_name:
            problems.append(f"{url} does not name the repository {repo_name}")
    return docs, problems


def test_config_names_the_expected_site():
    # Guards the expectation itself: a typo in the config would make every check moot.
    assert _docs_site() == "https://idossha.github.io/TI-Toolbox/"


def test_initialized_readme_links_to_the_live_docs(tmp_path, capsys):
    project = tmp_path / "proj"
    project.mkdir()
    initialize_project_structure(project)
    docs, problems = _check_links((project / "README").read_text(encoding="utf-8"))
    assert docs, "the README links to no docs page"
    assert problems == []


def test_initialized_dataset_description_names_the_repository(tmp_path, capsys):
    project = tmp_path / "proj"
    project.mkdir()
    initialize_project_structure(project)
    payload = json.loads((project / "dataset_description.json").read_text())
    links = payload["ReferencesAndLinks"]
    assert links, "no ReferencesAndLinks"
    assert _check_links("\n".join(links))[1] == []


def test_root_template_links_to_the_live_docs(tmp_path):
    ensure_dataset_descriptions(str(tmp_path), ["root"])
    payload = json.loads((tmp_path / "dataset_description.json").read_text())
    docs, problems = _check_links("\n".join(payload["ReferencesAndLinks"]))
    assert docs, "the root template links to no docs page"
    assert problems == []
