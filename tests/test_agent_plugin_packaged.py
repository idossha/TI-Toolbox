"""The agent plugin works as the desktop app ships it, and honours ``TI_TOOLBOX_REF``, 2026-10-22.

What this pins:

* **Packaged layout.** ``desktop/electron-builder.yml`` copies ``agent-plugin/`` into
  ``Resources/agent-plugin`` minus its filter (``__pycache__``, ``mcp/test_*.py``); there is no
  checkout beside it, so ``server.py`` must find none and both stdio servers must start from
  that copy alone, under ``python -I`` and under the oldest supported Python (3.9, the
  macOS ``/usr/bin/python3``) when this host has it: initialize, tools/list, one call each.
  Every import is standard library or the copy's own ``stdio_loop``, and every file parses
  as Python 3.9.
* **Docs ref pin.** Without a checkout the knowledge server reads GitHub at
  ``TI_TOOLBOX_REF`` (the Assistant sets it to the app's own tag, desktop/src/main/
  assistant.ts ``buildLaunch``): raw files from ``raw.githubusercontent.com/<repo>/<ref>/``,
  listings from the contents API with ``?ref=<ref>``, a cache keyed by ref (a cached ``main``
  file is never served for ``v3.1.1``), ``main`` by default, and no network at all with
  ``TI_TOOLBOX_OFFLINE=1``.

Where the expected values come from: the filter is parsed from electron-builder.yml; the tool
names are the ones agent-plugin/README.md documents (its "Tools" list and its job-server
table); the URLs are GitHub's raw/contents URL schemes for idossha/TI-Toolbox, written out
here; the 3.9 floor is the plugin's stated "Python 3.9+".

Reproduce: .venv/bin/python -m pytest tests/test_agent_plugin_packaged.py -q
Deliberately elsewhere: the protocol framing of agent-plugin/mcp/test_stdio.py and its CI
wiring (package p02); in-checkout stdio round trips (tests/test_agent_plugin_mcp.py).
"""

from __future__ import annotations

import ast
import fnmatch
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "agent-plugin"
OLD_PYTHON = "/usr/bin/python3"
RAW = "https://raw.githubusercontent.com/idossha/TI-Toolbox"
CONTENTS = "https://api.github.com/repos/idossha/TI-Toolbox/contents"


def _builder_filter() -> list[str]:
    config = yaml.safe_load((REPO / "desktop/electron-builder.yml").read_text())
    [entry] = [
        e
        for e in config["extraResources"]
        if isinstance(e, dict) and e.get("from") == "../agent-plugin"
    ]
    assert entry["to"] == "agent-plugin"
    return entry["filter"]


def _shipped(rel: str, patterns: list[str]) -> bool:
    """minimatch's verdict for the patterns electron-builder uses (``**/`` may match nothing)."""

    def match(pat: str) -> bool:
        return fnmatch.fnmatch(rel, pat) or (
            pat.startswith("**/") and fnmatch.fnmatch(rel, pat[3:])
        )

    included = any(match(p) for p in patterns if not p.startswith("!"))
    return included and not any(match(p[1:]) for p in patterns if p.startswith("!"))


@pytest.fixture(scope="module")
def packaged(tmp_path_factory) -> Path:
    """``Resources/agent-plugin`` as the packaged app has it, in a directory with no checkout."""
    patterns = _builder_filter()
    dest = tmp_path_factory.mktemp("Resources") / "agent-plugin"
    shipped = []
    for src in sorted(PLUGIN.rglob("*")):
        rel = src.relative_to(PLUGIN).as_posix()
        if src.is_file() and _shipped(rel, patterns):
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            shipped.append(rel)
    assert "mcp/server.py" in shipped and "mcp/stdio_loop.py" in shipped
    assert "mcp/jobs_server.py" in shipped and ".mcp.json" in shipped
    assert not [r for r in shipped if "/test_" in r or "__pycache__" in r]
    return dest


