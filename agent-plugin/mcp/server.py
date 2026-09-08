#!/usr/bin/env python3
"""TI-Toolbox MCP server.

Gives coding agents (Claude Code, Codex, any MCP client) read-only access to
TI-Toolbox knowledge:

* the wiki (``docs/wiki/*.md``) and changelog -- from a local checkout when one
  is available, otherwise fetched from GitHub and cached on disk;
* the nine developer documents of record (``docs/dev/*.md``);
* source files of the ``tit`` package and the v3 desktop app (same local/remote
  rule);
* a BIDS-aware inspector for a user's TI-Toolbox project directory, so the
  agent can see which subjects, head models, simulations, optimizations and
  reports actually exist on disk.

Zero third-party dependencies: JSON-RPC 2.0 over newline-delimited stdio, as
the MCP stdio transport specifies.  Python 3.9+.

Environment variables
---------------------
TI_TOOLBOX_ROOT   Path to a TI-Toolbox git checkout.  Auto-detected when this
                  file lives inside one (``<root>/agent-plugin/mcp/server.py``).
TI_TOOLBOX_REF    Git ref used for GitHub fetches (default ``main``).
TI_TOOLBOX_CACHE  Cache directory for fetched files
                  (default ``~/.cache/ti-toolbox-mcp``).
TI_TOOLBOX_OFFLINE  Set to ``1`` to forbid network access.

Run ``python3 server.py --selftest`` for a smoke test.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

SERVER_NAME = "ti-toolbox"
SERVER_VERSION = "0.2.0"
PROTOCOL_VERSION = "2025-06-18"

GITHUB_OWNER = "idossha"
GITHUB_REPO = "TI-Toolbox"
RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}"
API_BASE = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
SITE_BASE = "https://idossha.github.io/TI-Toolbox"

WIKI_DIR = "docs/wiki"
DEV_DOCS_DIR = "docs/dev"
CHANGELOG = "docs/releases/changelog.md"
PY_VERSION_FILE = "tit/__init__.py"  # __version__ of the `tit` package
DESKTOP_PACKAGE_JSON = "desktop/package.json"  # Electron app version (v3)

# docs/dev/ is the single source of truth for developers and is deliberately
# capped at nine files; read_dev_doc refuses anything outside this list.
DEV_DOCS = (
    "README",
    "ARCHITECTURE",
    "DECISIONS",
    "CONTRIBUTING",
    "DESIGN",
    "HISTORY",
    "BENCHMARKS",
    "SCIENTIFIC-CORRECTIONS",
    "RELEASE",
)

# Never listed, never searched, never counted: build output and vendored deps.
_SKIP_DIRS = {"__pycache__", "node_modules", "out", "dist", ".git", "coverage"}

MAX_CHARS = 60_000  # hard cap on any single text payload returned to the agent
CACHE_TTL_S = 24 * 3600

# --------------------------------------------------------------------------
# Configuration / locating the repo
# --------------------------------------------------------------------------


def _detect_repo_root() -> Optional[Path]:
    env = os.environ.get("TI_TOOLBOX_ROOT")
    if env:
        p = Path(env).expanduser()
        return p if (p / "tit").is_dir() else None
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "tit").is_dir() and (parent / WIKI_DIR).is_dir():
            return parent
    return None


REPO_ROOT = _detect_repo_root()
GIT_REF = os.environ.get("TI_TOOLBOX_REF", "main")
CACHE_DIR = Path(
    os.environ.get("TI_TOOLBOX_CACHE", "~/.cache/ti-toolbox-mcp")
).expanduser()
OFFLINE = os.environ.get("TI_TOOLBOX_OFFLINE") == "1"


class ToolError(Exception):
    """Raised for user-facing tool failures (reported as isError results)."""


# --------------------------------------------------------------------------
# File access: local checkout first, GitHub raw second (cached)
# --------------------------------------------------------------------------


def _safe_rel(path: str) -> str:
    """Normalise a repo-relative path and reject traversal / absolute paths."""
    rel = path.strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ToolError(f"Invalid repo path: {path!r}")
    return rel


def _cache_path(rel: str) -> Path:
    return CACHE_DIR / GIT_REF / rel


def _http_get(url: str, timeout: float = 20.0) -> bytes:
    if OFFLINE:
        raise ToolError(f"Offline mode (TI_TOOLBOX_OFFLINE=1); cannot fetch {url}")
    req = urllib.request.Request(
        url, headers={"User-Agent": f"{SERVER_NAME}-mcp/{SERVER_VERSION}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise ToolError(f"HTTP {e.code} fetching {url}") from e
    except urllib.error.URLError as e:
        raise ToolError(f"Network error fetching {url}: {e.reason}") from e


def read_repo_file(path: str, *, max_age_s: float = CACHE_TTL_S) -> str:
    """Return the text of a repo file (local checkout, then cache, then GitHub)."""
    rel = _safe_rel(path)
    if REPO_ROOT is not None:
        local = REPO_ROOT / rel
        if local.is_file():
            return local.read_text(encoding="utf-8", errors="replace")
        raise ToolError(f"File not found in local checkout: {rel}")

    cached = _cache_path(rel)
    if cached.is_file() and (time.time() - cached.stat().st_mtime) < max_age_s:
        return cached.read_text(encoding="utf-8", errors="replace")

    data = _http_get(f"{RAW_BASE}/{GIT_REF}/{rel}")
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(data)
    return data.decode("utf-8", errors="replace")


def list_repo_dir(path: str, *, max_age_s: float = CACHE_TTL_S) -> List[str]:
    """List entries of a repo directory (files and dirs, names only)."""
    rel = _safe_rel(path)
    if REPO_ROOT is not None:
        local = REPO_ROOT / rel
        if not local.is_dir():
            raise ToolError(f"Directory not found in local checkout: {rel}")
        return sorted(
            e.name + ("/" if e.is_dir() else "")
            for e in local.iterdir()
            if not e.name.startswith(".") and e.name not in _SKIP_DIRS
        )

    cached = _cache_path(rel + "/.listing.json")
    if cached.is_file() and (time.time() - cached.stat().st_mtime) < max_age_s:
        return json.loads(cached.read_text())

    data = _http_get(f"{API_BASE}/contents/{rel}?ref={GIT_REF}")
    entries = json.loads(data)
    if not isinstance(entries, list):
        raise ToolError(f"Not a directory: {rel}")
    names = sorted(
        e["name"] + ("/" if e.get("type") == "dir" else "")
        for e in entries
        if not e["name"].startswith(".") and e["name"] not in _SKIP_DIRS
    )
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(names))
    return names


def _truncate(text: str, limit: int = MAX_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[... truncated, {len(text) - limit} more characters]"


# --------------------------------------------------------------------------
# Wiki helpers
# --------------------------------------------------------------------------

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def _split_frontmatter(text: str) -> Dict[str, str]:
    m = _FRONTMATTER.match(text)
    meta: Dict[str, str] = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        meta["_body"] = text[m.end() :]
    else:
        meta["_body"] = text
    return meta


def _wiki_slugs() -> List[str]:
    return sorted(n[:-3] for n in list_repo_dir(WIKI_DIR) if n.endswith(".md"))


def _first_paragraph(body: str) -> str:
    for block in body.split("\n\n"):
        s = block.strip()
        if (
            s
            and not s.startswith("#")
            and not s.startswith("<")
            and not s.startswith("|")
        ):
            return re.sub(r"\s+", " ", s)[:240]
    return ""


def _headings(body: str) -> List[str]:
    return [ln.strip() for ln in body.splitlines() if re.match(r"^#{1,3}\s", ln)]


def tool_list_wiki_pages(_: Dict[str, Any]) -> Dict[str, Any]:
    pages = []
    for slug in _wiki_slugs():
        meta = _split_frontmatter(read_repo_file(f"{WIKI_DIR}/{slug}.md"))
        permalink = meta.get("permalink", f"/wiki/{slug}/")
        pages.append(
            {
                "slug": slug,
                "title": meta.get("title", slug),
                "url": SITE_BASE + permalink,
                "summary": _first_paragraph(meta["_body"]),
            }
        )
    return {"source": _source_label(), "pages": pages}


def tool_read_wiki_page(args: Dict[str, Any]) -> Dict[str, Any]:
    slug = str(args.get("page", "")).strip().strip("/")
    slug = slug.replace("wiki/", "").removesuffix(".md")
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", slug):
        raise ToolError(f"Invalid page slug: {slug!r}. Use list_wiki_pages.")
    section = args.get("section")
    text = read_repo_file(f"{WIKI_DIR}/{slug}.md")
    meta = _split_frontmatter(text)
    body = meta["_body"]
    if section:
        body = _extract_section(body, str(section))
    return {
        "slug": slug,
        "title": meta.get("title", slug),
        "url": SITE_BASE + meta.get("permalink", f"/wiki/{slug}/"),
        "headings": _headings(meta["_body"]),
        "content": _truncate(body),
    }


def _extract_section(body: str, heading: str) -> str:
    lines = body.splitlines()
    want = heading.lower().lstrip("#").strip()
    start = level = None
    for i, ln in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m and m.group(2).strip().lower() == want:
            start, level = i, len(m.group(1))
            break
    if start is None:
        raise ToolError(f"Section {heading!r} not found. Available: {_headings(body)}")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        m = re.match(r"^(#{1,6})\s", lines[j])
        if m and len(m.group(1)) <= level:
            end = j
            break
    return "\n".join(lines[start:end])


def tool_search_wiki(args: Dict[str, Any]) -> Dict[str, Any]:
    query = str(args.get("query", "")).strip()
    if not query:
        raise ToolError("query is required")
    limit = int(args.get("max_results", 20))
    terms = [t for t in re.split(r"\s+", query.lower()) if t]
    hits = []
    for slug in _wiki_slugs():
        text = read_repo_file(f"{WIKI_DIR}/{slug}.md")
        body = _split_frontmatter(text)["_body"]
        current_heading = ""
        for lineno, ln in enumerate(body.splitlines(), 1):
            if re.match(r"^#{1,6}\s", ln):
                current_heading = ln.strip("# ").strip()
            low = ln.lower()
            if all(t in low for t in terms):
                hits.append(
                    {
                        "page": slug,
                        "line": lineno,
                        "section": current_heading,
                        "text": ln.strip()[:300],
                    }
                )
    # Prefer pages with the most matches, keep document order within a page.
    counts: Dict[str, int] = {}
    for h in hits:
        counts[h["page"]] = counts.get(h["page"], 0) + 1
    hits.sort(key=lambda h: (-counts[h["page"]], h["page"], h["line"]))
    return {
        "query": query,
        "total_matches": len(hits),
        "pages_matched": sorted(counts, key=lambda p: -counts[p]),
        "results": hits[:limit],
    }


def tool_read_changelog(args: Dict[str, Any]) -> Dict[str, Any]:
    text = _split_frontmatter(read_repo_file(CHANGELOG))["_body"]
    version = args.get("version")
    if version:
        v = str(version).lstrip("v")
        sec = None
        for h in _headings(text):
            if h.lstrip("# ").startswith(f"v{v}"):
                sec = _extract_section(text, h.lstrip("# "))
                break
        if sec is None:
            raise ToolError(f"Version v{v} not found in changelog")
        return {"version": f"v{v}", "content": _truncate(sec)}
    n = int(args.get("max_versions", 3))
    versions = [h for h in _headings(text) if h.lstrip("# ").startswith("v")]
    parts = [_extract_section(text, h.lstrip("# ")) for h in versions[:n]]
    return {
        "versions_available": [h.lstrip("# ").split()[0] for h in versions],
        "content": _truncate("\n\n".join(parts)),
    }


def tool_get_toolbox_version(_: Dict[str, Any]) -> Dict[str, Any]:
    """Python package version (tit/__init__.py) and Electron app version.

    v3 keeps these in lockstep via ``dev/update/update_version.py --version X.Y.Z``;
    a mismatch here means a release is half-applied, not that one of them is right.
    """
    text = read_repo_file(PY_VERSION_FILE, max_age_s=3600)
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    version = m.group(1) if m else "unknown"

    desktop_version = None
    try:
        pkg = json.loads(read_repo_file(DESKTOP_PACKAGE_JSON, max_age_s=3600))
        desktop_version = pkg.get("version")
    except (ToolError, json.JSONDecodeError):
        pass

    base = version.split("-")[0]
    desktop_base = (desktop_version or "").split("-")[0]
    return {
        "tit_version": version,
        "tit_version_file": PY_VERSION_FILE,
        "desktop_version": desktop_version,
        "desktop_version_file": DESKTOP_PACKAGE_JSON,
        "in_lockstep": bool(desktop_version) and base == desktop_base,
        "docker_image": f"idossha/ti-toolbox:v{version}" if m else None,
        "version_sites_doc": "docs/dev/RELEASE.md (section A) — every file a version bump touches",
        "bump_command": "python3 dev/update/update_version.py --version X.Y.Z [--dry-run]",
        "source": _source_label(),
        "releases_url": f"{SITE_BASE}/releases/",
    }


def tool_read_dev_doc(args: Dict[str, Any]) -> Dict[str, Any]:
    """Read one of the nine docs/dev/*.md files — the developer source of truth."""
    name = str(args.get("name", "")).strip().removesuffix(".md")
    name = name.rsplit("/", 1)[-1]
    match = next((d for d in DEV_DOCS if d.lower() == name.lower()), None)
    if match is None:
        raise ToolError(
            f"Unknown dev doc {name!r}. docs/dev/ is capped at nine files: "
            + ", ".join(DEV_DOCS)
        )
    text = read_repo_file(f"{DEV_DOCS_DIR}/{match}.md")
    body = _split_frontmatter(text)["_body"]
    section = args.get("section")
    if section:
        body = _extract_section(body, str(section))
    return {
        "name": match,
        "path": f"{DEV_DOCS_DIR}/{match}.md",
        "headings": _headings(_split_frontmatter(text)["_body"]),
        "content": _truncate(body),
        "note": "docs/dev/ is not published; the user-facing site is docs/wiki/.",
    }


def tool_list_launch_paths(_: Dict[str, Any]) -> Dict[str, Any]:
    """The three supported ways to start v3, and the one file they all read."""
    return {
        "run_spec": {
            "path": "docker-compose.yml",
            "note": "The one run spec, at the repository root. One service, `tit`, on "
            "idossha/ti-toolbox:<ver>. Four readers: the Electron app "
            "(desktop/src/main/stack.ts -> desktop/src/shared/composeFile.ts), "
            "tit/launch.py#load_spec, loader.py/loader.sh, and dev/loader/. "
            "No FreeSurfer service and no X11 — both were dropped in v3.",
        },
        "ways_to_run": [
            {
                "who": "users, desktop app",
                "how": "Launch the packaged Electron app (desktop/). It starts the "
                "container and loads the UI over HTTP from tit.server.",
            },
            {
                "who": "users, no Electron",
                "how": "./loader.sh --project ~/datasets/000   (or: python loader.py "
                "--project ~/datasets/000). Both are bootstraps that pass every "
                "flag through to `tit launch`; loader.sh additionally finds a "
                "Python that can import tit. Flags: --project, --port, --image, "
                "--no-open, --timeout, --stop, --status, --logs [--follow].",
            },
            {
                "who": "installed package",
                "how": "tit launch --project ~/datasets/000  (tit/cli.py -> tit/launch.py; "
                "the only `tit` subcommand). Host needs CPython >= 3.11 and the "
                "docker CLI — not SimNIBS, Node or Electron.",
            },
            {
                "who": "developers",
                "how": "cd desktop && npm run dev  — container + Vite (HMR) + Electron, "
                "already connected. `npm run dev:web` is the same without Electron "
                "at http://127.0.0.1:5173/; `npm run dev:down` stops this project's "
                "container. Dev compose overrides: dev/loader/docker-compose.dev.yml, "
                "driven by dev/loader/loader_dev.{py,sh}.",
            },
        ],
        "server": {
            "origin": "http://127.0.0.1:8765 (tit/launch.py DEFAULT_PORT; TIT_SERVER_PORT)",
            "health": 'GET /api/health -> {"status": "ok"} — the only unauthenticated route',
            "auth": "Bearer token lives only in the container's env (TIT_SERVER_TOKEN); "
            "it is never written to the host. There is nothing for a user to paste.",
        },
        "first_run": "The first start pulls ~2.3 GB. If the tag does not exist "
        "(a pre-release checkout), tit launch says so and points at "
        "`container/blueprint/build.sh --tag <image>` or `--image` with a tag you have.",
    }


# --------------------------------------------------------------------------
# Source access
# --------------------------------------------------------------------------

_SOURCE_PREFIXES = (
    "tit/",
    "scripts/",
    "docs/",
    "tests/",
    "container/",
    "dev/",
    "contracts/",
    "desktop/src/",
    "desktop/tests/",
    "agent-plugin/",
)
_TEXT_EXT = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".cfg",
    ".ini",
    ".sh",
    ".csv",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".css",
}


def _check_source_path(rel: str) -> str:
    rel = _safe_rel(rel)
    top_ok = (
        rel.startswith(_SOURCE_PREFIXES)
        or (rel + "/") in _SOURCE_PREFIXES
        or rel
        in {
            "pyproject.toml",
            "version.py",
            "README.md",
            "AGENTS.md",
            "CONTRIBUTING.md",
            "SECURITY.md",
            "TODO.md",
            "docker-compose.yml",
            "loader.py",
            "loader.sh",
            "pytest.ini",
            "desktop/package.json",
        }
    )
    if not top_ok:
        raise ToolError(
            f"Path {rel!r} is outside the readable areas ({', '.join(_SOURCE_PREFIXES)})"
        )
    return rel


def tool_read_source_file(args: Dict[str, Any]) -> Dict[str, Any]:
    rel = _check_source_path(str(args.get("path", "")))
    if Path(rel).suffix.lower() not in _TEXT_EXT:
        raise ToolError(f"Refusing to read non-text file: {rel}")
    text = read_repo_file(rel)
    start = int(args.get("start_line", 1))
    end = args.get("end_line")
    lines = text.splitlines()
    if start > 1 or end:
        stop = int(end) if end else len(lines)
        seg = lines[start - 1 : stop]
        text = "\n".join(f"{start + i:5d}| {ln}" for i, ln in enumerate(seg))
    return {
        "path": rel,
        "ref": GIT_REF if REPO_ROOT is None else "local",
        "total_lines": len(lines),
        "content": _truncate(text),
    }


def tool_list_source_dir(args: Dict[str, Any]) -> Dict[str, Any]:
    rel = _check_source_path(str(args.get("path", "tit")))
    return {"path": rel, "entries": list_repo_dir(rel)}


def tool_find_symbol(args: Dict[str, Any]) -> Dict[str, Any]:
    """Locate ``def``/``class`` definitions by name across the ``tit`` package."""
    name = str(args.get("name", "")).strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ToolError("name must be a Python identifier")
    if REPO_ROOT is None:
        raise ToolError(
            "find_symbol needs a local checkout (set TI_TOOLBOX_ROOT). "
            "Without one, use list_source_dir + read_source_file."
        )
    pat = re.compile(rf"^\s*(?:async\s+def|def|class)\s+{re.escape(name)}\b")
    out = []
    for py in sorted((REPO_ROOT / "tit").rglob("*.py")):
        try:
            for i, ln in enumerate(
                py.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if pat.match(ln):
                    out.append(
                        {
                            "path": str(py.relative_to(REPO_ROOT)),
                            "line": i,
                            "text": ln.strip()[:200],
                        }
                    )
        except OSError:
            continue
    return {"name": name, "definitions": out}


def tool_search_source(args: Dict[str, Any]) -> Dict[str, Any]:
    pattern = str(args.get("pattern", ""))
    if not pattern:
        raise ToolError("pattern is required")
    if REPO_ROOT is None:
        raise ToolError("search_source needs a local checkout (set TI_TOOLBOX_ROOT)")
    sub = _check_source_path(str(args.get("path", "tit")))
    limit = int(args.get("max_results", 50))
    try:
        rx = re.compile(pattern, re.I if args.get("ignore_case", True) else 0)
    except re.error as e:
        raise ToolError(f"Invalid regex: {e}") from e
    root = REPO_ROOT / sub
    files = [root] if root.is_file() else sorted(root.rglob("*"))
    out = []
    for f in files:
        if (
            not f.is_file()
            or f.suffix.lower() not in _TEXT_EXT
            or _SKIP_DIRS.intersection(f.parts)
        ):
            continue
        try:
            for i, ln in enumerate(
                f.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if rx.search(ln):
                    out.append(
                        {
                            "path": str(f.relative_to(REPO_ROOT)),
                            "line": i,
                            "text": ln.strip()[:240],
                        }
                    )
                    if len(out) >= limit:
                        return {"pattern": pattern, "truncated": True, "results": out}
        except OSError:
            continue
    return {"pattern": pattern, "truncated": False, "results": out}


# --------------------------------------------------------------------------
# Project inspection (user's BIDS project on disk)
# --------------------------------------------------------------------------


def _ls(p: Path, *, dirs_only: bool = False) -> List[str]:
    if not p.is_dir():
        return []
    return sorted(
        e.name
        for e in p.iterdir()
        if not e.name.startswith(".") and (e.is_dir() or not dirs_only)
    )


def tool_inspect_project(args: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(str(args.get("project_root", ""))).expanduser()
    if not root.is_dir():
        raise ToolError(f"project_root is not a directory: {root}")
    subject_filter = args.get("subject")
    deriv = root / "derivatives"
    simnibs = deriv / "SimNIBS"

    raw_subjects = sorted(
        d.name[4:] for d in root.iterdir() if d.is_dir() and d.name.startswith("sub-")
    )
    simnibs_subjects = (
        sorted(
            d.name[4:]
            for d in simnibs.iterdir()
            if d.is_dir() and d.name.startswith("sub-")
        )
        if simnibs.is_dir()
        else []
    )
    all_ids = sorted(set(raw_subjects) | set(simnibs_subjects))
    if subject_filter:
        all_ids = [s for s in all_ids if s == str(subject_filter)]

    subjects = []
    for sid in all_ids:
        sub = simnibs / f"sub-{sid}"
        anat = root / f"sub-{sid}" / "anat"
        m2m = sub / f"m2m_{sid}"
        sims = sub / "Simulations"
        entry: Dict[str, Any] = {
            "id": sid,
            "anat_files": _ls(anat),
            "has_m2m": m2m.is_dir(),
            "has_head_mesh": (m2m / f"{sid}.msh").is_file(),
            "freesurfer_recon": (
                deriv / "freesurfer" / f"sub-{sid}" / "mri" / "aparc+aseg.mgz"
            ).is_file(),
            "qsirecon": (deriv / "qsirecon" / f"sub-{sid}").is_dir(),
            "leadfields": _ls(sub / "leadfields"),
            "freehand_configs": [
                f for f in _ls(m2m / "stim_configs") if f.endswith(".json")
            ],
            "simulations": {},
            "flex_search_runs": _ls(sub / "flex-search", dirs_only=True),
            "ex_search_runs": _ls(sub / "ex-search", dirs_only=True),
            "mex_search_runs": _ls(sub / "m-ex-search", dirs_only=True),
        }
        for sim in _ls(sims, dirs_only=True):
            sd = sims / sim
            entry["simulations"][sim] = {
                "contents": _ls(sd),
                "has_ti_dir": (sd / "TI").is_dir(),
                "mesh_files": [
                    f for f in _ls(sd / "TI" / "mesh") if f.endswith(".msh")
                ],
                "nifti_files": [
                    f
                    for f in _ls(sd / "TI" / "niftis")
                    if f.endswith((".nii", ".nii.gz"))
                ],
                "analyses": {
                    space: _ls(sd / "Analyses" / space, dirs_only=True)
                    for space in ("Mesh", "Voxel")
                    if (sd / "Analyses" / space).is_dir()
                },
                "has_fsaverage": (sd / "fsaverage").is_dir(),
            }
        subjects.append(entry)

    tt = deriv / "ti-toolbox"
    code = root / "code" / "ti-toolbox"
    cfg = code / "config"
    jobs = code / "jobs"

    # The v3 job store: one directory per job, each with status.json.
    job_dirs = _ls(jobs, dirs_only=True)
    job_summary: Dict[str, int] = {}
    recent_failures: List[Dict[str, Any]] = []
    for jid in job_dirs:
        sp = jobs / jid / "status.json"
        if not sp.is_file():
            continue
        try:
            st = json.loads(sp.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        state = str(st.get("state", "unknown"))
        job_summary[state] = job_summary.get(state, 0) + 1
        err = st.get("error") or {}
        if state in ("failed", "cancelled", "lost", "skipped") and err:
            recent_failures.append(
                {
                    "id": st.get("id", jid),
                    "kind": st.get("kind"),
                    "state": state,
                    "error_type": err.get("type"),
                    "message": err.get("message"),
                    "subject_ids": st.get("subject_ids", []),
                    "finished_at": st.get("finished_at"),
                }
            )
    recent_failures.sort(key=lambda r: str(r.get("finished_at") or ""), reverse=True)

    return {
        "project_root": str(root),
        "looks_like_ti_project": simnibs.is_dir() or code.is_dir(),
        "subjects": subjects,
        "sourcedata_subjects": _ls(root / "sourcedata", dirs_only=True),
        "config_files": _ls(cfg),
        "reports": _ls(tt / "reports"),
        "stats_analyses": {
            t: _ls(tt / "stats" / t, dirs_only=True)
            for t in _ls(tt / "stats", dirs_only=True)
        },
        "code_ti_toolbox": {
            "jobs_count": len(job_dirs),
            "jobs_by_state": job_summary,
            "recent_failures": recent_failures[:10],
            "notebooks": _ls(code / "notebooks"),
            "notebook_examples": _ls(code / "notebooks" / "examples"),
            "pipelines": [f for f in _ls(code / "pipelines") if f.endswith(".json")],
            "viewer_scenes": [
                f for f in _ls(code / "viewer") if f.endswith(".tetravox.json")
            ],
        },
        "notes": [
            "'Lost (server restarted mid-run)' (error.type 'lost') means the server "
            "restarted while the job was running — the job is over and will not resume. "
            "POST /api/jobs/{id}/force is the escape hatch for a job stuck at running.",
            "A flex/ex/mex run directory without its completion manifest (flex_meta.json, "
            "run_config.json) is deliberately ignored by the catalog, so a cancelled or "
            "in-progress run never appears as a result.",
        ],
        "layout_reference": f"{SITE_BASE}/wiki/overview/",
    }


def tool_read_project_config(args: Dict[str, Any]) -> Dict[str, Any]:
    """Read one JSON document from a project's v3 config locations.

    ``where`` selects the directory:

    * ``config``       ``code/ti-toolbox/config/``  (default; montage_list.json, ...)
    * ``pipelines``    ``code/ti-toolbox/pipelines/``
    * ``viewer``       ``code/ti-toolbox/viewer/``  (``<kind>.tetravox.json``)
    * ``stim_configs`` ``derivatives/SimNIBS/sub-<id>/m2m_<id>/stim_configs/``
      (free-hand electrode placements; requires ``subject``).  On-disk shape:
      ``{"name": ..., "type": "U"|"M", "electrode_positions": {label: [x, y, z]}}``
      in subject-RAS millimetres.
    """
    root = Path(str(args.get("project_root", ""))).expanduser()
    name = str(args.get("name", "")).strip()
    where = str(args.get("where", "config")).strip() or "config"
    if not re.fullmatch(r"[A-Za-z0-9_\-]+(\.tetravox)?\.json", name):
        raise ToolError("name must be a plain .json filename")

    code = root / "code" / "ti-toolbox"
    if where == "config":
        directory = code / "config"
    elif where == "pipelines":
        directory = code / "pipelines"
    elif where == "viewer":
        directory = code / "viewer"
    elif where == "stim_configs":
        sid = str(args.get("subject", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9_\-]+", sid):
            raise ToolError(
                "where='stim_configs' requires a `subject` id (without 'sub-')"
            )
        directory = (
            root
            / "derivatives"
            / "SimNIBS"
            / f"sub-{sid}"
            / f"m2m_{sid}"
            / "stim_configs"
        )
    else:
        raise ToolError("where must be one of: config, pipelines, viewer, stim_configs")

    p = directory / name
    if not p.is_file():
        raise ToolError(f"Not found: {p}. Available: {_ls(directory)}")
    text = p.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ToolError(f"{name} is not valid JSON: {e}") from e
    return {
        "path": str(p),
        "content": data if len(text) < MAX_CHARS else _truncate(text),
    }


def tool_get_quick_facts(_: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": "TI-Toolbox (Temporal Interference Toolbox)",
        "package": "tit  (from tit.sim import ...)",
        "docs": SITE_BASE,
        "wiki": f"{SITE_BASE}/wiki/",
        "api_reference": f"{SITE_BASE}/api/",
        "troubleshooting": f"{SITE_BASE}/wiki/troubleshooting/  (read_wiki_page('troubleshooting') -- verified archive of known errors and fixes; check it first for any error)",
        "repo": f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}",
        "architecture_v3": {
            "summary": "Three pieces. (1) An Electron desktop app on the host, `desktop/` "
            "(Electron main/preload + React + TypeScript strict + Vite) — a shell that "
            "starts the container and loads the UI over HTTP from it. (2) A FastAPI job "
            "server, `tit.server`, inside the single Docker image idossha/ti-toolbox — it "
            "owns the job model (queue, dependencies, locks, budget, live events, "
            "cancellation) and serves the React bundle at `/`. (3) The `tit` Python "
            "package — the only place scientific logic lives, still usable from scripts "
            "and notebooks.",
            "no_pyqt": "The PyQt5 GUI (tit/gui/) was DELETED in v3.0.0. `tit` imports no Qt. "
            "The core image ships no X11 and no FreeSurfer. Never cite tit/gui/**.",
            "wire_contract": "contracts/openapi.yaml (frozen interface — a change needs "
            "the contract edit and a DECISIONS.md entry in the same commit)",
            "origin": "http://127.0.0.1:8765 — HTTP + WebSockets (/ws/system, /ws/jobs, "
            "/ws/tetravox, /ws/kernels/{id}). Bearer token lives only in the container's env.",
        },
        "runtime": "Everything scientific runs inside the Docker image idossha/ti-toolbox "
        "(SimNIBS 4.x, Python 3.11, numpy 1.26; no FSL, no ANTs, no X11, no FreeSurfer). "
        "Use `simnibs_python`, not the host python. Project mounted at /mnt/<project>/.",
        "rail_pages": "Ten rows, ten digits — the rail counts from Cmd+0: Overview (0), "
        "Pre-processing (1), Simulator (2), Optimizer (3), Analyzer (4), Pipeline (5), "
        "Notebooks (6), Results (7), Viewer (8), Jobs (9). System, Settings and Help are "
        "pinned below a spacer and take no digit; System is the full-height monitor "
        "(one rolling five-minute CPU+memory timeline, Docker health, process table) "
        "reading the same /ws/system snapshot as the jobs panel's 260px Host tab, so the "
        "two cannot disagree. Cmd+, is Settings' only chord. Cmd+K palette, Cmd+J jobs "
        "panel, Cmd+Enter primary action.",
        "viewer_menu": "The Viewer's Menu is a COMPOSITION TREE, not a form: Subject and "
        "Space above it, then Anatomy / Simulations / Analyses branches of rows you tick. "
        "There is no view-kind or simulation selector (removed 2026-09-07). Anatomy is "
        "grouped by what a file IS — volume, label-volume, surface, mesh — per "
        "tit/catalog.py::classify_view_file; a mesh is a tetrahedral FEM (.msh) and a "
        "surface is a triangular sheet (.gii and friends), and the two are never conflated. "
        "A deep link (/viewer?kind=&subject=&path=&open=1) pre-fills the tree, and with "
        "open=1 also builds and shows the scene.",
        "subsystems": {
            "tit/jobs": "The job engine: kinds.py (kind -> module), scheduler.py (a pure "
            "evaluate() per queued job), manager.py, registry.py (the on-disk store), "
            "eta.py (estimates, always labelled as such), locks, costs, events.",
            "tit/pipeline": "DAG documents (document/plan/validate/notebook). A pipeline "
            "introduces no job kind and a pipeline run is ONE job group.",
            "tit/server/kernels.py": "Jupyter kernels driven in-process inside the "
            "container; WS /ws/kernels/{id}. Max 2 kernels, 30 min idle. There is no "
            "sandbox — a kernel runs arbitrary user code as the container's user.",
            "tit/server/notebooks.py": "The .ipynb on disk is the document; open+save must "
            "produce an empty git diff.",
            "tit/scene": "Builds skin / grey-matter / electrode / region-label scene "
            "payloads from a subject's real files, plus the packaged subject-free guide.",
            "tit/tetravox": "The Tetravox Embed (WebGL2 + WASM viewer) install/update "
            "channel. Coupling is a PROTOCOL RANGE, never a version; ask by feature name.",
            "tit/viewspec.py": "build_view(kind, ...) is a pure function returning a "
            "ViewSpec. The server resolves what to show; the client renders it.",
            "tit/catalog.py": "Subject/simulation discovery for the UI, built only on "
            "PathManager plus per-domain helpers. GET /api/catalog/overview is the "
            "Overview page's single read.",
            "tit/jobs/eta.py": "minutes = (fixed + per_unit * units) * mesh_scale * "
            "system.factor / parallel. EMULATION_FACTOR = 3.0 (amd64 under Rosetta).",
            "tit/launch.py + tit/cli.py": "`tit launch` — the installed, no-Electron way to run.",
        },
        "job_kinds": [
            "pre",
            "sim",
            "flex",
            "flex_adaptive",
            "flex_pareto",
            "ex",
            "mex",
            "leadfield",
            "analyzer",
            "stats",
            "source",
            "blender",
            "nifti_average",
            "nilearn",
            "tools",
            "project_init",
            "report",
        ],
        "job_states": [
            "queued",
            "running",
            "succeeded",
            "failed",
            "cancelled",
            "skipped",
            "lost",
        ],
        "failure_taxonomy": {
            "preflight": "Preflight check failed",
            "lock_wait": "Waiting on a lock",
            "budget_wait": "Waiting on the resource budget",
            "runner_failed": "Runner failed",
            "oom_suspected": "Likely out of memory",
            "cancelled": "Cancelled",
            "skipped": "Skipped",
            "lost": "Lost (server restarted mid-run)",
            "docker_unavailable": "Docker is unavailable",
            "kind_error": "Invalid job configuration",
        },
        "entry_points": {
            "desktop_app": "the packaged Electron app (desktop/)",
            "browser_no_electron": "./loader.sh --project <dir>  |  python loader.py "
            "--project <dir>  |  tit launch --project <dir>   (all three are the same "
            "thing: bootstraps over tit/launch.py, which owns the run spec)",
            "run_spec": "docker-compose.yml at the repository root — one service, `tit`. "
            "Dev overrides in dev/loader/. Call list_launch_paths for the full picture.",
            "dev_loop": "cd desktop && npm run dev   (container + Vite + Electron)",
            "python_api": "from tit.sim/opt/analyzer/stats/pre import ...",
            "json_config_runners": [
                "simnibs_python -m tit.sim config.json",
                "simnibs_python -m tit.opt.flex config.json",
                "simnibs_python -m tit.opt.ex config.json",
                "simnibs_python -m tit.opt.mex config.json",
                "simnibs_python -m tit.analyzer config.json",
                "simnibs_python -m tit.stats config.json",
                "simnibs_python -m tit.pre config.json",
                "simnibs_python -m tit.source config.json",
            ],
        },
        "project_layout": {
            "raw": "sub-<id>/anat/*.nii.gz, sourcedata/ (DICOM)",
            "head_model": "derivatives/SimNIBS/sub-<id>/m2m_<id>/",
            "freehand_electrodes": "derivatives/SimNIBS/sub-<id>/m2m_<id>/stim_configs/*.json "
            '— {"name", "type": "U"|"M", "electrode_positions": {label: [x, y, z]}} '
            "in subject-RAS millimetres",
            "simulations": "derivatives/SimNIBS/sub-<id>/Simulations/<montage>/TI/{mesh,niftis}",
            "optimization": "derivatives/SimNIBS/sub-<id>/{flex-search,ex-search,m-ex-search}/ "
            "— the run name IS the directory; a second run under the same name overwrites it",
            "leadfields": "derivatives/SimNIBS/sub-<id>/leadfields/",
            "reports": "derivatives/ti-toolbox/reports/",
            "stats": "derivatives/ti-toolbox/stats/<type>/<name>/",
            "config": "code/ti-toolbox/config/*.json (montage_list.json etc.)",
            "jobs_store": "code/ti-toolbox/jobs/<id>/{spec.json,status.json,events.jsonl,"
            "stdout.log} — inside the project so notebooks and a restarted server see the "
            "same jobs; .bidsignore carries the line code/ti-toolbox/jobs/",
            "notebooks": "code/ti-toolbox/notebooks/ (examples/ is the only subdirectory; "
            "examples/getting-started.ipynb is seeded on first listing)",
            "pipelines": "code/ti-toolbox/pipelines/<name>.json, run outputs under "
            "pipelines/runs/<pipeline>/<node>.<port>.json",
            "viewer": "code/ti-toolbox/viewer/<kind>.tetravox.json (suffix .tetravox.json, "
            "not .json)",
        },
        "science_rules": {
            "pair_count": "tit.constants.is_valid_pair_count — an even number of electrode "
            "pairs, at least 2. 2 pairs = TI, 4 or more (even) = mTI. Odd counts leave a "
            "channel with nothing to beat against; a single pair is tACS, not TI.",
            "envelope_api": "tit.calc exposes exactly three functions: "
            "get_TI_vectors(fields, psi=None), get_TI_avg(fields, psi=None), "
            "get_TI_dir(fields, directions, psi=None). `fields` is a LIST of 2K arrays "
            "paired positionally. get_nTI_vectors, get_mTI_vectors/get_mTI_dir, "
            "get_magnitude_am and the channels= parameter were all removed in v2.5.0.",
            "carrier_model": "Positional wiring: one field is one carrier "
            "(tit.fields.hf_peak(*fields) / hf_sar(*fields)). There is no montage.channels.",
            "exposure_metrics": "Quasi-static: E is a phasor AMPLITUDE (V/m, peak, not RMS), "
            "no time axis; every exposure quantity is a worst case over unknown relative "
            "phases. Per Cassara et al. 2025 Part II p.8, fields at identical frequencies "
            "superpose COHERENTLY (vector sum within a channel) and different frequencies "
            "INCOHERENTLY (SAR addition across carriers). hf_sar = sum_c |E_c|^2 in (V/m)^2 "
            "with no 1/2; calibrated SAR = (sigma/2rho)*hf_sar; RMS carrier field = "
            "sqrt(hf_sar/2) — the 1/2 appears once, in the calibration. "
            "hf_peak = max over signs |sum_c s_c E_c|, exact for <= 8 carriers "
            "(EXACT_SIGN_ENUM_MAX_FIELDS), a lower bound above that.",
            "integrity_rule": "Any change to tit/stats, tit/analyzer, tit/calc, tit/fields "
            "or tit/sim needs (1) a test in tests/numerical/ against the REAL libraries, "
            "asserting the claim independently rather than retyping the implementation, and "
            "(2) if any published result moves, an entry in docs/dev/SCIENTIFIC-CORRECTIONS.md "
            "saying what was wrong, which versions, which outputs move and by how much, how a "
            "user spots an affected result, and whether to re-run or rescale.",
        },
        "gate_commands": [
            "cd desktop && npm run typecheck && npm run lint && npx vitest run",
            "python3 -m pytest tests/ -q        # repo root; heavy libs mocked, numpy real",
            "docker exec -w /ti-toolbox <container> simnibs_python -m pytest tests/numerical -q",
            "python3 dev/route_import_guard.py && python3 dev/contracts_check.py",
            "cd desktop && TIT_E2E_OFFSCREEN=1 npm run e2e:quiet",
            "cd desktop && npm run build        # LAST, always",
        ],
        "gate_note": "Report the numbers, not 'green'. A 200 from /api/health is not "
        "evidence the new code loaded. Never run two FEM simulations in parallel under "
        "emulation. One Playwright run at a time (/tmp/tit-e2e.lock).",
        "docs_of_record": "docs/dev/ is the single source of truth for developers and is "
        "capped at NINE files: README, ARCHITECTURE, DECISIONS, CONTRIBUTING, DESIGN, "
        "HISTORY, BENCHMARKS, SCIENTIFIC-CORRECTIONS, RELEASE. Read them with read_dev_doc. "
        "Nothing in docs/dev/ is published; the user-facing site is docs/wiki/. There are no "
        "per-lane note files anywhere in the repository and none may be added.",
        "source_status": _source_label(),
        "tools_hint": "For any error message read_wiki_page('troubleshooting') first. Use "
        "search_wiki/read_wiki_page for user-facing how-to questions, read_dev_doc for how "
        "the system is built and verified, read_source_file/find_symbol for API details, and "
        "inspect_project for a user's data.",
    }


def _source_label() -> str:
    if REPO_ROOT is not None:
        return f"local checkout at {REPO_ROOT}"
    return f"GitHub {GITHUB_OWNER}/{GITHUB_REPO}@{GIT_REF} (cached in {CACHE_DIR})"


# --------------------------------------------------------------------------
# Tool registry
# --------------------------------------------------------------------------

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_quick_facts",
        "description": "Orientation for agents new to TI-Toolbox: what it is, how it runs (Docker/simnibs_python), "
        "entry points, on-disk project layout, and which tool to use next. Call this first.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "handler": tool_get_quick_facts,
    },
    {
        "name": "list_wiki_pages",
        "description": "List all TI-Toolbox wiki pages (slug, title, URL, one-line summary).",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "handler": tool_list_wiki_pages,
    },
    {
        "name": "read_wiki_page",
        "description": "Read a TI-Toolbox wiki page as Markdown, optionally only one section by heading text. "
        "The wiki is the USER-facing site. Slugs: overview, desktop-app, jobs, notebooks, "
        "pipelines, results, simulator, flex-search, ex-search, analyzer, scripting, "
        "pre-processing, diffusion-processing, atlases, reports, troubleshooting, "
        "visualizers, logging, extension, agent-plugin, ai-assistant, example-notebook, ... "
        "There is no 'mti' page any more — mTI is a section of 'simulator'. "
        "Call list_wiki_pages rather than guessing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "string",
                    "description": "Page slug, e.g. 'flex-search'",
                },
                "section": {
                    "type": "string",
                    "description": "Optional heading text to return only that section",
                },
            },
            "required": ["page"],
            "additionalProperties": False,
        },
        "handler": tool_read_wiki_page,
    },
    {
        "name": "search_wiki",
        "description": "Full-text search across all wiki pages. All whitespace-separated terms must appear on the same line.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {
                    "type": "integer",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 200,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "handler": tool_search_wiki,
    },
    {
        "name": "read_changelog",
        "description": "Read the release changelog: the latest N versions, or one specific version (e.g. '2.4.0').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "version": {"type": "string"},
                "max_versions": {
                    "type": "integer",
                    "default": 3,
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "additionalProperties": False,
        },
        "handler": tool_read_changelog,
    },
    {
        "name": "get_toolbox_version",
        "description": "Current versions: the tit package (tit/__init__.py) and the Electron "
        "desktop app (desktop/package.json), whether they are in lockstep, and the matching "
        "Docker image tag. v3 keeps every version site in lockstep via "
        "dev/update/update_version.py.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "handler": tool_get_toolbox_version,
    },
    {
        "name": "read_dev_doc",
        "description": "Read one of the nine docs/dev/*.md files — the DEVELOPER source of "
        "truth, not published on the site. Names: README (the map and reading order), "
        "ARCHITECTURE (how it is built, plus the science pipelines and DWI topology), "
        "DECISIONS (the numbered ADR log), CONTRIBUTING (dev loop, the gate, the smoke "
        "harness, the science-integrity rule), DESIGN (the UI contract and per-page "
        "acceptance numbers), HISTORY (what happened, per program), BENCHMARKS (every "
        "measured number, once), SCIENTIFIC-CORRECTIONS (what v2.x got numerically wrong "
        "and whether to re-run or rescale), RELEASE (version sites and what is still open). "
        "Optionally return one section by heading text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "e.g. 'ARCHITECTURE' or 'SCIENTIFIC-CORRECTIONS'",
                },
                "section": {
                    "type": "string",
                    "description": "Optional heading text to return only that section",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        "handler": tool_read_dev_doc,
    },
    {
        "name": "list_launch_paths",
        "description": "How TI-Toolbox v3 is started: the one run spec (root "
        "docker-compose.yml) and its four readers, the desktop app, loader.py / loader.sh, "
        "`tit launch`, the developer's `npm run dev`, the server origin and health route, "
        "and what the first run prints when the image tag does not exist.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "handler": tool_list_launch_paths,
    },
    {
        "name": "list_source_dir",
        "description": "List a directory of the TI-Toolbox repo (default 'tit'). Readable "
        "roots: tit/, scripts/, docs/, tests/, container/, dev/, contracts/, desktop/src/, "
        "desktop/tests/, agent-plugin/. node_modules and build output are "
        "never listed.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "default": "tit"}},
            "additionalProperties": False,
        },
        "handler": tool_list_source_dir,
    },
    {
        "name": "read_source_file",
        "description": "Read a text file from the TI-Toolbox repo, e.g. 'tit/sim/config.py' or 'scripts/flex.py'. "
        "Optional line range. Use to check dataclass fields, defaults and docstrings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer", "minimum": 1},
                "end_line": {"type": "integer", "minimum": 1},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        "handler": tool_read_source_file,
    },
    {
        "name": "find_symbol",
        "description": "Find where a function or class is defined in the tit package (local checkout only).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "e.g. 'FlexConfig' or 'run_simulation'",
                }
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        "handler": tool_find_symbol,
    },
    {
        "name": "search_source",
        "description": "Regex search over repo text files (local checkout only). Default scope 'tit'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string", "default": "tit"},
                "ignore_case": {"type": "boolean", "default": True},
                "max_results": {
                    "type": "integer",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 500,
                },
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
        "handler": tool_search_source,
    },
    {
        "name": "inspect_project",
        "description": "Inspect a user's TI-Toolbox/BIDS project directory: subjects, head "
        "models (m2m), FreeSurfer, leadfields, free-hand stim_configs, simulations "
        "(mesh/NIfTI outputs, analyses), flex/ex/mex search runs, reports, stats, and the v3 "
        "code/ti-toolbox tree — the job store (counts by state plus recent failures with "
        "their error.type), notebooks, pipelines and viewer scenes. Read-only; use it to "
        "answer 'what do I have / why is X missing / why did my job fail'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {
                    "type": "string",
                    "description": "Absolute path to the project directory",
                },
                "subject": {
                    "type": "string",
                    "description": "Optional subject id (without 'sub-') to restrict output",
                },
            },
            "required": ["project_root"],
            "additionalProperties": False,
        },
        "handler": tool_inspect_project,
    },
    {
        "name": "read_project_config",
        "description": "Read one JSON document from a project's v3 config locations: "
        "code/ti-toolbox/config/ (default — montage_list.json etc.), "
        "code/ti-toolbox/pipelines/, code/ti-toolbox/viewer/ (<kind>.tetravox.json), or a "
        "subject's m2m_<id>/stim_configs/ free-hand electrode placements "
        "({name, type: 'U'|'M', electrode_positions: {label: [x,y,z]}} in subject-RAS mm).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {"type": "string"},
                "name": {
                    "type": "string",
                    "description": "Filename, e.g. 'montage_list.json'",
                },
                "where": {
                    "type": "string",
                    "enum": ["config", "pipelines", "viewer", "stim_configs"],
                    "default": "config",
                },
                "subject": {
                    "type": "string",
                    "description": "Subject id without 'sub-'; required for where='stim_configs'",
                },
            },
            "required": ["project_root", "name"],
            "additionalProperties": False,
        },
        "handler": tool_read_project_config,
    },
]

_HANDLERS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    t["name"]: t["handler"] for t in TOOLS
}


def _public_tools() -> List[Dict[str, Any]]:
    return [{k: v for k, v in t.items() if k != "handler"} for t in TOOLS]


# --------------------------------------------------------------------------
# JSON-RPC / MCP plumbing
# --------------------------------------------------------------------------


def _result(id_: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _error(id_: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def handle(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = msg.get("method")
    id_ = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        return _result(
            id_,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "Read-only knowledge server for TI-Toolbox (temporal interference stimulation toolbox). "
                    "Start with get_quick_facts. v3 is an Electron desktop app plus a FastAPI server "
                    "(tit.server) in the Docker image plus the shared `tit` science core; the PyQt GUI "
                    "(tit/gui) was deleted, so never cite it. Use search_wiki/read_wiki_page for "
                    "user-facing questions, read_dev_doc for how the system is built and verified, "
                    "read_source_file/find_symbol for exact API signatures, list_launch_paths for how to "
                    "run it, and inspect_project on the user's project directory before diagnosing "
                    "missing outputs."
                ),
            },
        )
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return _result(id_, {})
    if method == "tools/list":
        return _result(id_, {"tools": _public_tools()})
    if method == "tools/call":
        name = params.get("name")
        fn = _HANDLERS.get(name)
        if fn is None:
            return _error(id_, -32602, f"Unknown tool: {name}")
        try:
            out = fn(params.get("arguments") or {})
            return _result(
                id_,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(out, indent=2, ensure_ascii=False),
                        }
                    ],
                    "isError": False,
                },
            )
        except ToolError as e:
            return _result(
                id_, {"content": [{"type": "text", "text": str(e)}], "isError": True}
            )
        except Exception as e:  # noqa: BLE001 - report, never crash the server
            return _result(
                id_,
                {
                    "content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}],
                    "isError": True,
                },
            )
    if id_ is None:
        return None  # unknown notification
    return _error(id_, -32601, f"Method not found: {method}")


def serve() -> None:
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            resp = _error(None, -32700, "Parse error")
        else:
            resp = handle(msg)
        if resp is not None:
            stdout.write((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
            stdout.flush()


def _call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    r = handle(
        {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        }
    )
    return r["result"]  # type: ignore[index]


def selftest() -> int:
    """Call every registered tool once and report pass/fail per tool.

    Tools that need a local checkout are skipped (not failed) when there is none;
    ``inspect_project`` / ``read_project_config`` run against a throwaway project
    tree so they exercise real code without needing the user's data.
    """
    import tempfile

    print(f"repo root: {REPO_ROOT or '(none -> GitHub)'}")
    listed = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = [t["name"] for t in listed["result"]["tools"]]  # type: ignore[index]
    print(f"tools ({len(names)}): {', '.join(names)}\n")

    tmp = Path(tempfile.mkdtemp(prefix="ti-mcp-selftest-"))
    (tmp / "sub-101" / "anat").mkdir(parents=True)
    (tmp / "code" / "ti-toolbox" / "config").mkdir(parents=True)
    (tmp / "code" / "ti-toolbox" / "config" / "montage_list.json").write_text(
        '{"nets": {}}', encoding="utf-8"
    )
    m2m = tmp / "derivatives" / "SimNIBS" / "sub-101" / "m2m_101" / "stim_configs"
    m2m.mkdir(parents=True)
    (m2m / "demo.json").write_text(
        '{"name": "demo", "type": "U", "electrode_positions": {"E1+": [1, 2, 3]}}',
        encoding="utf-8",
    )
    jobdir = tmp / "code" / "ti-toolbox" / "jobs" / "j1"
    jobdir.mkdir(parents=True)
    (jobdir / "status.json").write_text(
        '{"id": "j1", "kind": "sim", "state": "failed", "subject_ids": ["101"],'
        ' "error": {"type": "lost", "message": "server restarted"}}',
        encoding="utf-8",
    )

    cases: List[tuple] = [
        ("get_quick_facts", {}),
        ("list_wiki_pages", {}),
        ("read_wiki_page", {"page": "overview"}),
        ("search_wiki", {"query": "leadfield", "max_results": 3}),
        ("read_changelog", {"max_versions": 1}),
        ("get_toolbox_version", {}),
        ("read_dev_doc", {"name": "ARCHITECTURE"}),
        ("list_launch_paths", {}),
        ("list_source_dir", {"path": "tit"}),
        ("read_source_file", {"path": "tit/calc.py", "start_line": 1, "end_line": 20}),
        ("find_symbol", {"name": "get_TI_vectors"}),
        ("search_source", {"pattern": "def hf_sar", "path": "tit", "max_results": 3}),
        ("inspect_project", {"project_root": str(tmp)}),
        (
            "read_project_config",
            {"project_root": str(tmp), "name": "montage_list.json"},
        ),
        (
            "read_project_config",
            {
                "project_root": str(tmp),
                "name": "demo.json",
                "where": "stim_configs",
                "subject": "101",
            },
        ),
    ]

    failures = 0
    for name, args in cases:
        res = _call(name, args)
        text = res["content"][0]["text"]
        if res.get("isError"):
            if REPO_ROOT is None and "needs a local checkout" in text:
                print(f"SKIP  {name}: {text.splitlines()[0]}")
                continue
            failures += 1
            print(f"FAIL  {name}: {text.splitlines()[0]}")
        else:
            print(f"ok    {name}  ({len(text)} chars)")

    # Every registered tool must appear in the matrix above.
    covered = {name for name, _ in cases}
    missing = [n for n in names if n not in covered]
    if missing:
        failures += 1
        print(f"FAIL  self-test does not cover: {', '.join(missing)}")

    print("\nselftest:", "PASSED" if failures == 0 else f"{failures} FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    serve()
