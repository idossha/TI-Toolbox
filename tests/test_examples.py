"""``tit.examples`` -- the content-addressed example-data catalogue of datasets and parts.

No network: the URL opener is monkeypatched to serve synthetic bytes per catalogue URL, and the
catalogue itself is replaced by a one-dataset/two-part fixture whose hashes are of those bytes.
The real ``catalog.json`` is checked separately (shape, ids, placement) without downloading
anything.

Reproduce: ``python3 -m pytest -q tests/test_examples.py``.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from tit import examples
from tit.examples import __main__ as examples_main

STORE = "https://example.invalid/store/"


def _tarball(subject: str) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz, tarfile.open(fileobj=gz, mode="w|") as tar:
        for name, data in [
            (f"m2m_{subject}/{subject}.msh", b"mesh"),
            (f"m2m_{subject}/segmentation/labeling.nii.gz", b"lab"),
        ]:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _file(name: str, data: bytes) -> dict:
    digest = hashlib.sha256(data).hexdigest()
    return {"name": name, "bytes": len(data), "sha256": digest, "url": STORE + digest}


T1 = b"rawT1"
T2 = b"rawT2"
ERNIE_TAR = _tarball("ernie")


def _catalog() -> dict:
    return {
        "store": STORE,
        "datasets": [
            {
                "id": "ernie",
                "title": "Ernie",
                "description": "d",
                "source": "SimNIBS example dataset",
                "source_url": "https://github.com/simnibs/example-dataset",
                "licence": "GPL-3.0",
                "subject": "ernie",
                "parts": [
                    {
                        "id": "nifti",
                        "title": "Raw MRI",
                        "meaning": "Raw T1/T2 - needs pre-processing",
                        "dest": "sub-{subject}/anat",
                        "files": [_file("sub-ernie_T1w.nii.gz", T1), _file("sub-ernie_T2w.nii.gz", T2)],
                    },
                    {
                        "id": "headmodel",
                        "title": "Head model",
                        "meaning": "Head model - ready for optimizer, simulator, analyzer",
                        "dest": "derivatives/SimNIBS/sub-{subject}",
                        "target": "derivatives/SimNIBS/sub-{subject}/m2m_{subject}",
                        "verify": ["m2m_{subject}/{subject}.msh"],
                        "derivative": "SimNIBS",
                        "files": [_file("m2m_ernie.tar.gz", ERNIE_TAR)],
                    },
                ],
            }
        ],
    }


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


@pytest.fixture
def served(monkeypatch):
    """Serve each catalogue URL its own bytes, and record every URL opened."""
    catalog = _catalog()
    by_url = {}
    for dataset in catalog["datasets"]:
        for part in dataset["parts"]:
            for f in part["files"]:
                by_url[f["url"]] = {
                    "sub-ernie_T1w.nii.gz": T1,
                    "sub-ernie_T2w.nii.gz": T2,
                    "m2m_ernie.tar.gz": ERNIE_TAR,
                }[f["name"]]
    calls: list[str] = []
    monkeypatch.setattr(examples, "_load_catalog", lambda: catalog)
    monkeypatch.setattr(
        examples.urllib.request, "urlopen", lambda url, **kw: (calls.append(url), _Resp(by_url[url]))[1]
    )
    return calls


@pytest.fixture
def corrupt(served, monkeypatch):
    """The same store, serving one byte too few for every file."""
    monkeypatch.setattr(
        examples.urllib.request, "urlopen", lambda url, **kw: (served.append(url), _Resp(b"junk"))[1]
    )
    return served


def _installed(project) -> dict[str, bool]:
    return {s["id"]: s["installed"] for s in examples.status(project)}


def test_headmodel_part_layout_matches_path_manager(tmp_path: Path, served, capsys):
    from tit.paths import get_path_manager
    from tit.pre import check_m2m_exists

    m2m = examples.fetch("ernie", "headmodel", tmp_path)

    pm = get_path_manager(str(tmp_path))
    assert str(m2m) == pm.m2m("ernie")
    assert check_m2m_exists(str(tmp_path), "ernie")
    assert (m2m / "ernie.msh").read_bytes() == b"mesh"
    assert (m2m / "segmentation" / "labeling.nii.gz").read_bytes() == b"lab"
    assert not (tmp_path / "m2m_ernie.tar.gz").exists(), "the archive is unpacked, never kept"
    assert not (tmp_path / "sub-ernie").exists(), "the head model part carries no NIfTIs"
    assert (tmp_path / "dataset_description.json").exists()
    assert (tmp_path / "derivatives" / "SimNIBS" / "dataset_description.json").exists()
    status = json.loads((tmp_path / "code" / "ti-toolbox" / "config" / "project_status.json").read_text())
    assert status["example_subjects"] == ["ernie"]
    assert status["example_samples"] == ["ernie/headmodel"]
    assert "download 100%" in capsys.readouterr().out


def test_nifti_part_places_only_anat(tmp_path: Path, served):
    anat = examples.fetch("ernie", "nifti", tmp_path)
    assert anat == tmp_path / "sub-ernie" / "anat"
    assert (anat / "sub-ernie_T1w.nii.gz").read_bytes() == T1
    assert (anat / "sub-ernie_T2w.nii.gz").read_bytes() == T2
    assert not (tmp_path / "derivatives" / "SimNIBS" / "sub-ernie").exists()


def test_fetch_accepts_the_slash_id(tmp_path: Path, served):
    assert examples.fetch("ernie/nifti", tmp_path) == tmp_path / "sub-ernie" / "anat"


def test_fetch_ernie_takes_both_parts(tmp_path: Path, served):
    """The notebook's one-liner is the whole ernie dataset, and returns its head model."""
    target = examples.fetch_ernie(tmp_path)
    assert target == examples._target_dir(tmp_path, examples.part_by_id("ernie", "headmodel"))
    assert _installed(tmp_path) == {"ernie/nifti": True, "ernie/headmodel": True}


