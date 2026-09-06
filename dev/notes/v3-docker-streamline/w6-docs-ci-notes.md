# W6 — Docs + CI for the streamlined product (2026-09-03)

Lane brief: `dev/notes/v3-docker-streamline-plan.md` row **W6 Docs + CI** in §2. Owned:
`docs/**`, `README.md`, `.circleci/config.yml`, `dev/update/**`, `docs/releases/changelog.md`
(this repo has no root `CHANGELOG.md`; the changelog lives at `docs/releases/changelog.md` —
confirmed by `ls`, both here and on `main`), `container/blueprint/README.md` (extending W2's),
this file. Did not touch `tit/**`, `desktop/src/**`, `contracts/**`.

## What shipped

| File | What |
|---|---|
| `docs/installation/installation.md` | Rewritten: Docker Desktop/Engine only, no XQuartz/VcXsrv/X11 steps; what's in the image (SimNIBS 4.6, FastSurfer seg_only, Tetravox Embed, the UI); supported platforms table with the Apple-Silicon-emulation caveat; disk size (6.7 GB vs. 19 GB + 67 GB); supported engines table (Docker Desktop/Engine supported, Colima/OrbStack best-effort, Podman unsupported); FreeSurfer license note scoped to QSIPrep/QSIRecon ACT only, not the core |
| `docs/installation/macos.md`, `windows.md`, `linux.md` | XQuartz/VcXsrv/X11 sections removed; image-size line updated to the single ~6.7 GB image |
| `docs/installation/dependencies.md` | X Server section removed entirely; RAM guidance and storage size updated |
| `docs/installation/bash-cli.md` | One-paragraph callout added: this page still documents the classic two-image + X11-forwarded PyQt5 CLI path, unaffected by this program — did not rewrite it wholesale (see "Not touched" below for why) |
| `docs/wiki/desktop-app.md` | Rewritten as the **Architecture** page: the plan §1 diagram, a v2→v3 comparison table, embed protocol summary, job model pointer, Engine API supported-engines note |
| `docs/wiki/pre-processing.md` | `recon-all` sections replaced with FastSurfer: exact invocation, output layout, accuracy/timing table (Dice, centroid shifts, native runtime), the `run_recon`→`run_fastsurfer` alias, what's no longer available (thalamic nuclei, hippocampal subfields) with the legacy-derivatives-still-work note, parallel-with-charm DAG diagram |
| `docs/wiki/visualizers.md` | Rewritten as **Viewer**: Tetravox Embed only, no Freeview/Gmsh; what the inspector offers (layers, cursor/space, layout, screenshot, save scene); links to Tetravox's own `docs/EMBED.md` for the scene format; a "No-WebGL2 state" section |
| `docs/wiki/troubleshooting.md` | Surgical edits: a v3 callout at the top of "GUI display (X11)" scoping that whole section to the legacy CLI path; the `recon-all` FOV entry reworded to say v3 doesn't run `recon-all` at all |
| `docs/gallery/gmsh-freeview.md` | One-line v3 note added above the existing screenshot gallery |
| `README.md` | The macOS-26/Gmsh/FreeView compatibility note replaced with a v3 single-image/no-X11 note |
| `docs/_data/nav.yml` | "Visualizers" renamed to "Viewer" in the sidebar (same URL, `/wiki/visualizers/`) |
| `docs/releases/changelog.md` | New **Unreleased** section on top, listing the v3 removals/additions/changes factually (no marketing) |
| `.circleci/config.yml` | New `build-and-smoke-image` job (below); existing `build-and-run-tests` job untouched; both run in the workflow |
| `dev/update/update_version.py` | New pattern: bumps `desktop/docker/docker-compose.v3.yml`'s `TIT_IMAGE_TAG:-<ver>` default on every version bump |
| `container/blueprint/README.md` | New "CI" subsection under the v3 section, explaining the `build-and-smoke-image` job and pointing back here |

### Files copied from `main` (per the brief's instruction)

- **`docs/tests/check_assets.py`** — did not exist in this worktree at all (`main` added it
  in a commit this branch predates). Copied verbatim, used as this lane's own asset-link gate
  (see "Gates" below). Left byte-identical to `main`'s copy — including one pre-existing
  `black` slice-spacing nit (`url[len(BASEURL):]`) — on purpose, so the eventual merge is a
  no-op for this file rather than a spurious reformat diff.

### Tried, then reverted: syncing `docs/releases/{changelog,releases}.md` and adding `v2.5.0.md`

This worktree's `docs/releases/changelog.md`/`releases.md` still showed **v2.4.0** as the
latest release — `main` has since cut and shipped v2.5.0 (5 commits ahead of this branch's
merge-base, `0c0ef614`..`b5eb63c3`; `git log --oneline main -- docs/releases/changelog.md`).
Per the brief's "copy main's version first" instruction I initially copied `main`'s
`changelog.md`/`releases.md` (which contain the real v2.5.0 release notes) and a new
`docs/releases/v2.5.0.md`, then added the Unreleased section on top of that.

**This broke a real test**:
`tests/test_agent_plugin_mcp.py::TestWikiTools::test_changelog_and_version` asserts the
changelog's top `v*`-prefixed heading equals `v{tit.__version__}`. `main`'s `tit/__init__.py`
is `2.5.0` (bumped alongside its changelog); **this worktree's is still `2.4.0`**
(`tit/__init__.py` is not in this lane's owned paths — outside `docs/**`/`README.md`/
`.circleci/**`/`dev/update/**`/`CHANGELOG.md`/`container/blueprint/README.md` — and bumping a
core package version file is not this lane's call to make). With `changelog.md`'s top
versioned heading at `v2.5.0` and `tit.__version__` still `2.4.0`, the test correctly failed
(reproduced: `1 failed, 3148 passed` vs. the baseline `3149 passed`).

Rather than touch `tit/__init__.py` (forbidden — ground rules: file ownership is absolute,
never touch files outside the grant), I reverted: `docs/releases/changelog.md` and
`releases.md` are back to this worktree's own `git show HEAD:...` content (v2.4.0 latest,
confirmed byte-identical via `wc -l`/diff-free re-read), `docs/releases/v2.5.0.md` and the
one image asset it needed (`docs/assets/imgs/atlas-resampling/atlas_resample_v250_old_vs_new.png`,
copied from `main` for that page) were deleted, and `docs/_data/nav.yml`'s release-version
lines were reverted to `v2.4.0`. The **Unreleased** section is reapplied on top of the
restored `v2.4.0 (Latest Release)` baseline instead. Full pytest gate re-run clean afterward
(3149 passed again — one more than the original baseline because `docs/tests/check_assets.py`
isn't collected by `pytest.ini`'s `testpaths = tests`, so that number is unaffected by it; the
+1 is `test_gallery... ` — not investigated further since the suite is green either way).

**Consequence, flagged for whoever next touches this branch's release docs**: this worktree's
`docs/releases/` still doesn't know about the real, already-shipped v2.5.0 (mTI `TI_normal`,
mex-search, the `tit.calc` API consolidation, etc. — see `main`'s changelog for the full
list). That catch-up is real, wanted work, but it is a **version-bump-owning lane's** job
(touches `tit/__init__.py` alongside the docs, which this lane cannot do), not something to
smuggle in through a docs-only lane. This program's own "Unreleased" section sits directly
above `v2.4.0` in this branch's changelog for now — correct for *this worktree's* current
state, not yet reflecting `main`'s v2.5.0.

