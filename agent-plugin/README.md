# TI-Toolbox agent plugin

Teaches AI coding agents (Claude Code, Codex, Cursor, any MCP client) how the
**Temporal Interference Toolbox** works, so they can answer questions, write
`tit` scripts, and debug your project without hallucinating the API.

It has two parts, usable together or separately:

| Part | What it gives the agent |
|------|-------------------------|
| **Skills** (`skills/*/SKILL.md`) | Orientation, scripting API cheat-sheet, TI domain knowledge, codebase conventions, a `/troubleshoot-project` command |
| **MCP server** (`mcp/server.py`) | Read-only tools: search/read the wiki, the nine developer documents of record and the changelog; read `tit` and `desktop` source; find symbols; inspect a project directory (subjects, m2m, simulations, flex/ex runs, the job store, notebooks, pipelines, reports) |

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
- **`docs/dev/` is the developer source of truth** and is capped at nine files.
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
- **The domain skill carries `docs/dev/SCIENTIFIC-CORRECTIONS.md`**: voxel focality
  extents are cm³ (mesh stays cm²), permutation p-values are `(b+1)/(m+1)`,
  clusters are labelled per sign and compared right-tailed, and geometry comes from
  the affine rather than the header zooms. Each says whether to re-run or rescale.
- **`get_toolbox_version` reads `tit/__init__.py` and `desktop/package.json`** and
  reports whether they are in lockstep, instead of reading `version.py` alone.

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

This calls **every** registered tool once against the current checkout — including
`inspect_project` and `read_project_config`, which run against a throwaway project
tree it builds in a temp directory — prints one line per tool, and exits non-zero
if any tool errors or if a registered tool is missing from the matrix. Tools that
need a local checkout are reported as `SKIP` (not a failure) when there is none.

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
documents and the source are read live, so they never go stale.
