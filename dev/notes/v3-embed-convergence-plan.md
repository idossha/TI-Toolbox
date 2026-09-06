# Converging on one renderer, and decoupling TI-Toolbox releases from Tetravox (plan of record, 2026-09-04)

Maintainer's brief, verbatim: *"do whatever you think is best, however i would like to come up with a system that we
do not need to release a new version everytime tetravox updates. there should be some dynamic element that can update
tetravox internally if possible. other than that, go ahead and work on everything."*

Two goals, one programme: (a) the run-page 3-D panes stop using our own renderer and use the Tetravox embed, the way
the Viewer already does; (b) a Tetravox update no longer implies a TI-Toolbox release.

## 0. What is already true (measured 2026-09-04)

| Fact | Consequence |
|---|---|
| The engine already has a **points layer**, a **point tool** (arm per layer, ids, resolved selection) and a **probe** event; the sEEG extension draws contacts with it. | Nothing has to be *built* for electrode picking — only exposed. |
| `feat/host-camera-probe` (merged to origin/main as e5671b7) adds `scene.camera()` / `scene.setCamera(patch)` and forwards `probe` — on the **module host API**, for extensions running inside the Tetravox app. | The capability is proven and shaped, but on a different surface from ours. |
| Our panes are an **iframe host** on the embed's postMessage protocol; `packages/embed` exists only on the unpushed `feat/embed`, 32 commits behind `origin/main`, protocol 1, whose view spec knows only `VolumeLayer` and `MeshLayer`. | A version cut from main contains no embed at all. The embed branch must be rebased before it can carry protocol 2. |
| The image bakes the embed at `/opt/tetravox/embed`; `TIT_TETRAVOX_EMBED_DIR` already overrides it. | Delivery is a build-time constant today — which is exactly the coupling the maintainer wants removed. |

## 1. Decisions

| # | Decision | Failure it prevents |
|---|---|---|
| E1 | **The app pins a protocol RANGE and named features, never a version.** `SUPPORTED_EMBED_PROTOCOL = {min: 1, max: N}`; every pane feature declares what it needs (`markers`, `pick`, `camera`), and the host reads `manifest.protocol` (already surfaced in `/api/capabilities`) to decide. An additive Tetravox release therefore needs **no** TI-Toolbox change at all. | The thing the maintainer asked to remove: a TI-Toolbox release per Tetravox release. |
| E2 | **Two install roots, newest compatible wins.** The image keeps baking a floor version (offline and air-gapped installs work unchanged); a writable root under the already-mounted user config (`$TIT_USER_CONFIG/tetravox/embed/<version>/`) holds anything installed later. `/tetravox/` serves the active one: `TIT_TETRAVOX_EMBED_DIR` (dev override) → newest installed within the supported range → baked. | An update mechanism that breaks the offline install, or that cannot be rolled back. |
| E3 | **Install is explicit, verified, and never executes the tarball.** `POST /api/tetravox/install` takes a URL + sha256 (or a version from a release index), downloads over https from an allowlisted host, verifies the digest **before** unpacking, extracts traversal-safe into a temp dir, validates the manifest (name, `protocol` in range, `index.html` present), then activates by `os.replace`. No silent auto-update; rollback is `POST /api/tetravox/activate {version}`. | Runtime code loading turning into an unaudited update channel, or a half-written directory being served. |
| E4 | **The embed is never loaded cross-origin.** It is downloaded and served from this server, because the embed resolves dataset refs (`/api/files/raw/…`) against its own baseURI and the CSP is same-origin. | A CDN-loaded viewer that cannot read the project's own files. |
| E5 | **Protocol 2 is additive and exposes what the engine already has**: a points layer in the view spec (inline coordinates + ids), the point tool (arm/disarm, set selection), a `pick`/selection event carrying layer, point id, world position and label, and camera get/set. Absent, every protocol-1 host keeps working unchanged. | A breaking change that strands the Viewer, which is a protocol-1 host today. |
| E6 | **One renderer at the end.** When protocol 2 is installed, the three panes drive the embed and `desktop/src/renderer/scene/**` (2 214 code lines) is deleted. If the active embed is protocol 1, the panes say so in one line and every form control still works — they are never the only way to do anything. | Two renderers maintained forever; and a pane that breaks a page when the viewer is old. |
| E7 | **The scene service outlives the renderer, but changes format.** Cropping a 184 MB mesh to skin + cortex, simplifying to budget, aligning atlas labels and caching stays ours. It must emit what the embed can read (**GIfTI** surfaces), so `TVSC1` and its two codecs retire with the renderer. | Keeping a bespoke binary format alive for a renderer that no longer exists. |

## 2. Lanes

**T — Tetravox embed, protocol 2** (Opus, in the Tetravox repo). Own worktree per that repo's AGENTS.md rule 5:
`git worktree add ../tetravox-wt-embed-p2 -b feat/embed-protocol2 origin/main`, then bring `packages/embed`
forward from `feat/embed` (4 commits, 19 files) — never check out or push `main`, and another session is working in
that repo. Add E5's four pieces, additively; bump the embed to protocol 2 / version 0.4.0; update
`protocol.schema.json`, `viewspec.schema.json`, `docs/EMBED.md`, the example host, the CHANGELOG, and
`docs/ARCHITECTURE.md` in the same commit if a frozen interface moves (their rule 3). Their rule 1 applies: a
rendering feature ships an analytic pixel assertion plus a golden. Tests stay windowless (their rule 8, their own
`scripts/e2e-quiet-check.sh`). Deliver `pnpm --filter @tetravox/embed pack:embed` output: a tarball + manifest +
sha256. Commit locally on that branch; **do not push and do not open a PR** — the maintainer does that.