def _readme_tools() -> tuple[set[str], set[str]]:
    readme = (PLUGIN / "README.md").read_text()
    section = readme[readme.index("## Tools") :].split("\n## ", 1)[0]
    knowledge = set(re.findall(r"`(\w+)`", section.split("All `ti-toolbox`")[0]))
    table = readme[readme.index("| Tool | What it does |") :].split("\n\n", 1)[0]
    jobs = set(re.findall(r"^\| `(\w+)` \|", table, re.M))
    return knowledge, jobs


def _interpreters() -> list[list[str]]:
    out = [[sys.executable, "-I"]]
    if Path(OLD_PYTHON).is_file() and os.path.realpath(OLD_PYTHON) != os.path.realpath(
        sys.executable
    ):
        out.append([OLD_PYTHON, "-I"])
    return out


def _env(**extra: str) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("TI_TOOLBOX_", "TIT_SERVER_"))
    }
    return {**env, "TI_TOOLBOX_OFFLINE": "1", **extra}


def _exchange(argv: list[str], script: Path, call: dict, cwd: Path) -> dict:
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "packaged-smoke", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": call},
    ]
    proc = subprocess.run(
        [*argv, str(script)],
        input="".join(json.dumps(m) + "\n" for m in messages),
        capture_output=True,
        text=True,
        cwd=cwd,
        env=_env(),
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == "", proc.stderr
    return {r["id"]: r for r in map(json.loads, proc.stdout.splitlines())}


@pytest.mark.parametrize("argv", _interpreters(), ids=lambda a: a[0])
def test_both_servers_answer_from_the_packaged_copy(packaged, tmp_path, argv):
    version = subprocess.run(
        [argv[0], "-c", "import sys; print(sys.version_info[:2] >= (3, 9))"],
        capture_output=True,
        text=True,
        check=True,
    )
    if version.stdout.strip() != "True":
        pytest.skip(f"skipping: {argv[0]} is older than the plugin's Python 3.9 floor")
    knowledge, jobs = _readme_tools()
    assert len(knowledge) >= 10 and len(jobs) >= 8  # the README parse found the lists

    out = _exchange(
        argv,
        packaged / "mcp" / "server.py",
        {"name": "get_quick_facts", "arguments": {}},
        tmp_path,
    )
    assert out[1]["result"]["serverInfo"]["name"] == "ti-toolbox"
    assert {t["name"] for t in out[2]["result"]["tools"]} == knowledge
    facts = json.loads(out[3]["result"]["content"][0]["text"])
    # No checkout beside the copy: the server says it reads GitHub, not a local tree.
    assert facts["source_status"].startswith("GitHub idossha/TI-Toolbox@main")

    out = _exchange(
        argv,
        packaged / "mcp" / "jobs_server.py",
        {
            "name": "plan_job",
            "arguments": {"kind": "sim", "config": {}, "subject_ids": ["../x"]},
        },
        tmp_path,
    )
    assert out[1]["result"]["serverInfo"]["name"] == "ti-toolbox-jobs"
    assert {t["name"] for t in out[2]["result"]["tools"]} == jobs
    assert out[3]["result"]["isError"] is True
    assert "invalid subject id" in out[3]["result"]["content"][0]["text"]


@pytest.mark.parametrize("name", ["server", "jobs_server"])
def test_each_server_imports_the_copys_own_stdio_loop(packaged, tmp_path, name):
    script = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('m', {str(packaged / 'mcp' / (name + '.py'))!r})\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "print(sys.modules['stdio_loop'].__file__)\n"
        "print(getattr(m, 'REPO_ROOT', 'n/a'))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-c", script],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=_env(),
        timeout=60,
        check=True,
    )
    loop_file, repo_root = proc.stdout.splitlines()
    assert Path(loop_file).resolve() == (packaged / "mcp" / "stdio_loop.py").resolve()
    if name == "server":
        assert repo_root == "None"


