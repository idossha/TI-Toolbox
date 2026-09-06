# Lane SCA — the scene service (`tit/scene/` + `GET /api/scene/*`)

Plan of record: `dev/notes/v3-scene-ia-plan.md` §2 (the frozen wire contract), decisions S2/S3.
Everything below was run for real on 2026-09-04 against the dev container
`ti-toolbox-fad740e5-tit-1` (`http://127.0.0.1:8765`, project `/mnt/000` =
`/Users/idohaber/datasets/000`, this worktree bind-mounted at `/ti-toolbox`). Nothing is
committed; nothing showed a window.

---

## 0. Ground truth I measured before writing anything

Probe scripts run with `simnibs_python` inside the container (kept in the scratchpad, removed
from `/tmp` in the container afterwards).

| Measurement | Value |
|---|---|
| `ernie.msh` read (`mesh_io.read_msh`) | **1.26 s**, 847 165 nodes, 5 899 838 elements |
| skin = `crop_mesh(tags=[1005])` | 38 952 verts / **77 032** tris, crop 0.03 s |
| gm = `crop_mesh(tags=[1002])` | 168 952 verts / **335 930** tris, crop 0.10 s |
| gm mean/median/p95/max edge length | 1.122 / 1.108 / 1.847 / 3.809 mm |
| `surfaces/{lh,rh}.central.gii` | 245 762 verts, 491 520 faces **each** |
| `segmentation/{lh,rh}.ernie_DK40.annot` | 245 762 labels each, 36 ctab rows |
| Region counts read from the ctabs | DK40 70 / a2009s 152 / HCP_MMP1 362, **85 ms** for all three |
| `tit.opt.roi_spec` import cost in the container | **3197 ms** (vs 45 ms for `tit.catalog`) |
| Quadric decimation available in the image? | **No** — see A2 |

### A1 — the finding that shaped the whole design

The head mesh's GM surface (168 952 verts) is **not** the central surface (491 524 verts over
both hemispheres). It is a coarser, independent triangulation. An `.annot` label array therefore
can never be handed to the browser as-is: wrong length, wrong order. A renderer that assumed
otherwise would highlight a gyrus centimetres from the one the user clicked, and no test in the
repo would notice.

Nearest-neighbour distance from every gm vertex to the nearest central-surface vertex
(`cKDTree`): mean 2.570, median 1.147, p95 12.628, p99 34.362, **max 45.691 mm**; 90.9 % under
2 mm, **7.35 % over 5 mm**. The far tail is cerebellum + brainstem (gm bbox z-min −50.7 vs
central z-min −28.6) — anatomy the cortical atlases genuinely do not cover.

**Decision:** labels are transferred by nearest neighbour with a **3.0 mm radius**; beyond it the
vertex gets `0` = no region. *Failure it prevents:* painting cerebellum with whatever occipital
region happens to be least far away, so a user's "cortical ROI" silently includes it. Anything in
2–5 mm gives the same answer to within 1.8 % of vertices, so the constant is not load-bearing —
it is recorded in every sidecar as `radius_mm` next to the resulting `labelled_fraction`.

### A2 — why vertex clustering, not quadric decimation

Checked in the running container: `trimesh` 5.0.0 and `meshio` **are** installed, but
`Trimesh.simplify_quadric_decimation` raises `ModuleNotFoundError: No module named
'fast_simplification'` (trimesh 5 delegates, it has no built-in implementation); `open3d`,
`pymeshlab`, `vtk`, `pyvista`, `pyacvd`, `fast_simplification` are all absent. So no dependency
already in the image provides it, and adding one for a form control's backdrop is the decision S3
exists to refuse.

Grid vertex clustering needs only `numpy`, runs in ~0.4 s on the GM surface, and has a property
quadric decimation does not: **every output vertex is an input vertex, unmoved**. That is what
lets the per-vertex label array be carried by plain index selection (`attr[source_index]`) instead
of a second nearest-neighbour transfer with its own error, and what keeps an electrode measured in
the mesh's millimetres landing *on* the surface. Proved on real data:
`test_every_served_gm_vertex_is_an_untouched_mesh_vertex` re-reads the mesh and asserts exact
byte-level set membership of the served coordinate triples.