# ----------------------------------------------------------------- parts are independent (the point)


def test_parts_are_detected_independently(tmp_path: Path, served):
    """Deleting one part's files must not flip the other part to "not installed".

    This is the defect the dataset/part split closes: the old ``ernie-headmodel`` *sample*
    contained the NIfTIs, so removing ``sub-ernie/anat`` made the finished head model -- 590 MB
    still sitting on disk -- report itself as absent.
    """
    examples.fetch_ernie(tmp_path)
    assert _installed(tmp_path) == {"ernie/nifti": True, "ernie/headmodel": True}

    import shutil

    shutil.rmtree(tmp_path / "sub-ernie" / "anat")
    assert _installed(tmp_path) == {"ernie/nifti": False, "ernie/headmodel": True}

    examples.fetch("ernie", "nifti", tmp_path)
    shutil.rmtree(tmp_path / "derivatives" / "SimNIBS" / "sub-ernie" / "m2m_ernie")
    assert _installed(tmp_path) == {"ernie/nifti": True, "ernie/headmodel": False}


def test_a_part_downloads_only_its_own_files(tmp_path: Path, served):
    examples.fetch("ernie", "headmodel", tmp_path)
    assert len(served) == 1, "the head model part is the tarball alone"
    served.clear()
    examples.fetch("ernie", "nifti", tmp_path)
    assert len(served) == 2, "the nifti part is T1 and T2 alone"


def test_idempotent_skip(tmp_path: Path, served):
    examples.fetch("ernie", "nifti", tmp_path)
    n = len(served)
    examples.fetch("ernie", "nifti", tmp_path)
    assert len(served) == n, "second call must not download"
    examples.fetch("ernie", "nifti", tmp_path, force=True)
    assert len(served) == n + 2


def test_status_reports_installed_and_size(tmp_path: Path, served):
    before = {s["id"]: s for s in examples.status(tmp_path)}
    assert before["ernie/nifti"]["installed"] is False
    assert before["ernie/nifti"]["bytes"] == len(T1) + len(T2)
    assert before["ernie/nifti"]["dataset"] == "ernie"
    assert before["ernie/nifti"]["part"] == "nifti"
    assert before["ernie/headmodel"]["bytes"] == len(ERNIE_TAR)
    examples.fetch("ernie", "nifti", tmp_path)
    after = _installed(tmp_path)
    assert after["ernie/nifti"] is True
    assert after["ernie/headmodel"] is False, "its head model is still missing"


def test_sha_mismatch_rejected(tmp_path: Path, corrupt):
    with pytest.raises(ValueError, match="refusing to install"):
        examples.fetch("ernie", "headmodel", tmp_path)
    assert not (tmp_path / "derivatives").exists()
    assert not (tmp_path / "sub-ernie").exists()


