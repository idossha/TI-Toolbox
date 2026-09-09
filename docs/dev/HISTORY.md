# Development milestones

[ARCHITECTURE.md](ARCHITECTURE.md) is the current contract and [DECISIONS.md](DECISIONS.md)
explains consequential choices. [BENCHMARKS.md](BENCHMARKS.md) retains useful evidence;
[RELEASE.md](RELEASE.md) owns current readiness. Those records take precedence over this history.

Condensed on 2026-09-09 from accumulated program logs. Git history preserves the full narratives,
old requests and individual test receipts. Add meaningful dated milestones, not a paragraph for
every fix or a transcript of each implementation session.

## 2026-08-27 — Electron and the job server

Established `desktop/`, FastAPI routes, the hand-authored OpenAPI contract and the server-owned
queue, dependencies, groups, locks, progress, events and cancellation. Contract-first development
survived later UI redesigns. The early flat navigation and NiiVue evaluation did not.

The spike established why SimNIBS imports must be lazy and why field display percentiles need
a GM mask. GIfTI export must preserve scanner RAS; passing volume geometry can shift surfaces
by `c_ras`. Test telemetry was isolated after tests were found making production network calls.

## 2026-09-02 — Workflow-first navigation and Tetravox

Replaced the flat page collection with workflow navigation, merged optimization interfaces and
an iframe/postMessage viewer. In-process engine vendoring was rejected because it would also
require maintaining viewer chrome. Same-origin fetch and session cookies avoided a custom scheme.

## 2026-09-03 — Native desktop research (parked)

A native Apple Silicon runtime completed real simulation and matched the emulated container;
FastSurfer segmentation and Python replacements for FreeSurfer utilities were also evaluated.
The native deployment path was parked, not certified: no Windows or x86_64 machine was used,
full runtime signing/notarization was not attempted, and DWI still required Docker. Platform wheel
availability and commercial redistribution terms remained questions for any future native effort.

The retained useful outcomes were POSIX process-tree cancellation, labels for cancellation of
QSIPrep/QSIRecon sibling containers, and evidence for removing FreeSurfer as a mandatory runtime.
Measured numerical comparisons and the single-subject FastSurfer limits are in BENCHMARKS.

## 2026-09-03 — One Docker image and a real development loop

Kept Docker, removed X11 and the separate FreeSurfer image, and moved desktop orchestration onto
the typed Docker Engine API. The image owns the scientific package, server, UI, embed and
FastSurfer segmentation. Worktree mounting became an explicit development choice after an
unconditional mount was found replacing packaged source.

Added `dev`, `dev:web`, `dev:down` and a real-job smoke harness. Run pages gained the common
plan/terminal layout and measured layout checks. Production Docker images and ordinary host
launchers share the run specification; development adds checkout/reload/renderer overrides.

## 2026-09-04 — Scene service and retained pages

Built compact scene payloads, shared WebGL2 panes, subject selection and retained page state.
Real picking exposed inward-wound anatomy; outward orientation and a cache-version change fixed
it. Preview build failure handling became explicit instead of hiding errors behind endless retries.
The Tetravox delivery/update machinery shipped; migrating workflow panes into that embed was
subsequently reversed.

## 2026-09-05 — Overview, batch execution and explicit viewing

The R1–R5 program delivered aggregate Overview, a shared clearable console, scheduler-enforced
batch caps, packaged Ernie guide anatomy and draft-versus-loaded Viewer state. The A–D program
added compatible Tetravox updates, color-coded electrode dots, shared selection controls and the
pipeline canvas with public-API notebook export. These historical requirement labels still appear
in code; current behavior belongs in ARCHITECTURE and DESIGN.

A container restart during FEM exposed the importance of job recovery semantics. The Jobs layer
remains independent of pipeline UI code; dynamic bindings live in the Jobs package.

## 2026-09-06 — Native panes, job rows and notebooks

Restored native workflow panes and interactive atlas selection. Simulator, Analyzer and Optimizer
became per-job tables instead of subject × montage fan-outs. A host-installed external viewer was
adopted briefly, then explicitly reversed the same day: the image ships the embed, with Menu and
Tetravox as retained Viewer sub-pages. ADR rows 27–29 preserve that reversal.

Added container-backed notebooks, CodeMirror and kernel completion. Live testing caught a ZMQ
restart crash, editor command-mode interception and completion-range bugs that mocks missed.
The extra sticky run receipt was removed; report output later became an attachment of its job.

## 2026-09-07 — Scientific audit and v2.5.0 integration