Cell size is derived, not guessed: clustering a surface of mean edge `e` with cell `c` leaves
about `(e/c)²` of its triangles, so `c = e·sqrt(T / T_budget)` is the one-shot estimate. On all
three real subjects it landed inside the budget in **one round**.

### A3 — the bug this lane found in its own first implementation

The first version reported `max_representative_shift` = the largest distance from a vertex to its
own cluster's representative, and I asserted it bounded the surface error. It does not. A cluster
whose every triangle collapses keeps **no** representative in the compacted output — 108 of 70 685
clusters on `sub-ernie` — and its members are then further from the surface than their vanished
representative was. Measured gap: reported 2.474 mm, true 5.266 mm — a **2.1× understatement** of
the deviation, which is exactly the kind of number that gets quoted in a design doc and believed.

Fixed: the field is now `max_deviation`, the true one-sided Hausdorff distance from the input
vertex set to the output's, computed exactly in pure `numpy` (own-representative for almost every
vertex, brute-force search over the kept set for the few hundred orphaned ones). Pinned two ways:
a synthetic test with a deliberately orphaned stray triangle
(`test_max_deviation_covers_a_vertex_whose_own_representative_was_dropped`), and a real-data test
where an independent `cKDTree` must agree to 1e-3 mm on all three subjects.

### A4 — the LUT parser is copied, not imported

`parse_lut_text` first delegated to `tit.opt.roi_spec._parse_lut_line`, the parser the optimizer's
ROI picker uses, so the two legends could never disagree. Measured live: the first
`GET /api/scene/volume-legend` after a server start took **3378 ms**, because
`tit.opt.roi_spec` → `tit.opt.__init__` → the ex/flex engines → `simnibs`: **3197 ms of import**
to parse a colour table. That is more than the whole 2.5 s warm budget of decision S8 on its own,
and a scene service has no business importing an optimizer.

The twelve lines are copied into `tit/scene/build.py` with the rule stated, and
`test_the_lut_parse_matches_the_roi_pickers` drives *both* implementations over the same nine
awkward lines so they cannot drift. After: **44 ms** first call, **3 ms** warm.

### A5 — MNI152 does have atlases

