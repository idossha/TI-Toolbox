"""``tit.catalog.classify_view_file`` over sub-ernie's real file listing.

Maintainer, 2026-09-07, on the Menu's Anatomy branch tagging `lh.central`, `lh.pial` and
`lh.white` as MESH beside the true `Head mesh (ernie)`: *"Please distinguish between NIfTI, mesh,
and a surface — a mesh is a tetrahedral FEM, a surface is just a triangular 2-D surface."*

**Why the fixture is a real listing and not a hand-written one.** The failure it is guarding
against was not a missing rule; it was a rule (`path.endswith((".msh", ".gii"))`) that was right
about `ernie.msh` and silently wrong about every file next to it. A hand-written fixture is a
list of the cases the author already had in mind, so it reproduces exactly that blind spot. The
225 lines in `tests/data/ernie_file_listing.txt` are `find` output from the dev container's
`sub-ernie` — `m2m_ernie/` in full plus FreeSurfer's `surf/` and `mri/` — and they contain the
things nobody writes down: `lh.pial.sigma`, `lh.smoothwm.K.crv`, `lh.white.preaparc.H`,
`aparc_resampled_256x256x208.nii.gz`, a `.DS_Store`. Regenerate with

    docker exec <container> sh -c 'cd /mnt/000/derivatives/SimNIBS/sub-ernie && find m2m_ernie -type f | sort'

The listing is materialised as empty files under `tmp_path` rather than classified as bare
strings, because one of the rules — a `<stem>_LUT.txt` sidecar marks a label volume — is a fact
about a file's *neighbours*, and a string list cannot express it.
"""

from __future__ import annotations

import os

import pytest

from tit.catalog import (
    VIEW_ATTACHMENT_KINDS,
    classify_view_file,
    surface_attachments,
)

LISTING = os.path.join(os.path.dirname(__file__), "data", "ernie_file_listing.txt")

KINDS = {
    "volume",
    "label-volume",
    "surface",
    "mesh",
    "annotation",
    "morph",
    "surface-data",
}


@pytest.fixture(scope="module")
def listing() -> list[str]:
    with open(LISTING, encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip()]


@pytest.fixture(scope="module")
def tree(tmp_path_factory, listing: list[str]) -> str:
    """The listing as empty files — the sidecar rule needs real neighbours."""
    root = tmp_path_factory.mktemp("ernie")
    for relative in listing:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    return str(root)


@pytest.fixture(scope="module")
def classified(tree: str, listing: list[str]) -> dict[str, str | None]:
    return {rel: classify_view_file(os.path.join(tree, rel)) for rel in listing}


def test_every_file_is_classified_or_refused(classified):
    """No answer outside the seven kinds, and `None` is a legitimate one."""
    for relative, kind in classified.items():
        assert kind is None or kind in KINDS, f"{relative} -> {kind!r}"


def test_the_head_model_is_the_only_mesh(classified):
    """A mesh is the tetrahedral FEM domain. There is exactly one of those here."""
    assert [rel for rel, kind in classified.items() if kind == "mesh"] == [
        "m2m_ernie/ernie.msh"
    ]


