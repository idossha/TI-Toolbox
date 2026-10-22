"""Generator -> reports folder -> ``/api/catalog/reports`` -> ``/api/files/report/{id}``, end to end.

Pins (2026-10-22):
* the real report writers (simulation, flex-search, ex-search, DTI QC, and the charm copy) put one
  file each where the Reports list reads, and ``GET /api/catalog/reports?subject=X`` lists exactly
  those five, each with the kind its file name states and the title the Reports list gives it;
* every listed id is served by ``GET /api/files/report/{id}`` with status 200, the file's bytes
  unchanged, its generator's ``<title>``, one ``Content-Security-Policy`` header equal to the
  route's report policy (the app-wide policy must not be appended to it: browsers enforce two
  policies as their intersection, which would block the report's inline script), and ``nosniff``;
* that policy is tight on its own terms, checked against the intent typed here, not the route's
  constant: ``default-src 'none'``, ``sandbox allow-scripts``, and no other directive naming
  anything beyond ``'unsafe-inline'`` and ``data:`` (no scheme, host, ``*`` or ``'self'``);
* each served page is self-contained under the policy it is served with: every resource it would
  fetch (``src``, non-anchor ``href``, CSS ``url()``) is a ``data:`` URI that the matching fetch
  directive allows, there is no ``@import``, inline script and style are allowed by the policy,
  and the only links are in-page anchors or ``https://doi.org/`` citations (spec:
  ``tit/reporting/html/components.py`` module docstring, "A page makes no network request");
* an unknown id and an id that climbs out of the subject's reports folder are 404, even when the
  climb would land on a real HTML file inside the project;
* (real data, ``TIT_DATASET_000``) every SimNIBS ``charm_report.html`` in Dataset 000, copied by
  ``tit.pre.charm.copy_charm_report`` into a tmp project, is listed and served byte for byte under
  the report policy, which blocks nothing it embeds. The dataset is only read (mtimes compared).

Expected values: kinds and titles from ``REPORT_TITLES`` (docs/dev/DECISIONS.md 2026-09-28), a
report whose page names its run listed by that page title (c1_5);
page titles from the inputs (subject ``X``, simulation ``M``) and the reports' title convention;
the fetch-directive fallback rule from CSP Level 3 (a missing ``img-src``/``font-src``/... falls
back to ``default-src``). Inputs are the synthetic run folders of ``tests/test_reporting_runs.py``
and ``tests/test_reporting_dti_qc.py``; the cap image and DTI renderer are stubbed.

Reproduce: ``TIT_DATASET_000=/path/to/000 .venv/bin/python -m pytest
tests/test_report_catalog_route_chain.py -q -p no:cacheprovider`` (without the variable the
real-data test skips with its reason).
Deliberately elsewhere: what the browser does with a sandboxed iframe (desktop e2e), artifact
events (``tests/test_report_artifact_events.py``), same-second names
(``tests/test_report_filename_collision.py``).
"""

from __future__ import annotations

import os
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tests.test_report_artifact_events import (  # noqa: E402
    REPORT_TITLES,
    SUBJECT,
    WRITERS,
    make_project,
)
from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.routes import files  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}

#: The browser-tab title each report carries, from its inputs (subject X, simulation M, and the
#: run folders ``run`` and ``ex`` of tests/test_reporting_runs.py's flex and ex fixtures).
PAGE_TITLES = {
    "simulation_report": "M simulation",
    "flex_search_report": "run flex-search",
    "ex_search_report": "ex ex-search",
    "dti_qc": f"sub-{SUBJECT} DTI QC",
    "charm_report": f"charm report sub-{SUBJECT}",
}
#: The kinds whose page title names the run, so the Reports list shows that title.
_RUN_TITLED = ("simulation_report", "flex_search_report", "ex_search_report")

#: Which fetch directive governs a resource, by element (CSP Level 3 §6.1).
_DIRECTIVE_FOR_TAG = {
    "img": "img-src",
    "image": "img-src",  # SVG <image>
    "script": "script-src",
    "link": "style-src",
    "audio": "media-src",
    "video": "media-src",
    "source": "media-src",
    "track": "media-src",
    "iframe": "frame-src",
    "frame": "frame-src",
    "object": "object-src",
    "embed": "object-src",
}
_URL_ATTRS = (
    "src",
    "href",
    "xlink:href",
    "srcset",
    "poster",
    "data",
    "action",
    "formaction",
    "background",
    "manifest",
)