The lane brief said "MNI152 has no atlas — it must answer readably, not 500". On Dataset 000 that
is not true: `m2m_MNI152/segmentation/` holds `{lh,rh}.MNI152_{DK40,a2009s,HCP_MMP1}.annot` and
the manifest lists all three with correct region counts. The readable-failure path is still built
and verified, driven by an atlas the subject really lacks (`?atlas=NotAnAtlas` → 404 *"MNI152 has
no cortical atlas 'NotAnAtlas'; available: DK40, HCP_MMP1, a2009s"*) and by a subject with no head
model at all (404 naming the missing file and `charm`).

### A6 — a hardening the docstring forced me to actually implement

`MeshAtlasManager.find_atlas_file` interpolates the atlas id into a `glob` pattern, and a glob
pattern **does** walk `..` segments. An id of `../../../../etc/x` would have aimed `read_annot` at
any `lh.*.annot` on the machine. `annot_paths` now checks the id twice before it reaches the
filesystem — `tit.catalog.is_safe_name` (no separators, no traversal segment) and membership in
`MeshAtlasManager.list_atlases()` — and returns `{}` (a readable 404) otherwise. Six adversarial
ids are parameterised in `tests/test_scene_build.py`.

### A7 — small corrections made after the first live pass

- Every URL the manifest emits is now percent-encoded (`urllib.parse.quote`). These ids are file
  names off disk; an unquoted `&` or `#` in one would silently truncate the query the client sends
  back. Verified live: `volumes[0].url` →
  `/api/files/raw/mnt/000/.../segmentation/labeling.nii.gz` returns **200, 940 059 bytes**.
- `X-Scene-Build-Ms` reports the cost of building *the artifact being served* (read from its
  sidecar), and `X-Scene-Cache: hit | building` says whether this request paid it. The surfaces'
  sidecars also carry `mesh_read_ms`, because both parts come out of one `read_msh` and both
  `build_ms` figures therefore include the same mesh read — without that field the two numbers
  look like they add up and they do not.

---

## 1. What was built

| File | What it is |
|---|---|
| `tit/scene/__init__.py` | Package header carrying decision S1's **non-goals** (no slicing, colormaps, field overlays, screenshots, layer tree) and the module map |
| `tit/scene/tvsc.py` | The frozen §2.3 `TVSC1` codec. Pure `numpy` |
| `tit/scene/simplify.py` | Grid vertex clustering + the budget loop. Pure `numpy` |
| `tit/scene/cache.py` | §2.2 cache: fingerprints, atomic publish, stale pruning, per-subject lock, `.bidsignore` |
| `tit/scene/build.py` | The science: surfaces, label transfer, electrodes, volume legend. `simnibs`/`nibabel`/`scipy` imported **inside functions** |
| `tit/server/routes/scene.py` | The six routes, the 202/`Retry-After` machinery, `ETag`/304 |
| `contracts/openapi.v1.yaml` (+ regenerated `.json`) | A `scene` tag and six paths, additive |
| `tests/scene/make_fixtures.py` | The fixture writer lane SCB reads (`--check` mode for drift) |
| `tests/test_scene_{tvsc,simplify,cache,build,routes}.py` | **108** host tests, all green with `simnibs`/`nibabel`/`scipy` mocked |
| `tests/test_scene_realdata.py` | 12 tests gated on `TIT_SCENE_TESTDATA`; skip with a printed reason when it is unset |

Design decisions worth their own line, each with the failure it prevents:

- **The labels builder decodes the `gm` payload the surface route actually serves**, rather than
  re-deriving the vertex order from the mesh. *Prevents:* the one place the served order and the
  labelled order could silently diverge. Alignment becomes structural, not intentional.
- **Both surfaces come out of one `read_msh`.** *Prevents:* paying the only expensive step
  (1.26 s and ~600 MB RSS) twice.
- **The build unit is per subject, under a `threading.Lock`, published atomically
  (`write .tmp-<pid>-<uuid>` → `os.replace`).** *Prevents:* two panes opening at once both loading
  the 184 MB mesh (the lock), and any reader ever seeing a half-written `.tvsc` (the rename — which
  is what makes it correct even if a second *process* builds concurrently; the lock is only an
  efficiency measure).
- **A cold request answers 202 + `Retry-After: 1`; it never holds the connection.** An explicit,
  capped `?wait=<seconds>` (default 0, max 60) exists for callers that want one deterministic call
  — tests, smoke, curl. *Prevents:* a hung-looking app and a proxy dropping a 10 s request, without
  making every script a polling loop.
- **A failed background build is reported to the next request as a 500 naming the exception, then
  cleared.** *Prevents:* a subject with a corrupt mesh polling 202 forever with no diagnosis.
- **`must-revalidate` + a fingerprint `ETag`, not a long `max-age`.** The URL carries no
  fingerprint, so its content legitimately changes after a `charm` re-run. *Prevents:* a pane drawn
  from a head model the user replaced. Cost: one 304 round trip, measured at 3–6 ms.
- **Nothing in these routes takes a path from the client.** Subject, part, net *file name* and
  atlas id are each checked against what the project contains (`catalog.subject_ids`, `PART_TAGS`,
  `PathManager.list_eeg_caps`, `MeshAtlasManager.list_atlases`) before touching the filesystem.

---

## 2. Numbers

### 2.1 Budgets (decision S3: ≤ 150 000 triangles and ≤ 3 MB per surface)

| Subject | part | source tris | served tris | verts | bytes | cell mm | max deviation mm | in budget |
|---|---|---|---|---|---|---|---|---|
| ernie | skin | 77 032 | **77 032** | 38 952 | 1 391 840 (1.33 MiB) | — (not simplified) | 0.0 | yes |
| ernie | gm | 335 930 | **145 402** | 70 586 | 2 591 888 (2.47 MiB) | 1.6786 | **5.266** | yes |
| 101 | skin | 69 818 | **69 818** | 35 135 | 1 259 468 (1.20 MiB) | — | 0.0 | yes |
| 101 | gm | 352 150 | **147 193** | 70 961 | 2 617 880 (2.50 MiB) | 1.6719 | **6.245** | yes |
| MNI152 | skin | 80 380 | **80 380** | 40 503 | 1 450 628 (1.38 MiB) | — | 0.0 | yes |
| MNI152 | gm | 278 754 | **138 239** | 66 648 | 2 458 676 (2.34 MiB) | 1.7693 | **4.149** | yes |

Deviation distribution on `sub-ernie` (distance from each of the 168 952 original gm vertices to
the nearest served vertex, measured with an independent `cKDTree`): mean **0.504**, p95 **1.224**,
p99 **1.432**, max **5.266** mm. 101: 0.509 / 1.212 / 1.416 / 6.245. MNI152: 0.514 / 1.330 /
1.540 / 4.149. The max is set by a handful of vertices in collapsed clusters (A3); 99 % of the
surface moves under 1.5 mm, which is inside the ~1.1 mm the mesh's own edge length already
represents.

**No budget was missed.** `within_budget` is reported per part in the manifest, so a future
subject that cannot be squeezed says so with its true counts instead of shipping oversized.

### 2.2 Label payloads

| Subject | atlas | regions | vertices | labelled | build ms | bytes | regions checked / outside |
|---|---|---|---|---|---|---|---|
| ernie | DK40 | 70 | 70 586 | 87.5 % | 375.7 | 988 236 | 68 / **0** |
| ernie | a2009s | 152 | 70 586 | 87.5 % | 364.0 | 988 236 | 147 / **0** |
| ernie | HCP_MMP1 | 362 | 70 586 | 90.9 % | 378.4 | 988 236 | 351 / **0** |
| 101 | DK40 | 70 | 70 961 | 86.7 % | 378.8 | 993 488 | 68 / **0** |
| MNI152 | DK40 | 70 | 66 648 | 86.3 % | 390.7 | 933 104 | 68 / **0** |

The unlabelled 9–14 % is the cerebellum/brainstem tail of A1 plus the annot's own `unknown`
region (medial wall). Independently checked: unlabelled vertices have a mean z of −13.1 mm against
+28.3 mm for labelled ones on `sub-ernie` — they are *below* the cortex, which is what the radius
rule is supposed to select.

**The alignment proof** (`test_every_region_lands_where_the_annot_says_it_is`): for every region
with ≥ 20 served vertices, the centroid of the vertices carrying its `uint16` label falls inside
the region's bounding box read independently from the `.annot` + `.gii` pair (1 mm margin, for the
two surfaces not coinciding exactly). 0 failures across 5 subject×atlas combinations, up to 351
regions each.

