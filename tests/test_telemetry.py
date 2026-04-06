"""Tests for tit.telemetry — anonymous usage telemetry module.

Verifies config persistence, opt-out mechanisms, event payloads,
the track_operation context manager, and consent-prompt logic.
All HTTP calls are mocked — no real network traffic.
"""

import json
import os
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from tit import constants as const
from tit.telemetry import (
    TelemetryConfig,
    _config_path,
    _invalidate_cache,
    _system_params,
    consent_prompt_cli,
    is_enabled,
    load_config,
    save_config,
    set_enabled,
    track_event,
    track_operation,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path, monkeypatch):
    """Point telemetry config at a temp dir and reset the module cache."""
    config_dir = tmp_path / ".config" / const.TELEMETRY_CONFIG_DIR
    config_dir.mkdir(parents=True)
    config_file = config_dir / const.TELEMETRY_CONFIG_FILE

    monkeypatch.setattr("tit.telemetry._config_path", lambda: config_file)
    # Ensure env var is clean
    monkeypatch.delenv(const.ENV_NO_TELEMETRY, raising=False)
    _invalidate_cache()
    yield
    _invalidate_cache()


# ---------------------------------------------------------------------------
# Config load / save
# ---------------------------------------------------------------------------


class TestConfig:
    """TelemetryConfig persistence tests."""

    def test_defaults(self):
        cfg = load_config()
        assert cfg.enabled is False
        assert cfg.consent_shown is False
        assert len(cfg.client_id) == 32  # uuid4 hex

    def test_roundtrip(self):
        original = TelemetryConfig(enabled=True, client_id="abc123", consent_shown=True)
        save_config(original)
        loaded = load_config()
        assert loaded.enabled is True
        assert loaded.client_id == "abc123"
        assert loaded.consent_shown is True

    def test_corrupt_config_returns_defaults(self):
        path = _config_path()
        path.write_text("{invalid json!!")
        cfg = load_config()
        assert cfg.enabled is False

    def test_file_permissions(self):
        save_config(TelemetryConfig())
        import tit.telemetry

        path = tit.telemetry._config_path()
        mode = oct(os.stat(path).st_mode & 0o777)
        assert mode == "0o600"


# ---------------------------------------------------------------------------
# is_enabled()
# ---------------------------------------------------------------------------


class TestIsEnabled:
    """Opt-in / opt-out logic."""

    def test_disabled_by_default(self):
        assert is_enabled() is False

    def test_enabled_after_consent(self):
        set_enabled(True)
        _invalidate_cache()
        assert is_enabled() is True

    def test_env_var_overrides(self, monkeypatch):
        set_enabled(True)
        _invalidate_cache()
        monkeypatch.setattr("tit.constants.GA4_MEASUREMENT_ID", "G-REALVALUE")
        assert is_enabled() is True
        monkeypatch.setenv(const.ENV_NO_TELEMETRY, "1")
        assert is_enabled() is False

    def test_env_var_truthy_values(self, monkeypatch):
        set_enabled(True)
        _invalidate_cache()
        monkeypatch.setattr("tit.constants.GA4_MEASUREMENT_ID", "G-REALVALUE")
        for val in ("1", "true", "True", "yes", "YES"):
            monkeypatch.setenv(const.ENV_NO_TELEMETRY, val)
            assert is_enabled() is False

    def test_env_var_empty_does_not_disable(self, monkeypatch):
        set_enabled(True)
        _invalidate_cache()
        monkeypatch.setattr("tit.constants.GA4_MEASUREMENT_ID", "G-REALVALUE")
        monkeypatch.setenv(const.ENV_NO_TELEMETRY, "")
        assert is_enabled() is True


# ---------------------------------------------------------------------------
# set_enabled()
# ---------------------------------------------------------------------------


class TestSetEnabled:
    """Programmatic enable/disable."""

    def test_toggle(self):
        set_enabled(True)
        cfg = load_config()
        assert cfg.enabled is True
        assert cfg.consent_shown is True

        set_enabled(False)
        cfg = load_config()
        assert cfg.enabled is False


# ---------------------------------------------------------------------------
# System params
# ---------------------------------------------------------------------------


class TestSystemParams:
    """Non-identifying system metadata."""

    def test_keys_present(self):
        params = _system_params()
        expected = {
            "tit_version",
            "python_version",
            "os_name",
            "os_version",
            "platform",
        }
        assert set(params.keys()) == expected

    def test_version_matches(self):
        import tit

        assert _system_params()["tit_version"] == tit.__version__


# ---------------------------------------------------------------------------
# track_event()
# ---------------------------------------------------------------------------


