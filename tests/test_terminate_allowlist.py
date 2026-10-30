"""The System page's terminate allowlist is what v3 actually spawns.

``tit.server.routes.system.RELEVANT_KEYWORDS`` decides which processes the System page marks as
toolbox work, and which pids ``POST /api/system/terminate`` will kill. It was copied from the PyQt
monitor and still carried v2 script names (``ti_sim.py``, ``main-TI.sh``), FSL tools the image does
not ship, and the short words ``first`` and ``fast``, which made ``bash -c 'echo first'`` and
``vim notes_fast.txt`` killable.

Two oracles, neither of them the keyword list:

- the job runners: :func:`tit.jobs.kinds.command_for` builds the argv of every job kind, and
  each one must be relevant;
- everything else v3 spawns: :data:`CORPUS`, one real command line per external tool. Each entry
  names the source that builds it and a string that file must still contain, so a runner that
  stops spawning a tool takes its corpus line with it. The SimNIBS launcher shape
  (``/bin/bash -e <bin>/<tool>`` running ``<env>/bin/python -E -u .../simnibs/cli/<tool>.py``)
  and ``/opt/fastsurfer`` were read from ``idossha/ti-toolbox:v3.1.1`` (2026-10-22).

Every keyword has to match at least one of those lines; a keyword that matches none is dead and
only widens what a caller can kill.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
psutil = pytest.importorskip("psutil")

from fastapi.testclient import TestClient  # noqa: E402

from tit.jobs.kinds import MODULE_FOR_KIND, command_for  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.routes import system  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "test-token-terminate"
BASE = "http://127.0.0.1:8765"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
SPEC = "/data/code/ti-toolbox/jobs/20261022-0001/spec.json"
SIMNIBS_BIN = "/root/SimNIBS-4.6/bin"
SIMNIBS_CLI = "/root/SimNIBS-4.6/simnibs_env/lib/python3.11/site-packages/simnibs/cli"
SIMNIBS_PY = "/root/SimNIBS-4.6/simnibs_env/bin/python -E -u"
M2M = "/data/derivatives/SimNIBS/sub-101/m2m_101"

#: ``(source file, text that file must contain, a command line it makes the container run)``.
CORPUS: tuple[tuple[str, str, str], ...] = (
    (
        "tit/pre/charm.py",
        'cmd = ["charm", form_flag, subject_id, str(t1_file)]',
        f"/bin/bash -e {SIMNIBS_BIN}/charm --forceqform 101 /data/sub-101/anat/sub-101_T1w.nii.gz",
    ),
    (
        "tit/pre/charm.py",
        'cmd = ["charm", form_flag, subject_id, str(t1_file)]',
        f"{SIMNIBS_PY} {SIMNIBS_CLI}/charm.py --forceqform 101 /data/sub-101/anat/sub-101_T1w.nii.gz",
    ),
    (
        "tit/pre/charm.py",
        '"subject_atlas",',
        f"/bin/bash -e {SIMNIBS_BIN}/subject_atlas -a DK40 -o {M2M}/segmentation {M2M}",
    ),
    (
        "tit/sim/utils.py",
        '["subject2mni", "-i", t1, "-m", m2m_dir, "-o", out]',
        f"/bin/bash -e {SIMNIBS_BIN}/subject2mni -i {M2M}/T1.nii.gz -m {M2M} -o {M2M}/T1_101",
    ),
    (
        "tit/pre/dicom2nifti.py",
        '"dcm2niix",',
        "dcm2niix -z y -b y -d 9 -f sub-101_T1w -o /data/sub-101/anat "
        "/data/sourcedata/sub-101/T1w",
    ),
    (
        "tit/pre/fastsurfer.py",
        'DEFAULT_FASTSURFER_HOME = "/opt/fastsurfer"',
        "/bin/bash /opt/fastsurfer/run_fastsurfer.sh --seg_only --allow_root --no_cereb "
        "--no_hypothal --no_cc --sid sub-101 --sd /data/derivatives/fastsurfer "
        "--t1 /data/sub-101/anat/sub-101_T1w.nii.gz --device cpu --viewagg_device cpu "
        "--batch 1 --threads 4 --py python3",
    ),
    (
        "tit/constants.py",
        'QSI_QSIPREP_IMAGE = "pennlinc/qsiprep"',
        "docker run --rm --platform linux/amd64 --name qsiprep_101_1a2b3c4d "
        "--label tit.kind=qsiprep --cpus 8 --memory 32g -e OMP_NUM_THREADS=8 "
        "-v /host/project:/data:ro -v /host/project/derivatives/qsiprep:/out "
        "pennlinc/qsiprep:26.0.0 /data /out participant --participant-label 101",
    ),
    (
        "tit/constants.py",
        'QSI_QSIRECON_IMAGE = "pennlinc/qsirecon"',
        "docker run --rm --platform linux/amd64 --name qsirecon_101_dsi_studio_1a2b3c4d "
        "--label tit.kind=qsirecon --cpus 8 --memory 32g -e OMP_NUM_THREADS=8 "
        "-v /host/project/derivatives/qsiprep:/data:ro "
        "pennlinc/qsirecon:26.0.0 /data /out participant --participant-label 101",
    ),
    (
        "tit/pre/freesurfer.py",
        '"FS_LICENSE=/run/license.txt",',
        "docker run --rm --platform linux/amd64 --name tit-freesurfer-0123abcd "
        "--label tit.kind=freesurfer --cpus 4 --memory 16g -e FS_LICENSE=/run/license.txt "
        "-e OMP_NUM_THREADS=4 -v /host/project:/data "
        "idossha/ti-toolbox:freesurfer-20260910 recon-all -s sub-101 "
        "-sd /data/derivatives/freesurfer -all -parallel -openmp 4",
    ),
)

#: Ordinary processes that share a word with an old keyword. None of them may be killable.
NOT_TOOLBOX: tuple[tuple[str, str], ...] = (
    ("bash", "bash -c echo first"),
    ("vim", "vim notes_fast.txt"),
    ("python", "python -m http.server"),
)


def _runner_argvs() -> list[list[str]]:
    argvs = [command_for(kind, {}, SPEC) for kind in sorted(MODULE_FOR_KIND)]
    argvs.append(
        command_for(
            "tools",
            {"module": "tit.tools.electrode_overlay", "args": []},
            SPEC,
            project_dir="/data",
        )
    )
    return argvs


def _keyword_matches(keyword: str, name: str, cmdline: str) -> bool:
    return (
        re.search(system._keyword_pattern(keyword), f"{name} {cmdline}".lower())
        is not None
    )


@pytest.mark.parametrize("source,needle,line", CORPUS, ids=lambda v: str(v)[:40])
def test_each_corpus_line_is_still_spawned_by_its_source(source, needle, line) -> None:
    assert needle in (ROOT / source).read_text(encoding="utf-8"), (
        f"{source} no longer builds this command line; update CORPUS (and drop any "
        "keyword only it justified)"
    )


def test_every_job_kind_runner_is_relevant_under_either_interpreter_spelling() -> None:
    """``simnibs_python`` is a symlink to the env's python; psutil shows argv[0] as spawned."""
    argvs = _runner_argvs()
    assert {argv[2] for argv in argvs} >= set(MODULE_FOR_KIND.values())
    for argv in argvs:
        tail = " ".join(argv[1:])
        assert system.is_relevant_process(argv[0], " ".join(argv)), argv
        assert system.is_relevant_process(
            "simnibs_python", f"{SIMNIBS_BIN}/simnibs_python {tail}"
        ), argv


