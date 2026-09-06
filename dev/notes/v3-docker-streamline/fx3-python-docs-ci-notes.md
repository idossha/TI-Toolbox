# FX3 fix lane — Python, docs, CI (2026-09-03)

Fix lane closing 9 findings from the three QA reviews in this directory
(`qa-security-notes.md` = "engineer", `qa-neuro-researcher-notes.md` = "researcher",
`qa-senior-product-designer-notes.md` = "designer" — this lane's findings are all from the
first two). Time-boxed ~75 minutes; all 9 closed. No git commit/checkout/stash/reset/clean/
restore run, per the brief. No window ever put on this Mac's screen — the one Electron-adjacent
check (the new CI job) was validated via `circleci config validate`/`config process` and
`bash -n` only, never actually run locally.

## 1. `HEAD /` returns 405 (engineer finding 4)

`tit/server/static.py`: added `@router.head("/{path:path}", ...)` beside the SPA catch-all
`serve()`, matching the pattern R2 already used for `/tetravox/*` (same APIRoute
HEAD-inference gap; `FileResponse`/`HTMLResponse` already answer HEAD correctly with no
separate handler). Test: `tests/test_server_skeleton.py::test_spa_head_matches_get_headers_with_no_body`
(bundle SPA route, client-side route, static asset, and the no-bundle status page all
`HEAD`/`GET` compared for identical status + `content-length`, empty body).

## 2. Thalamic-nuclei ROI regions resolve to "Label 8103" (researcher finding 2)

**Deviated from the brief's suggested primary source, with evidence.** The brief proposed
pairing `ThalamicNuclei.v13.T1.volumes.txt`'s name list against the segmentation's own sorted
unique voxel-label ids "in order." I verified this against sub-ernie's real derivatives and two
other real subjects' `ThalamicNuclei.v13.T1.mgz`/`.volumes.txt` pairs (paths outside this repo,
under `/Users/idohaber/datasets/000` and two datasets under `/Volumes/IDO2`) and it does **not**
work: `volumes.txt`'s name order is anatomically grouped (LGN, MGN, PuI, PuM, L-Sg, VPL, CM, ...),
not numeric-id order, and — more importantly — the *set* of ids actually carrying voxels differs
per subject (small nuclei like Pc/id 8117 and Pt/id 8119 are each independently absent in some
subjects and present in others: ernie has 8117 but not 8119, a second subject had the reverse).
Naively zipping the two lists by position, as literally suggested, silently produces wrong names
(it would read id 8103 as "LGN"; the real name is "AV") — worse than the status quo, not better.

**What shipped instead**: fetched FreeSurfer's own authoritative table from
`https://raw.githubusercontent.com/freesurfer/freesurfer/dev/distribution/FreeSurferColorLUT.txt`
(the section headed "Labels for thalamus parcellation using histological atlas (Iglesias et
al.)", ids 8103-8136/8203-8236) and vendored it as `resources/atlas/ThalamicNuclei_LUT.txt`,
with a header citing the source, the Iglesias et al. 2018 NeuroImage reference (DOI
10.1016/j.neuroimage.2018.08.012, confirmed via a live web search, not from memory), and the
verification note above. `tit/atlas/segstats.py::resolve_lut_for_atlas` now special-cases the
`ThalamicNuclei*` atlas family (both `.v13.T1.mgz` and its `.FSvoxelSpace` sibling) onto this
table, tried after any real atlas-specific sidecar and before the general
`FreeSurferColorLUT.txt` fallback. Verified all 48 of sub-ernie's real label ids resolve to a
real name (zero missing, zero `"Label N"` placeholders) — script output and the exact id list are
in `tests/test_atlas_segstats.py::TestThalamicNucleiLut::test_all_48_real_ernie_label_ids_...`.
`resources/atlas/README.md` gets a matching section. 6 new tests.

**Not done**: did not implement any runtime read of `.volumes.txt` at all (see above — it cannot
correctly supply the id mapping, so there was nothing safe to build with it). If a future
FreeSurfer release changes this atlas's id assignment, the vendored table would need a
re-fetch — flagged here rather than silently trusted forever.

## 3. Raw layer names in the viewer (researcher finding 4)

`tit/viewspec.py`: `to_tetravox_viewspec` now calls a new `_scene_display_name(name, role=,
field_name=)` for each layer's `name` field (the dataset's own `name` — the real basename — is
untouched, per the brief). Renamed `_scene_mesh_field` → `_scene_field_name` (same logic, now
also used to name a non-mesh field volume, not only a mesh). Grammar, matching the brief's
examples exactly:

