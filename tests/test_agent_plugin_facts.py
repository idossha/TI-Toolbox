"""The checkable facts the agent plugin tells an agent are pinned to their sources, 2026-10-22.

What this pins: the text an agent reads from the plugin -- ``get_quick_facts``,
``list_launch_paths``, the tool descriptions of ``agent-plugin/mcp/server.py``, the six
``skills/*/SKILL.md`` and ``agent-plugin/README.md`` -- against the source each fact restates.
Only the facts in this table are pinned; free prose (what a page is for, how to diagnose a
failure) is not:

| Fact in the plugin | Must match |
|---|---|
| a repo-relative path (``dev/``, ``tit/``, ``desktop/``, ...), served dict keys included | exists in this checkout |
| a developer document cited by its bare name (``DECISIONS.md``) | exists at the root or in ``docs/dev/`` |
| the image's NumPy (and SimNIBS) version | ``container/blueprint/runtime-constraints.txt`` and ``verify_runtime.py`` |
| the seeded example notebook | ``tit.server.notebooks.EXAMPLE_NAME`` |
| the launcher flags | the option strings of ``tit.cli.launch_arguments()`` |
| the rail rows and their digits | ``NAV_ORDER`` / ``PINNED_ORDER`` in ``desktop/src/renderer/app/registry.ts`` and each page's ``title`` |
| what ``loader.sh`` needs | ``loader.sh`` line 2, "Python-free" |
| that ``loader.sh``, ``loader.py`` and ``tit launch`` open the desktop app | ``loader.sh`` ("The desktop app is the default UI") and ``tit.cli.LAUNCH_EPILOG`` |
| wiki slugs and WebSocket routes | ``docs/wiki/*.md`` and the ``@...websocket(...)`` routes under ``tit/server`` |
| "N ``error.type`` values" | the ``JobError(type=...)`` literals under ``tit/jobs`` |
| a server restart and re-adoption | ``JobManager._reconcile_all`` (never re-adopts; records ``lost``) |
| the pytest marker list | the ``markers`` of ``pytest.ini`` |
| the project layouts (ti-toolbox and ti-domain trees, quick facts ``project_layout``) | the directories ``PathManager``, ``NOTEBOOK_SUBDIR`` and ``tit.storage.kind_prefixes`` name, checked at the levels in ``_CHECKED_PARENTS``; each names ``TI/mesh`` and ``mTI/mesh`` |
| which ``npm run dev*`` opens Electron and which has HMR | ``USAGE`` in ``desktop/scripts/dev.ts`` and the scripts in ``desktop/package.json`` |

Where the expected values come from: each row's right-hand file, read off disk at test time;
nothing is retyped from the plugin. The two allowlists below name the only paths the plugin
may cite that do not exist, and each entry is itself checked (a deleted path must stay
deleted, an example name must sit in a real directory).

Reproduce: .venv/bin/python -m pytest tests/test_agent_plugin_facts.py -q
Deliberately elsewhere: job kinds, states and error-type labels (tests/test_agent_plugin_constants.py),
inspect_project's view of a project (tests/test_agent_plugin_inspect_project.py).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "agent-plugin"
SERVER = PLUGIN / "mcp" / "server.py"
DOCS = sorted(PLUGIN.glob("skills/*/SKILL.md")) + [PLUGIN / "README.md"]

#: Paths the plugin names *because* they are gone; each must stay gone.
DELETED_ON_PURPOSE = {
    "tit/gui": "the PyQt GUI, deleted in v3.0.0 -- cited as 'never cite'",
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
    """Every string in a served JSON value, dict keys included (``subsystems`` keys are paths)."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for kv in node.items() for v in kv for s in _strings(v)]
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
    facts = _tool(srv, "get_quick_facts")
    return {
        "get_quick_facts": "\n".join(_strings(facts)),
        "project_layout": "\n".join(_strings(facts["project_layout"])),
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


#: A developer document cited by its bare name (``DECISIONS.md``, ``RELEASE.md §B``) lives at
#: the repository root or in docs/dev/.
_BARE_DOC = re.compile(r"(?<![\w./-])([A-Z][A-Z0-9_]*\.md)\b")


def _check_paths(name: str, text: str) -> tuple[list[str], list[str]]:
    """(the cited paths that were checked, the ones that resolve nowhere)."""
    checked, missing = [], []
    for path in _cited_paths(name, text):
        if path.rstrip("/") in DELETED_ON_PURPOSE or path in EXAMPLE_NAMES:
            continue
        checked.append(path)
        target = REPO / path
        if not (target.exists() or target.with_suffix(".py").is_file()):
            missing.append(path)
    for doc in _BARE_DOC.findall(text):
        checked.append(doc)
        if not ((REPO / doc).is_file() or (REPO / "docs/dev" / doc).is_file()):
            missing.append(doc)
    return checked, missing


def test_the_path_check_sees_what_it_must():
    """The guard itself, on planted text: a dict key, a prose doc name, a backticked path."""
    served = "\n".join(_strings({"subsystems": {"tit/pipeline": "the canvas runner"}}))
    assert _check_paths("get_quick_facts", served)[1] == ["tit/pipeline"]
    gap = "Known open gap (RELEASE.md §B): see `dev/loader/` and DECISIONS.md."
    checked, missing = _check_paths("x/SKILL.md", gap)
    assert missing == ["dev/loader/", "RELEASE.md"]
    assert "DECISIONS.md" in checked


def test_every_cited_repo_path_exists(srv, texts):
    cited, missing = {}, []
    for name, text in texts.items():
        checked, gone = _check_paths(name, text)
        cited[name] = set(checked)
        missing += [f"{name}: {path}" for path in gone]
    assert not missing, "the plugin cites paths that do not exist:\n" + "\n".join(
        missing
    )
    assert sum(map(len, cited.values())) > 60, "too few cited paths: the scan is broken"
    # The quick-facts subsystem names are dict keys; each one was checked.
    keys = _tool(srv, "get_quick_facts")["subsystems"]
    named = {p for key in keys for p in re.findall(r"[\w./-]+/[\w./-]+", key)}
    assert len(named) >= len(keys) and named <= cited["get_quick_facts"], named
    assert "DECISIONS.md" in cited["get_quick_facts"]


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
    )
    for name, text in texts.items():
        for sentence in re.split(r"(?<=[.;])\s|\n", text):
            if "loader.sh" not in sentence:
                continue
            for claim in claims:
                assert not re.search(claim, sentence, re.I), f"{name}: {sentence!r}"


