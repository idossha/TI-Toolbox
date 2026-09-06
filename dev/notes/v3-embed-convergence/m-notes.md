# Lane M — migrate the panes to the Tetravox embed (E6, E7)

Worktree `/Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui`, branch
`feature/v3-electron-gui`. Nothing committed by this lane. Shared container
`ti-toolbox-fad740e5-tit-1` / `http://127.0.0.1:8765`, project `/Users/idohaber/datasets/000`.

## 0. The gate, answered first (2026-09-04)

The plan (§3, lane N1's note to lane M) says the migration is blocked *on the protocol* if protocol 2
cannot express N1 (a marker behind the scalp is occluded) and N2 (a marker inside the head is not).
So that was measured before anything was written, against the **real** 0.4.0 bundle installed into
the shared container and the **real** skin surface `tit.scene` builds.

`desktop/tests/e2e/real/embed-occlusion.spec.ts`, 4 tests, offscreen, quiet-check PASS:

| Scene | Probe | Differing pixels vs the same scene with no point |
|---|---|---|
| baseline against itself | — | **0** (so a non-zero number below is the point, not the renderer breathing) |
| **opaque** scalp (`opacity: 1`) | `Fpz` (near, eye anterior) | **318** — drawn |
| **opaque** scalp | `Oz` (far side) | **0** — contributes nothing. **N1 holds.** |
| **translucent** scalp (`0.22`) | a point at `(0, 10, 20)`, inside the head | **300** — drawn. **N2 holds.** |
| **translucent** scalp | `Oz` (far side) | **187** — *not* hidden |

**The finding: occlusion is a property of the SURFACE's opacity, not of the points layer.** The
engine draws points in the opaque pass with depth writes on (`render/passes/derived.ts`, after
`MeshPass`), and a translucent mesh draws in the transparent phases with depth writes **off**. So an
opaque surface occludes markers behind it and a translucent one occludes nothing. There is no
per-layer "depth-test the markers" flag in protocol 2 and **none is needed**: N1 and N2 belong to
gestures that never coexist, so the pane picks the surface opacity exactly where it picks
`markersOccluded` today (`gesture !== "sphere"`).

The consequence to state plainly, because it is a visible change: in the **montage** gesture the
scalp becomes opaque, so the cortex is no longer visible through it. Choosing electrodes does not
need the cortex, and an opaque scalp with electrodes on it is what every EEG cap tool draws — but it
is a change, not a no-op.

The method is the ported one, not a re-derived one: the same scene screenshotted with the points
layer empty and with exactly one point in it, and *a point is drawn iff the two pictures differ*.
No colour model, no projection matrix — which is what lets it cross two renderers that share nothing
(`tests/e2e/scene.spec.ts`'s "an electrode on the far side of the head is hidden by the scalp" is
the same shape).

Also measured in that run, and it settles lane U's request 1: the live protocol-2 embed's `ready` is
`{tvx: 1, version: 2, webgl2: true}`. **The envelope did not move.** See §3.

## 1. E7 — `tit.scene` emits GIfTI

Serialisation only. The cropping, the simplification, the label alignment, the fingerprinted cache
and every budget are untouched; one build now publishes two payloads per artifact.

| Decision | The failure it prevents |
|---|---|
| **GIfTI, written by hand in `tit/scene/gifti.py` (numpy + stdlib), not by nibabel.** | `tests/conftest.py` replaces `nibabel` with a `MagicMock`, so a nibabel-based writer could not be exercised by the host suite at all — and this is the half whose bug is invisible until a renderer draws garbage. 18 host tests pin the bytes; a **real** nibabel 5.4.2 and the engine itself read them back (§1.3). |
| **`GZipBase64Binary` (a zlib stream, not gzip), FLOAT32 points, INT32 triangles, INT32 labels.** | Read out of the engine's own reader (`crates/tvx-mesh-io/src/gifti.rs`), not assumed. A gzip header fails on its first byte and the whole surface fails to load. |
| **The `<LabelTable>`'s first row is `Key="0"`, "unlabelled", alpha 0.** | The engine remaps a labelled array to a **dense index** — the row's *position* — and maps a value the table does not name to dense **0**. Put a real region there and every unlabelled vertex takes that region's colour: a whole cortex in one colour, and it looks plausible. |
| **A labels array with no `<LabelTable>` is refused by the encoder.** | The engine does not report it: without a table the values stay continuous and the cortex is painted through a colormap. It renders; it just is not the atlas. |
| **`?format=tvsc\|gii`, default `tvsc`; both built by one `build_surfaces`.** | A default that moved would change what every client already fetching that URL receives. Both from the same vertices and triangles is what lets the two renderers be compared and the loser deleted by dropping one entry from `cache.FORMATS`. |
| **The format is part of the ETag.** | One key + one fingerprint now name two payloads. An ETag naming only the key answers a `format=gii` request carrying the `tvsc` ETag with a **304** — the client then draws TVSC1 bytes believing they are GIfTI, and nothing downstream reports it. |
| **A format that is not published yet answers 202, never the other file.** | `publish` writes one format at a time, so between the two writes the sidecar exists and one payload does not. A route falling back to the file it *can* find would hand GIfTI to a TVSC1 reader. |
| **`DEFAULT_FORMAT` is published last.** | The sidecar is shared between formats and `publish` stamps `bytes` with the payload it just wrote, so the manifest's `bytes` would otherwise be whichever format happened to be second. |

### 1.1 Measured on the live container (sub-ernie)

| Artifact | TVSC1 | GIfTI | vertices / triangles |
|---|---|---|---|
| `skin` | 1 391 840 B | **1 299 239 B** | 38 952 / 77 032 |
| `gm` | 2 591 888 B | **2 444 872 B** | 70 586 / 145 402 |
| `labels-DK40` | 988 236 B | 1 093 920 B | 70 586, 70 regions + unlabelled |

GIfTI is *smaller* than the bespoke binary for both surfaces (zlib beats raw float32/uint32); the
labels payload is larger because it repeats the vertex positions the engine needs to hang the field
on. Every payload is inside decision S3's 3 MB budget, and the budget test now checks **every**
serialisation rather than the one `bytes` happens to name.

Surface build (both formats, one `read_msh`): `x-scene-build-ms: 988.3` for `skin`, 2 140 ms for
`gm`, i.e. the GIfTI encode is inside the existing budget rather than beside it.

### 1.2 The alignment guarantee, re-run on the new format

`tests/test_scene_realdata.py`'s fixtures are now parametrised over `["tvsc", "gii"]`, and the GIfTI
half is decoded with **nibabel** — a different reader from the writer, deliberately, since a round
trip through our own parser would prove only that it agrees with itself.

```
tests/test_scene_realdata.py::test_the_labels_payload_is_aligned_to_the_served_gm_surface[format=tvsc] PASSED
tests/test_scene_realdata.py::test_every_region_lands_where_the_annot_says_it_is[format=tvsc]          PASSED
tests/test_scene_realdata.py::test_the_bounding_box_check_can_actually_fail[format=tvsc]               PASSED
tests/test_scene_realdata.py::test_the_labels_payload_is_aligned_to_the_served_gm_surface[format=gii]  PASSED
tests/test_scene_realdata.py::test_the_gifti_label_table_is_the_atlas_and_starts_with_no_region[gii]   PASSED
tests/test_scene_realdata.py::test_every_region_lands_where_the_annot_says_it_is[format=gii]           PASSED
tests/test_scene_realdata.py::test_the_bounding_box_check_can_actually_fail[format=gii]                PASSED
```

Both formats: `[ernie] DK40: 68 regions checked, 0 outside`, and the mirror control
`34 lh regions tested against their rh boxes, 0 would have passed`. Whole file:
**28 passed, 1 skipped** in 12.1 s (`simnibs_python -m pytest`, `TIT_SCENE_TESTDATA=/mnt/000`).

### 1.3 Each new test shown failing first

| Test | What was removed | Observed |
|---|---|---|
| `test_the_gifti_label_table_is_the_atlas_and_starts_with_no_region` | the `NO_REGION` row from `label_table_from_legend` | `AssertionError: the first row of the table is 1/'bankssts', so an unlabelled vertex would take that region's colour` |
| `test_the_etag_names_the_format_so_one_payload_cannot_answer_for_the_other` | the `fmt` from the ETag | 1 failed (`tvsc_response.headers["etag"] != gii_response.headers["etag"]`) |

`tests/test_scene_gifti.py` (18 tests) pins the document itself: intents, declared dimensions, the
scanner-anat identity coordinate system, zlib-not-gzip, float64→float32, the four guards.

### 1.4 Files

`tit/scene/gifti.py` (new) · `tit/scene/build.py` (`_publish_formats`, `DEFAULT_FORMAT`, both
encoders) · `tit/scene/cache.py` (`FORMATS`, `ext=` on `artifact_paths`/`find_cached`/`publish`) ·
`tit/server/routes/scene.py` (`?format`, `_payload_response`, the format in the ETag) ·
`contracts/openapi.v1.yaml` (+ regenerated `.json` and `desktop/src/renderer/api/schema.d.ts`) ·
`tests/test_scene_gifti.py` (new) · `tests/test_scene_routes.py` (+5) ·
`tests/test_scene_realdata.py` (parametrised, +1) · `desktop/tests/e2e/real/embed-occlusion.spec.ts`
(new).

## 2. Requests / corrections to other lanes

1. **Lane U's request 1 is a misreading, and acting on it would be a regression.** Lane U asked for
   `isEmbedMessage` to accept `tvx` across the supported *protocol* range. But lane T deliberately
   left the **envelope** at 1 and moved only `ready.version` — measured live above:
   `{tvx: 1, version: 2}`. `tvx` is the field whose whole job is to reject a message this host
   cannot parse; widening it to `1..2` would make the host accept an envelope from a future
   *breaking* protocol and try to read it as protocol 1. **`viewer/protocol.ts` is left as it is**,
   and the reason is written into it.
2. **Lane T / the maintainer: `docs/EMBED.md`'s host→embed table says `setPoints` → "Reply:
   `layers`".** It is not a reply — `host.ts`'s `setPoints` case returns without `withId`, so the
   `layers` event carries no correlation id and a host awaiting one hangs. Measured: the first run
   of the occlusion spec failed with `no reply to setPoints` after 60 s. Same for `setPointTool` and
   `setPointSelection`. Either the table should say "Event" for those rows, or the handlers should
   echo the id.