class TestTrackEvent:
    """Fire-and-forget event sending."""

    def test_no_send_when_disabled(self):
        with patch("tit.telemetry._send_ga4") as mock:
            track_event("test_event")
            mock.assert_not_called()

    def test_sends_when_enabled(self, monkeypatch):
        set_enabled(True)
        _invalidate_cache()
        monkeypatch.setattr("tit.constants.GA4_MEASUREMENT_ID", "G-REALVALUE")

        payloads = []

        def capture(p):
            payloads.append(p)

        with patch("tit.telemetry._send_ga4", side_effect=capture):
            track_event("sim_ti", {"status": "start"})

        # Wait for daemon thread
        import threading

        for t in threading.enumerate():
            if t.daemon and t.is_alive():
                t.join(timeout=2)

        assert len(payloads) == 1
        event = payloads[0]["events"][0]
        assert event["name"] == "sim_ti"
        assert event["params"]["status"] == "start"
        assert "tit_version" in event["params"]
        assert "os_name" in event["params"]

    def test_payload_has_client_id(self, monkeypatch):
        set_enabled(True)
        _invalidate_cache()
        monkeypatch.setattr("tit.constants.GA4_MEASUREMENT_ID", "G-REALVALUE")

        payloads = []
        with patch("tit.telemetry._send_ga4", side_effect=lambda p: payloads.append(p)):
            track_event("test")

        import threading

        for t in threading.enumerate():
            if t.daemon and t.is_alive():
                t.join(timeout=2)

        assert "client_id" in payloads[0]
        assert len(payloads[0]["client_id"]) == 32


# ---------------------------------------------------------------------------
# track_operation() context manager
# ---------------------------------------------------------------------------


class TestTrackOperation:
    """Start/success/error event pairs."""

    def _force_enabled(self, monkeypatch):
        set_enabled(True)
        _invalidate_cache()
        monkeypatch.setattr("tit.constants.GA4_MEASUREMENT_ID", "G-REALVALUE")

    def test_success_sends_two_events(self, monkeypatch):
        self._force_enabled(monkeypatch)
        payloads = []
        with patch("tit.telemetry._send_ga4", side_effect=lambda p: payloads.append(p)):
            with track_operation("flex_search"):
                pass

        import threading

        for t in threading.enumerate():
            if t.daemon and t.is_alive():
                t.join(timeout=2)

        assert len(payloads) == 2
        assert payloads[0]["events"][0]["params"]["status"] == "start"
        assert payloads[1]["events"][0]["params"]["status"] == "success"

    def test_error_sends_error_event(self, monkeypatch):
        self._force_enabled(monkeypatch)
        payloads = []
        with patch("tit.telemetry._send_ga4", side_effect=lambda p: payloads.append(p)):
            with pytest.raises(ValueError):
                with track_operation("sim_ti"):
                    raise ValueError("boom")

        import threading

        for t in threading.enumerate():
            if t.daemon and t.is_alive():
                t.join(timeout=2)

        assert len(payloads) == 2
        error_event = payloads[1]["events"][0]
        assert error_event["params"]["status"] == "error"
        assert error_event["params"]["error_type"] == "ValueError"

    def test_exception_is_reraised(self, monkeypatch):
        self._force_enabled(monkeypatch)
        with patch("tit.telemetry._send_ga4"):
            with pytest.raises(RuntimeError, match="test"):
                with track_operation("analysis"):
                    raise RuntimeError("test")

    def test_noop_when_disabled(self):
        with patch("tit.telemetry._send_ga4") as mock:
            with track_operation("sim_ti"):
                pass
            mock.assert_not_called()


# ---------------------------------------------------------------------------
# consent_prompt_cli()
# ---------------------------------------------------------------------------


class TestConsentCLI:
    """Terminal consent prompt."""

    def test_accepts_yes(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", StringIO("y\n"))
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        consent_prompt_cli()
        cfg = load_config()
        assert cfg.enabled is True
        assert cfg.consent_shown is True

    def test_accepts_empty_as_yes(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", StringIO("\n"))
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        consent_prompt_cli()
        cfg = load_config()
        assert cfg.enabled is True

    def test_declines_no(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", StringIO("n\n"))
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        consent_prompt_cli()
        cfg = load_config()
        assert cfg.enabled is False
        assert cfg.consent_shown is True

    def test_skips_non_tty(self):
        """Non-interactive environments should not prompt."""
        # Default StringIO has no isatty, so stdin.isatty() returns False
        consent_prompt_cli()
        cfg = load_config()
        assert cfg.consent_shown is False

    def test_only_prompts_once(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", StringIO("y\n"))
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        consent_prompt_cli()

        # Second call should be a no-op (consent_shown is True)
        monkeypatch.setattr("sys.stdin", StringIO("n\n"))
        consent_prompt_cli()
        cfg = load_config()
        assert cfg.enabled is True  # Still yes from first call
