"""Pin AppleDouble move handling with real temporary files (2026-09-13).

Authored byte payloads are checked through pathlib, independently of shutil.
Run: python3 -m pytest tests/test_sim_safe_move_metadata.py -q
Simulation numerics and platform-specific automatic sidecar moves are elsewhere.
"""

import pytest

from tit.sim.utils import safe_move


@pytest.mark.parametrize("directory_destination", [False, True])
def test_moves_real_data(tmp_path, directory_destination):
    source = tmp_path / "lh.central"
    source.write_bytes(b"cortical surface")
    destination = tmp_path / "output"
    destination.mkdir()
    target = destination / source.name

    safe_move(str(source), str(destination if directory_destination else target))

    assert target.read_bytes() == b"cortical surface"
    assert not source.exists()


@pytest.mark.parametrize("directory_destination", [False, True])
@pytest.mark.parametrize("destination_metadata_exists", [False, True])
def test_disappeared_sidecar_after_companion_move_is_harmless(
    tmp_path, directory_destination, destination_metadata_exists
):
    source = tmp_path / "._lh.central"
    destination = tmp_path / "output"
    destination.mkdir()
    # Reproduce a stale listdir entry after macOS moved the companion itself.
    companion = destination / "lh.central"
    companion.write_bytes(b"cortical surface")
    target = destination / source.name
    if destination_metadata_exists:
        target.write_bytes(b"moved metadata")

    safe_move(str(source), str(destination if directory_destination else target))

    assert companion.read_bytes() == b"cortical surface"
    if destination_metadata_exists:
        assert target.read_bytes() == b"moved metadata"


def test_missing_genuine_data_raises_even_if_destination_exists(tmp_path):
    source = tmp_path / "lh.central"
    destination = tmp_path / "output"
    destination.mkdir()
    target = destination / source.name
    target.write_bytes(b"previous surface")

    with pytest.raises(FileNotFoundError):
        safe_move(str(source), str(target))


def test_present_sidecar_is_moved(tmp_path):
    source = tmp_path / "._lh.central"
    source.write_bytes(b"metadata")
    target = tmp_path / "output" / source.name
    target.parent.mkdir()

    safe_move(str(source), str(target))

    assert target.read_bytes() == b"metadata"
    assert not source.exists()


def test_missing_sidecar_without_moved_companion_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        safe_move(str(tmp_path / "._lh.central"), str(tmp_path / "output"))


def test_missing_sidecar_with_unmoved_companion_raises(tmp_path):
    (tmp_path / "lh.central").write_bytes(b"source surface")
    target = tmp_path / "output" / "._lh.central"
    target.parent.mkdir()
    target.with_name("lh.central").write_bytes(b"previous surface")

    with pytest.raises(FileNotFoundError):
        safe_move(str(tmp_path / "._lh.central"), str(target))
