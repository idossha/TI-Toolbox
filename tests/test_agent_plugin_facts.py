"""Every fact the agent plugin tells an agent is pinned to the file it describes, 2026-10-22.

What this pins: the text an agent reads from the plugin -- ``get_quick_facts``,
``list_launch_paths``, the tool descriptions of ``agent-plugin/mcp/server.py``, the six
``skills/*/SKILL.md`` and ``agent-plugin/README.md`` -- against the source each fact restates:

| Fact in the plugin | Must match |
|---|---|
| a repo-relative path (``dev/``, ``tit/``, ``desktop/``, ...) | exists in this checkout |
| the image's NumPy (and SimNIBS) version | ``container/blueprint/runtime-constraints.txt`` and ``verify_runtime.py`` |
| the seeded example notebook | ``tit.server.notebooks.EXAMPLE_NAME`` |
| the launcher flags | the option strings of ``tit.cli.launch_arguments()`` |
| the rail rows and their digits | ``NAV_ORDER`` / ``PINNED_ORDER`` in ``desktop/src/renderer/app/registry.ts`` and each page's ``title`` |
| what ``loader.sh`` needs | ``loader.sh`` line 2, "Python-free" |
| wiki slugs and WebSocket routes | ``docs/wiki/*.md`` and the ``@...websocket(...)`` routes under ``tit/server`` |

Where the expected values come from: each row's right-hand file, read off disk at test time;
nothing is retyped from the plugin. The two allowlists below name the only paths the plugin
may cite that do not exist, and each entry is itself checked (a deleted path must stay
deleted, an example name must sit in a real directory).

Reproduce: .venv/bin/python -m pytest tests/test_agent_plugin_facts.py -q
Deliberately elsewhere: job kinds/states/error types (tests/test_agent_plugin_constants.py),
inspect_project's view of a project (tests/test_agent_plugin_inspect_project.py).
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "agent-plugin"
SERVER = PLUGIN / "mcp" / "server.py"
DOCS = sorted(PLUGIN.glob("skills/*/SKILL.md")) + [PLUGIN / "README.md"]

#: Paths the plugin names *because* they are gone; each must stay gone.
DELETED_ON_PURPOSE = {
    "tit/gui": "the PyQt GUI, deleted in v3.0.0 -- cited as 'never cite'"
}
#: Example names for a file a developer would create; the directory must exist.
EXAMPLE_NAMES = {
    "tit/reporting/generators/my_report.py": "ti-codebase: how to add a report generator"
}
_ROOTS = (
    "dev/",
    "tit/",
    "desktop/",
    "container/",
    "contracts/",
    "docs/",
    "examples/",
    "tests/",
    "agent-plugin/",
    "resources/",
)


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("ti_mcp_server_facts", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _strings(node) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for v in node.values() for s in _strings(v)]
    if isinstance(node, list):
        return [s for v in node for s in _strings(v)]
    return []


def _tool(srv, name: str) -> dict:
    resp = srv.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": {}},
        }
    )
    assert resp["result"]["isError"] is False, resp
    return json.loads(resp["result"]["content"][0]["text"])


@pytest.fixture(scope="module")
def served(srv) -> dict[str, str]:
    """What the knowledge server says, one text per source."""
    listed = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    init = srv.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}},
        }
    )
    return {
        "get_quick_facts": "\n".join(_strings(_tool(srv, "get_quick_facts"))),
        "list_launch_paths": "\n".join(_strings(_tool(srv, "list_launch_paths"))),
        "tool descriptions": "\n".join(
            t["description"] for t in listed["result"]["tools"]
        ),
        "instructions": init["result"].get("instructions", ""),
    }


@pytest.fixture(scope="module")
def texts(served) -> dict[str, str]:
    docs = {str(p.relative_to(REPO)): p.read_text(encoding="utf-8") for p in DOCS}
    assert len(docs) == 7, "six skills and the README"
    return {**served, **docs}


# ---------------------------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------------------------


def _cited_paths(name: str, text: str) -> list[str]:
    if name.endswith(".md"):
        # Markdown: what is in backticks.
        tokens = re.findall(r"`([^`\s]+)`", text)
    else:
        # Served JSON strings carry no Markdown; any token that starts at a repo root.
        tokens = re.findall(
            r"(?<![\w./-])((?:%s)[^\s,;()'\"`]*)"
            % "|".join(re.escape(r) for r in _ROOTS),
            text,
        )
    out = []
    for token in tokens:
        if not token.startswith(_ROOTS):
            continue
        path = re.split(r"#|::", token)[0].rstrip(".,:;)")
        if any(c in path for c in "<>*{}[]"):
            continue  # a pattern or a placeholder, not a file
        out.append(path)
    return out


def test_every_cited_repo_path_exists(texts):
    checked, missing = 0, []
    for name, text in texts.items():
        for path in _cited_paths(name, text):
            if path.rstrip("/") in DELETED_ON_PURPOSE or path in EXAMPLE_NAMES:
                continue
            checked += 1
            target = REPO / path
            if not (target.exists() or target.with_suffix(".py").is_file()):
                missing.append(f"{name}: {path}")
    assert not missing, "the plugin cites paths that do not exist:\n" + "\n".join(
        missing
    )
    assert checked > 60, f"only {checked} cited paths found: the scan is broken"


def test_the_allowlisted_paths_are_what_they_claim():
    for path in DELETED_ON_PURPOSE:
        assert not (REPO / path).exists(), f"{path} is back; drop it from the allowlist"
    for path in EXAMPLE_NAMES:
        assert not (REPO / path).exists() and (REPO / path).parent.is_dir(), path


# ---------------------------------------------------------------------------------------------
# runtime versions
# ---------------------------------------------------------------------------------------------


def _pinned_versions() -> tuple[str, str, str]:
    constraints = (REPO / "container/blueprint/runtime-constraints.txt").read_text()
    numpy = re.search(r"^numpy==(\S+)$", constraints, re.M).group(1)
    verify = (REPO / "container/blueprint/verify_runtime.py").read_text()
    blender = re.search(r"numpy\.__version__ == '([\d.]+)'", verify).group(1)
    simnibs = re.search(r'metadata\.version\("simnibs"\) != "([\d.]+)"', verify).group(
        1
    )
    return numpy, blender, simnibs


def test_numpy_and_simnibs_versions_match_the_image(texts):
    numpy, blender, simnibs = _pinned_versions()
    seen = set()
    for name, text in texts.items():
        for m in re.finditer(r"numpy\s+v?(\d+(?:\.\d+)+)", text, re.I):
            before = text[max(0, m.start() - 40) : m.start()]
            want = blender if "Blender" in before else numpy
            assert m.group(1) == want, f"{name}: {m.group(0)!r}, the image has {want}"
            seen.add(name)
        for m in re.finditer(r"SimNIBS\s+(\d+\.[\dx]+)", text):
            assert simnibs.startswith(m.group(1) + "."), f"{name}: {m.group(0)!r}"
    # The three places an agent reads the runtime from.
    assert {
        "get_quick_facts",
        "agent-plugin/skills/ti-toolbox/SKILL.md",
        "agent-plugin/skills/ti-scripting/SKILL.md",
    } <= seen


# ---------------------------------------------------------------------------------------------
# the seeded notebook
# ---------------------------------------------------------------------------------------------


def test_the_seeded_notebook_is_the_one_the_server_seeds(texts):
    from tit.server.notebooks import EXAMPLE_NAME, NOTEBOOK_SUBDIR

    names = {
        (name, m)
        for name, text in texts.items()
        for m in re.findall(r"[\w./-]+\.ipynb", text)
    }
    assert names, "no notebook cited at all"
    for name, cited in names:
        assert cited.endswith(Path(EXAMPLE_NAME).name), f"{name}: {cited}"
    quick = texts["get_quick_facts"]
    assert EXAMPLE_NAME in quick
    seeded = f"{NOTEBOOK_SUBDIR.as_posix()}/{EXAMPLE_NAME}"
    assert seeded in texts["agent-plugin/skills/ti-scripting/SKILL.md"]


# ---------------------------------------------------------------------------------------------
# launcher flags and loader.sh
# ---------------------------------------------------------------------------------------------


def _cli_flags() -> tuple[set[str], set[str]]:
    """(every option string, the first long spelling of each user-facing option)."""
    import argparse

    from tit.cli import launch_arguments

    every, primary = set(), set()
    for action in launch_arguments()._actions:
        longs = [o for o in action.option_strings if o.startswith("--")]
        if not longs:
            continue
        every.update(action.option_strings)
        if action.help != argparse.SUPPRESS:
            primary.add(longs[0])
    return every, primary


def test_list_launch_paths_names_exactly_the_cli_flags(srv):
    _, primary = _cli_flags()
    terminal = next(
        w
        for w in _tool(srv, "list_launch_paths")["ways_to_run"]
        if "loader.sh" in w["how"]
    )
    listed = set(re.findall(r"(?<![\w-])--[a-z][a-z-]*", terminal["how"]))
    assert (
        listed == primary
    ), f"missing {sorted(primary - listed)}, unknown {sorted(listed - primary)}"


def test_skills_cite_only_real_launcher_flags(texts):
    every, _ = _cli_flags()
    checked = 0
    for name, text in texts.items():
        # A quoted command of another tool (`container/blueprint/build.sh --tag ...`) is not
        # a launcher line even when it shares one with `tit launch`.
        text = re.sub(
            r"`[^`]*`",
            lambda m: (
                ""
                if re.search(r"\w\.sh\b", m.group(0)) and "loader" not in m.group(0)
                else m.group(0)
            ),
            text,
        )
        for line in text.splitlines():
            if not re.search(r"loader\.(sh|py)|tit launch", line):
                continue
            for flag in re.findall(r"(?<![\w-])--[a-z][a-z-]*", line):
                checked += 1
                assert flag in every, f"{name}: {flag} is not a launcher flag: {line}"
    assert checked > 10


def test_loader_sh_is_never_said_to_need_python(texts):
    assert "Python-free" in (REPO / "loader.sh").read_text().splitlines()[1]
    claims = (
        r"\bfinds?\s+(?:a\s+)?(?:usable\s+)?python",
        r"\b(?:needs?|requires?)\s+(?:a\s+)?python",
        r"bootstrap\w*\s+over\s+`?tit/launch\.py",
        r"no electron",
    )
    for name, text in texts.items():
        for sentence in re.split(r"(?<=[.;])\s|\n", text):
            if "loader.sh" not in sentence:
                continue
            for claim in claims:
                assert not re.search(claim, sentence, re.I), f"{name}: {sentence!r}"


# ---------------------------------------------------------------------------------------------
# the rail
# ---------------------------------------------------------------------------------------------


def _rail() -> tuple[list[str], list[str]]:
    """(rail titles in ⌘-order, pinned titles) from registry.ts and each page's title."""
    registry = (REPO / "desktop/src/renderer/app/registry.ts").read_text()

    def ids(const: str) -> list[str]:
        body = re.search(rf"export const {const} = \[(.*?)\] as const", registry, re.S)
        return re.findall(r'"([\w-]+)"', body.group(1))

    def title(page_id: str) -> str:
        src = (REPO / f"desktop/src/renderer/pages/{page_id}/index.tsx").read_text()
        return re.search(rf'id: "{page_id}",\s*title: "([^"]+)"', src).group(1)

    return [title(i) for i in ids("NAV_ORDER")], [title(i) for i in ids("PINNED_ORDER")]