@pytest.mark.parametrize("source,needle,line", CORPUS, ids=lambda v: str(v)[:40])
def test_every_external_tool_v3_spawns_is_relevant(source, needle, line) -> None:
    name = line.split()[0].rsplit("/", 1)[-1]
    assert system.is_relevant_process(name, line), line


def test_every_keyword_matches_something_v3_spawns() -> None:
    lines = [(argv[0], " ".join(argv)) for argv in _runner_argvs()]
    lines += [(line.split()[0].rsplit("/", 1)[-1], line) for _, _, line in CORPUS]
    dead = [
        k
        for k in system.RELEVANT_KEYWORDS
        if not any(_keyword_matches(k, name, cmd) for name, cmd in lines)
    ]
    assert dead == [], f"keywords no v3 process matches: {dead}"


@pytest.mark.parametrize("name,cmdline", NOT_TOOLBOX)
def test_ordinary_processes_are_not_relevant(name, cmdline) -> None:
    assert not system.is_relevant_process(name, cmdline)


class _FakeProcess:
    """Stands in for ``psutil.Process(pid)``; records whether the route killed it."""

    killed: list[int] = []

    def __init__(self, pid: int, name: str, cmdline: str) -> None:
        self.pid, self._name, self._cmdline = pid, name, cmdline

    def name(self) -> str:
        return self._name

    def cmdline(self) -> list[str]:
        return self._cmdline.split()

    def terminate(self) -> None:
        _FakeProcess.killed.append(self.pid)

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def kill(self) -> None:  # pragma: no cover - wait() never times out here
        _FakeProcess.killed.append(self.pid)


@pytest.fixture()
def client(tmp_path: Path):
    get_path_manager(str(tmp_path))
    (tmp_path / "dataset_description.json").write_text("{}")
    settings = ServerSettings(project_dir=str(tmp_path), token=TOKEN)
    with TestClient(create_app(settings), base_url=BASE) as c:
        yield c


def _terminate(client, monkeypatch, name: str, cmdline: str):
    pid = 424242
    assert pid != os.getpid()
    _FakeProcess.killed = []
    monkeypatch.setattr(psutil, "Process", lambda p: _FakeProcess(p, name, cmdline))
    return client.post("/api/system/terminate", json={"pid": pid}, headers=BEARER), pid


@pytest.mark.parametrize("name,cmdline", NOT_TOOLBOX)
def test_terminate_refuses_an_ordinary_process(
    client, monkeypatch, name, cmdline
) -> None:
    r, _ = _terminate(client, monkeypatch, name, cmdline)
    assert r.status_code == 403
    assert "not a toolbox-relevant process" in r.json()["detail"]
    assert _FakeProcess.killed == []


def test_terminate_kills_a_job_runner(client, monkeypatch) -> None:
    """The control for the refusals above: the same fake, with a runner argv, is killed."""
    argv = command_for("sim", {}, SPEC)
    r, pid = _terminate(client, monkeypatch, argv[0], " ".join(argv))
    assert r.status_code == 200
    assert r.json() == {"pid": pid, "terminated": True}
    assert _FakeProcess.killed == [pid]