_LAUNCHER = r"loader\.(?:sh|py)|tit launch"
_NO_ELECTRON = r"\b(?:no|without)[- ]Electron\b"


def _launcher_contexts(srv, texts) -> dict[str, list[str]]:
    """Every unit of text that describes loader.sh, loader.py or ``tit launch``: a sentence
    naming one, a ``ways_to_run`` entry (who + how) whose command is one, and in a fenced
    code block a launcher line with the comment lines heading its group."""
    found: dict[str, list[str]] = {"sentence": [], "entry": [], "code line": []}
    for text in texts.values():
        found["sentence"] += [
            s for s in re.split(r"(?<=[.;])\s|\n", text) if re.search(_LAUNCHER, s)
        ]
    for way in _tool(srv, "list_launch_paths")["ways_to_run"]:
        if re.match(rf"\s*(?:\./|python3? )?(?:{_LAUNCHER})", way["how"]):
            found["entry"].append(f"{way['who']}: {way['how']}")
    for name in (n for n in texts if n.endswith(".md")):
        for block in re.findall(r"```[^\n]*\n(.*?)```", texts[name], re.S):
            header, prev_comment = [], False
            for line in block.splitlines():
                comment = line.lstrip().startswith("#")
                if comment:
                    header = (header if prev_comment else []) + [line]
                elif re.match(rf"\s*(?:\./|python3? )?(?:{_LAUNCHER})", line):
                    found["code line"].append("\n".join(header + [line]))
                elif not line.strip():
                    header = []
                prev_comment = comment
    return found


