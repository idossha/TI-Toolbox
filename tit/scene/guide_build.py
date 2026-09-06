"""Generate the packaged guide scene (``tit/scene/guide/``) from one head model.

This is a **developer tool**, not part of the running app: it needs SimNIBS,
nibabel and scipy, it reads a 184 MB mesh, and it takes minutes. The server
only ever reads what it wrote (:mod:`tit.scene.guide`).

Run it inside the toolbox container, where SimNIBS lives::

    docker exec ti-toolbox-fad740e5-tit-1 \\
        /root/SimNIBS-4.6/bin/simnibs_python -m tit.scene.guide_build \\
        --project /mnt/000 --subject ernie --out /ti-toolbox/tit/scene/guide

What it does, and why in this order:

1. Builds the two surfaces and every cortical atlas' labels through the
   **ordinary** :mod:`tit.scene.build` pipeline, into the project's own scene
   cache. The guide is therefore built by the same code that builds a
   subject's pane, so a budget or winding fix cannot apply to one and not the
   other.
2. Copies those exact cached bytes into the package, renamed to
   fingerprint-free, stable file names — the packaged guide is immutable, so
   the fingerprint that keys a *cache* has no job here.
3. Reads every EEG net as JSON (a few hundred rows each; cheap and exact).
4. Writes ``manifest.json`` enumerating all of it with a ``sha256`` and a byte
   count per file, so the gate test can prove that what the manifest
   advertises is what the package contains.

Never copied: the ``m2m_`` directory, the head mesh, the label *volume*.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from tit.scene import build, cache, guide

#: Serialisations packaged per artifact kind, and the reason for each choice.
#:
#: Surfaces ship both: ``gii`` is what the embedded Tetravox renderer reads,
#: and ``tvsc`` keeps the frozen §2.3 wire format — and its ≤3 MB / ≤150 k
#: budget — a checkable property of the guide rather than of subject data only.
#: Labels ship both for the same reason: the desktop pane's own WebGL2 renderer
#: reads ``tvsc`` (per-vertex ``uint16`` labels aligned to ``gm``), and the
#: ``gii`` copies stay while anything else still consumes them. Between
#: 2026-09-05 and 2026-09-06 labels shipped as ``gii`` only, on the premise
#: that nothing read the ``tvsc`` payload — true while the renderer was
#: retired, and the reason the pane could not highlight a region when it came
#: back.
SURFACE_FORMATS = ("tvsc", "gii")
LABEL_FORMATS = ("tvsc", "gii")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy(src: Path, dest: Path) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    return {"bytes": dest.stat().st_size, "sha256": sha256_of(dest)}


def _write_json(dest: Path, body: Any) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(body, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    return {"bytes": dest.stat().st_size, "sha256": sha256_of(dest)}


def _union(boxes: list[list[float]]) -> list[float] | None:
    box: list[float] | None = None
    for other in boxes:
        if not other:
            continue
        box = (
            list(other)
            if box is None
            else [min(a, b) for a, b in zip(box[:3], other[:3])]
            + [max(a, b) for a, b in zip(box[3:], other[3:])]
        )
    return box


def generate(project: str, subject: str, out: Path, label: str) -> dict[str, Any]:
    """Build every guide asset and write ``out/manifest.json``. Returns it."""
    from tit import catalog
    from tit.paths import get_path_manager

    pm = get_path_manager(project_dir=project)
    started = time.perf_counter()

    surface_metas = build.build_surfaces(pm, subject)
    surface_fp = build.surface_fingerprint(pm, subject)

    out.mkdir(parents=True, exist_ok=True)
    parts: list[dict[str, Any]] = []
    for part in build.PART_TAGS:
        meta = surface_metas[part]
        files: dict[str, Any] = {}
        for fmt in SURFACE_FORMATS:
            found = cache.find_cached(pm.project_dir, subject, part, surface_fp, fmt)
            if found is None:
                raise SystemExit(f"{part}.{fmt} was not published by build_surfaces")
            rel = f"surfaces/{part}.{fmt}"
            files[fmt] = rel
            files[f"{fmt}_meta"] = _copy(found.path, out / rel)
        parts.append(
            {
                "id": part,
                "kind": "surface",
                "triangles": meta["triangles"],
                "vertices": meta["vertices"],
                # `bytes` is the TVSC1 payload's size, as in the scene
                # manifest, so §S3's ≤3 MB budget reads off the same number.
                "bytes": files["tvsc_meta"]["bytes"],
                "fingerprint": f"guide-{guide.GUIDE_VERSION}-{part}",
                "url": f"/api/guide/surface?part={part}",
                "simplified": meta["simplified"],
                "within_budget": meta["within_budget"],
                "max_deviation_mm": meta["max_deviation_mm"],
                "bbox": meta["bbox"],
                "focus_bbox": meta["focus_bbox"],
                "files": files,
            }
        )

    atlases: list[dict[str, Any]] = []
    for entry in catalog.atlases(pm, subject, kind="cortical") or []:
        atlas_id = str(entry["id"])
        hemispheres = sorted(build.annot_paths(pm, subject, atlas_id))
        if not hemispheres:
            continue
        meta = build.build_labels(pm, subject, atlas_id)
        fp = build.labels_fingerprint(pm, subject, atlas_id)
        key = build._labels_key(atlas_id)
        files = {}
        for fmt in LABEL_FORMATS:
            found = cache.find_cached(pm.project_dir, subject, key, fp, fmt)
            if found is None:
                raise SystemExit(f"{key}.{fmt} was not published by build_labels")
            rel = f"labels/{atlas_id}.{fmt}"
            files[fmt] = rel
            files[f"{fmt}_meta"] = _copy(found.path, out / rel)
        legend_rel = f"legends/{atlas_id}.json"
        legend_body = {
            "atlas": atlas_id,
            "space": guide.GUIDE_SPACE,
            "aligned_to": meta.get("aligned_to", "gm"),
            "vertices": meta["vertices"],
            "radius_mm": meta["radius_mm"],
            "labelled_fraction": meta["labelled_fraction"],
            "legend": meta["legend"],
            "url": f"/api/guide/labels?atlas={atlas_id}",
        }
        legend_meta = _write_json(out / legend_rel, legend_body)
        atlases.append(
            {
                "id": atlas_id,
                "hemispheres": hemispheres,
                "regions": len(meta["legend"]),
                "url": f"/api/guide/regions?atlas={atlas_id}",
                "files": files,
                "legend_file": legend_rel,
                "legend_meta": legend_meta,
            }
        )

    nets: list[dict[str, Any]] = []
    for net_name in sorted(pm.list_eeg_caps(subject)):
        body = build.read_net(pm, subject, net_name)
        electrodes = body.get("electrodes", [])
        if not electrodes:
            continue
        rel = f"nets/{net_name}.json"
        net_body = {
            "net": net_name,
            "space": guide.GUIDE_SPACE,
            "electrodes": electrodes,
        }
        file_meta = _write_json(out / rel, net_body)
        nets.append(
            {
                "name": net_name,
                "electrodes": len(electrodes),
                "url": f"/api/guide/electrodes?net={net_name}",
                "file": rel,
                **file_meta,
            }
        )

    manifest = {
        "guide": {"id": subject, "label": label},
        "guide_version": guide.GUIDE_VERSION,
        "builder_version": build.BUILDER_VERSION,
        # Never "subject-ras": these millimetres belong to the guide head, and
        # writing them into a research subject's config would be wrong in a
        # way nothing downstream can detect (R4).
        "space": guide.GUIDE_SPACE,
        "bbox": _union([p["bbox"] for p in parts]),
        "focus_bbox": _union([p["focus_bbox"] for p in parts]),
        "parts": parts,
        "nets": nets,
        "atlases": atlases,
        # The label volume is deliberately not packaged: it is a ~10 MB NIfTI
        # whose only use in a pane is region picking, which the atlas payloads
        # already do on the surface the pane draws.
        "volumes": [],
        "cache": {"state": "ready", "built_ms": 0.0},
        "provenance": {
            "source": "SimNIBS example dataset, subject 'ernie'",
            "source_url": "https://github.com/simnibs/example-dataset",
            "license": "GPL-3.0-or-later",
            "notes": "See tit/scene/guide/PROVENANCE.md.",
        },
        "generated": {
            "subject": subject,
            "generator": "tit.scene.guide_build",
            "seconds": round(time.perf_counter() - started, 1),
        },
    }
    _write_json(out / guide.MANIFEST_NAME, manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="BIDS project holding the source subject")
    parser.add_argument("--subject", default="ernie")
    parser.add_argument("--out", default=str(guide.GUIDE_DIR))
    parser.add_argument("--label", default="Ernie (SimNIBS example head)")
    args = parser.parse_args(argv)
    manifest = generate(args.project, args.subject, Path(args.out), args.label)
    total = sum(
        f["bytes"]
        for entry in manifest["parts"] + manifest["atlases"]
        for key, f in entry.get("files", {}).items()
        if key.endswith("_meta")
    ) + sum(n["bytes"] for n in manifest["nets"]) + sum(
        a["legend_meta"]["bytes"] for a in manifest["atlases"]
    )
    for part in manifest["parts"]:
        print(
            f"{part['id']:5s} {part['triangles']:>7d} tris  "
            f"tvsc {part['files']['tvsc_meta']['bytes'] / 1e6:.2f} MB  "
            f"gii {part['files']['gii_meta']['bytes'] / 1e6:.2f} MB  "
            f"within_budget={part['within_budget']}"
        )
    for atlas in manifest["atlases"]:
        print(
            f"{atlas['id']:10s} {atlas['regions']:>4d} regions  "
            f"tvsc {atlas['files']['tvsc_meta']['bytes'] / 1e6:.2f} MB  "
            f"gii {atlas['files']['gii_meta']['bytes'] / 1e6:.2f} MB"
        )
    print(f"{len(manifest['nets'])} nets, packaged total {total / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":  # pragma: no cover - developer entry point
    sys.exit(main())
