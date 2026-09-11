"""Mailbox protocol regressions, 2026-09-10.

Authored protocol messages and real tmp_path files independently exercise host
replies and path containment. Run: pytest tests/test_native_fastsurfer.py -q.
Actual MPS inference and image quality are tested separately on the native host.
"""

import json
import logging
import threading
import time
import uuid

import pytest

from tit.pre.native_fastsurfer import run_native_fastsurfer
from tit.pre.utils import PreprocessCancelled, PreprocessError


@pytest.fixture
def project(tmp_path):
    source = tmp_path / "sub-101" / "anat" / "sub-101_T1w.nii.gz"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"fixture")
    mailbox = tmp_path / "code/ti-toolbox/native-fastsurfer"
    mailbox.mkdir(parents=True)
    return tmp_path, source, mailbox


def advertise(mailbox, **overrides):
    message = dict(version=1, session=str(uuid.uuid4()), lastSeen=time.time() * 1000)
    message.update(overrides)
    (mailbox / "availability.json").write_text(json.dumps(message))
    return message


def run(project, event=None, **overrides):
    root, source, _ = project
    args = dict(
        project_dir=str(root),
        subject_id="101",
        input_path=source,
        threads=2,
        logger=logging.getLogger("native-test"),
        stop_event=event or threading.Event(),
    )
    args.update(overrides)
    return run_native_fastsurfer(**args)


class ReplyEvent(threading.Event):
    def __init__(self, mailbox, reply):
        super().__init__()
        self.mailbox = mailbox
        self.reply = reply

    def wait(self, timeout=None):
        request = next((self.mailbox / "requests").glob("*/request.json"))
        self.reply(request.parent, json.loads(request.read_text()))
        return self.is_set()


def test_absent_native_worker_keeps_existing_container_route(project):
    assert run(project) is False
    assert not (project[2] / "requests").exists()


@pytest.mark.parametrize(
    "overrides",
    [
        dict(lastSeen=0),
        dict(session="bad"),
        dict(version=2),
        dict(lastSeen=float("nan")),
    ],
)
def test_invalid_or_stale_availability_never_falls_back_to_cpu(project, overrides):
    advertise(project[2], **overrides)
    with pytest.raises(PreprocessError):
        run(project)
    assert not (project[2] / "requests").exists()


def test_worker_receives_only_scoped_parameters_and_logs_are_streamed(project, caplog):
    root, source, mailbox = project
    advertisement = advertise(mailbox)

    def reply(directory, request):
        assert request == dict(
            version=1,
            session=advertisement["session"],
            id=directory.name,
            subject_id="101",
            threads=2,
            input_path="sub-101/anat/sub-101_T1w.nii.gz",
        )
        heartbeat = json.loads((directory / "heartbeat.json").read_text())
        assert abs(time.time() * 1000 - heartbeat["lastSeen"]) < 2000
        (directory / "stdout.log").write_text("Coronal completed\n")
        (directory / "result.json").write_text('{"ok": true}')

    with caplog.at_level(logging.INFO):
        assert run(project, ReplyEvent(mailbox, reply)) is True
    assert "Coronal completed" in caplog.text
    assert not list(mailbox.glob("requests/*/cancel"))


@pytest.mark.parametrize(
    "result", [{"ok": False, "error": "MPS unavailable"}, {"ok": "true"}, {}]
)
def test_worker_failure_is_reported_and_cancelled(project, result):
    mailbox = project[2]
    advertise(mailbox)

    def reply(directory, request):
        (directory / "result.json").write_text(json.dumps(result))

    with pytest.raises(PreprocessError, match="Native FastSurfer failed"):
        run(project, ReplyEvent(mailbox, reply))
    assert len(list(mailbox.glob("requests/*/cancel"))) == 1


@pytest.mark.parametrize("change", ["session", "stale", "removed"])
def test_lost_host_is_cancelled_instead_of_waiting_forever(project, change):
    mailbox = project[2]
    advertise(mailbox)

    def reply(directory, request):
        if change == "removed":
            (mailbox / "availability.json").unlink()
        else:
            advertise(mailbox, **({"lastSeen": 0} if change == "stale" else {}))

    with pytest.raises(PreprocessError):
        run(project, ReplyEvent(mailbox, reply))
    assert len(list(mailbox.glob("requests/*/cancel"))) == 1


def test_cancellation_signals_host(project):
    mailbox = project[2]
    advertise(mailbox)
    event = ReplyEvent(mailbox, lambda directory, request: event.set())
    with pytest.raises(PreprocessCancelled):
        run(project, event)
    assert len(list(mailbox.glob("requests/*/cancel"))) == 1


def test_subject_cannot_escape_output_directory(project):
    advertise(project[2])
    with pytest.raises(PreprocessError, match="subject"):
        run(project, subject_id="../escape")


@pytest.mark.parametrize("symlink", [False, True])
def test_input_cannot_escape_project(project, tmp_path_factory, symlink):
    outside = tmp_path_factory.mktemp("outside") / "input.nii.gz"
    outside.write_bytes(b"not-project-data")
    advertise(project[2])
    source = outside
    if symlink:
        source = project[0] / "linked.nii.gz"
        source.symlink_to(outside)
    with pytest.raises(PreprocessError, match="escapes"):
        run(project, input_path=source)


def test_mailbox_cannot_be_redirected_outside_project(project, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    mailbox = project[2]
    mailbox.rmdir()
    mailbox.symlink_to(outside, target_is_directory=True)
    with pytest.raises(PreprocessError, match="escapes"):
        run(project)


def test_native_route_backfills_standard_outputs_without_container_runtime(
    project, monkeypatch
):
    from tit.paths import reset_path_manager
    from tit.pre import fastsurfer
    from tit.pre.utils import CommandRunner

    root, source, mailbox = project
    advertise(mailbox)
    monkeypatch.setenv("PROJECT_DIR", str(root))
    monkeypatch.setenv("FASTSURFER_HOME", str(root / "missing-runtime"))
    monkeypatch.setenv("TIT_FASTSURFER_DEVICE", "mps")
    monkeypatch.setattr(fastsurfer, "_find_anat_files", lambda sid: (str(source), None))
    derived = []
    monkeypatch.setattr(
        fastsurfer, "write_derived_outputs", lambda path, **kw: derived.append(path)
    )

    def reply(directory, request):
        output = root / "derivatives/fastsurfer/sub-101/mri"
        output.mkdir(parents=True)
        (output / fastsurfer.SEG_FILENAME).write_bytes(b"segmentation fixture")
        (directory / "result.json").write_text('{"ok": true}')

    reset_path_manager()
    try:
        fastsurfer.run_fastsurfer(
            str(root),
            "101",
            logger=logging.getLogger("native-test"),
            runner=CommandRunner(ReplyEvent(mailbox, reply)),
        )
        assert derived == [root / "derivatives/fastsurfer/sub-101/mri"]
    finally:
        reset_path_manager()