def test_unknown_dataset_and_part(tmp_path: Path, served):
    with pytest.raises(KeyError, match="unknown example dataset"):
        examples.fetch("no-such", "nifti", tmp_path)
    with pytest.raises(KeyError, match="unknown example part"):
        examples.fetch("ernie", "no-such", tmp_path)
    with pytest.raises(KeyError, match="not a DATASET/PART id"):
        examples.parse_part_id("ernie")


def test_part_id_parsing():
    assert examples.parse_part_id("ernie/headmodel") == ("ernie", "headmodel")
    assert examples.parse_part_id("ernie:headmodel") == ("ernie", "headmodel"), "the colon form too"
    assert examples.part_by_id("ernie/headmodel").full_id == "ernie/headmodel"


def test_progress_callback_counts_the_whole_part(tmp_path: Path, served):
    seen: list[tuple[str, str, int, int]] = []
    examples.fetch("ernie", "nifti", tmp_path, progress=lambda *a: seen.append(a))
    total = len(T1) + len(T2)
    assert {p[3] for p in seen} == {total}
    assert {p[0] for p in seen} == {"ernie/nifti"}, "progress is reported under the part id"
    assert seen[-1][2] == total, "the last report is the whole part"


def test_cli(tmp_path: Path, served, capsys):
    assert examples_main.main(["--project", str(tmp_path), "ernie/nifti"]) == 0
    assert (tmp_path / "sub-ernie" / "anat" / "sub-ernie_T1w.nii.gz").exists()
    assert not (tmp_path / "derivatives" / "SimNIBS" / "sub-ernie").exists()
    assert examples_main.main(["--project", str(tmp_path), "--list"]) == 0
    out = capsys.readouterr().out
    assert "ernie/nifti" in out and "ernie/headmodel" in out and "installed" in out


def test_cli_takes_several_parts_and_a_bare_dataset(tmp_path: Path, served):
    assert examples_main.main(["--project", str(tmp_path), "ernie/nifti", "ernie/headmodel"]) == 0
    assert _installed(tmp_path) == {"ernie/nifti": True, "ernie/headmodel": True}

    other = tmp_path / "other"
    assert examples_main.main(["--project", str(other), "ernie"]) == 0
    assert _installed(other) == {"ernie/nifti": True, "ernie/headmodel": True}


def test_cli_defaults_to_the_head_model_part(tmp_path: Path, served):
    assert examples_main.main(["--project", str(tmp_path)]) == 0
    assert examples.DEFAULT_PART == "ernie/headmodel"
    assert (tmp_path / "derivatives" / "SimNIBS" / "sub-ernie" / "m2m_ernie" / "ernie.msh").exists()
    assert not (tmp_path / "sub-ernie").exists()


def test_cli_rejects_a_bare_part_name(tmp_path: Path, served, capsys):
    assert examples_main.main(["--project", str(tmp_path), "headmodel"]) == 1
    assert "unknown example dataset" in capsys.readouterr().err


def test_cli_reports_a_bad_download(tmp_path: Path, corrupt, capsys):
    assert examples_main.main(["--project", str(tmp_path), "ernie/nifti"]) == 1
    assert "refusing to install" in capsys.readouterr().err


def test_project_init_runner_never_fetches_example_data(tmp_path: Path, served):
    """``project_init`` *initializes*, full stop.

    Example data was briefly an ``example_sample`` config key on this job, so asking an
    established project for a sample re-ran the initializer and reprinted its "New project
    detected" banner. The runner now ignores the key entirely -- it opens no URL and writes no
    subject -- and a download is :func:`tit.examples.fetch` behind ``POST /api/example-data``.
    """
    from tit.project_init.__main__ import main

    project = tmp_path / "project"
    project.mkdir()
    config = tmp_path / "c.json"
    config.write_text(
        json.dumps(
            {
                "project_dir": str(project),
                # Both spellings the old job understood; both must now be inert.
                "example_sample": "ernie/nifti",
                "example_subject": True,
            }
        )
    )
    assert main([str(config)]) == 0
    assert served == [], "project_init must not touch the example-data store"
    assert not (project / "sub-ernie").exists()
    assert not (project / "derivatives" / "SimNIBS" / "sub-ernie").exists()
    # It did do its actual job.
    assert (project / "dataset_description.json").is_file()


