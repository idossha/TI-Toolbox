"""Unit tests for :mod:`tit.viewspec`.

Filenames used here (``<sim>_TI_subject_TI_max.nii.gz``,
``<sim>_TI_MNI_MNI_TI_max.nii.gz``, ``ernie_TDCS_1_scalar_subject_magnE.nii.gz``,
atlas LUT sidecar names, ...) are copied verbatim from a real run on
``sub-ernie`` in Dataset 000 (container check at the bottom of this lane's
final report), not invented -- so a passing test here is evidence the layer
logic matches what a real project actually contains on disk.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tit import viewspec
from tit.paths import PathManager, get_path_manager, reset_path_manager


@pytest.fixture(autouse=True)
def _reset():
    reset_path_manager()
    yield
    reset_path_manager()


@pytest.fixture()
def pm(tmp_path: Path, monkeypatch) -> PathManager:
    """``ernie``: m2m + one TI simulation with subject and MNI TI_max/HF niftis.

    Also patches :func:`tit.viewspec.mni_resources_dir` at a tmp directory
    seeded with a fake MNI template/atlas/LUT (bug 4's fallback path).
    """
    pm = get_path_manager(str(tmp_path))  # build_view() reads the global singleton
    m2m = pm.m2m("ernie")
    os.makedirs(m2m)
    Path(m2m, "T1.nii.gz").write_bytes(b"t1")
    Path(m2m, "T1_ernie_MNI.nii.gz").write_bytes(b"t1mni")
    seg_dir = os.path.join(m2m, "segmentation")
    os.makedirs(seg_dir)
    Path(seg_dir, "labeling.nii.gz").write_bytes(b"lab")
    Path(seg_dir, "labeling_LUT.txt").write_text("0 Unknown 0 0 0\n1 GM 0 255 0\n")

    sim_dir = pm.simulation("ernie", "L_Insula")
    ti_niftis = os.path.join(sim_dir, "TI", "niftis")
    os.makedirs(ti_niftis)
    for name in (
        "L_Insula_TI_subject_TI_max.nii.gz",
        "grey_L_Insula_TI_subject_TI_max.nii.gz",
        "L_Insula_TI_MNI_MNI_TI_max.nii.gz",
        "grey_L_Insula_TI_MNI_MNI_TI_max.nii.gz",
        "white_L_Insula_TI_subject_TI_max.nii.gz",
    ):
        Path(ti_niftis, name).write_bytes(b"x")

    hf_niftis = os.path.join(sim_dir, "high_Frequency", "niftis")
    os.makedirs(hf_niftis)
    for name in (
        "ernie_TDCS_1_scalar_subject_magnE.nii.gz",
        "ernie_TDCS_2_scalar_subject_magnE.nii.gz",
        "ernie_TDCS_1_scalar_MNI_MNI_magnE.nii.gz",
        "ernie_TDCS_2_scalar_MNI_MNI_magnE.nii.gz",
    ):
        Path(hf_niftis, name).write_bytes(b"x")

    # A fake resources/atlas dir for the MNI-space branches, at a repo-relative
    # style layout so mni_resources_dir()'s fallback logic is what we exercise.
    resources = tmp_path / "resources_atlas"
    resources.mkdir()
    (resources / "MNI152_T1_1mm.nii.gz").write_bytes(b"mni-t1")
    (resources / "CIT168_labeling_MNI152NLin2009cAsym.nii.gz").write_bytes(b"atlas")
    (resources / "CIT168_labeling_MNI152NLin2009cAsym_LUT.txt").write_text(
        "1 Region 1 2 3\n"
    )
    monkeypatch.setattr(viewspec, "mni_resources_dir", lambda: str(resources))
    monkeypatch.setattr(viewspec, "MNI_TEMPLATE", "MNI152_T1_1mm.nii.gz")
    monkeypatch.setattr(
        viewspec, "DEFAULT_MNI_ATLAS", "CIT168_labeling_MNI152NLin2009cAsym.nii.gz"
    )

    return pm


# ── bug 1: HF glob ────────────────────────────────────────────────────────────


def test_hf_glob_matches_real_filenames_subject_space(pm: PathManager) -> None:
    sim_dir = pm.simulation("ernie", "L_Insula")
    layers = viewspec._hf_layers(sim_dir, "subject")
    paths = {os.path.basename(layer["path"]) for layer in layers}
    assert paths == {
        "ernie_TDCS_1_scalar_subject_magnE.nii.gz",
        "ernie_TDCS_2_scalar_subject_magnE.nii.gz",
    }


def test_hf_glob_matches_real_filenames_mni_space(pm: PathManager) -> None:
    sim_dir = pm.simulation("ernie", "L_Insula")
    layers = viewspec._hf_layers(sim_dir, "mni")
    paths = {os.path.basename(layer["path"]) for layer in layers}
    assert paths == {
        "ernie_TDCS_1_scalar_MNI_MNI_magnE.nii.gz",
        "ernie_TDCS_2_scalar_MNI_MNI_magnE.nii.gz",
    }


def test_original_hf_pattern_would_have_matched_nothing(pm: PathManager) -> None:
    """Pin the bug itself: the Qt tab's literal pattern never matches."""
    import glob

    hf_dir = os.path.join(
        pm.simulation("ernie", "L_Insula"), "high_Frequency", "niftis"
    )
    assert glob.glob(os.path.join(hf_dir, "*_scalar_magnE.nii.gz")) == []


# ── bug 2: labeling_LUT.txt ───────────────────────────────────────────────────


def test_subject_space_labeling_atlas_gets_its_lut(pm: PathManager) -> None:
    layer = viewspec._subject_atlas_layer(pm, "ernie", "subject")
    assert layer is not None
    assert layer["path"].endswith("labeling.nii.gz")
    assert layer["lut"] is not None
    assert layer["lut"].endswith("labeling_LUT.txt")


def test_subject_atlas_layer_prefers_fastsurfer_over_freesurfer(
    tmp_path: Path,
) -> None:
    """No ``segmentation/labeling.nii.gz`` -> falls through to
    ``VoxelAtlasManager``, which must search the FastSurfer ``mri/`` dir
    before the legacy FreeSurfer one (``tit.viewspec`` now passes
    ``fastsurfer_mri_dir`` alongside ``freesurfer_mri_dir``)."""
    pm = get_path_manager(str(tmp_path))
    m2m = pm.m2m("ernie")
    os.makedirs(m2m)
    Path(m2m, "T1.nii.gz").write_bytes(b"t1")

    fs_mri = pm.freesurfer_mri("ernie")
    os.makedirs(fs_mri)
    Path(fs_mri, "aparc.DKTatlas+aseg.mgz").write_bytes(b"legacy")

    fastsurfer_mri = pm.fastsurfer_mri("ernie")
    os.makedirs(fastsurfer_mri)
    Path(fastsurfer_mri, "aparc.DKTatlas+aseg.deep.mgz").write_bytes(b"deep")

    layer = viewspec._subject_atlas_layer(pm, "ernie", "subject")
    assert layer is not None
    assert layer["path"] == str(Path(fastsurfer_mri, "aparc.DKTatlas+aseg.deep.mgz"))


# ── bug 3: "*_LUT.txt" in MNI/group mode ─────────────────────────────────────


def test_mni_atlas_lut_finds_the_lut_suffix_sidecar(pm: PathManager) -> None:
    atlas_path = viewspec._default_mni_atlas_path()
    assert atlas_path is not None
    lut = viewspec._mni_atlas_lut(atlas_path)
    assert lut is not None and lut.endswith("_LUT.txt")


def test_massp_special_case_lut(tmp_path: Path) -> None:
    resources = tmp_path / "atlas"
    resources.mkdir()
    (resources / "massp2021-parcellation_decade-18to40.nii.gz").write_bytes(b"x")
    (resources / "massp2021_labels.txt").write_text("1 X 1 1 1\n")
    lut = viewspec._mni_atlas_lut(
        str(resources / "massp2021-parcellation_decade-18to40.nii.gz")
    )
    assert lut == str(resources / "massp2021_labels.txt")


# ── bug 4: MNI resources dir fallback ────────────────────────────────────────


def test_mni_resources_dir_falls_back_off_container_path(monkeypatch) -> None:
    monkeypatch.setattr(viewspec, "MNI_ATLAS_DIR", "/no/such/container/path")
    resolved = viewspec.mni_resources_dir()
    assert os.path.isdir(resolved)
    assert resolved == str(
        Path(viewspec.__file__).resolve().parent.parent / "resources" / "atlas"
    )


# ── bug 5: absolute thresholds kept regardless of "percentile" ──────────────


def test_heatscale_emitted_for_absolute_thresholds_without_a_percentile_flag() -> None:
    spec = {
        "space": "subject",
        "layers": [
            {
                "path": "/x/field.nii.gz",
                "kind": "volume",
                "colormap": "heat",
                "opacity": 0.8,
                "visible": True,
                "cal_min": 0.1,
                "cal_max": 0.5,
                "lut": None,
            }
        ],
    }
    args = viewspec.to_freeview_args(spec)
    assert args == [
        "/x/field.nii.gz:colormap=heat:opacity=0.8:visible=1:heatscale=0.1,0.5"
    ]


def test_no_heatscale_when_thresholds_absent() -> None:
    spec = {
        "space": "subject",
        "layers": [
            {
                "path": "/x/t1.nii.gz",
                "kind": "volume",
                "colormap": "grayscale",
                "opacity": 1.0,
                "visible": True,
            }
        ],
    }
    assert viewspec.to_freeview_args(spec) == [
        "/x/t1.nii.gz:colormap=grayscale:opacity=1.0:visible=1"
    ]


# ── bug 6: single-subject MNI is reachable ───────────────────────────────────


def test_subject_kind_mni_space_uses_mni_t1_and_mni_atlas(pm: PathManager) -> None:
    spec = viewspec.build_view("subject", subject="ernie", space="mni")
    assert spec is not None
    assert spec["space"] == "mni"
    paths = [layer["path"] for layer in spec["layers"]]
    assert any(p.endswith("T1_ernie_MNI.nii.gz") for p in paths)
    atlas_layers = [layer for layer in spec["layers"] if layer["colormap"] == "lut"]
    assert len(atlas_layers) == 1
    assert atlas_layers[0]["path"].endswith(
        "CIT168_labeling_MNI152NLin2009cAsym.nii.gz"
    )
    assert atlas_layers[0]["lut"] is not None


def test_subject_kind_subject_space_uses_subject_t1_and_labeling_atlas(
    pm: PathManager,
) -> None:
    spec = viewspec.build_view("subject", subject="ernie", space="subject")
    assert spec is not None
    paths = [layer["path"] for layer in spec["layers"]]
    assert any(p.endswith(os.sep + "T1.nii.gz") for p in paths)
    atlas_layers = [layer for layer in spec["layers"] if layer["colormap"] == "lut"]
    assert len(atlas_layers) == 1
    assert atlas_layers[0]["path"].endswith("labeling.nii.gz")


# ── build_view / to_freeview_args / freeview_command, general shape ────────


def test_build_view_unknown_kind_returns_none(pm: PathManager) -> None:
    assert viewspec.build_view("nonsense") is None


def test_build_view_unknown_subject_returns_none(pm: PathManager) -> None:
    assert viewspec.build_view("subject", subject="nope") is None


def test_build_view_simulation_ti_max_layers(pm: PathManager) -> None:
    spec = viewspec.build_view(
        "simulation", subject="ernie", simulation="L_Insula", space="subject"
    )
    assert spec is not None
    names = {os.path.basename(layer["path"]) for layer in spec["layers"]}
    assert "L_Insula_TI_subject_TI_max.nii.gz" in names
    assert "grey_L_Insula_TI_subject_TI_max.nii.gz" in names
    assert not any("MNI" in n for n in names if "TI_max" in n)
    # visibility: only the grey_ variant defaults to visible
    grey = next(
        layer
        for layer in spec["layers"]
        if os.path.basename(layer["path"]).startswith("grey_")
    )
    plain = next(
        layer
        for layer in spec["layers"]
        if os.path.basename(layer["path"]) == "L_Insula_TI_subject_TI_max.nii.gz"
    )
    assert grey["visible"] is True
    assert plain["visible"] is False


def test_build_view_simulation_unknown_returns_none(pm: PathManager) -> None:
    assert viewspec.build_view("simulation", subject="ernie", simulation="nope") is None


def test_build_view_custom_path(pm: PathManager) -> None:
    """A ``custom`` path is client-supplied and now jailed (ra_14 finding
    11) -- it must be a real file inside the project/resources tree, and the
    layer/args carry its *resolved* form (defeats a same-named symlink)."""
    mesh_path = os.path.join(pm.project_dir, "custom.msh")
    Path(mesh_path).write_bytes(b"mesh")
    resolved = str(Path(mesh_path).resolve())

    spec = viewspec.build_view("custom", path=mesh_path)
    assert {k: v for k, v in spec.items() if k != "scene"} == {
        "space": "subject",
        "layers": [
            {
                "path": resolved,
                "kind": "label",
                "colormap": "grayscale",
                "opacity": 1.0,
                "visible": True,
                "cal_min": None,
                "cal_max": None,
                "lut": None,
            }
        ],
        "freeview_args": [f"{resolved}:colormap=grayscale:opacity=1.0:visible=1"],
    }
    # The scene is the real Tetravox ViewSpec v2; tests/test_viewspec_scene.py owns its shape.
    # datasets[].path is the /api/files/raw URL (origin-relative), not the container path.
    assert spec["scene"]["datasets"][0]["path"] == "/api/files/raw" + resolved


def test_build_view_custom_no_path_returns_none() -> None:
    assert viewspec.build_view("custom") is None


def test_build_view_custom_path_outside_jail_returns_none(
    pm: PathManager, tmp_path_factory
) -> None:
    """A real, readable file is not enough -- it must be inside the project
    or ``resources/`` (ra_14 finding 11: this used to reach ``nib.load`` on
    any path on disk, including e.g. ``/etc/passwd``)."""
    outside = tmp_path_factory.mktemp("outside") / "secret.msh"
    outside.write_bytes(b"mesh")
    assert viewspec.build_view("custom", path=str(outside)) is None


def test_build_view_custom_path_nonexistent_returns_none(pm: PathManager) -> None:
    missing = os.path.join(pm.project_dir, "nope.msh")
    assert viewspec.build_view("custom", path=missing) is None


def test_freeview_command_prefixes_binary(pm: PathManager) -> None:
    path = os.path.join(pm.project_dir, "x.nii.gz")
    Path(path).write_bytes(b"x")
    spec = viewspec.build_view("custom", path=path)
    assert viewspec.freeview_command(spec)[0] == "freeview"
    assert viewspec.freeview_command(spec)[1:] == spec["freeview_args"]


def test_jail_roots_includes_project_and_resources_parent(pm: PathManager) -> None:
    roots = viewspec.jail_roots()
    assert Path(pm.project_dir).resolve() in roots
    resources_parent = Path(viewspec.mni_resources_dir()).resolve().parent
    assert resources_parent in roots


def test_resolve_jailed_rejects_traversal_and_missing_files(pm: PathManager) -> None:
    inside = os.path.join(pm.project_dir, "ok.txt")
    Path(inside).write_text("x")
    assert viewspec.resolve_jailed(inside) == Path(inside).resolve()
    assert viewspec.resolve_jailed(os.path.join(pm.project_dir, "missing.txt")) is None
    assert viewspec.resolve_jailed("/etc/passwd") is None
    assert (
        viewspec.resolve_jailed(os.path.join(pm.project_dir, "../../../etc/passwd"))
        is None
    )


def test_build_view_group_kind_uses_mni_template_and_atlas(pm: PathManager) -> None:
    spec = viewspec.build_view("group")
    assert spec is not None
    assert spec["space"] == "mni"
    names = [os.path.basename(layer["path"]) for layer in spec["layers"]]
    assert "MNI152_T1_1mm.nii.gz" in names
    assert "CIT168_labeling_MNI152NLin2009cAsym.nii.gz" in names


# ── percentile thresholding (v1) ──────────────────────────────────────────────


def test_build_view_heat_layers_carry_default_percentile_window(
    pm: PathManager,
) -> None:
    spec = viewspec.build_view(
        "simulation", subject="ernie", simulation="L_Insula", space="subject"
    )
    assert spec is not None
    heat_layers = [layer for layer in spec["layers"] if layer["colormap"] == "heat"]
    assert heat_layers
    assert all(layer["percentile"] == {"lo": 95.0, "hi": 99.9} for layer in heat_layers)


def test_build_view_never_crashes_when_percentile_cannot_be_resolved(
    pm: PathManager,
) -> None:
    """The fixture niftis are fake bytes, not real volumes: resolution must
    fail closed (leaving cal_min/cal_max as None) rather than raise."""
    spec = viewspec.build_view(
        "simulation", subject="ernie", simulation="L_Insula", space="subject"
    )
    assert spec is not None
    heat_layers = [layer for layer in spec["layers"] if layer["colormap"] == "heat"]
    assert all(
        layer["cal_min"] is None and layer["cal_max"] is None for layer in heat_layers
    )


def test_percentiles_from_array_computes_absolute_bounds() -> None:
    import numpy as np

    data = np.array([0, 0, 1, 2, 3, 4, 5, 100])
    resolved = viewspec._percentiles_from_array(data, 0, 100)
    assert resolved == (pytest.approx(1.0), pytest.approx(100.0))


def test_percentiles_from_array_returns_none_for_all_zero_volume() -> None:
    import numpy as np

    assert viewspec._percentiles_from_array(np.zeros((4, 4)), 50, 95) is None


def test_resolve_percentiles_fills_cal_min_max_from_a_real_volume(
    monkeypatch,
) -> None:
    import sys
    import types

    import numpy as np

    class _FakeImage:
        def get_fdata(self):
            return np.array([0, 1, 2, 3, 4, 100])

    fake_nib = types.SimpleNamespace(load=lambda path: _FakeImage())
    monkeypatch.setitem(sys.modules, "nibabel", fake_nib)

    spec = {
        "layers": [
            {
                "path": "/x.nii.gz",
                "cal_min": None,
                "cal_max": None,
                "percentile": {"lo": 0, "hi": 100},
            },
            {"path": "/y.nii.gz", "cal_min": None, "cal_max": None},
        ]
    }
    viewspec.resolve_percentiles(spec)
    assert spec["layers"][0]["cal_min"] == pytest.approx(1.0)
    assert spec["layers"][0]["cal_max"] == pytest.approx(100.0)
    assert spec["layers"][1]["cal_min"] is None  # no percentile: untouched


def test_resolve_percentiles_leaves_thresholds_unresolved_on_load_error(
    monkeypatch,
) -> None:
    import sys
    import types

    def _raise(_path):
        raise OSError("not a real nifti")

    fake_nib = types.SimpleNamespace(load=_raise)
    monkeypatch.setitem(sys.modules, "nibabel", fake_nib)

    spec = {
        "layers": [
            {
                "path": "/bad.nii.gz",
                "cal_min": None,
                "cal_max": None,
                "percentile": {"lo": 95, "hi": 99.9},
            }
        ]
    }
    viewspec.resolve_percentiles(spec)
    assert spec["layers"][0]["cal_min"] is None
    assert spec["layers"][0]["cal_max"] is None


def test_resolve_percentiles_does_not_overwrite_explicit_cal_min_max(
    monkeypatch,
) -> None:
    """An explicit absolute threshold wins over an accompanying percentile hint."""
    import sys
    import types

    calls = []
    fake_nib = types.SimpleNamespace(load=lambda path: calls.append(path))
    monkeypatch.setitem(sys.modules, "nibabel", fake_nib)

    spec = {
        "layers": [
            {
                "path": "/x.nii.gz",
                "cal_min": 0.2,
                "cal_max": 0.9,
                "percentile": {"lo": 95, "hi": 99.9},
            }
        ]
    }
    viewspec.resolve_percentiles(spec)
    assert spec["layers"][0]["cal_min"] == 0.2
    assert spec["layers"][0]["cal_max"] == 0.9
    assert calls == []  # never even attempted to read the file


# ── R5: the optional `atlas` parameter (docs/dev/v3-implementation-plan.md) ───────
#
# The contract's promise is exactly two sentences: naming an atlas overlays THAT
# atlas, and naming nothing leaves every previous caller's scene byte-for-byte
# what it was. Both are asserted here, plus the stale-id fallback, because an
# atlas a subject no longer has is a bookmark problem and not a reason to answer
# a person with no picture at all.


def test_atlas_absent_keeps_the_servers_own_choice(pm: PathManager) -> None:
    before = viewspec.build_view("subject", subject="ernie")
    after = viewspec.build_view("subject", subject="ernie", atlas=None)
    assert before == after
    assert before is not None
    assert [os.path.basename(layer["path"]) for layer in before["layers"]] == [
        "T1.nii.gz",
        "labeling.nii.gz",
    ]


def test_atlas_selects_a_named_subject_space_atlas(pm: PathManager, tmp_path: Path):
    # A second atlas the VoxelAtlasManager can list, alongside the labeling.nii.gz
    # the server would otherwise pick on its own.
    fastsurfer_mri = pm.fastsurfer_mri("ernie")
    os.makedirs(fastsurfer_mri)
    Path(fastsurfer_mri, "aparc.DKTatlas+aseg.deep.mgz").write_bytes(b"deep")

    default = viewspec.build_view("subject", subject="ernie")
    chosen = viewspec.build_view(
        "subject", subject="ernie", atlas="aparc.DKTatlas+aseg.deep.mgz"
    )
    assert default is not None and chosen is not None
    default_paths = [layer["path"] for layer in default["layers"]]
    chosen_paths = [layer["path"] for layer in chosen["layers"]]
    assert default_paths != chosen_paths
    assert any(p.endswith("labeling.nii.gz") for p in default_paths)
    assert any(p.endswith("aparc.DKTatlas+aseg.deep.mgz") for p in chosen_paths)


def test_unknown_atlas_falls_back_instead_of_dropping_the_overlay(
    pm: PathManager,
) -> None:
    spec = viewspec.build_view("subject", subject="ernie", atlas="NotAnAtlas")
    fallback = viewspec.build_view("subject", subject="ernie")
    assert spec == fallback


def test_atlas_selects_a_bundled_mni_atlas(pm: PathManager, tmp_path: Path) -> None:
    resources = Path(viewspec.mni_resources_dir())
    (resources / "MorelMNI152_labeling_1mm.nii.gz").write_bytes(b"other-atlas")

    default = viewspec.build_view("subject", subject="ernie", space="mni")
    chosen = viewspec.build_view(
        "subject", subject="ernie", space="mni", atlas="MorelMNI152_labeling_1mm.nii.gz"
    )
    assert default is not None and chosen is not None
    assert any(
        layer["path"].endswith("CIT168_labeling_MNI152NLin2009cAsym.nii.gz")
        for layer in default["layers"]
    )
    assert any(
        layer["path"].endswith("MorelMNI152_labeling_1mm.nii.gz") for layer in chosen["layers"]
    )


def test_group_view_honors_the_requested_mni_atlas(pm: PathManager) -> None:
    resources = Path(viewspec.mni_resources_dir())
    (resources / "MorelMNI152_labeling_1mm.nii.gz").write_bytes(b"other-atlas")

    default = viewspec.build_view("group")
    chosen = viewspec.build_view("group", atlas="MorelMNI152_labeling_1mm.nii.gz")
    assert default is not None and chosen is not None
    assert [layer["path"] for layer in default["layers"]] != [
        layer["path"] for layer in chosen["layers"]
    ]
    assert any(
        layer["path"].endswith("MorelMNI152_labeling_1mm.nii.gz") for layer in chosen["layers"]
    )


# ── the percentile cache (VE, 2026-09-06) ────────────────────────────────────
#
# Reading a volume to find its percentile window is the most expensive thing `build_view` does --
# ~150 ms warm and ~860 ms cold for one five-layer simulation scene, because `get_fdata()`
# decompresses the whole gzip stream and materialises it as float64. The Viewer's file list used to
# re-resolve through that code on every add, remove and reorder. These pin the memoisation that
# makes the second call free, and the two ways it must NOT be free.


@pytest.fixture
def _fake_volume(monkeypatch, tmp_path):
    """A real file on disk plus a counting `nibabel`, so "did it read?" is observable."""
    import sys
    import types

    import numpy as np

    path = tmp_path / "vol.nii.gz"
    path.write_bytes(b"not really a nifti, but it has a size and an mtime")
    reads: list[str] = []

    def _load(p):
        reads.append(str(p))
        return types.SimpleNamespace(get_fdata=lambda: np.array([0, 1, 2, 3, 4, 100]))

    monkeypatch.setitem(sys.modules, "nibabel", types.SimpleNamespace(load=_load))
    viewspec.clear_percentile_cache()
    yield path, reads
    viewspec.clear_percentile_cache()


def _pct_spec(path) -> dict:
    return {
        "layers": [
            {
                "path": str(path),
                "cal_min": None,
                "cal_max": None,
                "percentile": {"lo": 0, "hi": 100},
            }
        ]
    }


def test_a_second_resolve_of_an_unchanged_file_reads_nothing(_fake_volume) -> None:
    path, reads = _fake_volume

    first = _pct_spec(path)
    viewspec.resolve_percentiles(first)
    assert reads == [str(path)]

    second = _pct_spec(path)
    viewspec.resolve_percentiles(second)

    # The whole point: one read, two answers, and the same answer.
    assert reads == [str(path)], "the volume was read again for a file that had not changed"
    assert second["layers"][0]["cal_min"] == first["layers"][0]["cal_min"]
    assert second["layers"][0]["cal_max"] == first["layers"][0]["cal_max"]
    assert first["layers"][0]["cal_max"] == pytest.approx(100.0)


def test_a_rewritten_file_is_read_again(_fake_volume) -> None:
    """The key is (path, size, mtime_ns, lo, hi) -- a simulation that overwrites a volume must not
    keep yesterday's window on screen."""
    import os

    path, reads = _fake_volume
    viewspec.resolve_percentiles(_pct_spec(path))
    assert len(reads) == 1

    path.write_bytes(b"different bytes entirely, so both the size and the mtime move")
    os.utime(path, ns=(0, 0))  # a mtime the first stat cannot have seen

    viewspec.resolve_percentiles(_pct_spec(path))
    assert len(reads) == 2, "a changed file kept its cached window"


def test_a_different_window_on_the_same_file_is_read_again(_fake_volume) -> None:
    """`lo`/`hi` are part of the key: two layers of one volume can ask for different windows."""
    path, reads = _fake_volume
    viewspec.resolve_percentiles(_pct_spec(path))
    other = _pct_spec(path)
    other["layers"][0]["percentile"] = {"lo": 5, "hi": 95}
    viewspec.resolve_percentiles(other)
    assert len(reads) == 2


def test_an_unreadable_volume_is_not_cached(monkeypatch, tmp_path) -> None:
    """A file that fails to load is usually mid-write. Remembering "this one has no window" would
    outlive the cause, and the layer would stay unthresholded until the process restarted."""
    import sys
    import types

    import numpy as np

    path = tmp_path / "half-written.nii.gz"
    path.write_bytes(b"truncated")
    attempts: list[str] = []
    ok = False

    def _load(p):
        attempts.append(str(p))
        if not ok:
            raise OSError("truncated file")
        return types.SimpleNamespace(get_fdata=lambda: np.array([0, 1, 2, 3, 4, 100]))

    monkeypatch.setitem(sys.modules, "nibabel", types.SimpleNamespace(load=_load))
    viewspec.clear_percentile_cache()
    try:
        first = _pct_spec(path)
        viewspec.resolve_percentiles(first)
        assert first["layers"][0]["cal_min"] is None
        assert len(attempts) == 1

        ok = True
        second = _pct_spec(path)
        viewspec.resolve_percentiles(second)
        assert len(attempts) == 2, "the failure was cached, so the retry never happened"
        assert second["layers"][0]["cal_max"] == pytest.approx(100.0)
    finally:
        viewspec.clear_percentile_cache()


def test_an_all_zero_volume_caches_its_none(monkeypatch, tmp_path) -> None:
    """The opposite case: "this volume is all zeros" IS a stable fact about the file, and re-reading
    17 MB to learn it again on every list edit is the defect this cache exists for."""
    import sys
    import types

    import numpy as np

    path = tmp_path / "zeros.nii.gz"
    path.write_bytes(b"zeros")
    reads: list[str] = []

    def _load(p):
        reads.append(str(p))
        return types.SimpleNamespace(get_fdata=lambda: np.zeros((4, 4)))

    monkeypatch.setitem(sys.modules, "nibabel", types.SimpleNamespace(load=_load))
    viewspec.clear_percentile_cache()
    try:
        for _ in range(3):
            spec = _pct_spec(path)
            viewspec.resolve_percentiles(spec)
            assert spec["layers"][0]["cal_min"] is None
        assert reads == [str(path)]
    finally:
        viewspec.clear_percentile_cache()


def test_the_cache_is_bounded(_fake_volume, tmp_path) -> None:
    """A long-lived server must not grow one entry per volume it has ever seen."""
    path, _reads = _fake_volume
    for i in range(viewspec._PERCENTILE_CACHE_MAX + 20):
        other = tmp_path / f"v{i}.nii.gz"
        other.write_bytes(b"x" * (i + 1))
        viewspec.resolve_percentiles(_pct_spec(other))
    assert len(viewspec._PERCENTILE_CACHE) <= viewspec._PERCENTILE_CACHE_MAX
