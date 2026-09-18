"""Every regenerable file lands in ``.ti-toolbox/``, proved on a real project.

Env-gated, because it needs a real head model and real libraries::

    TIT_DOTCACHE_PROJECT=/mnt/scratch simnibs_python -m pytest \
        tests/numerical/test_dot_cache_layout.py -q

inside ``idossha/ti-toolbox:v3.0.0``. ``TIT_DOTCACHE_PROJECT`` is a *writable*
BIDS project whose ``derivatives/SimNIBS/sub-<id>/m2m_<id>`` may be a link into
a read-only dataset -- the point of the test is that nothing is written there.
``TIT_DOTCACHE_SUBJECT`` names the subject (default ``ernie``).
"""

import os
import pathlib

import pytest

PROJECT = os.environ.get("TIT_DOTCACHE_PROJECT")
SUBJECT = os.environ.get("TIT_DOTCACHE_SUBJECT", "ernie")

pytestmark = pytest.mark.skipif(
    not PROJECT,
    reason="TIT_DOTCACHE_PROJECT is unset; run in the toolbox container",
)


@pytest.fixture
def project():
    from tit.paths import get_path_manager, reset_path_manager

    reset_path_manager()
    get_path_manager(PROJECT)
    yield pathlib.Path(PROJECT)
    reset_path_manager()


def _top_level(root: pathlib.Path) -> set[str]:
    return {p.name for p in root.iterdir()}


def _rerun_with_real_simnibs(test_name: str) -> bool:
    """Preload SimNIBS in a child before the host conftest installs its mocks."""
    import subprocess
    import sys

    if os.environ.get("TIT_DOTCACHE_CHILD") == test_name:
        return False
    code = (
        "import importlib.util,sys; "
        "sys.exit(77) if importlib.util.find_spec('simnibs') is None else None; "
        "import simnibs,pytest; "
        f"sys.exit(pytest.main([{str(pathlib.Path(__file__).resolve())!r}, '-q']))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "TIT_DOTCACHE_CHILD": test_name},
        capture_output=True,
        text=True,
        timeout=900,
    )
    if result.returncode == 77:
        pytest.skip("real SimNIBS is unavailable; run in the toolbox container")
    assert result.returncode == 0, result.stdout + result.stderr
    return True


def test_scene_build_and_prepared_mask_land_in_the_dot_directory(project):
    if _rerun_with_real_simnibs("dot_cache_layout"):
        return
    import nibabel as nib
    import numpy as np
    from tit.opt.masks import prepare_mask
    from tit.paths import get_path_manager
    from tit.scene import build, cache

    pm = get_path_manager()
    before = _top_level(project)

    # 1. A real scene build, through the builder the scene route calls.
    mesh = build.head_mesh_path(pm, SUBJECT)
    assert os.path.isfile(str(mesh)), f"no head mesh for sub-{SUBJECT}"
    metas = build.build_surfaces(pm, SUBJECT)
    assert metas
    fp = build.surface_fingerprint(pm, SUBJECT)
    scene_dir = pathlib.Path(pm.scene_cache(SUBJECT))
    assert scene_dir.is_dir()
    for part in metas:
        found = cache.find_cached(project, SUBJECT, part, fp)
        assert found is not None
        assert found.path.parent == scene_dir

    # 2. A prepared (MNI -> subject) mask, in the flex-search cache directory.
    source = project / ".ti-toolbox" / "tmp-mask.nii"
    source.parent.mkdir(parents=True, exist_ok=True)
    data = np.zeros((20, 20, 20), dtype=np.uint8)
    data[8:12, 8:12, 8:12] = 1
    nib.save(nib.Nifti1Image(data, np.eye(4)), str(source))
    out = pm.ensure_cache("masks", f"sub-{SUBJECT}")
    prepared = prepare_mask(str(source), "mni", pm.m2m(SUBJECT), out, binary=True)
    assert pathlib.Path(prepared).parent == pathlib.Path(out)
    source.unlink()

    # 3. The dot-directory is self-describing, ignored by bids-validator, and
    #    it is the ONLY thing that appeared at the visible top level.
    assert "regenerable" in (project / ".ti-toolbox" / "README").read_text()
    assert ".ti-toolbox/" in (project / ".bidsignore").read_text().splitlines()
    assert _top_level(project) - before <= {".ti-toolbox", ".bidsignore"}

    # 4. Nothing was written into the (possibly read-only) head model.
    assert not os.path.exists(os.path.join(pm.masks(SUBJECT), ".prepared"))
