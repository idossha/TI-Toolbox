# TI-Toolbox agent plugin

Teaches AI coding agents (Claude Code, Codex, Cursor, any MCP client) how the
**Temporal Interference Toolbox** works, so they can answer questions, write
`tit` scripts, and debug your project without hallucinating the API.

It has two parts, usable together or separately:

| Part | What it gives the agent |
|------|-------------------------|
| **Skills** (`skills/*/SKILL.md`) | Orientation, scripting API cheat-sheet, TI domain knowledge, codebase conventions, a `/troubleshoot-project` command |
| **MCP server** (`mcp/server.py`) | Read-only tools: search/read the wiki, the developer reference documents and the changelog; read `tit` and `desktop` source; find symbols; inspect a project directory (subjects, m2m, simulations, flex/ex runs, the job store, notebooks, pipelines, reports) |

The MCP server is a single Python 3.9+ file with **no dependencies**. It reads
from a local TI-Toolbox checkout when one is present, otherwise it fetches the
files from GitHub (`main`) and caches them in `~/.cache/ti-toolbox-mcp`.

## What changed in v3

v3.0.0 replaced the PyQt5 desktop GUI with an Electron app and a server, and the
plugin was rewritten to match. If you are carrying an older copy of these skills,
these are the facts that changed:

- **The architecture is three pieces**: an Electron desktop app on the host
  (`desktop/`) that starts the container and loads the UI from it; a FastAPI job
  server (`tit.server`) *inside* the Docker image `idossha/ti-toolbox`, which owns
  the job model and serves the UI; and the shared `tit` science core.
  `contracts/openapi.yaml` is the wire contract between the first two.
- **`tit/gui/` was deleted.** `tit` imports no Qt, and the core image ships no X11
  and no FreeSurfer. Any answer that cites `tit/gui/**` is wrong.
- **New subsystems the skills now cover**: `tit/jobs` (kinds, the pure scheduler,
  the on-disk job store, the ETA model in `tit/jobs/eta.py`, the ten-value failure
  taxonomy including *"Lost (server restarted mid-run)"*), `tit/pipeline`,
  `tit/server/kernels.py` and notebooks, `tit/scene`, `tit/tetravox`,
  `tit/viewspec.py`, `tit/catalog.py`, `tit/launch.py`.
- **The UI is a ten-row rail counting from ⌘0** (Overview … Jobs at ⌘9); Settings
  is not a rail row and answers only to `⌘,`.
- **One run spec.** The root `docker-compose.yml` is it, with four readers: the
  Electron app, `tit launch`, `loader.py`/`loader.sh`, and the dev overrides in
  `dev/loader/`. The new MCP tool `list_launch_paths` reports all of it.
- **`docs/dev/` is the developer source of truth**; its index defines document ownership.
  The new MCP tool `read_dev_doc(name)` reads them. The user-facing site remains
  `docs/wiki/`, whose pages were restructured — the `mti` page is gone (mTI is now
  a section of `simulator`) and `overview`, `jobs`, `notebooks`, `pipelines` and
  `results` are new.
- **The science API consolidated.** `tit.calc` exposes exactly three functions —
  `get_TI_vectors(fields, psi=None)`, `get_TI_avg(fields, psi=None)`,
  `get_TI_dir(fields, directions, psi=None)` — each taking a *list* of fields
  paired positionally. `get_nTI_vectors`, `get_mTI_vectors`/`get_mTI_dir`,
  `get_magnitude_am` and the `channels=` carrier-regrouping parameter are gone;
  carrier wiring is always positional, one field per carrier.