def test_fetch_works_on_an_established_project(tmp_path: Path, served, capsys):
    """Example data must not depend on ``project_init`` state in any way.

    An established project -- markers, a real subject, derivatives -- takes a part exactly as a
    fresh one does: no initialization marker is consulted, no ``project_status.json`` is required
    up front, and above all the initializer's "New project detected" banner is never printed,
    because a download is not an initialization.
    """
    from tit.project_init.initializer import has_project_data_or_markers

    project = tmp_path / "established"
    (project / "sub-0042" / "anat").mkdir(parents=True)
    (project / "sub-0042" / "anat" / "sub-0042_T1w.nii.gz").write_bytes(b"not really a nifti")
    (project / "derivatives" / "SimNIBS").mkdir(parents=True)
    (project / "code" / "ti-toolbox" / "config").mkdir(parents=True)
    (project / "code" / "ti-toolbox" / "config" / ".initialized").touch()
    assert has_project_data_or_markers(project)
    # Deliberately absent: the fetch must not need it.
    assert not (project / "code" / "ti-toolbox" / "config" / "project_status.json").exists()

    capsys.readouterr()
    examples.fetch("ernie", "nifti", project)
    out = capsys.readouterr().out
    assert "New project detected" not in out
    assert "Initializing BIDS-compliant structure" not in out

    assert (project / "sub-ernie" / "anat" / "sub-ernie_T1w.nii.gz").is_file()
    assert (project / "sub-0042" / "anat" / "sub-0042_T1w.nii.gz").is_file(), "left alone"
    # status() reads the disk, not any marker.
    assert _installed(project)["ernie/nifti"] is True
    # Recording what was installed is allowed -- and is the only thing that writes the status file.
    from tit.project_init import load_project_status

    assert "ernie/nifti" in load_project_status(project).get("example_samples", [])


def test_fetch_needs_no_project_init_at_all(tmp_path: Path, served):
    """Not even a directory that was ever initialized: a bare empty dir takes a part."""
    project = tmp_path / "bare"
    project.mkdir()
    examples.fetch("ernie", "nifti", project)
    assert (project / "sub-ernie" / "anat" / "sub-ernie_T1w.nii.gz").is_file()
    assert _installed(project)["ernie/nifti"] is True


def test_examples_module_never_mentions_jobs_or_project_init_gating():
    """The public surface is plain functions: no jobs, no stages, no init gating."""
    source = Path(examples.__file__).read_text()
    code = source.split('"""', 2)[-1]  # drop the module docstring
    for banned in ("tit.jobs", "emit_stage", "emit_result", "is_new_project", "has_project_data"):
        assert banned not in code, banned


def test_project_init_module_does_not_import_examples():
    """A guard on the shape, not just the behaviour: no ``tit.examples`` in the entry point."""
    source = (Path(examples.__file__).parents[1] / "project_init" / "__main__.py").read_text()
    body = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith(("#", ":"))
    )
    code = body.split('"""', 2)[-1]  # drop the module docstring, which may name the module in prose
    assert "tit.examples" not in code and "from tit import examples" not in code


# --------------------------------------------------------------- the real catalogue (no network)


def test_shipped_catalogue_is_complete_and_content_addressed():
    datasets = examples.catalogue()
    assert [d.id for d in datasets] == ["ernie", "mni152"]
    store = examples._load_catalog()["store"]
    for d in datasets:
        assert d.subject in {"ernie", "MNI152"}
        assert d.licence.startswith("GPL-3.0")
        assert [p.id for p in d.parts] == ["nifti", "headmodel"]
        for part in d.parts:
            assert part.full_id == f"{d.id}/{part.id}"
            assert part.files and part.meaning and part.verify
            for f in part.files:
                assert len(f.sha256) == 64 and f.bytes > 0
                assert f.url == store + f.sha256, "an asset is named by its own hash"
            if part.id == "headmodel":
                assert [f.name for f in part.files] == [f"m2m_{d.subject}.tar.gz"]
                assert part.dest == "derivatives/SimNIBS/sub-{subject}"
                assert part.derivative == "SimNIBS"
            else:
                assert all(f.name.endswith(".nii.gz") for f in part.files)
                assert part.dest == "sub-{subject}/anat"


def test_every_part_has_its_own_files_and_no_overlap():
    """No part may contain another part's files -- that overlap is what made deleting the
    NIfTIs flip the head model to "not installed"."""
    for dataset in examples.catalogue():
        seen: set[str] = set()
        for part in dataset.parts:
            names = {f.name for f in part.files}
            assert not (names & seen), f"{part.full_id} repeats a file of an earlier part"
            seen |= names


def test_the_default_part_exists_and_is_a_head_model():
    part = examples.part_by_id(examples.DEFAULT_PART)
    assert part.dataset_id == examples.ERNIE and part.id == "headmodel"