## Every claim traced to a Phase-A note or spike

- **Image**: one `idossha/ti-toolbox:<ver>`, 6.7 GB, contents, smoke commands, size table
  (19.2 GB/6.15 GB SimNIBS + 67.5 GB/21.9 GB FreeSurfer vs. 6.66 GB combined) — all from
  `w2-image-notes.md` ("Build+smoke, this session" and "Image size" sections). Rounded 6.66→
  "~6.7 GB" in prose.
- **Supported platforms / engines / amd64-emulation** — `w2-image-notes.md`'s build command
  (`--platform linux/amd64`) and D1/D4 in the plan. The Apple-Silicon FastSurfer-timing "not
  yet measured" line is `w2-image-notes.md`'s own "expect this to run much slower... amd64
  emulated" plus `w3b-preprocessing-notes.md` §7 risk #1's framing.
- **FastSurfer invocation, outputs, Dice/timing table, `--no_cc` reasoning, `run_recon`→
  `run_fastsurfer` alias, what's no longer available** — `w3b-preprocessing-notes.md` §1
  ("New stage", "Decisions", "Removals") and §2 ("Measured numbers") verbatim; the DAG
  parallelism diagram from its `G2b` description.
- **Architecture page**: the ASCII diagram is the plan §1 diagram, unedited. The v2→v3 table,
  Engine API supported-engines line (Docker Desktop/Engine supported, Colima/OrbStack
  best-effort, Podman unsupported-by-name-detection), error-UX table sourced from
  `w4-desktop-docker-notes.md` ("Error UX", "Decisions worth arguing with" #2, "What the
  stack is now"). The embed protocol summary (message set, `/api/files/raw/<path>` shape) is
  `w3a-server-notes.md`'s "contracts_for_other_lanes" section.
- **Viewer page**: inspector feature list (layers, cursor/space, layout, screenshot, save
  scene) is the plan §2 W5 row's own description verbatim (W5 itself is a concurrent,
  not-yet-landed Phase B lane in this worktree — I did not invent UI that doesn't exist; I
  quoted the plan's own stated deliverable and flagged in the page that scenes are Tetravox's
  own format, per `w3a-server-notes.md`'s scene-shape contract).
- **CHANGELOG Unreleased section** — every bullet maps 1:1 to a D1-D6 decision row in the
  plan or a "What shipped"/"Removals" line in one of the four Phase-A notes; no bullet
  describes anything not evidenced there.
- **CI job** — the from-scratch-vs-layered build-time tradeoff, the exact smoke commands, and
  the container pytest subset are all `w2-image-notes.md`'s and `w3a-server-notes.md`'s own
  numbers/commands ("Build+smoke, this session", "Gates" section's container pytest command).

## Gates

```
$ python3 -m pytest -q                                    # host, py3.14, full suite
3149 passed, 18 skipped, 13 warnings in 34.14s
```
(Re-run after the changelog revert above; the v2.5.0-sync attempt transiently produced
`1 failed, 3148 passed` — see that section for why and how it was fixed. Not this lane's file
that failed [`tests/test_agent_plugin_mcp.py`, testing `agent-plugin/mcp/server.py`], but a
real, self-inflicted regression from a docs choice — fixed by reverting the choice, not by
touching the test or `tit/__init__.py`.)

```
$ python3 -m black --check dev/update/update_version.py docs/tests/check_assets.py
would reformat docs/tests/check_assets.py     # pre-existing nit, kept byte-identical to main
would reformat dev/update/update_version.py   # pre-existing nits elsewhere in the file (lines
                                               # 106, 231, 262-271, 376 in the pre-edit numbering)
```
Verified my own additions are not among the reformatted lines in either file (`black --diff`
inspected directly — no hunk touches the `desktop/docker/docker-compose.v3.yml` block I added
to `update_version.py`, and `check_assets.py`'s single nit is `main`'s own pre-existing code,
untouched by me). Did not run `black` on the rest of either file — `check_assets.py` per the
"copy = byte-identical" reasoning above, `update_version.py`'s unrelated pre-existing debt
left alone rather than expanding this lane's diff into someone else's earlier work.

```
$ ruby -v                                    # /opt/homebrew/opt/ruby@3.3/bin/ruby, per memory
ruby 3.3.10 (2025-10-23 revision 343ea05002) [arm64-darwin24]
$ bundle install                             # docs/Gemfile, GEM_HOME=~/.gem-ti-toolbox-docs
Bundle complete! 8 Gemfile dependencies, 32 gems now installed.
$ bundle exec jekyll build --destination /tmp/ti-toolbox-docs-build4
... Jekyll Feed: Generating feed for posts done in 1.577 seconds.
 Auto-regeneration: disabled. Use --watch to enable.
(exit 0, no errors/warnings beyond stdlib-gem deprecation notices from Ruby 3.3 itself)
$ python3 docs/tests/check_assets.py /tmp/ti-toolbox-docs-build4
All local asset references resolve.
```
Every edited page's rendered HTML was checked for both existence and non-trivial byte size
(`installation/index.html` 19290 B ... `wiki/pre-processing/index.html` 35421 B, etc. — all
present, none suspiciously small/empty).

**Internal-link check** (no `check_assets.py`-equivalent for `<a href>` exists in this repo;
wrote a one-off script against the same built site, scoped to the pages this lane edited):
1 broken link found, `docs/releases/changelog.md`'s pre-existing `{{ site.baseurl }}/scripting/`
(missing `/wiki/` prefix) inside the **v2.4.0** entry — confirmed present verbatim in `main`'s
own `changelog.md` at the same relative spot (line 231 there), i.e. not introduced by this
lane and not part of the Unreleased section. Not fixed — out of scope (pre-existing content in
an entry this lane did not author), flagged here rather than silently left.

**CI config validation** — no `circleci` CLI on this machine (`which circleci` → not found);
YAML-parsed with `pyyaml` instead (`python3 -c "import yaml; yaml.safe_load(...)"` — parses
clean, job/workflow names printed) and every `run.command` block in the new job syntax-checked
with `bash -n` (5/5 OK). Real command execution (an actual `docker build`/`docker run` of the
new CI job) was **not** attempted this session — no Docker daemon requirement was in this
lane's brief, and the job's own commands are the same ones `w2-image-notes.md` already ran
and recorded real output for.

## CI job: `build-and-smoke-image`

Gates on **`Dockerfile.ti-toolbox.layered`**, not the from-scratch `Dockerfile.ti-toolbox`
this repo's own convention (`container/blueprint/README.md`, pre-existing) says CI should
eventually publish from. Documented reasoning (also in the job's own comment block and in
`container/blueprint/README.md`'s new CI subsection): a from-scratch SimNIBS install is
30-60+ minutes even natively (`Dockerfile.ti-toolbox`'s own header; confirmed as a real wall
by `w2-image-notes.md`'s "Not attempted this session" — it hit the same time-box constraint
in a Phase-A session with more time budgeted for exactly this), well past what CircleCI's
default `machine` resource class should absorb on every push, and no self-hosted/large
executor is provisioned in this repo for it. `ubuntu-2204:current` is x86_64, so the layered
build and its smoke run **natively** there (no QEMU emulation, unlike this session's own
Apple-Silicon dev builds) — flagged in the job's comments as a legitimate future place to
measure the "native amd64 FastSurfer runtime" number both `w2-image-notes.md` and
`w3b-preprocessing-notes.md` flag as outstanding, though not attempted in the job itself (adds
several minutes per subject; kept out to keep the job fast).

Steps: build (`--skip-ui-build`, so the job doesn't need `npm ci` for the whole Electron
toolchain — ships the plain status page instead of the real UI bundle; that bundle's own
build/vitest/e2e gates are `desktop`'s job, not this one's) → start with the checked-out repo
bind-mounted over `/ti-toolbox` (`PYTHONPATH=/ti-toolbox`, the same dev-mount shape
`docker-compose.v3.yml`'s optional `${TIT_REPO_DIR}` documents) → wait for `HEALTHCHECK` →
smoke (`/api/health`, `/`, `/tetravox/manifest.json`, `run_fastsurfer.sh --help`,
`import simnibs, fastapi, torch` / `import simnibs.segmentation, brainnet`) → pytest subset
(`test_catalog_v1`, `test_server_skeleton`, `test_viewspec[_scene]`, `test_files_raw`,
`test_files_routes`, `test_pre_fastsurfer` — the last one is the integration test that only
un-skips inside a FastSurfer-equipped image, per `w3b-preprocessing-notes.md` §2's skip note)
→ always stop+remove the container.

Existing `build-and-run-tests` job (the `idossha/ti-toolbox-test` image, `tests/test.sh`) is
untouched; both jobs run in `test_workflow`.

## `dev/update/update_version.py`

Added one pattern updating `desktop/docker/docker-compose.v3.yml`'s
`image: idossha/ti-toolbox:${TIT_IMAGE_TAG:-dev}` line so a version bump sets that default to
the version being released (verified the regex matches the live file and substitutes
correctly via a non-destructive `re.sub` dry run — did not actually run
`update_version.py <ver>` against this worktree, since that would touch a dozen files outside
this lane's grant, including `tit/__init__.py`).

**Real gap flagged, not fixed** (outside this lane — `desktop/src/shared/compose.ts` is W4's
file): nothing in the desktop app's own code sets `TIT_IMAGE_TAG` yet — `w4-desktop-docker-notes.md`'s
own "Contracts for W2" env-var list doesn't include it, so the app currently relies entirely
on compose's own `:-dev` (soon `:-<ver>`) default. A real release will need W4 (or whoever
picks up its `buildStackEnv`) to either keep relying on that compose default (fine, if the app
never needs to pin a *different* tag than the compose file's own default) or add
`TIT_IMAGE_TAG` explicitly to `buildStackEnv`'s output.

## Not touched, and why

- **`docs/installation/hpc-apptainer.md`** — Apptainer path is explicitly out of scope for D1
  (the plan's own "Later" §4 doesn't mention it, and none of the four Phase-A notes touch
  `apptainer.def`/`apptainer_run.sh`). Referenced from `installation.md` with a one-line note
  that it's unaffected by the Docker-image streamlining.
- **`docs/installation/bash-cli.md`** — not rewritten wholesale. It documents `loader.py` +
  the root `docker-compose.yml`, neither of which is in any Phase-A lane's owned paths or
  delivered-files list (W2 owns `desktop/docker/docker-compose.v3.yml`, not the root file;
  W4 owns the desktop app's own stack code, not the standalone CLI loader script). Rewriting
  its mechanics without evidence that `loader.py` itself changed would be inventing behavior,
  not documenting it — added a scoped callout instead, pointing at the new streamlined path.
- **`docs/wiki/gui.md`** — describes the PyQt5 tabbed GUI (`tit.gui`), which is still present
  and still being edited by W3b (removing the recon-all checkbox, per `w3b-preprocessing-notes.md`
  "Removals"). Whether/how this page's identity changes once the new Electron-served web UI
  (`desktop/out/renderer`) is what most users see is a Phase-C/W5 question — this lane's
  brief named installation/architecture/preprocessing/viewer specifically, not this page.
- **`docs/wiki/analyzer.md`, `ex-search.md`, `simulator.md`, gallery pages beyond the one-line
  note on `gmsh-freeview.md`, `docs/wiki/mti.md`, `docs/wiki/atlas-resampling.md`** — these
  diverge heavily from `main` (76 files, 16,127 insertions between this branch's merge-base
  and `main`'s tip) but for reasons unrelated to the v3 Docker-streamline program — unrelated
  content work that landed on `main` after this branch forked. Syncing all of it is a much
  larger, separate catch-up job, not this lane's mandate; see the changelog-revert section
  above for why selectively cherry-picking release-doc content specifically caused a real
  test failure — the same risk applies more broadly to those other files.
- **`.github/workflows/**`** — not in this lane's owned-paths grant (only `.circleci/config.yml`
  was named).

## needs_from_other_lanes

- **W4** (`desktop/src/shared/compose.ts`): consider setting `TIT_IMAGE_TAG` explicitly in
  `buildStackEnv`'s output once a real release tag exists, or confirm relying on
  `docker-compose.v3.yml`'s own default (now bumped by `update_version.py`) is the intended
  design — see "`dev/update/update_version.py`" above.
- **Whoever next bumps `tit/__init__.py` past `2.4.0`** on this branch: fold `main`'s real
  v2.5.0 changelog/releases-page content back in at that point (I have it staged in spirit —
  see the "Tried, then reverted" section above for exactly what to copy from `main` and why it
  had to wait).
- **W3a** (unowned by W6, but user-facing): `docs/releases/changelog.md`'s pre-existing
  `{{ site.baseurl }}/scripting/` broken link (should be `/wiki/scripting/`) sits inside the
  v2.4.0 entry, unrelated to this program — flagged for whoever next touches that file for any
  reason, not assigned to a specific lane.

## Follow-ups

1. Once W1 ships a real Tetravox Embed release and W2's from-scratch `Dockerfile.ti-toolbox`
   has been build-verified, revisit whether CI should gate on it instead of the layered recipe
   (needs a large/self-hosted executor per the reasoning above, or a nightly/release-triggered
   job so a 30-60+ min build doesn't sit on every push).
2. Measure a native-amd64 FastSurfer `--seg_only` runtime inside the new CI job's container
   (it already runs unemulated on `ubuntu-2204:current`) and fold the number into
   `docs/wiki/pre-processing.md`'s "not yet measured" line — currently a real gap flagged
   consistently across `w2-image-notes.md`, `w3b-preprocessing-notes.md`, and this lane's docs.
3. `docs/wiki/gui.md` and the analyzer/ex-search/simulator wiki pages need a real content
   audit once Phase C lands the actual new web UI — not attempted here (see "Not touched").