@pytest.fixture()
def chain(tmp_path):
    """A project with one report of every kind, written by the real writers, and a client."""
    pytest.importorskip("PIL.Image")  # the flex run folder holds real PNGs
    pm = make_project(tmp_path / "project")
    written = {
        kind: write(pm, tmp_path / "scratch" / kind) for kind, write in WRITERS.items()
    }
    settings = ServerSettings(project_dir=pm.project_dir, token=TOKEN)
    client = TestClient(create_app(settings), base_url="http://127.0.0.1:8765")
    return pm, written, client


def _policy(header: str) -> dict[str, list[str]]:
    out = {}
    for part in header.split(";"):
        name, *sources = part.split()
        out[name.lower()] = sources
    return out


def _allows(policy: dict[str, list[str]], directive: str, url: str) -> bool:
    """Whether *url* (a ``data:`` URI or other) may be fetched under *directive*."""
    sources = policy.get(directive, policy.get("default-src", []))
    scheme = url.split(":", 1)[0].lower() + ":" if ":" in url else ""
    return scheme == "data:" and "data:" in sources


class _Resources(HTMLParser):
    """Every URL the page would fetch or link to, and its inline scripts and styles."""

    def __init__(self) -> None:
        super().__init__()
        self.fetches: list[tuple[str, str]] = []  # (directive, url)
        self.links: list[str] = []  # <a href>
        self.css: list[str] = []
        self.inline_scripts = 0
        self.inline_styles = 0
        self._in = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self._in = tag
        if tag == "script" and "src" not in a:
            # A JSON data block is inert; anything else is code the policy must allow.
            if (a.get("type") or "").lower() != "application/json":
                self.inline_scripts += 1
        if tag == "style":
            self.inline_styles += 1
        if a.get("style"):
            self.css.append(a["style"])
        for attr in _URL_ATTRS:
            value = (a.get(attr) or "").strip()
            if not value:
                continue
            if tag == "a" and attr == "href":
                self.links.append(value)
            elif value.startswith("#"):
                continue  # an in-document reference (SVG <use href="#...">) fetches nothing
            else:
                self.fetches.append((_DIRECTIVE_FOR_TAG.get(tag, "default-src"), value))

    def handle_endtag(self, tag):
        self._in = ""

    def handle_data(self, data):
        if self._in == "style":
            self.css.append(data)


def _css_urls(css: str) -> list[str]:
    return [
        u.strip().strip("'\"") for u in re.findall(r"url\(\s*([^)]*?)\s*\)", css, re.I)
    ]


def test_the_reports_list_names_exactly_the_written_reports(chain):
    pm, written, client = chain

    r = client.get("/api/catalog/reports", params={"subject": SUBJECT}, headers=BEARER)

    assert r.status_code == 200
    listed = r.json()
    assert len(listed) == 5
    assert {e["path"]: e["kind"] for e in listed} == {
        str(path): kind for kind, path in written.items()
    }
    # A page that names its run is listed by it (c1_5); the DTI page names only the subject, so
    # it is listed by kind and the time in its file name; the charm copy has no time in its name.
    dti_stamp = re.search(r"_(\d{8})_(\d{6})$", written["dti_qc"].stem).groups()
    dti_when = (
        f"{dti_stamp[0][:4]}-{dti_stamp[0][4:6]}-{dti_stamp[0][6:]} "
        f"{dti_stamp[1][:2]}:{dti_stamp[1][2:4]}:{dti_stamp[1][4:]}"
    )
    assert {e["kind"]: e["title"] for e in listed} == {
        **{k: PAGE_TITLES[k] for k in _RUN_TITLED},
        "dti_qc": f"{REPORT_TITLES['dti_qc']}, {dti_when}",
        "charm_report": REPORT_TITLES["charm_report"],
    }
    assert {e["id"] for e in listed} == {
        f"{SUBJECT}/{path.stem}" for path in written.values()
    }


@pytest.mark.parametrize("kind", sorted(WRITERS))
def test_each_listed_report_is_served_intact_under_the_report_policy(chain, kind):
    pm, written, client = chain
    listed = client.get(
        "/api/catalog/reports", params={"subject": SUBJECT}, headers=BEARER
    ).json()
    (entry,) = [e for e in listed if e["kind"] == kind]

    r = client.get(f"/api/files/report/{entry['id']}", headers=BEARER)

    assert r.status_code == 200
    assert r.content == written[kind].read_bytes()
    assert f"<title>{PAGE_TITLES[kind]}</title>" in r.text
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers.get_list("content-security-policy") == [files.REPORT_CSP]


