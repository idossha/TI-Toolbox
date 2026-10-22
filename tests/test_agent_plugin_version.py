"""Both MCP servers and the plugin README report the version in plugin.json, 2026-10-22.

What this pins: Claude Code refreshes a marketplace install when ``version`` in
``agent-plugin/.claude-plugin/plugin.json`` changes, so that file is the source. Each server
(``mcp/server.py``, ``mcp/jobs_server.py``) must answer ``initialize`` with that version in
``serverInfo``, and the README's "Plugin version **X**" line must name it. A bump that misses
one of them makes an agent (or a user reading ``/mcp``) see a different plugin than the one
installed.

Where the expected value comes from: plugin.json, read off disk; the servers' answers come from
starting them as the plugin does (a subprocess speaking JSON-RPC on stdio), not from importing
their constants.

Reproduce: .venv/bin/python -m pytest tests/test_agent_plugin_version.py -q
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1] / "agent-plugin"


def _plugin_version() -> str:
    version = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())[
        "version"
    ]
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), version
    return version


def _server_info(script: Path, tmp_path: Path) -> dict:
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "version-check", "version": "1"},
            },
        },
    ]
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("TI_TOOLBOX_", "TIT_SERVER_"))
    }
    proc = subprocess.run(
        [sys.executable, "-I", str(script)],
        input="".join(json.dumps(m) + "\n" for m in messages),
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**env, "TI_TOOLBOX_OFFLINE": "1"},
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    [reply] = [json.loads(line) for line in proc.stdout.splitlines()]
    return reply["result"]["serverInfo"]


@pytest.mark.parametrize(
    "script, name",
    [("server.py", "ti-toolbox"), ("jobs_server.py", "ti-toolbox-jobs")],
)
def test_each_server_reports_the_plugin_version(tmp_path, script, name):
    info = _server_info(PLUGIN / "mcp" / script, tmp_path)
    assert info == {"name": name, "version": _plugin_version()}


def test_the_readme_names_the_plugin_version():
    readme = (PLUGIN / "README.md").read_text(encoding="utf-8")
    stated = re.findall(r"Plugin version \*\*([^*]+)\*\*", readme)
    assert stated == [_plugin_version()]