| shape | example |
|---|---|
| base T1 | `T1` |
| electrode overlay | `Electrodes` |
| atlas overlay | `Atlas` |
| bare field volume | `TI_max (volume)` |
| `grey_`/`white_` field volume | `GM · TI_max (volume)` / `WM · TI_max (volume)` |
| bare field mesh | `Mesh · TI_max` / `Mesh (tags)` |
| `grey_`/`white_` field mesh | `GM mesh · TI_max` / `WM mesh · TI_max` / `GM mesh (tags)` |
| anything unrecognised (e.g. an analysis ROI overlay, a `custom`-view file outside this
  grammar) | unchanged — today's plain basename stem |

Only ever replaces a name once the shape is understood; never invents one for something it
doesn't recognise (so an ROI overlay like `roi_overlay.nii.gz` still shows as `roi_overlay` —
out of scope for this finding, which was about the pipeline's own TI-simulation output names).

Updated: `tests/test_viewspec_scene.py` (renamed the `_scene_mesh_field` reference, replaced the
raw-stem assertions in `test_scene_volume_and_mesh_colormaps`,
`test_scene_field_scale_falls_back_when_the_volume_cannot_be_read`, and
`test_scene_mesh_visibility_matches_viewspec` with the curated names) — all pass, including the
schema validation (`contracts/tetravox-viewspec-v2.schema.json`) every scene test already runs
through.

`desktop/tests/mock-server/server.mjs` — the JS 1:1 port of `to_tetravox_viewspec` — got the
identical port: `sceneMeshField` → `sceneFieldName` (same rename), a new `sceneDisplayName`
function line-for-line matching `_scene_display_name`, wired into `sceneFor` the same way.
`npx vitest run tests/mock-server` passes (21/21).

`desktop/tests/fixtures/scene_ernie_thalamus.json`: this fixture turned out to be **orphaned** —
`rg` found zero importers anywhere in `desktop/` — and is in the old, retired "TitScene" (v1)
shape (`role`/`window`/`isLabel`/`lazy` fields), not the real v2 `ViewSpec` `sceneFor` builds.
Updated its layer `name` fields to the same curated values anyway (mechanical, low-risk, and the
brief named this file explicitly), but flagging here that it is dead weight independent of this
change — worth someone confirming it can be deleted in a later cleanup, since it currently reads
as a live reference fixture and isn't one.

## 4. `run_recon` migration warns only to the log (researcher finding 5, low)

`tit/pre/config.py::migrate_legacy_keys` gained an optional `warnings: list[str] | None = None`
kwarg — when given, every deprecation message is appended there in addition to the existing log
line (same message text, so nothing about the log-only behavior for other callers changed).
`tit/server/routes/plan.py`'s `POST /api/plan/{kind}` (kind == "pre") now passes its own
`warnings` list through, so the migration shows up in the HTTP response's `warnings` field, not
only server-side logs. Tests: 2 new cases in `tests/test_pre_config_migration.py` (the
`warnings=` kwarg collects the same messages the logger gets; omitting it still works, unchanged
from before) + 1 new case in `tests/test_plan_routes.py`
(`test_plan_pre_legacy_run_recon_key_surfaces_a_response_warning`, hits the real route with a
legacy `run_recon` config and asserts the response's `warnings` array names both the old and new
key).

## 5. `analyzer.md` lists legacy-only atlases with no caveat (researcher finding 3)

`docs/wiki/analyzer.md`'s "Voxel atlases" bullet now leads with
`aparc.DKTatlas+aseg.deep.mgz` (the actual FastSurfer filename every current-pipeline subject
gets — the old bullet never mentioned it at all) and `segmentation/labeling.nii.gz`, then names
the other five listed filenames explicitly as legacy-`recon-all`-only, with a cross-reference to
`pre-processing.md#what-changed-from-freesurfer`. Verified against `tit/atlas/constants.py`
(`FASTSURFER_ATLASES`/`LEGACY_FREESURFER_ATLASES`) that the five previously-listed filenames were
in fact *exactly* the legacy set, unmodified — confirmed the finding, not just documented around
it. Cross-reference anchor verified against a real Jekyll build (kramdown auto-id
`what-changed-from-freesurfer` on the real `pre-processing.md` heading — see gate section).

## 6. Image size "21.3 GB vs 6.7 GB" (researcher finding 6, flagged for confirmation only)

Reconciled, not a bug in either number. Measured on this machine, read-only (no container
started/stopped):

```
$ docker images idossha/ti-toolbox:dev
IMAGE                    ID             DISK USAGE   CONTENT SIZE   EXTRA
idossha/ti-toolbox:dev   317621083ac2       21.3GB         6.67GB   U

$ docker system df -v | grep idossha/ti-toolbox
idossha/ti-toolbox   dev   ...   21.3GB   13.09GB (shared)   8.237GB (unique)
```

