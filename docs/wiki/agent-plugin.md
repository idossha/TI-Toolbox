---
layout: wiki
title: Agent Plugin Internals
permalink: /wiki/agent-plugin/
---

Developer reference for the AI-assistant integration. For end-user installation see [AI Assistant]({{ site.baseurl }}/wiki/ai-assistant/).

## Layout

```
AGENTS.md                            # repo-wide agent instructions (Codex/Cursor/Claude read this)
.claude-plugin/marketplace.json      # makes the repo a Claude Code plugin marketplace
agent-plugin/
  .claude-plugin/plugin.json         # plugin manifest
  .mcp.json                          # registers mcp/server.py via ${CLAUDE_PLUGIN_ROOT}
  mcp/server.py                      # MCP server, stdlib only, Python 3.9+
  skills/
    ti-toolbox/SKILL.md              # orientation (auto-loaded)
    ti-scripting/SKILL.md            # Python API cheat-sheet (auto-loaded)
    ti-domain/SKILL.md               # TI physics/neuroscience background (auto-loaded)
    ti-codebase/SKILL.md             # module graph and conventions (auto-loaded)
    troubleshoot-project/SKILL.md    # /ti-toolbox:troubleshoot-project <root> [subject]
  README.md
tests/test_agent_plugin_mcp.py
```

`AGENTS.md` at the repo root is the single source of project context for agents working *on* the codebase; the plugin is for agents working *with* the toolbox. Keep the two consistent when the architecture changes.

## MCP server

`agent-plugin/mcp/server.py` implements JSON-RPC 2.0 over newline-delimited stdio (the MCP stdio transport) by hand — no SDK, no dependencies, so it runs on any user's Python.

**Source resolution.** On start it looks for a TI-Toolbox checkout: `TI_TOOLBOX_ROOT`, otherwise the first ancestor of `server.py` containing `tit/` and `docs/wiki/`. With a checkout, every tool reads the working tree (so `claude --plugin-dir ./agent-plugin` from the repo gives you live source). Without one, files are fetched from `raw.githubusercontent.com` / the GitHub contents API at `TI_TOOLBOX_REF` (default `main`) and cached for 24 h in `TI_TOOLBOX_CACHE` (default `~/.cache/ti-toolbox-mcp`).

**Tools.**

| Tool | Notes |
|------|-------|
| `get_quick_facts` | Static orientation blob; agents are told to call it first |
| `list_wiki_pages`, `read_wiki_page`, `search_wiki` | Parse `docs/wiki/*.md` front matter; `read_wiki_page` can return a single `##` section |
| `read_changelog`, `get_toolbox_version` | `docs/releases/changelog.md`, `version.py` |
| `list_source_dir`, `read_source_file` | Restricted to `tit/ scripts/ docs/ tests/ container/ dev/` + top-level manifests; text extensions only; path traversal rejected |
| `find_symbol`, `search_source` | Local checkout only (regex over the tree) |
| `inspect_project`, `read_project_config` | Walk a user's BIDS project using the same directory conventions as `tit/paths.py`; names only, no file contents except `code/ti-toolbox/config/*.json` |

Every payload is capped at 60 kB. Tool failures are returned as `isError: true` results, never as crashes.

**Adding a tool.** Write a `tool_<name>(args) -> dict` function, append an entry to `TOOLS` with a JSON-schema `inputSchema`, and add a test. Keep tools read-only; anything that writes belongs in the toolbox proper, not in the agent surface.

## Skills

Skills are Markdown with YAML front matter. `user-invocable: false` marks background knowledge the model loads by itself when the description matches; `argument-hint` is for slash-command skills. Inside a plugin they are namespaced as `/ti-toolbox:<skill>`.

`ti-domain` and `ti-codebase` are copies of `.claude/skills/ti-domain` and `.claude/skills/codebase-guide` (plugins must be self-contained). When you edit one, copy it to the other.

## Testing

```bash
python3 agent-plugin/mcp/server.py --selftest            # smoke test, local or remote mode
pytest tests/test_agent_plugin_mcp.py -q                  # 15 tests: tools, path guards, fake BIDS project, stdio round-trip
claude plugin validate agent-plugin                       # manifest check
claude plugin validate .claude-plugin/marketplace.json
claude --plugin-dir ./agent-plugin                        # run Claude Code with the working-tree plugin
```

To test remote mode, copy `server.py` outside the repo and run `--selftest`; it should report `repo root: (none -> GitHub)`.

## Releasing

Bump `version` in `agent-plugin/.claude-plugin/plugin.json` when tools or skills change in a user-visible way. Users on the marketplace pick up changes with `/plugin update ti-toolbox@ti-toolbox`; the wiki/source themselves are read live, so documentation updates need no plugin release.