**And the proof that the proof can fail** (`test_the_bounding_box_check_can_actually_fail`): a
bounding-box test passes trivially if the boxes are large, so each left-hemisphere region's
centroid is also fed to the *same region's right-hemisphere* box. 34 lh regions (175 for
HCP_MMP1), **0 wrongly accepted** — the check discriminates.

### 2.3 Electrodes are in the surfaces' space and units

Nearest-vertex distance from every electrode to the served skin payload, every net each subject
has (`test_every_electrode_sits_on_the_skin`, threshold 15 mm):

| Subject | nets | electrodes | mean mm | **max mm** |
|---|---|---|---|---|
| ernie | 8 | 60…342 per net | 0.69–0.82 | **1.81** |
| 101 | 12 | 18…342 per net | 0.65–0.80 | **1.74** |
| MNI152 | 8 | 18…342 per net | 0.68–0.82 | **1.57** |

Fiducials (a second, independent witness): max 1.19 / 1.19 / 0.94 mm. A metre/millimetre mix-up is
off by 10³ and an LPS/RAS flip by tens of millimetres, so 15 mm is loose enough never to flake and
tight enough to catch either.

### 2.4 Live HTTP, cold and warm (measured through `http://127.0.0.1:8765`)

| Request | ernie cold | ernie warm | 101 cold | 101 warm | MNI152 cold |
|---|---|---|---|---|---|
| `manifest` first call | **202 in 199 ms** | 200 in 86 ms | 202 in 139 ms | 200 in 72 ms | 202 in 143 ms |
| `manifest` polled to ready | 200 after **1.22 s** (2 polls) | — | 200 after **2.23 s** (3 polls) | — | 200 after **1.17 s** (2 polls) |
| `manifest` warm | — | **51 ms** | — | 54 ms | 57 ms |
| `surface?part=skin` | — | **12 ms** (1 391 840 B) | — | 12 ms | 12 ms |
| `surface?part=gm` | — | **14 ms** (2 591 888 B) | — | 20 ms | 16 ms |
| `surface` with `If-None-Match` | — | **304 in 3–5 ms**, 0 B | — | 304 in 3 ms | 304 in 4 ms |
| `regions?atlas=DK40` first call | 202 in 13 ms → 200 after **1.02 s** | 200 in **6 ms** | 202 → 200 after 1.02 s | 5 ms | 202 → 200 after 1.03 s |
| `labels?atlas=DK40` | — | **15 ms** (988 236 B) | — | 8 ms | 17 ms |
| `electrodes` | — | **4 ms** | — | 5 ms | 5 ms |
| `volume-legend` | — | **4 ms** (56 entries) | — | 3 ms | 5 ms |
| unknown subject / part / atlas | — | **404 in 2–6 ms**, readable | — | 404 | 404 |

