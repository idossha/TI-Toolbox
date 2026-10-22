"""Telemetry never raises into the operation it wraps, and only a JSON ``true`` enables it.

What this pins (2026-10-22, package p18 "telemetry-never-crashes"): ``tit.telemetry`` promises
that its calls "never block or crash the user's workflow" and that telemetry stays disabled
"until the user gives explicit consent". Before this fix:

- a ``telemetry.json`` holding ``[]`` (or any non-object) made ``load_config`` raise
  ``AttributeError``, so ``with track_operation(...)`` raised before the science body ran;
- an unwritable user config directory made ``_config_path``'s ``mkdir`` raise ``OSError`` the same
  way (a read-only HOME, or a launcher mount that is not there);
- ``{"enabled": "false"}`` -- a string -- turned telemetry *on*, and ``PUT /api/settings`` did
  ``bool(body["enabled"])``, so the string ``"false"`` sent from any client enabled it too, while
  ``GET /api/settings`` (pydantic coercion) reported it off.

Where the expected values come from: that docstring contract (the body runs, nothing is raised,
nothing is sent without an explicit JSON ``true``) and ``contracts/openapi.yaml``'s
``Telemetry.enabled: boolean``. The config files are authored below; the real config directory
is resolved through ``PathManager.user_config_dir`` with ``TIT_USER_CONFIG`` pointing into
``tmp_path`` (the in-container mount path is redirected to a path that cannot exist).

Run: ``python -m pytest tests/test_telemetry_robustness.py -q -p no:cacheprovider``.
Deliberately elsewhere: payload shapes and consent prompts (``tests/test_telemetry.py``).
"""

from __future__ import annotations

import os
import threading
from unittest.mock import patch

import pytest

from tit import constants as const
from tit import telemetry

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

TOKEN = "test-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}

#: telemetry.json bodies that are not an explicit opt-in.
NOT_CONSENT = [
    "[]",
    "null",
    '"x"',
    "42",
    '{"enabled": "false"}',
    '{"enabled": "true"}',
    '{"enabled": 1}',
    '{"enabled": null}',
    '{"enabled": [true]}',
    "{not json",
]


@pytest.fixture()
def config_dir(tmp_path, monkeypatch):
    """The user config dir as PathManager resolves it, inside tmp_path."""
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, so nothing can be created below it")
    monkeypatch.setattr(const, "USER_CONFIG_CONTAINER_PATH", str(blocker / "x"))
    target = tmp_path / "user-config"
    monkeypatch.setenv("TIT_USER_CONFIG", str(target))
    monkeypatch.delenv(const.ENV_NO_TELEMETRY, raising=False)
    monkeypatch.setattr(const, "GA4_MEASUREMENT_ID", "G-TESTVALUE")
    telemetry._invalidate_cache()
    yield target
    telemetry._invalidate_cache()


def _write_config(config_dir, body: str) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / const.TELEMETRY_CONFIG_FILE).write_text(body)
    telemetry._invalidate_cache()


def _run_tracked() -> tuple[bool, list[dict]]:
    """Run a tracked body; return whether it ran and every payload handed to the sender."""
    sent: list[dict] = []
    ran = False
    with patch("tit.telemetry._send_ga4", side_effect=sent.append):
        with telemetry.track_operation("sim_ti"):
            ran = True
        for thread in threading.enumerate():
            if thread.name == "tit-telemetry":
                thread.join(timeout=5)
    return ran, sent


@pytest.mark.parametrize("body", NOT_CONSENT)
def test_a_config_without_explicit_consent_never_breaks_or_sends(config_dir, body):
    _write_config(config_dir, body)
    ran, sent = _run_tracked()
    assert ran
    assert sent == []
    assert telemetry.is_enabled() is False


def test_explicit_consent_sends_the_start_and_success_events(config_dir):
    """Control: the same harness does see events when the file holds ``enabled: true``."""
    _write_config(config_dir, '{"enabled": true, "consent_shown": true}')
    ran, sent = _run_tracked()
    assert ran
    assert telemetry.is_enabled() is True
    statuses = sorted(p["events"][0]["params"]["status"] for p in sent)
    assert statuses == ["start", "success"]


def test_an_exception_in_the_body_is_reraised_unchanged_when_the_config_is_corrupt(
    config_dir,
):
    _write_config(config_dir, "[]")
    with patch("tit.telemetry._send_ga4") as send:
        with pytest.raises(KeyError, match="the science failed"):
            with telemetry.track_operation("sim_ti"):
                raise KeyError("the science failed")
    send.assert_not_called()


def test_a_failure_while_building_an_event_never_reaches_the_operation(
    config_dir, monkeypatch
):
    """With consent given, a broken payload builder still lets the tracked body run."""
    _write_config(config_dir, '{"enabled": true}')

    def broken():
        raise RuntimeError("platform probe failed")

    monkeypatch.setattr(telemetry, "_system_params", broken)
    ran, sent = _run_tracked()
    assert ran and sent == []


