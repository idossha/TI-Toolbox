"""The packaged guide scene: what ships, and that the manifest describes it.

What this pins (plan R4's gate, the half that is about the *package*)
    every asset the manifest advertises resolves on disk; its recorded size and
    SHA-256 are the file's own; the manifest's atlas and net ids are exactly
    the ids of the packaged catalogs; every surface stays inside the frozen
    §S3 budget (≤ 150 000 triangles, ≤ 3 MB of TVSC1); the coordinate space is
    ``guide-ras`` and never ``subject-ras``; and no head model, mesh or label
    volume was packaged along the way.

Where the numbers come from
    The package itself. Triangle counts are re-read out of the TVSC1 header by
    :func:`tit.scene.tvsc.decode` -- an independent reader of the same bytes --
    rather than trusted from the sidecar the generator wrote.

Deliberately elsewhere
    The HTTP surface is ``tests/test_guide_routes.py``. What a real mesh
    produces is ``tit/scene/guide_build.py``'s own run, recorded in
    ``tit/scene/guide/PROVENANCE.md``.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from tit.scene import build, guide, tvsc

pytestmark = pytest.mark.skipif(
    not (guide.GUIDE_DIR / guide.MANIFEST_NAME).is_file(),
    reason=(
        "the guide assets are not present in this checkout; regenerate with "
        "`simnibs_python -m tit.scene.guide_build --project <bids> --subject ernie`"
    ),
)


@pytest.fixture(scope="module")
def manifest() -> dict:
    return guide.manifest()


def test_the_guide_declares_its_own_space_and_never_subject_ras(manifest: dict) -> None:
    """The whole point of R4: these millimetres are not any subject's.

    A guide payload labelled ``subject-ras`` would be indistinguishable on the
    wire from a real subject's scene, and a client would then be free to write
    a guide coordinate into a research subject's configuration.
    """
    assert manifest["space"] == guide.GUIDE_SPACE == "guide-ras"
    for atlas in manifest["atlases"]:
        assert guide.legend(atlas["id"])["space"] == "guide-ras"
    for net in manifest["nets"]:
        assert guide.electrodes(net["name"])["space"] == "guide-ras"


def test_every_asset_the_manifest_advertises_resolves(manifest: dict) -> None:
    assets = guide.iter_assets()
    assert assets, "the manifest advertises at least one asset"
    for rel, asset in assets:
        assert asset.path.is_file(), rel


def test_recorded_sizes_and_digests_are_the_files_own(manifest: dict) -> None:
    """A manifest that merely *claims* a size and a digest proves nothing.

    Recomputed here from the bytes on disk, so a truncated or half-copied asset
    is a failure rather than a manifest the server happily serves.
    """
    checked = 0
    for entry in manifest["parts"] + manifest["atlases"]:
        for fmt, rel in entry.get("files", {}).items():
            if fmt.endswith("_meta"):
                continue
            meta = entry["files"][f"{fmt}_meta"]
            path = guide.GUIDE_DIR / rel
            assert path.stat().st_size == meta["bytes"], rel
            assert hashlib.sha256(path.read_bytes()).hexdigest() == meta["sha256"], rel
            checked += 1
    for net in manifest["nets"]:
        path = guide.GUIDE_DIR / net["file"]
        assert path.stat().st_size == net["bytes"], net["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == net["sha256"], net["file"]
        checked += 1
    assert checked >= 6, "surfaces in two formats, three atlases and the nets"


def test_manifest_ids_equal_the_packaged_catalog_ids(manifest: dict) -> None:
    """R4's gate: what the manifest lists is what the package contains.

    Both directions. An id in the manifest with no file is a broken pane; a
    file with no manifest row is dead weight in every installation and, worse,
    an atlas the user cannot select even though it shipped.
    """
    packaged_atlases = sorted(p.stem for p in (guide.GUIDE_DIR / "labels").glob("*.gii"))
    assert sorted(guide.atlas_ids()) == packaged_atlases
    assert sorted(guide.atlas_ids()) == sorted(
        p.stem for p in (guide.GUIDE_DIR / "legends").glob("*.json")
    )

    packaged_nets = sorted(p.name[: -len(".json")] for p in (guide.GUIDE_DIR / "nets").glob("*.json"))
    assert sorted(guide.net_names()) == packaged_nets

    packaged_parts = sorted({p.stem for p in (guide.GUIDE_DIR / "surfaces").glob("*")})
    assert sorted(guide.part_ids()) == packaged_parts


def test_every_surface_stays_inside_the_frozen_tvsc_budget(manifest: dict) -> None:
    """≤ 3 MB and ≤ 150 000 triangles per surface, read back from the payload.

    ``decode`` is the independent reader: the triangle count asserted is the
    one in the TVSC1 header, not the one the generator recorded beside it.
    """
    assert [p["id"] for p in manifest["parts"]] == ["skin", "gm"]
    for part in manifest["parts"]:
        blob = (guide.GUIDE_DIR / part["files"]["tvsc"]).read_bytes()
        payload = tvsc.decode(blob)
        triangles = int(payload.indices.shape[0])  # decode() reshapes to (N, 3)
        assert triangles == part["triangles"]
        assert triangles <= build.MAX_TRIANGLES, (part["id"], triangles)
        assert len(blob) <= build.MAX_BYTES, (part["id"], len(blob))
        assert part["within_budget"] is True
        assert part["bytes"] == len(blob)


def test_the_budget_check_can_fail(manifest: dict) -> None:
    """The assertion above would pass on any number if the limits were huge."""
    gm = next(p for p in manifest["parts"] if p["id"] == "gm")
    assert gm["triangles"] > 1000, "a real cortical surface, not a stub"
    assert build.MAX_TRIANGLES == 150_000 and build.MAX_BYTES == 3 * 1024 * 1024


def test_no_head_model_volume_or_mesh_was_packaged() -> None:
    """"Do not package a full m2m or rebuild at runtime" (R4), as a check.

    The failure it prevents is silent and expensive: a generator change that
    started copying ``labeling.nii.gz`` or an ``.annot`` would add tens of MB
    to every installation and nobody would notice until a release was built.
    """
    forbidden = {".msh", ".nii", ".gz", ".mgz", ".annot", ".mat"}
    offenders = [
        str(p.relative_to(guide.GUIDE_DIR))
        for p in guide.GUIDE_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in forbidden
    ]
    assert offenders == []
    total = sum(p.stat().st_size for p in guide.GUIDE_DIR.rglob("*") if p.is_file())
    # The source m2m_ernie is ~1.3 GB and its mesh alone is 184 MB; a guide that
    # crossed 40 MB would mean something whole was copied rather than derived.
    assert total < 40 * 1024 * 1024, f"packaged guide is {total / 1e6:.1f} MB"


def test_provenance_and_licence_are_recorded(manifest: dict) -> None:
    provenance = manifest["provenance"]
    assert provenance["source"] and provenance["license"]
    note = (guide.GUIDE_DIR / "PROVENANCE.md").read_text(encoding="utf-8")
    assert provenance["license"] in note
    assert "redistribution" in note.lower()


def test_electrode_and_region_payloads_carry_names_a_form_can_use(manifest: dict) -> None:
    """Name-based selection is the only selection the guide is allowed to drive."""
    net = manifest["nets"][0]["name"]
    electrodes = guide.electrodes(net)["electrodes"]
    assert len(electrodes) == manifest["nets"][0]["electrodes"]
    assert all(isinstance(e["name"], str) and e["name"] for e in electrodes)
    assert all(len(e["world"]) == 3 for e in electrodes)

    atlas = manifest["atlases"][0]["id"]
    legend = guide.legend(atlas)["legend"]
    assert len(legend) == manifest["atlases"][0]["regions"]
    assert {row["hemi"] for row in legend} <= {"lh", "rh"}
    assert all(row["label"] > 0 and row["name"] for row in legend)


def test_a_missing_guide_says_how_to_regenerate_it(tmp_path, monkeypatch) -> None:
    """The failure a broken installation gets is a sentence, not a traceback."""
    monkeypatch.setenv("TIT_GUIDE_DIR", str(tmp_path))
    with pytest.raises(guide.GuideUnavailable) as excinfo:
        guide.manifest()
    assert "guide_build" in str(excinfo.value)


def test_an_unknown_id_lists_what_is_packaged(manifest: dict) -> None:
    for call in (
        lambda: guide.surface("cerebellum"),
        lambda: guide.labels("NoSuchAtlas"),
        lambda: guide.electrodes("no-such-net.csv"),
    ):
        with pytest.raises(guide.GuideUnavailable) as excinfo:
            call()
        assert "it has:" in str(excinfo.value)


def test_a_hand_edited_manifest_cannot_read_outside_the_package(tmp_path, monkeypatch) -> None:
    """The manifest's paths are data too, and data is not trusted with a path."""
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "space": "guide-ras",
                "parts": [{"id": "skin", "files": {"tvsc": "../../../etc/passwd"}}],
                "nets": [],
                "atlases": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TIT_GUIDE_DIR", str(tmp_path))
    with pytest.raises(guide.GuideUnavailable):
        guide.surface("skin", "tvsc")