One cold run taken immediately after a server reload (so the 184 MB mesh was out of the page
cache too) took **4.78 s** end to end — the worst cold number I measured, against decision S8's
12 s cold budget. Warm first paint has 51 ms of manifest + 14 ms of gm to work with against S8's
2.5 s.

The warm manifest's ~50 ms is dominated by reading three `.annot` colour tables to report region
counts (85 ms measured for all three; the rest is cached file reads). Left as a real read rather
than a cached count, because a cached count is one more thing that can go stale against the
annotation files.

### 2.5 Gates

| Gate | Result |
|---|---|
| Host `python3 -m pytest -q` | **3 462 passed, 30 skipped, 21 deselected, 38.0 s** — 3 354 passed / 18 skipped with this lane's six files ignored, so +108 passing and +12 skipping |
| `tests/test_scene_realdata.py` with `TIT_SCENE_TESTDATA` unset | 12 skipped, each printing its reason |
| `tests/test_scene_realdata.py` in the container, ernie / 101 / MNI152 | **12 passed** each |
| `python3 dev/contracts_check.py contracts/openapi.v1.yaml <fresh dump>` | **47 problems → 47 problems** (unchanged, all pre-existing), warnings 121 → 139, all of the pre-existing "dict/list response has no declared schema" class every `/api/catalog` route already produces. **No regression.** |
| `python3 tests/scene/make_fixtures.py --check` | clean (also asserted from pytest) |
| `desktop/ npm run typecheck` | passes |

---

## 3. What lane SCB gets

`desktop/tests/fixtures/scene/` now also contains, written by `tests/scene/make_fixtures.py`:

| File | Bytes | Pins |
|---|---|---|
| `tri-surface.tvsc` | 128 | a surface with **no** labels: flags bit0 clear, no trailing block — a reader that always looks for labels reads past the end |
| `labels-only.tvsc` | 104 | what `GET /api/scene/labels` returns: `indexCount` 0, an **odd** vertex count so the `uint16` block needs 2 bytes of tail padding |
| `labelled-surface.tvsc` | 140 | all three blocks: a reader that computes the label offset from the header instead of accumulating the index block lands wrong |
| `fixtures.json` | — | every expected value, **authored** from the §2.3 spec table and a position formula, never read back from the encoder |

The fixtures are adversarial on purpose: the three axes have different magnitudes and signs
(`x = 1.5i`, `y = 40 − 7.25i`, `z = −12 + 3i²`) so a transposed axis moves a vertex by tens of
millimetres rather than by rounding; `y` decreases while `x` increases so a reversed vertex order
is visible; one label is `0` (no region) and one is `65535` so a signed/unsigned mistake is loud;
and the triangle list references the last vertex so an off-by-one overruns instead of landing on a
plausible neighbour.

§2.3's *"one test in each language reads a fixture the other wrote"* is satisfied **both ways**:
`tests/test_scene_tvsc.py::test_this_reader_parses_the_fixtures_the_other_language_wrote` reads
every `.tvsc` in that directory this lane did not write. It already passes over SCB's own
`skin.tvsc` and `gm.tvsc` (2 145 verts / 4 096 tris each, magic/version/reserved correct, labels in
1…32 on `gm`), so the two encoders agree today.

Notes for SCB's reader:
- The **labels payload repeats the `gm` positions** (`988 236 B` = 32 + 12V + pad(2V) for ernie).
  §2.3 makes positions unconditional, and the repetition is useful: compare them against the `gm`
  payload's before applying labels and a misalignment fails in the client instead of drawing the
  wrong region.