Reproduced and corrected cluster-tail, grid, unit, affine, p-value and degenerate-statistic defects;
exposure conventions and weak-modulation arithmetic were clarified. SCI-01–09 in
[scientific corrections](../releases/v3.0.0.md#scientific-corrections) retain affected outputs and remediation.
Singleton-group pooled variance was a code defect, not evidence of an intrinsically untestable
voxel set. Fixing it does not overcome the inference limits of a tiny cohort.

Merged v2.5.0 and its positional TI/mTI API. Callers, notebooks and generated contracts needed
updates even where Git found no conflict. A second envelope implementation in the accelerated
path required the same numerical correction. Existing project copies of seeded notebooks do not
automatically inherit source-template repairs.

Server hardening added resource reservations, dependency rejection, path containment, revisioned
notebook saves, reconnect reconciliation and rich-output sanitization. Packaging review found the
old release workflow would publish the v2 launcher and that required compose/assets were omitted
from packaged builds. The legacy launcher was retired and artifact inspection became a release gate.

## 2026-09-07 — Viewer composition and documentation consolidation

The Viewer became a subject/space tree distinguishing volumes, tetrahedral meshes and surfaces.
Compositions save choices to re-resolve; scenes save Tetravox's actual camera/layer state. Layer
names use filenames. Persisted full-data statistics and client caching removed repeated volume
reads; meaningful windows and fitted cameras replaced arbitrary defaults. Results and job artifacts
now carry explicit “Open in viewer” intent.

Developer documentation was folded to nine files and per-lane note trees removed. The follow-up
found stale citations, stale test selectors and an order-dependent mock leak; an isolated test pass
had previously hidden a failed full suite. Full-suite failures remain failures until resolved.

## 2026-09-08 — Internal distribution and Blender isolation

Rebuilt the runtime instead of treating a mounted development image as release evidence. `bpy`
had downgraded scientific NumPy; Blender moved to its supported background executable with a
prepared-data boundary. Actual subject export/reopen established the larger montage memory need.
Image-identity checks prevented loaders from silently attaching to an old image, and internal
publication was serialized by resolved tag.

Real validation repaired stale UI selectors, missing fixtures and an obsolete mEx carrier field.
These runtime/planner fixes did not add scientific-formula corrections. Validation used a copied
dataset; individual earlier successes did not certify the rebuilt artifact.

## 2026-09-09 — Security and development closeout

Hosted analysis prompted further concrete path, symlink, WebSocket and search-DOM containment
fixes. Filesystem fixtures were checked in Linux as well as on the host. Kernels remain
unsandboxed; this work does not claim defense against malicious concurrent local filesystem races.
A packaged first launch failed on an external `yaml` dependency, then passed after bundling it.
Earlier failed jobs and inconclusive native-monitor runs remain distinct from later functional passes.

A clean internal image and wheel were retained for local testing. The development branch became
`release/3.0.0` without rewriting ancestry. Documentation now describes the current product;
installation owns actual artifact availability. Main merge and Docker Hub publication were deferred
until manual testing. Current delivery status is in RELEASE, not inferred from this milestone.

## 2026-09-09 — Workflow polish and progressive viewing

Unified extension inputs/plan/terminal layouts and selection-aware export previews. Moved optional
fsaverage mapping into individual simulation jobs, stabilized participant table actions and CSV/TSV
interchange, pinned automatic optimization folders before submission, and exposed solver settings.
Form controls retain aligned starts. Results reopens its selected preview and passes exact artifact
paths to the Viewer.

Tetravox now adopts completed layers progressively and retains datasets when selections grow;
TI-Toolbox reconciles progress and keeps successful layers visible after partial failure. This was
locally activated through the existing installer, not published as a new toolbox image.

Missing ImageMagick had left copied blank cap templates appearing successful. Restored the runtime
dependency/fonts and made montage rendering atomic with explicit failures. Two confirmed blank
images were repaired from saved configuration without rerunning simulations.

## Retired root plan — 2026-09-09

Removed root `TODO.md`: its August plan mixed completed work, superseded designs and an incorrect
public-release claim. Contributor invitations and unresolved work moved to
[RELEASE.md](RELEASE.md). Historical `TODO §2.x` citations refer to the
[original plan in Git history](https://github.com/idossha/TI-Toolbox/blob/b6304f7fbae6d5ebd4f90881e8383ad728282b7e/TODO.md),
not the current contract. Agent integration gained direct stdio registration and plain-file fallbacks;
protocol process tests do not claim full native-client acceptance.

## 2026-09-09 — Current checkout and overwrite safety

Replaced an idle development container mounting an obsolete secondary checkout. The existing dev
loop now verifies the primary checkout and local frontend instead of trusting environment markers
or baked files. Obsolete runtime containers/images and secondary worktrees were removed after
inspection; dirty source was archived under `~/TI-toolbox-worktree-backups/20260909-023601/`.
Datasets, the retained internal image and unrelated unmerged branches were preserved.

A confirmed replacement job still failed because `JobSpec.overwrite` never reached SimNIBS.
The runner now forwards confirmation to SESSION's supported option. The existing project setting
also gates replacement in dialogs and server submission; old confirmation does not authorize a new
rerun. Tests used temporary fixtures and did not rerun existing user outputs.

## Lessons retained from the migration

- Test the actual boundary: Python 3.11 archive extraction and case-sensitive container paths do
  not behave like the macOS host. A passing mock cannot prove filesystem or numerical behavior.
- Follow deleted APIs/test IDs through callers, generated schemas and seeded examples. A clean
  merge can preserve an obsolete formula or broken example without a conflict.
- Inspect the packaged artifact, not only its build configuration. Ignore rules can hide required
  icons; packaging allowlists can omit compose files; unresolved externals can break first launch.
- A successful request or emitted artifact event does not establish a visible pane or a file on
  disk. Check dimensions/pixels and produced files at the consuming boundary.
- Shared build output, concurrent GUI tests and high machine load corrupt measurements. An
  inconclusive native visibility monitor is not a pass, even when functional assertions pass.
- Global mock assignments can poison later tests. Diagnose scene-guide failures in isolation but
  require the failed full suite to pass after the cause is repaired.
- Electron does not provide browser `prompt` or reliable blob-download behavior automatically;
  file export uses the owned host bridge. Auto-open effects must not recursively depend on the
  draft state they update.
