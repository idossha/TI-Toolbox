---
layout: wiki
title: AI Assistant
permalink: /wiki/ai-assistant/
---

TI-Toolbox ships a small, free plugin that teaches AI coding assistants — **Claude Code**, **OpenAI Codex**, **Cursor**, or any tool that speaks the Model Context Protocol (MCP) — how the toolbox works. Once installed, your assistant can answer questions from this wiki, write correct `tit` scripts, and look at your project folder to tell you what is missing, instead of guessing.

> The knowledge tools are **read-only**. A second, optional set of tools lets your assistant run jobs for you through the TI-Toolbox you have open (see [Let your assistant run pipelines](#let-your-assistant-run-pipelines)); by default it only proposes them, and you approve each plan in the app. Network access only fetches public documentation/source from GitHub when you do not have a local checkout. Tool results, including project names and requested configuration text, are passed to your chosen assistant; that assistant's own data policies apply.

## What it does

| You ask | The assistant does |
|---------|-------------------|
| "How do I run a flex-search with an atlas ROI?" | Searches and reads the wiki, quotes the right section, gives a working `FlexConfig` |
| "Write a script that simulates 3 montages for subjects 101–105" | Reads the real `SimulationConfig` fields from the source so the script matches your installed version |
| "Why is my simulation not showing up in the Analyzer?" | Inspects `derivatives/SimNIBS/sub-101/Simulations/` and reports which outputs exist and what step failed |
| "What changed in v2.4.0?" | Reads the changelog |
| "Which subjects still need a head model?" | Lists every subject with/without `m2m_<id>` |

Under the hood it installs three things:

- **Skills** — short reference documents (how TI-Toolbox runs, the Python API, the codebase layout, TI domain background, plus a `/troubleshoot-project` command) that the assistant reads automatically when you mention TI-Toolbox.
- **An MCP server** — a tiny Python program (no dependencies) that gives the assistant tools such as `search_wiki`, `read_wiki_page`, `read_source_file`, `read_changelog`, and `inspect_project`.
- **A job server** — a second tiny program that lets the assistant run TI-Toolbox jobs through the app you have open.

## Install

### Claude Code

Inside a Claude Code session, run:

```text
/plugin marketplace add idossha/TI-Toolbox
/plugin install ti-toolbox@ti-toolbox
```

That's it. Skills load on demand and the MCP server starts with each session. Python 3.9+ must be installed and available on your PATH.

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

## Let your assistant run pipelines

With the TI-Toolbox desktop app open on your project, you can ask for work instead of instructions:

> *Organise the raw scans in ~/Downloads/scan into BIDS as sub-101, preprocess them, run a flex-search targeting the bilateral thalamus with high intensity, then simulate the best montage.*

The assistant then looks at the scans and proposes which series is the T1w, T2w, CT or DWI; copies them into the project's `sourcedata/sub-101/` (it never moves or overwrites your files); and **proposes** the work as a plan for you to approve: pre-processing first, then — once it can find the left and right thalamus in that subject's own atlas — the flex-search and a simulation of its winning electrodes. Each approved step is an ordinary job: it appears in **Jobs** and in the page's terminal as it runs, writes the same outputs and reports as a job you start yourself, carries a small **agent** badge, and can be cancelled from the app.

**It uses your own assistant and your own login.** Claude Code runs on your Claude Pro/Max login, Codex on your ChatGPT login. TI-Toolbox never sees, stores or forwards those credentials and has no AI service of its own; the job tools talk only to the TI-Toolbox running on your computer.

- **Claude Code:** nothing more to do; the plugin installed above includes the job server (`ti-toolbox-jobs`) and the `ti-run-pipelines` skill.
- **Codex:** register the second server too, and expose the `ti-run-pipelines` skill as described in the [plugin README](https://github.com/idossha/TI-Toolbox/blob/main/agent-plugin/README.md#codex-cli-or-desktop):
  ```toml
  [mcp_servers.ti-toolbox-jobs]
  command = "python3"
  args = ["/Users/you/TI-Toolbox/agent-plugin/mcp/jobs_server.py"]
  ```

The job server needs the `docker` command on the assistant's `PATH`, except when started from the Assistant page below. With several projects open at once, the assistant asks which one you mean.

### The Assistant page in the desktop app

No setup at all: open **Assistant** in the desktop app's rail (just above System). It is a real terminal running your own `claude` or `codex` on your computer, in your project folder, already connected to the TI-Toolbox you have open — there is nothing to install or configure in TI-Toolbox itself.

1. Pick **Claude Code** or **Codex** at the top.
2. **Start** it. If it is not signed in yet, sign in inside the pane: type `/login` in Claude Code; Codex asks you to sign in with ChatGPT when it starts.
3. Ask for what you want, or click an example such as **Bilateral thalamus pipeline**: it types the request into the assistant's input so you can edit it before pressing Enter.
4. The assistant proposes the work as a plan; approve it on the **Jobs** page (see [Approving a plan](#approving-a-plan)). Nothing runs before you do.

The app starts the assistant with the TI-Toolbox plugin of the same version attached for that session only (Claude Code: `--plugin-dir`; Codex: `-c mcp_servers.…` overrides plus a pointer to the `ti-run-pipelines` guide). Nothing is written to your `~/.claude` or `~/.codex`, and a plugin you installed yourself is not registered twice. It also tells the job tools exactly which TI-Toolbox to use, so the page works without Docker on the assistant's `PATH`, with a native (non-Docker) session too.

- **Not installed?** The page says so and shows the install command (Claude Code: `curl -fsSL https://claude.ai/install.sh | bash`; Codex: `npm install -g @openai/codex`). Install it in a terminal, then click **check again**. TI-Toolbox finds it on the same `PATH` your terminal uses.
- **Prefer your own terminal?** **Open in system terminal** starts the same session in Terminal (macOS), the default terminal (Linux, through `x-terminal-emulator`) or a console window (Windows).
- **Restart** starts a fresh session; **Stop** ends it. Closing the project, switching projects or quitting the app ends every Assistant session.
- The Assistant page needs the desktop app and a project on this computer; in a browser session it explains this instead.

Your login stays with your assistant: TI-Toolbox never sees, stores or forwards it, and only checks whether the assistant reports itself signed in.

### Approving a plan

Nothing the assistant asks for runs until you approve it. Its plan appears as a card at the top of the **Jobs** page, and the **Jobs** item in the side bar shows how many plans are waiting (a notice pops up when one arrives). The card shows:

- the title, the assistant's reasoning, and which assistant sent it (Claude Code, Codex, ...);
- each step in order — what it does (pre-process, flex-search, simulate the flex result, ...), for which subjects, and its key settings in plain terms (goal, target region, current, electrode size, run name, currents), with the folder it will write and an estimated time;
- which steps wait for others ("after step 1"): a later step starts by itself when the steps it waits on have succeeded — a simulation of a flex-search result picks up that run's electrodes and currents once it exists;
- in red, **any existing result the plan would replace**.

Then:

- **Approve and run** queues the plan. You can close the assistant: the app runs the remaining steps itself, and the card follows each step live (waiting, queued, running, succeeded, failed); click a job id to open it in the table. If a step fails, the steps after it are skipped; **Retry step** runs it again once you have fixed the cause.
- **Edit** a step first to change its subjects, run name, current or currents, or any setting in its JSON config, and to allow it to replace existing output. The card re-checks the step as you save. What you approve is what runs, and the assistant is told what you changed.
- **Reject…** with an optional note, such as *"use the right thalamus"*. The assistant reads your note and asks you what to change; it does not send the same plan again unchanged.

A plan that would replace an existing result cannot be approved until you allow replacing on that step (or give it a new run name), and a plan with an error or a missing input cannot be approved at all.

To let the assistant queue jobs directly, without a plan card, turn on **Settings ▸ Project ▸ AI assistant ▸ Agent may submit without approval**. It then asks you in the chat before replacing an existing result. This is a rule the assistant's tools follow, not a lock: anything with the app's session token can do what the app can.

## Using it well

- **Give it your project path.** `inspect_project` needs the absolute path of your BIDS project (the folder you point the desktop app at). On the host that is e.g. `/Users/you/Studies/my_project`; inside the container it is `/mnt/my_project`.
- **Ask it to check, not assume.** Prompts like *"read the wiki page before answering"* or *"verify the config fields in the source"* make it use the tools.
- **Scripts still run in the container.** The assistant writes code; you run it with `simnibs_python` inside the SimNIBS container (see [Scripting]({{ site.baseurl }}/wiki/scripting/)). The assistant knows this and will remind you.
- **Versions.** With a local checkout the plugin reads that checkout. Without one it reads `main` by default. Ask it to call `get_toolbox_version` and state your installed version; use a matching checkout, or set `TI_TOOLBOX_REF=v2.5.0` for remote legacy documentation.

## Privacy and safety

- The knowledge tools are read-only. The job tools only copy raw scans into `sourcedata/` (never overwriting), propose plans for your approval (or, if you allowed it, submit jobs), and follow or cancel jobs through the running app; they never delete files, and replacing a result needs your explicit yes.
- Project inspection only lists directory and file names — it never opens imaging data.
- Source/doc access is restricted to approved repository trees and manifests, including `tit/`, `desktop/src/`, `desktop/tests/`, `contracts/`, `agent-plugin/`, docs and scripts.
- Set `TI_TOOLBOX_OFFLINE=1` to forbid network access entirely (requires a local clone).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "MCP server failed to start" | Run `python3 --version` (needs 3.9+). On Windows use `python` instead of `python3` in the config. |
| Tools return "HTTP 403/429" | GitHub rate limit for unauthenticated requests; wait a few minutes or clone the repo and set `TI_TOOLBOX_ROOT`. |
| `find_symbol` / `search_source` say they need a local checkout | Those two tools grep the source tree; clone the repo and set `TI_TOOLBOX_ROOT=/path/to/TI-Toolbox`. |
| Stale answers | Delete the cache: `rm -rf ~/.cache/ti-toolbox-mcp`. |
| "No running TI-Toolbox found" | Open the desktop app on your project (or run `tit launch`), then ask again. |
| "docker was not found on PATH" | Add Docker's folder (`which docker`) to the job server's environment in your assistant's MCP settings, or use the desktop app's **Assistant** page, which needs no Docker on the `PATH`. |
| The assistant says its job was refused (HTTP 403) | Approval is on: it should propose a plan instead; look for the card on the **Jobs** page. |
| A plan card shows "Cannot run as proposed" | A step has an error or a missing input (often: pre-process first). Reject it with a note, or edit the step. |
| Assistant page says "not installed" although it works in your terminal | TI-Toolbox reads the `PATH` of a login shell. Make sure the folder holding `claude`/`codex` is added in your shell profile (`~/.zprofile`, `~/.zshrc` or `~/.bashrc`), then click **check again**. |

For the plugin's internals (skills layout, server architecture, tests), see [Agent Plugin Internals]({{ site.baseurl }}/wiki/agent-plugin/).