def test_no_surface_is_reported_as_a_mesh(classified):
    """The regression itself: a `.gii` sheet is not the FEM volume.

    Stated over the whole listing rather than over the three names in the screenshot, because the
    bug was a rule that swept a whole extension.
    """
    surfaces = {rel for rel, kind in classified.items() if kind == "surface"}
    assert "m2m_ernie/surfaces/lh.central.gii" in surfaces
    assert "m2m_ernie/surfaces/rh.pial.gii" in surfaces
    assert "m2m_ernie/surfaces/lh.white.gii" in surfaces
    assert not any(rel.endswith(".gii") and kind == "mesh" for rel, kind in classified.items())


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        # NIfTI / MGZ, continuous.
        ("m2m_ernie/T1.nii.gz", "volume"),
        ("m2m_ernie/T2_reg.nii.gz", "volume"),
        ("m2m_ernie/T1_ernie_MNI.nii.gz", "volume"),
        ("m2m_ernie/segmentation/T1_bias_corrected.nii.gz", "volume"),
        ("freesurfer/mri/brain.mgz", "volume"),
        # NIfTI / MGZ, integer parcellations. `labeling` and `final_tissues` are caught by their
        # own `_LUT.txt` sidecar; the FreeSurfer ones carry no sidecar and are caught by name.
        ("m2m_ernie/segmentation/labeling.nii.gz", "label-volume"),
        ("m2m_ernie/final_tissues.nii.gz", "label-volume"),
        ("freesurfer/mri/aparc+aseg.mgz", "label-volume"),
        ("freesurfer/mri/aparc.a2009s+aseg.mgz", "label-volume"),
        ("freesurfer/mri/aseg.mgz", "label-volume"),
        ("freesurfer/mri/ThalamicNuclei.v13.T1.mgz", "label-volume"),
        # Geometry.
        ("m2m_ernie/ernie.msh", "mesh"),
        ("m2m_ernie/surfaces/lh.central.gii", "surface"),
        ("m2m_ernie/surfaces/rh.sphere.reg.gii", "surface"),
        ("freesurfer/surf/lh.pial", "surface"),
        ("freesurfer/surf/rh.inflated", "surface"),
        ("freesurfer/surf/lh.smoothwm", "surface"),
        # Attachments.
        ("m2m_ernie/segmentation/lh.ernie_DK40.annot", "annotation"),
        ("m2m_ernie/segmentation/rh.ernie_HCP_MMP1.annot", "annotation"),
        ("freesurfer/surf/lh.thickness", "morph"),
        ("freesurfer/surf/rh.curv", "morph"),
        ("freesurfer/surf/lh.sulc", "morph"),
        ("freesurfer/surf/rh.area", "morph"),
        # Refused: recon-all's own bookkeeping, and things that are not geometry at all.
        ("freesurfer/surf/lh.pial.T1", None),
        ("freesurfer/surf/lh.orig.nofix", None),
        ("freesurfer/surf/lh.smoothwm.K.crv", None),
        ("freesurfer/surf/lh.curv.pial", None),
        ("freesurfer/surf/lh.area.mid", None),
        ("freesurfer/surf/rh.white.preaparc", None),
        ("m2m_ernie/surfaces/lh.pial.sigma", None),
        ("m2m_ernie/segmentation/coregistrationMatrices.mat", None),
        ("m2m_ernie/eeg_positions/GSN-HydroCel-185.csv", None),
        ("m2m_ernie/charm_report.html", None),
        ("m2m_ernie/segmentation/labeling_LUT.txt", None),
    ],
)
def test_named_files(tree, relative, expected):
    assert classify_view_file(os.path.join(tree, relative)) == expected


def test_data_gifti_is_not_geometry(tmp_path):
    """`.func.gii`/`.shape.gii` are numbers *for* a surface, not a surface.

    Not in ernie's own listing — SimNIBS writes none — but it is what an fsaverage projection
    produces, and the branch has to be right before that lands rather than after.
    """
    for name, expected in (
        ("lh.thickness.shape.gii", "surface-data"),
        ("lh.TI_max.func.gii", "surface-data"),
        ("lh.central.surf.gii", "surface"),
        ("lh.central.gii", "surface"),
    ):
        target = tmp_path / name
        target.touch()
        assert classify_view_file(str(target)) == expected, name


def test_attachments_are_matched_by_hemisphere(tree):
    """A left surface offers the left parcellations, and none of the right ones."""
    surfaces = os.path.join(tree, "m2m_ernie", "surfaces")
    segmentation = os.path.join(tree, "m2m_ernie", "segmentation")
    found = surface_attachments(
        os.path.join(surfaces, "lh.central.gii"), extra_dirs=(segmentation,)
    )
    names = [os.path.basename(p) for p in found]
    assert names == [
        "lh.ernie_DK40.annot",
        "lh.ernie_HCP_MMP1.annot",
        "lh.ernie_a2009s.annot",
    ]
    assert all(classify_view_file(p) in VIEW_ATTACHMENT_KINDS for p in found)
    assert not any(os.path.basename(p).startswith("rh.") for p in found)


def test_attachments_of_a_non_hemisphere_surface_are_empty(tree):
    assert surface_attachments(os.path.join(tree, "m2m_ernie", "ernie.msh")) == []