- **Numerical migration guidance** lives in the [release notes](../docs/releases/v3.0.0.md#scientific-corrections).
  Domain skills describe current behavior and link to that guidance.
- **`get_toolbox_version` reads `tit/__init__.py` and `desktop/package.json`** and
  reports whether they are in lockstep, instead of reading `version.py` alone.

## Claude Code

```text
/plugin marketplace add idossha/TI-Toolbox
/plugin install ti-toolbox@ti-toolbox
```

Skills load automatically when TI-Toolbox comes up; the MCP server starts with the
session. Try `/ti-toolbox:troubleshoot-project /path/to/my/project 101`.

Developers working in a clone: `claude --plugin-dir ./agent-plugin` from the repo
root (the server then reads your working tree, and `find_symbol`/`search_source`
become available).

## Codex (CLI or desktop)

Register the stdio server with the CLI (replace the checkout path):

```bash
codex mcp add ti-toolbox -- python3 /absolute/path/to/TI-Toolbox/agent-plugin/mcp/server.py
codex mcp list
```

Or add the equivalent configuration to `~/.codex/config.toml`:

```toml
[mcp_servers.ti-toolbox]
command = "python3"
args = ["/absolute/path/to/TI-Toolbox/agent-plugin/mcp/server.py"]
```

The server detects the checkout from its own location; its working directory does
not matter. Restart the client after configuration changes, then ask it to call
`get_quick_facts` and `read_dev_doc` with `name: "README"`. A configuration listing
alone does not prove the server connected. See the [official Codex MCP guide](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

Skills are installed separately from MCP. Copy or symlink each of the five folders
under `agent-plugin/skills/` into your project's `.agents/skills/` or your personal
`~/.agents/skills/`, preserving any existing folders. Codex supports both locations
and symlinks; see the [official skill discovery guide](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills).
For example, from this checkout, to expose the orientation skill in this project:

```bash
mkdir -p .agents/skills
ln -s ../../agent-plugin/skills/ti-toolbox .agents/skills/ti-toolbox
```

Repeat for `ti-scripting`, `ti-domain`, `ti-codebase` and `troubleshoot-project` as
needed. Do not overwrite an existing installation. Alternatively, tell the agent
to read the appropriate `agent-plugin/skills/<name>/SKILL.md` directly; that works
without automatic skill discovery.

## Other agents and MCP clients

Use a **local stdio** connection, Python 3.9+ and an absolute script path. For
clients using the `mcpServers` JSON format, merge this entry into their configuration:

```json
{
  "mcpServers": {
    "ti-toolbox": {
      "command": "python3",
      "args": ["/absolute/path/to/TI-Toolbox/agent-plugin/mcp/server.py"]
    }
  }
}
```

Other clients may use different configuration keys; the command and arguments
stay the same. HTTP-only clients cannot launch this stdio server directly. On
Windows, use the installed Python executable and an absolute Windows script path.
The server must run on a machine that can read the project directory being
inspected; a host server needs the host path, not a container's `/mnt/...` path.

The `.claude-plugin/` manifest and `${CLAUDE_PLUGIN_ROOT}` in `.mcp.json` are
Claude Code packaging. Other agents use the direct command above. Skills are
ordinary Markdown with `name` and `description` metadata: load them using your
agent's skill support or read the files explicitly. Slash commands and optional
frontmatter such as `user-invocable` are client conveniences, not requirements.
For troubleshooting, supply the project root and optional subject in the request.

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
python3 -m unittest discover -s agent-plugin/mcp -p "test_*.py" -v
```

This calls **every** registered tool once against the current checkout — including
`inspect_project` and `read_project_config`, which run against a throwaway project
tree it builds in a temp directory — prints one line per tool, and exits non-zero
if any tool errors or if a registered tool is missing from the matrix. Tools that
need a local checkout are reported as `SKIP` (not a failure) when there is none.

The separate stdio tests launch a real server process from a temporary working
directory and verify initialization, notification handling, tool discovery and
successful/error tool calls offline. These are protocol checks, not claims that
Codex, Claude Code or every other client has been tested end to end.

## Tools

`get_quick_facts`, `list_wiki_pages`, `read_wiki_page`, `search_wiki`,
`read_dev_doc`, `list_launch_paths`, `read_changelog`, `get_toolbox_version`,
`list_source_dir`, `read_source_file`, `find_symbol`\*, `search_source`\*,
`inspect_project`, `read_project_config`
(\* need a local checkout).

All tools are read-only. `inspect_project` and `read_project_config` only look at
the path you pass them; source tools are restricted to `tit/`, `scripts/`, `docs/`,
`tests/`, `container/`, `dev/`, `contracts/`, `desktop/src/`, `desktop/tests/`,
`agent-plugin/` and a short list of top-level manifests.
`node_modules` and build output are never listed, read or searched.

## Keeping it current

`skills/ti-domain` and `skills/ti-codebase` are copies of the developer skills in
`.claude/skills/`; update both when one changes. The wiki, the `docs/dev/`
documents and source are read from the checkout or the configured GitHub ref.
Remote reads use a 24-hour cache; pin `TI_TOOLBOX_REF` to match the toolbox
version when using a standalone server.
