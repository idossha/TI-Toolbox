---
layout: wiki
title: AI Assistant
permalink: /wiki/ai-assistant/
---

TI-Toolbox ships a small, free plugin that teaches AI coding assistants — **Claude Code**, **OpenAI Codex**, **Cursor**, or any tool that speaks the Model Context Protocol (MCP) — how the toolbox works. Once installed, your assistant can answer questions from this wiki, write correct `tit` scripts, and look at your project folder to tell you what is missing, instead of guessing.

> Everything the plugin does is **read-only**. It never modifies your data, never uploads it anywhere, and the only network access is fetching the public documentation/source from GitHub when you don't have a local copy of the repository.

## What it does

| You ask | The assistant does |
|---------|-------------------|
| "How do I run a flex-search with an atlas ROI?" | Searches and reads the wiki, quotes the right section, gives a working `FlexConfig` |
| "Write a script that simulates 3 montages for subjects 101–105" | Reads the real `SimulationConfig` fields from the source so the script matches your installed version |
| "Why is my simulation not showing up in the Analyzer?" | Inspects `derivatives/SimNIBS/sub-101/Simulations/` and reports which outputs exist and what step failed |
| "What changed in v2.4.0?" | Reads the changelog |
| "Which subjects still need a head model?" | Lists every subject with/without `m2m_<id>` |

Under the hood it installs two things:

- **Skills** — short reference documents (how TI-Toolbox runs, the Python API, the codebase layout, TI domain background, plus a `/troubleshoot-project` command) that the assistant reads automatically when you mention TI-Toolbox.
- **An MCP server** — a tiny Python program (no dependencies) that gives the assistant tools such as `search_wiki`, `read_wiki_page`, `read_source_file`, `read_changelog`, and `inspect_project`.

## Install

### Claude Code

Inside a Claude Code session, run:

```text
/plugin marketplace add idossha/TI-Toolbox
/plugin install ti-toolbox@ti-toolbox
```

That's it. Skills load on demand and the MCP server starts with each session. Python 3.9+ must be on your PATH (it is on macOS and every Linux distribution).

Try:

```text
/ti-toolbox:troubleshoot-project /path/to/my_project 101
```

### OpenAI Codex CLI

1. Clone or download the repository once:
   ```bash
   git clone https://github.com/idossha/TI-Toolbox.git ~/TI-Toolbox
   ```
2. Register the MCP server in `~/.codex/config.toml`:
   ```toml
   [mcp_servers.ti-toolbox]
   command = "python3"
   args = ["/Users/you/TI-Toolbox/agent-plugin/mcp/server.py"]
   ```
3. Tell Codex to read the skills, by adding to your `AGENTS.md` (in your project or `~/.codex/AGENTS.md`):
   ```markdown
   When working with TI-Toolbox, first read
   ~/TI-Toolbox/agent-plugin/skills/ti-toolbox/SKILL.md and
   ~/TI-Toolbox/agent-plugin/skills/ti-scripting/SKILL.md,
   and use the `ti-toolbox` MCP tools instead of guessing the API.
   ```

### Cursor, Windsurf, Continue, and other MCP clients

Add the same stdio server to your client's MCP configuration:

```json
{
  "mcpServers": {
    "ti-toolbox": {
      "command": "python3",
      "args": ["/path/to/TI-Toolbox/agent-plugin/mcp/server.py"]
    }
  }
}
```

Then reference the skill files above in your project's rules/instructions file so the assistant reads them.

## Using it well

- **Give it your project path.** `inspect_project` needs the absolute path of your BIDS project (the folder you point the desktop app at). On the host that is e.g. `/Users/you/Studies/my_project`; inside the container it is `/mnt/my_project`.
- **Ask it to check, not assume.** Prompts like *"read the wiki page before answering"* or *"verify the config fields in the source"* make it use the tools.
- **Scripts still run in the container.** The assistant writes code; you run it with `simnibs_python` inside the SimNIBS container (see [Scripting]({{ site.baseurl }}/wiki/scripting/)). The assistant knows this and will remind you.
- **Versions.** The plugin reads documentation from the `main` branch by default. If you run an older release, ask the assistant to call `get_toolbox_version` / `read_changelog` and mention your version, or set `TI_TOOLBOX_REF=v2.4.0` in the server's environment.

## Privacy and safety

- All tools are read-only; there is no tool that writes, deletes, or runs anything.
- Project inspection only lists directory and file names — it never opens imaging data.
- Source/doc access is restricted to the public `tit/`, `docs/`, `scripts/`, `tests/`, `container/`, `dev/` trees of the repository.
- Set `TI_TOOLBOX_OFFLINE=1` to forbid network access entirely (requires a local clone).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "MCP server failed to start" | Run `python3 --version` (needs 3.9+). On Windows use `python` instead of `python3` in the config. |
| Tools return "HTTP 403/429" | GitHub rate limit for unauthenticated requests; wait a few minutes or clone the repo and set `TI_TOOLBOX_ROOT`. |
| `find_symbol` / `search_source` say they need a local checkout | Those two tools grep the source tree; clone the repo and set `TI_TOOLBOX_ROOT=/path/to/TI-Toolbox`. |
| Stale answers | Delete the cache: `rm -rf ~/.cache/ti-toolbox-mcp`. |

For the plugin's internals (skills layout, server architecture, tests), see [Agent Plugin Internals]({{ site.baseurl }}/wiki/agent-plugin/).
