#!/usr/bin/env python3
"""TI-Toolbox MCP server.

Gives coding agents (Claude Code, Codex, any MCP client) read-only access to
TI-Toolbox knowledge:

* the wiki (``docs/wiki/*.md``) and changelog -- from a local checkout when one
  is available, otherwise fetched from GitHub and cached on disk;
* source files of the ``tit`` package (same local/remote rule);
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
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2025-06-18"

GITHUB_OWNER = "idossha"
GITHUB_REPO = "TI-Toolbox"
RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}"
API_BASE = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
SITE_BASE = "https://idossha.github.io/TI-Toolbox"

WIKI_DIR = "docs/wiki"
CHANGELOG = "docs/releases/changelog.md"
VERSION_FILE = "version.py"

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
            if not e.name.startswith(".") and e.name != "__pycache__"
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
        if not e["name"].startswith(".") and e["name"] != "__pycache__"
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
    text = read_repo_file(VERSION_FILE, max_age_s=3600)
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return {
        "version": m.group(1) if m else "unknown",
        "source": _source_label(),
        "docker_image": f"idossha/simnibs:v{m.group(1)}" if m else None,
        "releases_url": f"{SITE_BASE}/releases/",
    }


# --------------------------------------------------------------------------
# Source access
# --------------------------------------------------------------------------

_SOURCE_PREFIXES = ("tit/", "scripts/", "docs/", "tests/", "container/", "dev/")
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
            "CLAUDE.md",
            "CONTRIBUTING.md",
            "docker-compose.yml",
            "loader.py",
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
            or "__pycache__" in f.parts
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
    cfg = root / "code" / "ti-toolbox" / "config"
    return {
        "project_root": str(root),
        "looks_like_ti_project": simnibs.is_dir() or cfg.is_dir(),
        "subjects": subjects,
        "sourcedata_subjects": _ls(root / "sourcedata", dirs_only=True),
        "config_files": _ls(cfg),
        "reports": _ls(tt / "reports"),
        "stats_analyses": {
            t: _ls(tt / "stats" / t, dirs_only=True)
            for t in _ls(tt / "stats", dirs_only=True)
        },
        "layout_reference": f"{SITE_BASE}/wiki/pre-processing/",
    }


def tool_read_project_config(args: Dict[str, Any]) -> Dict[str, Any]:
    """Read one of the JSON config files under code/ti-toolbox/config/ (e.g. montage_list.json)."""
    root = Path(str(args.get("project_root", ""))).expanduser()
    name = str(args.get("name", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-]+\.json", name):
        raise ToolError("name must be a plain .json filename")
    p = root / "code" / "ti-toolbox" / "config" / name
    if not p.is_file():
        raise ToolError(f"Not found: {p}. Available: {_ls(p.parent)}")
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
        "runtime": "Everything runs inside the Docker container idossha/simnibs (SimNIBS 4.x, Python 3.11). "
        "Use `simnibs_python`, not the host python. Project mounted at /mnt/<project>/.",
        "entry_points": {
            "gui": "launched by the Electron desktop app or loader.py",
            "python_api": "from tit.sim/opt/analyzer/stats/pre import ...",
            "json_config_runners": [
                "simnibs_python -m tit.sim config.json",
                "simnibs_python -m tit.opt.flex config.json",
                "simnibs_python -m tit.opt.ex config.json",
                "simnibs_python -m tit.opt.mex config.json",
                "simnibs_python -m tit.analyzer config.json",
                "simnibs_python -m tit.stats config.json",
                "simnibs_python -m tit.pre config.json",
            ],
        },
        "project_layout": {
            "raw": "sub-<id>/anat/*.nii.gz, sourcedata/ (DICOM)",
            "head_model": "derivatives/SimNIBS/sub-<id>/m2m_<id>/",
            "simulations": "derivatives/SimNIBS/sub-<id>/Simulations/<montage>/TI/{mesh,niftis}",
            "optimization": "derivatives/SimNIBS/sub-<id>/{flex-search,ex-search,m-ex-search}/",
            "leadfields": "derivatives/SimNIBS/sub-<id>/leadfields/",
            "reports": "derivatives/ti-toolbox/reports/",
            "stats": "derivatives/ti-toolbox/stats/<type>/<name>/",
            "config": "code/ti-toolbox/config/*.json (montage_list.json etc.)",
        },
        "source_status": _source_label(),
        "tools_hint": "For any error message read_wiki_page('troubleshooting') first. Use search_wiki/read_wiki_page for how-to questions, "
        "read_source_file/find_symbol for API details, inspect_project for a user's data.",
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
        "Slugs: simulator, flex-search, ex-search, mti, analyzer, scripting, pre-processing, "
        "diffusion-processing, atlases, reports, logging, gui, extension, ...",
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
        "description": "Current TI-Toolbox version (from version.py) and matching Docker image tag.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "handler": tool_get_toolbox_version,
    },
    {
        "name": "list_source_dir",
        "description": "List a directory of the TI-Toolbox repo (default 'tit'). Readable roots: tit/, scripts/, docs/, tests/, container/, dev/.",
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
        "description": "Inspect a user's TI-Toolbox/BIDS project directory: subjects, head models (m2m), FreeSurfer, "
        "leadfields, simulations (mesh/NIfTI outputs, analyses), flex/ex/mex search runs, reports, stats. "
        "Read-only; use it to answer 'what do I have / why is X missing'.",
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
        "description": "Read a JSON config from <project>/code/ti-toolbox/config/, e.g. montage_list.json.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {"type": "string"},
                "name": {
                    "type": "string",
                    "description": "Filename, e.g. 'montage_list.json'",
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
                    "Start with get_quick_facts. Use search_wiki/read_wiki_page for usage questions, "
                    "read_source_file/find_symbol for exact API signatures, and inspect_project on the user's "
                    "project directory before diagnosing missing outputs."
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


def selftest() -> int:
    print(f"repo root: {REPO_ROOT or '(none -> GitHub)'}")
    r = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    print("tools:", [t["name"] for t in r["result"]["tools"]])
    r = handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_toolbox_version", "arguments": {}},
        }
    )
    print(r["result"]["content"][0]["text"])
    r = handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "search_wiki",
                "arguments": {"query": "leadfield", "max_results": 3},
            },
        }
    )
    print(r["result"]["content"][0]["text"][:600])
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    serve()