#: Every source a report's policy may name, typed from the policy's intent rather than imported
#: from the route (ra_14 finding 6, and ``tit/reporting/html/components.py``: "A page makes no
#: network request"): inline script and style, and data: images and fonts. A scheme (http:,
#: https:), a host, ``*``, ``'self'`` or ``'unsafe-eval'`` would let a report reach past itself.
NO_NETWORK_SOURCES = {"'unsafe-inline'", "data:"}


def test_every_served_report_policy_blocks_everything_but_inline_and_data(chain):
    """The route's policy is not only what the pages need, it is no wider: nothing by default,
    no directive that names the network or an origin, and an opaque-origin sandbox."""
    pm, written, client = chain
    listed = client.get(
        "/api/catalog/reports", params={"subject": SUBJECT}, headers=BEARER
    ).json()
    assert len(listed) == len(WRITERS)

    for entry in listed:
        header = client.get(f"/api/files/report/{entry['id']}", headers=BEARER).headers[
            "content-security-policy"
        ]
        names = [part.split()[0].lower() for part in header.split(";")]
        assert len(names) == len(set(names)), f"a directive is repeated: {header}"
        policy = _policy(header)
        assert policy.pop("default-src") == ["'none'"], header
        assert policy.pop("sandbox") == ["allow-scripts"], header
        assert {
            name: sources
            for name, sources in policy.items()
            if not set(sources) <= NO_NETWORK_SOURCES
        } == {}, header


def policy_problems(html: str, header: str) -> tuple[int, list[str]]:
    """``(resources checked, what the policy in *header* would block or forbid in *html*)``."""
    policy = _policy(header)
    page = _Resources()
    page.feed(html)
    css = "\n".join(page.css)
    css_fetches = [
        ("font-src" if u.lower().startswith("data:font/") else "img-src", u)
        for u in _css_urls(css)
        if not u.startswith("#")
    ]
    fetches = page.fetches + css_fetches
    problems = [f"{d} blocks {u[:60]}" for d, u in fetches if not _allows(policy, d, u)]
    if "@import" in css.lower():
        problems.append("@import")
    if page.inline_scripts and "'unsafe-inline'" not in policy.get("script-src", []):
        problems.append(f"{page.inline_scripts} inline scripts blocked")
    if page.inline_styles and "'unsafe-inline'" not in policy.get("style-src", []):
        problems.append(f"{page.inline_styles} inline styles blocked")
    if policy.get("sandbox") != ["allow-scripts"]:
        problems.append(f"sandbox {policy.get('sandbox')}")
    return len(fetches), problems


@pytest.mark.parametrize("kind", sorted(WRITERS))
def test_each_served_report_fetches_nothing_its_policy_blocks(chain, kind):
    pm, written, client = chain
    r = client.get(f"/api/files/report/{SUBJECT}/{written[kind].stem}", headers=BEARER)
    assert r.status_code == 200

    checked, problems = policy_problems(r.text, r.headers["content-security-policy"])

    assert checked, f"{kind}: the page embeds nothing, so there is nothing to check"
    assert problems == [], f"{kind}: {problems}"
    page = _Resources()
    page.feed(r.text)
    assert all(
        link.startswith("#") or link.startswith("https://doi.org/")
        for link in page.links
    ), page.links


def test_a_generated_report_has_inline_code_and_images_to_check(chain):
    """The policy check above is not vacuous: the generated pages carry the things it checks."""
    pm, written, client = chain
    page = _Resources()
    page.feed(
        client.get(
            f"/api/files/report/{SUBJECT}/{written['dti_qc'].stem}", headers=BEARER
        ).text
    )

    assert page.inline_scripts >= 1 and page.inline_styles >= 1
    assert any(d == "img-src" and u.startswith("data:image/") for d, u in page.fetches)
    assert (
        sum(u.startswith("data:font/woff2") for u in _css_urls("\n".join(page.css)))
        == 4
    )
    assert any(link.startswith("https://doi.org/") for link in page.links)