Modern Docker Desktop's `docker images` (no `--format`) now prints *two* columns —
"DISK USAGE" and "CONTENT SIZE" — and the researcher's number is the first one. Content size
(6.67 GB) matches the docs' and `w2-image-notes.md`'s own 6.66-6.7 GB figure almost exactly.
Disk usage (21.3 GB) is real too, and `docker system df -v` explains it: `idossha/simnibs:v2.5.0`
(the `.layered` recipe's base image) is independently cached on this machine again, and
`idossha/ti-toolbox:dev` now shares 13.09 GB of base layers with it — the identical pattern
`w2-image-notes.md` already documented for the base image itself (19.2 GB disk / 6.15 GB
content), just not visible on `ti-toolbox:dev` at the moment that note was written (a genuinely
fresh, isolated build, with no other locally-cached image sharing its base). Updated both
locations rather than picking one number:

- `docs/installation/installation.md`'s "Disk size" section: content size (6.7 GB) is now stated
  as *"what a fresh `docker pull` downloads"*, with an explicit paragraph on why `docker images`
  can show a larger number locally and that it isn't a sign of bloat. Also added the SimNIBS
  base image's own two numbers for the same reason, matching how the FreeSurfer-image comparison
  already worked.
- `dev/notes/v3-docker-streamline/w2-image-notes.md`: appended an addendum (not a rewrite of W2's
  own text) recording today's re-measurement and explaining why the "single fresh build, both
  numbers agree" line no longer holds on this machine — expected, not a regression.

**Docs build gate caught a real bug this introduced**: the literal `{{.Size}}` /
`{{println .}}` Go-template syntax in the new `docker inspect --format` examples collided with
Jekyll's Liquid templating (`{{ }}` is Liquid's own interpolation syntax) — a real
`Liquid Warning: Liquid syntax error` on the first build attempt, not a false alarm. Fixed by
wrapping both inline-code spans in `{% raw %}...{% endraw %}`; rebuilt clean (0 warnings) and
spot-checked the rendered HTML actually contains the literal `{{.Size}}` text, not something
Liquid ate. Worth remembering for any future doc mentioning a Go `--format` template.

## 7. Bearer token readable via `docker inspect` (engineer finding 3)

`docs/installation/installation.md` gained a "Docker access is a trust boundary" section: one
factual paragraph naming the mechanism (`docker inspect`/`docker exec ... env`/
`/proc/<pid>/environ` all show the token in plaintext to anything with Docker socket access),
that this is a no-op on a single-user machine (socket access is already root-equivalent), and
that on a shared multi-user host it is a real cross-user disclosure — worth an admin knowing
before adding mutually-untrusted accounts to the same `docker` group.

**Follow-up opened here, not in code** (per the brief — "open a follow-up for per-attach token
rotation in the notes"): the engineer's proposed hardening — rotate the token on each
`stack.ts::tryAttach`, or require the connecting client to additionally prove host-side
knowledge unavailable to a mere `docker inspect` (e.g. a per-invoking-user file under that user's
own `userData` dir, `0600`, checked alongside the env-derived token) — is real desktop-app work
(`desktop/src/main/stack.ts`), out of this lane's owned paths and out of a 75-minute time box.
Whoever owns `desktop/src/main/docker/**`/`stack.ts` next should pick this up; the installation
doc above at least makes the current trust boundary explicit for anyone deploying on a shared
host in the meantime.

## 8. No desktop CI (engineer finding 2)

Added a `desktop-checks` job to `.circleci/config.yml`, wired into `test_workflow` alongside the
two existing jobs. Runs on the same `vm-docker` (`ubuntu-2204:current`) executor the other two
jobs already use (chosen over a lighter `docker:` executor: this job needs a real X11-capable
Linux userspace for Electron to start at all, which is most of what `playwright install-deps`
would need to add to a minimal image anyway — no real savings, and `vm-docker` is the one
executor type already proven to work on this project).

Steps: install Node 22 via the machine image's own `nvm` (package.json's `engines.node` is
`>=22.12.0`) → restore/save an `~/.npm` cache keyed on `desktop/package-lock.json`'s checksum
(not `node_modules` itself — `npm ci` always wipes and reinstalls it by design, so the npm
download cache is what caching actually helps) → `npm ci` → `npm run typecheck` → `npm run lint`
→ `npx vitest run` → `npm run build` → install Xvfb + `npx playwright install-deps chromium`
(Electron bundles Chromium, so the same OS libraries Playwright's own Chromium needs are what
Electron needs to start) → `xvfb-run -a npm run e2e` under `TIT_E2E_OFFSCREEN=1` → artifacts
(`desktop/test-results`, `when: always`).