# ------------------------------------------------------------------- regressions (2026-09-15)


def test_installed_detection_is_case_insensitive(tmp_path: Path, served):
    """A project holding ``sub-Ernie/m2m_Ernie`` reports both ernie parts installed.

    The container filesystem is case-sensitive and the host's is not, so an existing SimNIBS
    ``Ernie`` tree looked absent only in the container.
    """
    anat = tmp_path / "sub-Ernie" / "anat"
    anat.mkdir(parents=True)
    (anat / "sub-Ernie_T1w.nii.gz").write_bytes(T1)
    (anat / "sub-Ernie_T2w.nii.gz").write_bytes(T2)
    m2m = tmp_path / "derivatives" / "SimNIBS" / "sub-Ernie" / "m2m_Ernie"
    m2m.mkdir(parents=True)
    (m2m / "Ernie.msh").write_bytes(b"mesh")

    assert _installed(tmp_path) == {"ernie/nifti": True, "ernie/headmodel": True}
    examples.fetch("ernie", "headmodel", tmp_path)
    assert not served, "an installed part must not be downloaded again"


def test_fetch_reuses_an_existing_differently_cased_tree(tmp_path: Path, served):
    """``fetch`` fills the ``sub-Ernie`` tree already on disk instead of making a second one.

    On a case-insensitive host filesystem the two names *are* one directory, so this asserts
    identity rather than spelling; the container run in the changelog covers the case-sensitive leg.
    """
    (tmp_path / "sub-Ernie" / "anat").mkdir(parents=True)
    simnibs_sub = tmp_path / "derivatives" / "SimNIBS" / "sub-Ernie"
    simnibs_sub.mkdir(parents=True)

    m2m = examples.fetch("ernie", "headmodel", tmp_path)
    examples.fetch("ernie", "nifti", tmp_path)

    assert m2m.parent.samefile(simnibs_sub)
    assert (m2m / f"{m2m.name[len('m2m_') :]}.msh").read_bytes() == b"mesh"
    assert (tmp_path / "sub-Ernie" / "anat" / "sub-ernie_T1w.nii.gz").read_bytes() == T1
    assert [d.name for d in simnibs_sub.parent.iterdir() if d.is_dir()] == ["sub-Ernie"]
    assert _installed(tmp_path)["ernie/headmodel"] is True


def test_downloads_use_a_verifying_tls_context(tmp_path: Path, served, monkeypatch):
    """Every download carries a verifying context -- never an unverified one."""
    import ssl

    seen: list[ssl.SSLContext] = []
    inner = examples.urllib.request.urlopen

    def record(url, **kw):
        seen.append(kw["context"])
        return inner(url)

    monkeypatch.setattr(examples.urllib.request, "urlopen", record)
    examples.fetch("ernie", "nifti", tmp_path)
    assert seen
    for ctx in seen:
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True


def test_ssl_cert_file_is_honoured(tmp_path: Path, monkeypatch):
    """A TLS-inspecting proxy's bundle is used when ``SSL_CERT_FILE`` names it."""
    from tit import certs

    bundle = tmp_path / "proxy-ca.pem"
    # OpenSSL's compiled-in path can name a nonexistent build-host file (CircleCI #1065).
    # Use the installed requests/certifi bundle as this proxy-override fixture.
    bundle.write_bytes(Path(_certifi()).read_bytes())
    monkeypatch.setenv("SSL_CERT_FILE", str(bundle))
    assert certs.ca_bundle() == str(bundle)
    monkeypatch.delenv("SSL_CERT_FILE")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(bundle))
    assert certs.ca_bundle() == str(bundle)


def _certifi() -> str:
    import certifi

    return certifi.where()


def test_ssl_context_never_disables_verification(monkeypatch):
    """No environment makes :func:`tit.certs.ssl_context` skip verification."""
    import ssl

    from tit import certs

    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.setattr(certs, "_certifi_bundle", lambda: None)
    monkeypatch.setattr(certs, "_SYSTEM_CA_BUNDLES", ())
    ctx = certs.ssl_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_no_source_disables_certificate_verification():
    """A guard: the toolbox must never build an unverified TLS context."""
    import tit

    root = Path(tit.__file__).parent
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in ("= ssl.CERT_NONE", "_create_unverified_context(", ".check_hostname = False"):
            if needle in text:
                offenders.append(f"{path.relative_to(root)}: {needle}")
    assert not offenders, offenders