_NUMBER_WORDS = {8: "eight", 9: "nine", 10: "ten", 11: "eleven"}


def test_quick_facts_rail_is_the_registry_rail(texts):
    rows, pinned = _rail()
    assert len(rows) == 9 and "Overview" in rows  # the parse found the rail
    text = texts["get_quick_facts"]
    rail = text[text.index("counting from Cmd+0") :]
    listed = re.findall(r"([A-Z][\w-]*(?: [A-Z][\w-]*)*) \((\d)\)", rail)
    assert listed == [(t, str(i)) for i, t in enumerate(rows)]
    for t in pinned:
        assert t in rail
    assert text.lower().count(f"{_NUMBER_WORDS[len(rows)]} rows") >= 1


def test_every_rail_digit_an_agent_reads_matches_the_registry(texts):
    rows, pinned = _rail()
    checked = 0
    for name, text in texts.items():
        for i, title in enumerate(rows):
            for m in re.finditer(rf"{re.escape(title)}`?\s*(?:page\s*)?\(?⌘(\d)", text):
                checked += 1
                assert m.group(1) == str(i), f"{name}: {m.group(0)!r}, rail has ⌘{i}"
        for title in pinned:
            assert not re.search(rf"`{re.escape(title)}`\s*⌘\d", text), name
        for m in re.finditer(r"\b(\w+)[- ]rows?\b", text.lower()):
            if m.group(1) in _NUMBER_WORDS.values() and "rail" in text.lower():
                assert m.group(1) == _NUMBER_WORDS[len(rows)], f"{name}: {m.group(0)}"
    assert (
        checked >= len(rows) + 1
    )  # the skill's rail row list plus ti-scripting's Notebooks