def test_no_launcher_is_said_to_run_without_electron(srv, texts):
    """loader.sh, loader.py and ``tit launch`` open the desktop app by default (loader.sh: "The
    desktop app is the default UI"; ``tit launch``'s epilog); only ``--browser`` opts out.
    """
    assert "The desktop app is the default UI" in (REPO / "loader.sh").read_text()
    from tit.cli import LAUNCH_EPILOG

    assert "The desktop app is downloaded" in LAUNCH_EPILOG
    found = _launcher_contexts(srv, texts)
    for kind, units in found.items():
        for unit in units:
            assert not re.search(_NO_ELECTRON, unit, re.I), f"{kind}: {unit!r}"
    # Each kind of context was reached: the terminal and installed entries, the skill's block.
    assert len(found["entry"]) >= 2, found["entry"]
    assert len(found["code line"]) >= 3 and len(found["sentence"]) > 10, found


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


# ---------------------------------------------------------------------------------------------
# the job engine: error types, restarts
# ---------------------------------------------------------------------------------------------


def test_the_error_type_count_is_the_job_managers(texts):
    import ast

    # The types the job manager writes (every literal JobError(type=...) under tit/jobs); the
    # contract enum is not the source, it still lists types nothing emits.
    emitted = set()
    for path in sorted((REPO / "tit" / "jobs").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            func = getattr(node, "func", None)
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if isinstance(node, ast.Call) and name == "JobError":
                [value] = [k.value for k in node.keywords if k.arg == "type"]
                emitted.add(value.value)
    assert {"runner_failed", "lost"} <= emitted  # the collector found the common ones
    words = (
        "zero one two three four five six seven eight nine ten eleven twelve".split()
    )
    # Both ways a text states the count: "six `error.type` values" and "the six-value
    # (failure) taxonomy" (the README's wording, which may wrap across a line).
    counted = re.compile(
        r"\b(\w+)\s+`?error\.type`?\s+values\b|\b(\w+)-value\s+(?:failure\s+)?taxonomy\b",
        re.I,
    )
    checked = set()
    for name, text in texts.items():
        for m in counted.finditer(text):
            count = (m.group(1) or m.group(2)).lower()
            if not (count.isdigit() or count in words):
                continue  # "Failure `error.type` values ..." states no count
            checked.add(name)
            n = int(count) if count.isdigit() else words.index(count)
            assert n == len(
                emitted
            ), f"{name}: {m.group(0)!r}, the job manager writes {len(emitted)}"
    assert {
        "agent-plugin/skills/ti-codebase/SKILL.md",
        "agent-plugin/README.md",
    } <= checked


def test_no_text_says_a_restart_re_adopts_a_job(texts):
    manager = (REPO / "tit/jobs/manager.py").read_text()
    # The source: reconciliation replaced re-attaching, and records the job as `lost`.
    assert "This replaces the older re-attach behaviour" in manager
    assert 'type="lost", message=note' in manager
    checked = 0
    for name, text in texts.items():
        for sentence in re.split(r"(?<=[.;:])\s|\n\n", text):
            m = re.search(r"re-?(?:adopt|attach)", sentence, re.I)
            if not m:
                continue
            checked += 1
            assert re.search(
                r"\b(?:never|not|no)\b", sentence[: m.start()], re.I
            ), f"{name}: {sentence!r}"
    assert checked >= 2  # ti-codebase and troubleshoot-project


# ---------------------------------------------------------------------------------------------
# pytest markers
# ---------------------------------------------------------------------------------------------


def test_the_marker_list_is_pytest_ini(texts):
    import configparser

    ini = configparser.ConfigParser(interpolation=None)
    ini.read(REPO / "pytest.ini")
    registered = set(re.findall(r"^(\w+):", ini["pytest"]["markers"], re.M))
    assert {"unit", "smoke"} <= registered  # the parse found pytest.ini's list
    skill = texts["agent-plugin/skills/ti-codebase/SKILL.md"]
    listed = re.search(r"pytest markers:\s*`([^`]+)`", skill).group(1).split()
    assert len(listed) == len(set(listed))
    assert set(listed) == registered


# ---------------------------------------------------------------------------------------------
# the project layout
# ---------------------------------------------------------------------------------------------

#: The levels whose children are checked: below them the plugin may name files and
#: directories other modules write (``high_Frequency/``, ``eeg_positions/``, ...).
_CHECKED_PARENTS = (
    "",
    "code",
    "code/ti-toolbox",
    "derivatives",
    "derivatives/ti-toolbox",
    "derivatives/SimNIBS/sub-*",
)


def _toolbox_paths(tmp_path) -> set[str]:
    """Every project path the toolbox names, project-relative, ids and names as ``*``."""
    import inspect

    from tit.paths import PathManager
    from tit.server.notebooks import NOTEBOOK_SUBDIR
    from tit.storage import kind_prefixes

    pm = PathManager(str(tmp_path))
    sid, name = "qzq7", "qzqname"
    found = {NOTEBOOK_SUBDIR.as_posix()}
    found |= {os.path.relpath(p, tmp_path) for p, _ in kind_prefixes(pm)}
    for attr, fn in inspect.getmembers(pm, inspect.ismethod):
        if attr.startswith(("_", "ensure", "list_")) or attr in (
            "user_config_dir",
            "extensions_config",
        ):
            continue  # creators, listers and the per-user config outside the project
        params = inspect.signature(fn).parameters.values()
        required = [
            p
            for p in params
            if p.default is p.empty and p.kind == p.POSITIONAL_OR_KEYWORD
        ]
        try:
            path = fn(*[sid, name, name][: len(required)])
        except (TypeError, ValueError):
            continue
        if isinstance(path, str) and path.startswith(str(tmp_path) + os.sep):
            found.add(os.path.relpath(path, tmp_path))
    assert not any(tmp_path.iterdir()), "the sweep created something"
    return {p.replace(sid, "*").replace(name, "*") for p in found}


def _expand(path: str) -> list[str]:
    """``a/{b,c}/d`` -> both alternatives; a single ``<id>``/``{run}`` placeholder -> ``*``."""
    m = re.search(r"\{([^{}]*,[^{}]*)\}", path)
    if m:
        return [
            q
            for alt in m.group(1).split(",")
            for q in _expand(path[: m.start()] + alt + path[m.end() :])
        ]
    return [re.sub(r"<[^>]*>|\{[^}]*\}", "*", path)]


def _tree_paths(block: str) -> list[str]:
    """Project-relative paths named by an indented or box-drawn tree (first line = root)."""
    out, stack = [], []  # stack: (column, path) of the open directories
    for line in block.splitlines()[1:]:
        body = line.split(" #")[0].rstrip()
        col = re.match(r"[\s│├└─]*", body).end()
        spec = re.split(r"\s{2,}", body[col:])[0].split(" + ")[0]
        items = [i.strip().rstrip(",)") for i in re.split(r"\s*,\s+", spec)]
        items = [i for i in items if "/" in i and not i.startswith("(")]  # not prose
        if not items:
            continue
        while stack and stack[-1][0] >= col:
            stack.pop()
        parent = stack[-1][1] + "/" if stack else ""
        out += [parent + i.rstrip("/") for i in items]
        if items[0].endswith("/"):
            stack.append((col, parent + items[0].rstrip("/")))
    return out


def _layouts(texts) -> dict[str, list[str]]:
    def block(name: str, heading: str) -> str:
        text = texts[name]
        start = text.index("```", text.index(heading))
        return text[text.index("\n", start) + 1 : text.index("```", start + 3)]

    cited = re.findall(
        r"(?<![\w/.-])((?:derivatives|code|sourcedata)/(?:\{[^}]*\}|[^\s,;()'\"{])*)",
        texts["project_layout"],
    )
    return {
        "ti-toolbox": _tree_paths(
            block("agent-plugin/skills/ti-toolbox/SKILL.md", "## On-disk layout")
        ),
        "ti-domain": _tree_paths(
            block("agent-plugin/skills/ti-domain/SKILL.md", "## 10. BIDS Data")
        ),
        "quick facts project_layout": cited,
    }


def test_layouts_name_only_directories_the_toolbox_creates(texts, tmp_path):
    known = _toolbox_paths(tmp_path)
    allowed = {
        parent: {
            k.split("/")[parent.count("/") + bool(parent)]
            for k in known
            if not parent or k.startswith(parent + "/")
        }
        for parent in _CHECKED_PARENTS
    }
    assert "pipelines" not in allowed["code/ti-toolbox"]
    assert {"jobs", "notebooks", "viewer"} <= allowed["code/ti-toolbox"]
    for source, paths in _layouts(texts).items():
        seen = set()
        for path in (q for p in paths for q in _expand(p)):
            parts = path.rstrip("/").split("/")
            assert "pipelines" not in parts, f"{source}: {path}"
            for i, child in enumerate(parts):
                parent = "/".join(parts[:i])
                if parent in allowed:
                    seen.add(parent)
                    assert child in allowed[parent], f"{source}: {path} ({child!r})"
        # The parse reached every level it checks (no vacuous pass on a reformatted tree).
        assert {"", "derivatives", "derivatives/SimNIBS/sub-*"} <= seen, source
        assert "code/ti-toolbox" in seen, source


def test_layouts_name_where_ti_and_mti_results_land(texts, tmp_path):
    """A 2-pair run writes ``TI/mesh``, a 4+ pair run ``mTI/mesh`` (PathManager.ti_mesh_dir /
    mti_mesh_dir); every layout an agent reads must name both, or it will look for an mTI
    result in the wrong place."""
    results = {
        p
        for p in _toolbox_paths(tmp_path)
        if re.search(r"/Simulations/\*/m?TI/mesh$", p)
    }
    assert len(results) == 2, results  # TI/mesh and mTI/mesh
    for source, paths in _layouts(texts).items():
        named = {q.rstrip("/") for p in paths for q in _expand(p)}
        assert results <= named, f"{source} omits {sorted(results - named)}"


# ---------------------------------------------------------------------------------------------
# the developer loop
# ---------------------------------------------------------------------------------------------


def test_dev_loop_text_matches_dev_ts(texts):
    usage = re.search(
        r"const USAGE = `(.*?)`;",
        (REPO / "desktop/scripts/dev.ts").read_text(),
        re.S,
    ).group(1)
    reload_flag = re.search(r"use (--\w+) for renderer live reload", usage).group(1)
    assert re.search(rf"^\s+{reload_flag}\s.*no Electron window", usage, re.M)
    scripts = json.loads((REPO / "desktop/package.json").read_text())["scripts"]
    checked = set()
    for name, text in texts.items():
        for m in re.finditer(r"npm run (dev(?::[\w-]+)?)\b", text):
            rest = text[m.end() :]
            clause = re.split(r"npm run |\n|; |\. ", rest)[0]
            live = re.search(r"\bHMR\b|\bVite\b|live reload", clause, re.I)
            no_window = re.search(r"\b(?:no|without)\s+Electron", clause, re.I)
            window = re.search(r"Electron", clause) and not no_window
            if not (live or no_window or window):
                continue
            script = scripts[m.group(1)]
            web = reload_flag in script.split()
            if live or no_window:
                assert (
                    web
                ), f"{name}: `npm run {m.group(1)}` is not {reload_flag}: {clause!r}"
            if window:
                assert (
                    not web
                ), f"{name}: `npm run {m.group(1)}` opens no Electron window"
            checked.add((name, m.group(1)))
    for where in (
        "get_quick_facts",
        "list_launch_paths",
        "agent-plugin/skills/ti-toolbox/SKILL.md",
    ):
        assert {(where, "dev"), (where, "dev:web")} <= checked, where