`npm run e2e:quiet` itself is **not** what CI runs — it stays macOS-only by its own header
comment (*"macOS only -- it is the platform with the monitor to hijack (Linux CI runs under
Xvfb)"*), which this job's own top comment quotes and explains: CI runs the plain `npm run e2e`
it wraps, under Xvfb, because Electron's Chromium backend needs a real X display to initialize at
all even with the app's own offscreen flag set (a window built but never shown is not the same
as no window server existing) — so Xvfb supplies one rather than skipping the offscreen
guarantee's e2e suite in CI.

**Validation performed** (brief: "validate the YAML (circleci CLI if present, else a YAML
parse)"): installed the `circleci` CLI fresh via Homebrew (was not present) —
`circleci config validate .circleci/config.yml` passes, and `circleci config process` was also
run to confirm the whole file expands with no reference errors (workflow lists all three jobs,
`store_artifacts`'s `when: always` is accepted). `bash -n` run against every `command:` block in
the file (17 blocks — all 3 jobs, not just the new one) via a small PyYAML-based extractor — 0
failures. Not run live against an actual CircleCI Linux box in this session (no such environment
available) — the YAML/shell mechanics are verified, not a real end-to-end pass of the new job.

## 9. `docker_engine.py`'s stale docstring about `docker_builder` labels (engineer finding 7, low)

Three docstrings (module docstring, `run_job_container`, `run_qsiprep_example`) claimed
`tit/pre/qsi/docker_builder.py` "never sets" the `tit.job_id` label — false today:
`docker_builder.py`'s own `_label_args()` sets it on both the `qsiprep` and `qsirecon` `docker
run` invocations (confirmed: `rg -n "tit\.job_id" tit/pre/qsi/docker_builder.py` → 2 hits, not
0). Updated all three to state what's actually still open instead: `docker_builder.py` still
shells out to the `docker` CLI directly rather than through this Engine API client (that gap is
real, tracked separately by W2/W3b's own notes and the engineer's finding 7 in this same review —
not fixed here, out of this item's scope).

**Ran `black` on the whole file**, not just the touched docstring lines: the file (marked
"(comment)"-only in this lane's ownership) had substantial pre-existing non-black-formatted code
(long unwrapped call signatures in `logs`/`events`/`create_container`/etc., none of it touched by
this fix) that made `black --check` fail on the file regardless of my own edits, and the stated
gate is "black on touched files." Whole-file `black` is purely mechanical (no semantic change —
confirmed by re-running the full host pytest suite after, still 3159 passed) and this file has no
other current owner in the three QA reviews or the lane table beyond this "(comment)" grant, so
the collision risk of reformatting lines I didn't author was judged low. Flagging the deviation
explicitly in case another lane is mid-edit on this file and sees an unexpected whitespace-only
diff.

## Gate results

- `python3 -m pytest -q` (host): **3159 passed, 18 skipped, 0 failed** (full suite, not just
  touched modules).
- `black --check` on all touched Python files: clean (`tit/server/static.py`,
  `tit/jobs/docker_engine.py`, `tit/pre/config.py`, `tit/server/routes/plan.py`,
  `tit/atlas/segstats.py`, `tit/viewspec.py`, and the 5 touched test files) — 2 files needed an
  actual `black` run (`tests/test_atlas_segstats.py`, my own new tests; `tit/jobs/docker_engine.py`,
  see item 9); `tit/viewspec.py` needed one for a single line of my own new function signature.
- `cd desktop && npx vitest run tests/mock-server`: **21 passed** (2 files).
- Docs build: `bundle exec jekyll build` with Homebrew `ruby@3.3` (already installed on this
  machine from a prior W6 session) + this repo's own `docs/Gemfile`/`Gemfile.lock` — clean build,
  0 Liquid warnings (after the `{% raw %}` fix in item 6), cross-reference anchor from item 5
  spot-checked in the rendered HTML.
- CI YAML: `circleci config validate` (installed via Homebrew this session) passes;
  `circleci config process` expands cleanly; `bash -n` on all 17 `run` command blocks in the
  file passes.

## Not reached / explicitly out of scope

- Item 7's actual token-rotation hardening (desktop-side code, not this lane's paths).
- `desktop/tests/fixtures/scene_ernie_thalamus.json`'s orphaned status (item 3) — updated for
  consistency, not deleted; flagged for a future cleanup pass, not this lane's call.
- The `docker_engine.py` CLI-shell-out gap docker_builder.py still has (item 9's docstring now
  states it accurately; fixing the shell-out itself was never in this item's scope).
- Did not attempt to run the new `desktop-checks` CircleCI job on an actual CircleCI Linux
  runner — only YAML/shell validation, per the time box and no such environment being available
  locally.