**U — dynamic embed delivery** (Opus, TI-Toolbox). E1–E4: the resolver, the install/activate/remove API, the release
index fetch, Settings UI (current version + protocol, check for updates, install, roll back, offline statement), the
capability gate the panes will use, docs, and tests including a traversal-safe extraction test and a digest-mismatch
test. Does not depend on lane T.

**M — migrate the panes** (Opus, TI-Toolbox, after T). The scene service emits GIfTI (E7); `ScenePane` drives an
embed iframe instead of `SceneCanvas`; the three panes keep today's behaviour and today's tests; `scene/**` is
deleted. Mount only the visible pane and tear it down on unmount — measure resident memory with the pane open and
closed, because each embed instance carries its own wasm heap and workers.

**V — verify** (Sonnet). Re-runs the gates and the acceptance numbers, and proves E1 by installing an embed the app
has never seen and using it without rebuilding anything.

## 3. What the embed-backed pane must still be true of (added by lane N1, 2026-09-04)

E6 says the panes end up driving the embed and `desktop/src/renderer/scene/**` is deleted. These are properties the
panes have **today**, each one a defect the maintainer reported and this lane fixed; they are written here because a
renderer swap is exactly the kind of change that loses them silently, and because "the three panes keep today's
behaviour and today's tests" (lane M) is not checkable until someone says which behaviour. Full working:
`dev/notes/v3-scene-ia/n1-notes.md`.

| # | Requirement | The failure it prevents | How it is proved today |
|---|---|---|---|
| **N1** | **A marker behind the scalp is occluded by the scalp.** An electrode on the far hemisphere must contribute nothing to the frame, and must not be pickable either. The tolerance is a stated distance in millimetres, not a depth-buffer unit: an electrode within ~2 mm of the served skin is ON it and must still be drawn, because the skin is simplified and every net lands within 1.81 mm of it either way (`MARKER_OCCLUSION_BIAS_MM = 4`). | The reported defect. Markers were drawn first, opaque and depth-writing, so every electrode was painted over the head whichever side of it it was on: **12 of 12** far-side electrodes drawn, up to 157/255 per channel, 112–190 mm behind the scalp. A user sees all 75 electrodes of a net at once and reads it as "the positions look wrong". | `tests/e2e/scene.spec.ts` → *"an electrode on the far side of the head is hidden by the scalp"* and *"what the eye can no longer see, the cursor can no longer hit"*; `tests/e2e/real/scene-simulator.spec.ts` → *"an electrode behind the scalp is hidden by it…"*. Both read pixels back and need no colour model: the same frame is rendered twice, with and without the marker pass, and a marker is painted where the two differ. |
| **N2** | **A marker that names a point INSIDE the head is not occluded.** The sphere centre of the Analyzer and Optimizer is in the brain by construction. Occlusion is a property of what the markers mean, not of the renderer. | Applying N1 unconditionally hides the only thing telling the user where they put the sphere centre. | `<SceneCanvas markersOccluded>`, set from `gesture !== "sphere"` in `ScenePane.tsx`; `tests/e2e/real/scene-{analyzer,optimizer}.spec.ts`'s sphere-centre tests. |
| **N3** | **The pane states its laterality convention on screen, derived from the live camera.** Today: `data-testid="scene-orientation"`, e.g. `Anterior view · right = subject's L`, computed by `screenAnatomy` from the same `cameraBasis` the view matrix comes from, so it follows a free orbit rather than the last preset button. | A 3-D head view has no universal convention and the two plausible ones are mirror images (facing the subject, their left is on your right; looking down from above, it is on your left). A viewer that does not say which one it is showing is a viewer nobody can trust, and the maintainer's report was half exactly this. | `tests/unit/scene-orientation.test.ts` (20 assertions, two landmark sets — pure anatomical directions, and ernie's served 10-20 coordinates) plus the real-anatomy half of the Simulator spec, which reads the caption off the canvas and checks the served Fp1/Fp2, T7/T8, O1/O2 pairs fall on the side it claims. |
| **N4** | **The camera presets are the right way up.** `top` looks down from a fraction of a degree *posterior* of the vertex (`yaw: pi`), so the axial view has the nose at the top and the subject's left on the viewer's left. | With `yaw: 0` the eye sat anterior of the vertex, `up` collapsed onto -Y and the axial view came out upside down — Fp1/Fp2 at screen y 289 and O1/O2 at 38 on a 400x320 pane. | The `top` rows of `tests/unit/scene-orientation.test.ts`; restoring `yaw: 0` fails 4 of its 20. |

Two notes for lane M specifically. First, N1 and N2 are **not** the embed's `points` layer for free: E5's point tool
has to be told whether a point layer is depth-tested against the meshes, and if protocol 2 cannot express that, the
migration is blocked on it rather than on the pane. Second, the three e2e proofs above are written against
`window.__scene`'s `samplePixels` and against the pure `camera.ts`; the pixel half ports to any renderer that can
render a frame with and without its point layer, and the camera half needs an equivalent of `scene.camera()` — which
`feat/host-camera-probe` already has (§0). Port the tests, do not re-derive the properties.