def test_the_copy_is_standard_library_python_3_9(packaged):
    files = sorted(packaged.rglob("*.py"))
    assert {f.name for f in files} == {"server.py", "jobs_server.py", "stdio_loop.py"}
    allowed = set(sys.stdlib_module_names) | {"stdio_loop"}
    for f in files:
        tree = ast.parse(f.read_text(), feature_version=(3, 9))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module]
            else:
                continue
            for mod in names:
                assert mod.split(".")[0] in allowed, f"{f.name} imports {mod}"


# ---------------------------------------------------------------------------------------------
# TI_TOOLBOX_REF
# ---------------------------------------------------------------------------------------------


def _load(packaged: Path, monkeypatch, tag: str, **env: str):
    for key in ("TI_TOOLBOX_ROOT", "TI_TOOLBOX_REF", "TI_TOOLBOX_OFFLINE"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location(
        f"ti_mcp_packaged_{tag}", packaged / "mcp" / "server.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.REPO_ROOT is None
    return mod


def _record(mod, monkeypatch, answer: bytes) -> list[str]:
    urls: list[str] = []

    def fake_get(url: str, timeout: float = 20.0) -> bytes:
        urls.append(url)
        return answer

    monkeypatch.setattr(mod, "_http_get", fake_get)
    return urls


def test_the_pinned_ref_names_every_github_url(packaged, monkeypatch, tmp_path):
    srv = _load(
        packaged,
        monkeypatch,
        "pinned",
        TI_TOOLBOX_REF="v3.1.1",
        TI_TOOLBOX_CACHE=str(tmp_path / "cache"),
    )
    urls = _record(srv, monkeypatch, b"# Overview\n")
    assert srv.read_repo_file("docs/wiki/overview.md") == "# Overview\n"
    assert urls == [f"{RAW}/v3.1.1/docs/wiki/overview.md"]
    urls = _record(
        srv, monkeypatch, json.dumps([{"name": "a.md", "type": "file"}]).encode()
    )
    assert srv.list_repo_dir("docs/wiki") == ["a.md"]
    assert urls == [f"{CONTENTS}/docs/wiki?ref=v3.1.1"]
    # The Assistant is the caller that sets the ref, for both clients it launches.
    assistant = (REPO / "desktop/src/main/assistant.ts").read_text()
    assert "env.TI_TOOLBOX_REF = o.docsRef" in assistant
    assert "mcp_servers.ti-toolbox.env_vars=['TI_TOOLBOX_REF']" in assistant


def test_the_cache_never_serves_another_refs_copy(packaged, monkeypatch, tmp_path):
    cache = str(tmp_path / "cache")
    main = _load(packaged, monkeypatch, "main", TI_TOOLBOX_CACHE=cache)
    urls = _record(main, monkeypatch, b"main copy")
    assert main.read_repo_file("tit/calc.py") == "main copy"
    assert urls == [f"{RAW}/main/tit/calc.py"]  # main is the default ref
    assert main.read_repo_file("tit/calc.py") == "main copy" and len(urls) == 1

    pinned = _load(
        packaged, monkeypatch, "v311", TI_TOOLBOX_REF="v3.1.1", TI_TOOLBOX_CACHE=cache
    )
    urls = _record(pinned, monkeypatch, b"v3.1.1 copy")
    assert pinned.read_repo_file("tit/calc.py") == "v3.1.1 copy"
    assert urls == [f"{RAW}/v3.1.1/tit/calc.py"]


def test_offline_raises_before_any_network(packaged, monkeypatch, tmp_path):
    srv = _load(
        packaged,
        monkeypatch,
        "offline",
        TI_TOOLBOX_OFFLINE="1",
        TI_TOOLBOX_CACHE=str(tmp_path / "empty-cache"),
    )
    opened: list[object] = []
    monkeypatch.setattr(srv.urllib.request, "urlopen", lambda *a, **k: opened.append(a))
    with pytest.raises(srv.ToolError, match="Offline"):
        srv.read_repo_file("docs/wiki/overview.md")
    with pytest.raises(srv.ToolError, match="Offline"):
        srv.list_repo_dir("docs/wiki")
    assert opened == []