# ---------------------------------------------------------------------------------------------
# wiki slugs and WebSocket routes
# ---------------------------------------------------------------------------------------------


def test_cited_wiki_slugs_exist(texts):
    slugs = {p.stem for p in (REPO / "docs/wiki").glob("*.md")}
    skill = texts["agent-plugin/skills/ti-toolbox/SKILL.md"]
    section = skill[skill.index("## Wiki map") : skill.index("## The pipeline")]
    bullets = [ln for ln in section.splitlines() if ln.startswith(("- ", "  "))]
    cited = set(re.findall(r"`([\w-]+)`", "\n".join(bullets)))
    described = re.search(r"Slugs: (.*?)\.\.\.", texts["tool descriptions"], re.S)
    cited |= {s.strip() for s in described.group(1).split(",") if s.strip()}
    assert len(cited) > 25
    assert cited <= slugs, sorted(cited - slugs)


def test_cited_websockets_are_served():
    routes = set()
    for py in (REPO / "tit/server").rglob("*.py"):
        routes |= set(re.findall(r'websocket\("(/ws/[^"]+)"\)', py.read_text()))
    norm = {re.sub(r"\{[^}]*\}", "{}", r) for r in routes}
    assert {"/ws/system", "/ws/jobs"} <= norm
    for doc in [SERVER, *DOCS]:
        for cited in re.findall(r"/ws/[\w/{}]*\w}?", doc.read_text()):
            assert re.sub(r"\{[^}]*\}", "{}", cited) in norm, f"{doc.name}: {cited}"