def test_a_report_is_served_as_the_bytes_on_disk(tmp_path):
    """The route serves the file, it does not re-type it: Dataset 000's MNI152 charm report has
    98 CRLF line endings among 109 (measured 2026-10-22), which a text-mode read turned into LF,
    and a byte that is not UTF-8 made the route fail instead of serving the file."""
    from tit.pre.charm import copy_charm_report

    pm = make_project(tmp_path / "project")
    body = (
        b"\r\n<!DOCTYPE html>\r\n<html><head><title>CHARM report</title></head>\r\n"
        b"<body><p>T\xe9st \xe2\x80\x94 Latin-1 and UTF-8 side by side</p>\n</body></html>\r\n"
    )
    (Path(pm.m2m(SUBJECT)) / "charm_report.html").write_bytes(body)
    copy_charm_report(pm.project_dir, SUBJECT, logger=MagicMock())
    client = TestClient(
        create_app(ServerSettings(project_dir=pm.project_dir, token=TOKEN)),
        base_url="http://127.0.0.1:8765",
    )

    r = client.get(f"/api/files/report/{SUBJECT}/charm_report", headers=BEARER)

    assert r.status_code == 200
    assert r.content == body
    assert r.headers.get_list("content-security-policy") == [files.REPORT_CSP]


def test_unknown_and_climbing_report_ids_are_not_served(chain):
    pm, written, client = chain
    # A real HTML file inside the project, two levels above the subject's reports folder:
    # exactly where "X/../../secret" would land if the id were joined unchecked.
    secret = Path(pm.reports()).parent / "secret.html"
    secret.write_text("<html><title>not a report</title></html>")

    unknown = client.get(
        f"/api/files/report/{SUBJECT}/nope_20260101_000000", headers=BEARER
    )
    climb = client.get(f"/api/files/report/{SUBJECT}/..%2F..%2Fsecret", headers=BEARER)

    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "Unknown report id"
    assert climb.status_code == 404
    assert (
        climb.json()["detail"] == "Unknown report id"
    )  # reached the route, refused there
    assert "not a report" not in climb.text


# ── real data: SimNIBS's own charm reports (the one report TI-Toolbox does not write) ──

_DATASET = os.environ.get("TIT_DATASET_000", "")


@pytest.mark.skipif(
    not _DATASET or not os.path.isdir(_DATASET),
    reason="skipping: TIT_DATASET_000 is unset or not a directory (path of a Dataset 000 copy)",
)
def test_real_charm_reports_are_copied_listed_and_served_intact(tmp_path):
    """Every charm report in Dataset 000, copied by the real copier into a tmp project, is listed
    and served byte for byte (they are 3-15 MB of inline images and jQuery) under the report
    policy, which blocks nothing they embed. The dataset is only read."""
    from tit.pre.charm import copy_charm_report

    sources = sorted(
        Path(_DATASET).glob("derivatives/SimNIBS/sub-*/m2m_*/charm_report.html")
    )
    assert (
        sources
    ), f"no charm_report.html under {_DATASET}, so there is nothing to check"
    before = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in sources}

    root = tmp_path / "project"
    root.mkdir()
    pm = get_path_manager(str(root))
    subjects = {}
    for source in sources:
        sid = source.parent.name.removeprefix("m2m_")
        Path(pm.m2m(sid)).mkdir(parents=True)
        shutil.copyfile(source, Path(pm.m2m(sid)) / "charm_report.html")
        assert copy_charm_report(pm.project_dir, sid, logger=MagicMock()) is not None
        subjects[sid] = source
    client = TestClient(
        create_app(ServerSettings(project_dir=pm.project_dir, token=TOKEN)),
        base_url="http://127.0.0.1:8765",
    )

    for sid, source in subjects.items():
        listed = client.get(
            "/api/catalog/reports", params={"subject": sid}, headers=BEARER
        ).json()
        assert [(e["id"], e["kind"], e["title"]) for e in listed] == [
            (f"{sid}/charm_report", "charm_report", REPORT_TITLES["charm_report"])
        ]
        r = client.get(f"/api/files/report/{sid}/charm_report", headers=BEARER)
        assert r.status_code == 200
        assert r.content == source.read_bytes(), sid
        assert r.headers.get_list("content-security-policy") == [files.REPORT_CSP]
        checked, problems = policy_problems(
            r.text, r.headers["content-security-policy"]
        )
        assert checked and problems == [], (sid, problems)

    assert {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in sources} == before
