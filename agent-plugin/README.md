# TI-Toolbox agent plugin

Teaches AI coding agents (Claude Code, Codex, Cursor, any MCP client) how the
**Temporal Interference Toolbox** works, so they can answer questions, write
`tit` scripts, and debug your project without hallucinating the API.

It has two parts, usable together or separately:

| Part | What it gives the agent |
|------|-------------------------|
| **Skills** (`skills/*/SKILL.md`) | Orientation, scripting API cheat-sheet, TI domain knowledge, codebase conventions, a `/troubleshoot-project` command |
| **MCP server** (`mcp/server.py`) | Read-only tools: search/read the wiki and changelog, read `tit` source, find symbols, inspect a project directory (subjects, m2m, simulations, flex/ex runs, reports) |

The MCP server is a single Python 3.9+ file with **no dependencies**. It reads
from a local TI-Toolbox checkout when one is present, otherwise it fetches the
files from GitHub (`main`) and caches them in `~/.cache/ti-toolbox-mcp`.

## Claude Code (recommended)

```text
/plugin marketplace add idossha/TI-Toolbox
/plugin install ti-toolbox@ti-toolbox
```

Skills load automatically when TI-Toolbox comes up; the MCP server starts with the
session. Try `/ti-toolbox:troubleshoot-project /path/to/my/project 101`.

Developers working in a clone: `claude --plugin-dir ./agent-plugin` from the repo
root (the server then reads your working tree, and `find_symbol`/`search_source`
become available).

## Codex CLI

Add the MCP server to `~/.codex/config.toml`:

```toml
[mcp_servers.ti-toolbox]
command = "python3"
args = ["/path/to/TI-Toolbox/agent-plugin/mcp/server.py"]
# env = { TI_TOOLBOX_ROOT = "/path/to/TI-Toolbox" }   # optional, for source search
```

Then point Codex at the skills by adding to your `AGENTS.md` (project or `~/.codex/AGENTS.md`):

```markdown
When working with TI-Toolbox, read /path/to/TI-Toolbox/agent-plugin/skills/ti-toolbox/SKILL.md
and /path/to/TI-Toolbox/agent-plugin/skills/ti-scripting/SKILL.md first, and use the
`ti-toolbox` MCP tools instead of guessing the API.
```

If your Codex version supports skills directories, copy or symlink `skills/*` into
it instead.

## Any other MCP client (Cursor, Windsurf, Continue, …)

Same stdio server definition:

```json
{ "mcpServers": { "ti-toolbox": { "command": "python3", "args": ["/path/to/agent-plugin/mcp/server.py"] } } }
```

## Configuration

| Variable | Effect |
|----------|--------|
| `TI_TOOLBOX_ROOT` | Use this checkout instead of GitHub (auto-detected when the plugin lives inside the repo) |
| `TI_TOOLBOX_REF` | Git ref for GitHub fetches (default `main`) |
| `TI_TOOLBOX_CACHE` | Cache directory (default `~/.cache/ti-toolbox-mcp`) |
| `TI_TOOLBOX_OFFLINE=1` | Never touch the network |

## Smoke test

```bash
python3 agent-plugin/mcp/server.py --selftest
```

## Tools

`get_quick_facts`, `list_wiki_pages`, `read_wiki_page`, `search_wiki`,
`read_changelog`, `get_toolbox_version`, `list_source_dir`, `read_source_file`,
`find_symbol`*, `search_source`*, `inspect_project`, `read_project_config`
(\* need a local checkout).

All tools are read-only. `inspect_project` and `read_project_config` only look at
the path you pass them; source tools are restricted to `tit/`, `scripts/`, `docs/`,
`tests/`, `container/`, `dev/` and the top-level manifests.

## Keeping it current

`skills/ti-domain` and `skills/ti-codebase` are copies of the developer skills in
`.claude/skills/`; update both when one changes. The wiki and source are read live,
so they never go stale.