- `uint16` `0` means **no region**. The values index `legend[].label` from
  `GET /api/scene/regions`, not the `.annot` row — `legend[].id` is the `.annot` row (the integer
  `FlexConfig.AtlasROI.label` wants) and `legend[].hemi` disambiguates it, because lh row 5 and rh
  row 5 are different regions.
- A `202` is normal on a cold cache. Honour `Retry-After` (1 s) and poll; do not add `?wait=` to
  the app's own fetches — it exists for scripts.

---

## 4. Requests to other lanes

1. **SCB / SCC — regenerate the API types.** `contracts/openapi.v1.json` now carries the six
   `/api/scene/*` paths; `desktop/src/renderer/api/schema.d.ts` is generated from it by
   `npm run gen:api` and is not this lane's file to touch. Run it before typing a scene fetch.
2. **SCB — the electrode field name.** `desktop/tests/fixtures/scene/electrodes.json` (SCB's own
   fixture) uses `{id, label, world}`. The frozen §2.1 shape, and what
   `GET /api/scene/electrodes` returns, is `{name, world}` — plus additive `space`, `reference`
   and `fiducials` arrays. Either rename in the renderer or say why and I will add an alias; a
   mismatch here shows up as unlabelled markers.
3. **SCC — the manifest is the entry point.** Call `GET /api/scene/manifest?subject=<id>` first
   and drive everything off its `parts[].url`, `nets[].url`, `atlases[].url` and
   `volumes[].legend_url` rather than composing URLs; that is what keeps a future part addition
   from needing a renderer change.

---

## 5. What I created on Dataset 000, and how to remove it

- `derivatives/ti-toolbox/scene_cache/sub-{ernie,101,MNI152}/` — **14 MB**, 6 files per subject
  (`skin`/`gm`/`labels-DK40`, each `.tvsc` + `.json`). This is the feature's own cache, entirely
  regenerable on the next request, and lanes SCB/SCC/CR want it warm, so I left it in place.
  Remove with `rm -rf /Users/idohaber/datasets/000/derivatives/ti-toolbox/scene_cache`.
- `.bidsignore` gained one line, `derivatives/ti-toolbox/scene_cache/`, appended without touching
  the six lines already there — the same convention `tit/jobs/registry.ensure_bidsignore` uses for
  `code/ti-toolbox/jobs/`.
- Nothing under `m2m_101` / `m2m_ernie` / `m2m_MNI152` was written or read for anything but input.
  No job was submitted. No pre-existing output was overwritten.

---

## 6. Incident: I took the shared container down for ~4 minutes

`tit/scene/tvsc.py`'s first version carried a module-level `assert _HEADER.size == HEADER_SIZE`
with a wrong format string (`<4sIIII8s` = 28 bytes, not 32). Route modules are **auto-discovered**,
so the moment `tit/server/routes/scene.py` appeared the reloader imported it, hit the failing
assert at import time, and `create_app` raised — every `/api/*` request on
`ti-toolbox-fad740e5-tit-1` failed for every lane until I touched a watched file and it reloaded
clean.

Two things worth writing down:

- **Verify a new module imports inside the container before the route module that pulls it in
  exists.** `docker exec <c> bash -lc 'cd /ti-toolbox && simnibs_python -c "import
  tit.server.routes.scene"'` takes two seconds and is the whole fix. An import-time failure in an
  auto-discovered route module is not a local mistake — it is a shared outage.
- **The reloader does not always notice.** WatchFiles picked up every change to
  `tit/server/routes/scene.py` but did *not* pick up the fix to `tit/scene/tvsc.py` (the
  crash-loop appears to swallow events on this bind mount). `touch tit/server/routes/scene.py`
  forces it; `curl -s $URL/api/health` showing a small `uptime_s` is how you know it took. I hit
  this again later — a `tit/scene/build.py` edit sat unloaded for a minute with the server
  reporting `uptime_s: 427` — so **check `uptime_s` after every edit you expect to be live**,
  do not assume the ~2 s reload happened.

No job was running at any point (checked `GET /api/jobs` before and after); no container was
restarted or recreated.