def test_a_failure_while_describing_the_error_keeps_the_operations_own_exception(
    config_dir, monkeypatch
):
    _write_config(config_dir, '{"enabled": true}')

    def broken(exc):
        raise TypeError("scrubber failed")

    monkeypatch.setattr(telemetry, "_error_detail", broken)
    with patch("tit.telemetry._send_ga4"):
        with pytest.raises(KeyError, match="the science failed"):
            with telemetry.track_operation("sim_ti"):
                raise KeyError("the science failed")


def test_a_config_dir_that_cannot_be_resolved_never_breaks_the_operation(
    config_dir, monkeypatch
):
    from tit.paths import PathManager

    def refuse():
        raise PermissionError(13, "Permission denied", "/root/.config/ti-toolbox")

    monkeypatch.setattr(PathManager, "user_config_dir", staticmethod(refuse))
    telemetry._invalidate_cache()
    ran, sent = _run_tracked()
    assert ran and sent == []
    assert telemetry.is_enabled() is False
    assert telemetry.load_config().enabled is False


def _home_cases(tmp_path):
    cases = {}
    as_file = tmp_path / "home-is-a-file"
    as_file.write_text("")
    cases["home is a file"] = as_file
    if os.geteuid() != 0:  # root ignores directory permissions
        read_only = tmp_path / "read-only-home"
        read_only.mkdir()
        read_only.chmod(0o555)
        cases["home is read-only"] = read_only
    return cases


def test_an_unwritable_home_never_breaks_the_operation(
    config_dir, tmp_path, monkeypatch
):
    monkeypatch.delenv("TIT_USER_CONFIG", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    cases = _home_cases(tmp_path)
    try:
        for name, home in cases.items():
            monkeypatch.setenv("HOME", str(home))
            telemetry._invalidate_cache()
            ran, sent = _run_tracked()
            assert ran and sent == [], name
            assert telemetry.is_enabled() is False, name
            # Saving consent degrades to "not saved", never to an exception.
            telemetry.set_enabled(False)
    finally:
        for home in cases.values():
            if home.is_dir():
                home.chmod(0o755)  # let pytest clean tmp_path up


# -- the settings route --------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path, config_dir):
    from fastapi.testclient import TestClient

    from tit.paths import get_path_manager
    from tit.server.app import create_app
    from tit.server.settings import ServerSettings

    project = tmp_path / "project"
    project.mkdir()
    get_path_manager(str(project))
    settings = ServerSettings(project_dir=str(project), token=TOKEN)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


@pytest.mark.parametrize(
    "body", NOT_CONSENT + ['{"enabled": true}', '{"enabled": false}']
)
def test_get_settings_reports_what_is_enabled_says(client, config_dir, body):
    _write_config(config_dir, body)
    response = client.get("/api/settings", headers=BEARER)
    assert response.status_code == 200
    assert response.json()["telemetry"]["enabled"] is telemetry.is_enabled()
    assert response.json()["telemetry"]["enabled"] is (body == '{"enabled": true}')


def test_get_settings_answers_when_the_config_dir_is_unusable(client, monkeypatch):
    from tit.paths import PathManager

    def refuse():
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(PathManager, "user_config_dir", staticmethod(refuse))
    telemetry._invalidate_cache()
    response = client.get("/api/settings", headers=BEARER)
    assert response.status_code == 200
    assert response.json()["telemetry"] == {"consented": False, "enabled": False}


@pytest.mark.parametrize(
    "telemetry_body",
    [
        {"enabled": "false"},
        {"enabled": "true"},
        {"enabled": 0},
        {"enabled": 1},
        {"enabled": None},
        {"consented": "yes"},
        "enabled",
        ["enabled"],
    ],
)
def test_put_settings_refuses_a_telemetry_flag_that_is_not_a_boolean(
    client, config_dir, telemetry_body
):
    response = client.put(
        "/api/settings",
        json={"telemetry": telemetry_body, "panels": [], "theme": "system"},
        headers=BEARER,
    )
    assert response.status_code == 422
    assert telemetry.is_enabled() is False
    assert not (config_dir / const.TELEMETRY_CONFIG_FILE).exists()


@pytest.mark.parametrize("enabled", [True, False])
def test_put_settings_applies_a_boolean_telemetry_flag(client, enabled):
    with patch("tit.telemetry._send_ga4"):
        response = client.put(
            "/api/settings",
            json={
                "telemetry": {"consented": True, "enabled": enabled},
                "panels": [],
                "theme": "system",
            },
            headers=BEARER,
        )
    assert response.status_code == 200
    assert response.json()["telemetry"] == {"consented": True, "enabled": enabled}
    assert telemetry.is_enabled() is enabled


def test_put_settings_with_an_invalid_theme_changes_no_telemetry(client, config_dir):
    response = client.put(
        "/api/settings",
        json={"telemetry": {"enabled": True}, "panels": [], "theme": "solarized"},
        headers=BEARER,
    )
    assert response.status_code == 422
    assert telemetry.is_enabled() is False
