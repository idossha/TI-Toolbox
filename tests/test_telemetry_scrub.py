"""``error_detail`` and the error fingerprint never carry a path fragment or a subject id.

What this pins (2026-10-22, package p18 "telemetry-scrub-gaps"): the privacy contract in
``tit.telemetry``'s module docstring -- "Not collected: file paths, subject IDs ... usernames".
Before this fix ``_scrub`` treated only ``/\\S+`` as a path, so:

- ``C:\\Users\\JohnDoe\\...`` and ``\\\\fileserver\\lab\\JaneDoe\\...`` went out unchanged;
- ``/Users/John Doe/Data`` became ``<path> Doe<path>`` (the second half of the user name leaked);
- ``subjects ['101', '102']`` and ``Subjects: 101, 102`` kept every id after the first.

Where the expected values come from: the contract itself -- each message below is written with
its paths replaced by ``<path>`` and its subject ids by ``<id>``, everything else kept -- worked
out by hand per row; the property test builds each expected string from the same template with
the id slot filled by ``<id>``. Ids are drawn from ``tit.paths.SUBJECT_ID_RE``'s alphabet with a
fixed seed, so a failure reproduces.

Run: ``python -m pytest tests/test_telemetry_scrub.py -q -p no:cacheprovider``.
Deliberately elsewhere: the subject forms already pinned before this fix, and the real charm /
FastSurfer / group-grid messages (``tests/test_telemetry.py::TestErrorDetailScrubsSubjects``).
"""

from __future__ import annotations

import random
import string

import pytest

from tit.paths import SUBJECT_ID_RE
from tit.telemetry import _error_detail, _error_fingerprint

#: Every token that identifies a person or a subject in the rows below.
PRIVATE_TOKENS = [
    "JohnDoe",
    "John",
    "Doe",
    "JaneDoe",
    "fileserver",
    "101",
    "102",
    "ernie",
]

ROWS = [
    (r"cannot open C:\Users\JohnDoe\TI\x.nii", "cannot open <path>"),
    (r"no project at \\fileserver\lab\JaneDoe\p", "no project at <path>"),
    ("/Users/John Doe/Data/proj missing", "<path> missing"),
    ("subjects ['101', '102'] mismatch", "subjects ['<id>', '<id>'] mismatch"),
    ("Subjects: 101, 102 differ", "Subjects: <id>, <id> differ"),
    (r"C:\Users\John Doe\TI\x.nii not found", "<path> not found"),
    (
        "[Errno 2] No such file or directory: '/Users/John Doe/x.nii'",
        "[Errno 2] No such file or directory: '<path>'",
    ),
    ("subject_ids=['101', 'ernie'] invalid", "subject_ids=['<id>', '<id>'] invalid"),
]


@pytest.fixture(autouse=True)
def _no_job_subjects(monkeypatch):
    monkeypatch.delenv("TIT_JOB_SUBJECT_IDS", raising=False)


@pytest.mark.parametrize("message, expected", ROWS)
def test_paths_and_id_lists_are_scrubbed(message, expected):
    detail = _error_detail(ValueError(message))
    assert detail == expected
    for token in PRIVATE_TOKENS:
        assert token not in detail


# -- property: random subject ids in every documented form --------------------------------------

#: (message template, expected template); "{sid}"/"{other}" are subject ids.
FORMS = [
    ("sub-{sid} failed", "sub-<id> failed"),
    ("m2m_{sid} has no EEG net", "m2m_<id> has no EEG net"),
    ("No head model for subject {sid}", "No head model for subject <id>"),
    ("bad subject_id='{sid}'", "bad subject_id='<id>'"),
    (
        "cannot read /data/proj/derivatives/SimNIBS/sub-{sid}/m2m_{sid}/eeg.csv",
        "cannot read <path>",
    ),
    (r"cannot read C:\proj\sub-{sid}\x.msh", "cannot read <path>"),
    ("montage for {sid} is empty", "montage for <id> is empty"),
    ("subjects ['{sid}', '{other}'] mismatch", "subjects ['<id>', '<id>'] mismatch"),
]
_FIRST = string.ascii_letters + string.digits
_REST = _FIRST + "_-"


def _random_ids(n: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    ids = []
    while len(ids) < n:
        sid = rng.choice(_FIRST) + "".join(
            rng.choice(_REST) for _ in range(rng.randint(0, 19))
        )
        assert SUBJECT_ID_RE.match(sid)
        ids.append(sid)
    return ids


IDS = _random_ids(200, seed=20261022)


@pytest.mark.parametrize("template, expected", FORMS)
def test_no_random_subject_id_survives_in_any_documented_form(
    monkeypatch, template, expected
):
    for sid, other in zip(IDS, reversed(IDS)):
        # The runner exports the job's own subjects (tit.jobs.runner.runner_env).
        monkeypatch.setenv("TIT_JOB_SUBJECT_IDS", f"{sid},{other}")
        detail = _error_detail(RuntimeError(template.format(sid=sid, other=other)))
        assert detail == expected[:80], (sid, other)
        assert len(detail) <= 80


def test_the_property_ids_are_not_trivial():
    """The draw covers ids with every character class the rule allows."""
    joined = "".join(IDS)
    assert len(set(IDS)) == len(IDS)
    assert "-" in joined and "_" in joined
    assert any(c.isdigit() for c in joined) and any(c.isupper() for c in joined)
    assert max(len(s) for s in IDS) == 20


# -- fingerprint --------------------------------------------------------------------------------


def _fingerprint_of(message: str) -> str:
    try:
        raise FileNotFoundError(message)  # one raise site: same traceback location
    except FileNotFoundError as exc:
        return _error_fingerprint(exc)


@pytest.mark.parametrize(
    "template",
    [
        r"cannot open C:\Users\{user}\TI\x.nii",
        r"no project at \\fileserver\lab\{user}\p",
        "cannot open /Users/{user}/Data/proj",
    ],
)
def test_the_fingerprint_does_not_depend_on_the_user_name(template):
    assert _fingerprint_of(template.format(user="JohnDoe")) == _fingerprint_of(
        template.format(user="Jane Roe")
    )


def test_the_fingerprint_still_tells_different_errors_apart():
    """Control: the invariance above is not a constant fingerprint."""
    assert _fingerprint_of("cannot open /a/b") != _fingerprint_of("cannot write /a/b")
