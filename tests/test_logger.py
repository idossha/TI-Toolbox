#!/usr/bin/env simnibs_python
"""
Unit tests for tit/logger.py — Logging infrastructure.

Tests the logging setup utilities including:
- setup_logging: configures tit logger hierarchy
- add_file_handler: attaches FileHandler to named logger
- add_stream_handler: attaches StreamHandler to named logger
- get_file_only_logger: creates isolated file-only logger
- Third-party logger silencing
"""

import sys
import logging
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tit.logger import (
    setup_logging,
    add_file_handler,
    add_stream_handler,
    get_file_only_logger,
    LOG_FORMAT,
    DATE_FORMAT,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _cleanup_loggers():
    """Clear handlers from tit loggers before and after each test."""
    logger = logging.getLogger("tit")
    logger.handlers.clear()
    yield
    logger.handlers.clear()
    # Clean up any test-specific loggers
    for name in list(logging.Logger.manager.loggerDict):
        if name.startswith("test_logger_"):
            logging.getLogger(name).handlers.clear()


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_sets_info_level_by_default(self):
        setup_logging()
        logger = logging.getLogger("tit")
        assert logger.level == logging.INFO

    def test_sets_debug_level(self):
        setup_logging(level="DEBUG")
        logger = logging.getLogger("tit")
        assert logger.level == logging.DEBUG

    def test_sets_warning_level(self):
        setup_logging(level="WARNING")
        logger = logging.getLogger("tit")
        assert logger.level == logging.WARNING

    def test_sets_error_level(self):
        setup_logging(level="ERROR")
        logger = logging.getLogger("tit")
        assert logger.level == logging.ERROR

    def test_sets_critical_level(self):
        setup_logging(level="CRITICAL")
        logger = logging.getLogger("tit")
        assert logger.level == logging.CRITICAL

    def test_case_insensitive_level(self):
        setup_logging(level="debug")
        logger = logging.getLogger("tit")
        assert logger.level == logging.DEBUG

    def test_clears_existing_handlers(self):
        logger = logging.getLogger("tit")
        logger.addHandler(logging.StreamHandler())
        logger.addHandler(logging.StreamHandler())
        assert len(logger.handlers) == 2
        setup_logging()
        assert len(logger.handlers) == 0

    def test_sets_propagate_false(self):
        setup_logging()
        logger = logging.getLogger("tit")
        assert logger.propagate is False

    def test_no_handlers_added(self):
        setup_logging()
        logger = logging.getLogger("tit")
        assert len(logger.handlers) == 0

    def test_idempotent(self):
        setup_logging(level="DEBUG")
        setup_logging(level="INFO")
        logger = logging.getLogger("tit")
        assert logger.level == logging.INFO
        assert len(logger.handlers) == 0

    def test_silences_matplotlib(self):
        setup_logging()
        mpl_logger = logging.getLogger("matplotlib")
        assert mpl_logger.level == logging.ERROR

    def test_silences_matplotlib_font_manager(self):
        setup_logging()
        fm_logger = logging.getLogger("matplotlib.font_manager")
        assert fm_logger.level == logging.ERROR

    def test_silences_pil(self):
        setup_logging()
        pil_logger = logging.getLogger("PIL")
        assert pil_logger.level == logging.ERROR

    def test_invalid_level_falls_back_to_info(self):
        setup_logging(level="NONEXISTENT")
        logger = logging.getLogger("tit")
        assert logger.level == logging.INFO


# ---------------------------------------------------------------------------
# add_file_handler
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAddFileHandler:
    """Tests for add_file_handler function."""

    def test_returns_file_handler(self, tmp_path):
        log_file = tmp_path / "test.log"
        handler = add_file_handler(log_file)
        assert isinstance(handler, logging.FileHandler)

    def test_creates_log_file(self, tmp_path):
        log_file = tmp_path / "test.log"
        setup_logging()
        handler = add_file_handler(log_file)
        logger = logging.getLogger("tit")
        logger.info("hello")
        handler.flush()
        assert log_file.exists()

    def test_writes_to_file(self, tmp_path):
        log_file = tmp_path / "test.log"
        setup_logging()
        handler = add_file_handler(log_file)
        logger = logging.getLogger("tit")
        logger.info("test message 12345")
        handler.flush()
        content = log_file.read_text()
        assert "test message 12345" in content

    def test_creates_parent_directories(self, tmp_path):
        log_file = tmp_path / "deep" / "nested" / "dir" / "test.log"
        handler = add_file_handler(log_file)
        assert log_file.parent.exists()
        handler.close()

    def test_default_level_debug(self, tmp_path):
        log_file = tmp_path / "test.log"
        handler = add_file_handler(log_file)
        assert handler.level == logging.DEBUG
        handler.close()

    def test_custom_level(self, tmp_path):
        log_file = tmp_path / "test.log"
        handler = add_file_handler(log_file, level="WARNING")
        assert handler.level == logging.WARNING
        handler.close()

    def test_attaches_to_tit_logger_by_default(self, tmp_path):
        log_file = tmp_path / "test.log"
        handler = add_file_handler(log_file)
        logger = logging.getLogger("tit")
        assert handler in logger.handlers
        handler.close()

    def test_attaches_to_custom_logger(self, tmp_path):
        log_file = tmp_path / "test.log"
        handler = add_file_handler(log_file, logger_name="test_logger_custom")
        logger = logging.getLogger("test_logger_custom")
        assert handler in logger.handlers
        handler.close()

    def test_has_formatter(self, tmp_path):
        log_file = tmp_path / "test.log"
        handler = add_file_handler(log_file)
        assert handler.formatter is not None
        assert handler.formatter._fmt == LOG_FORMAT
        handler.close()

    def test_append_mode(self, tmp_path):
        log_file = tmp_path / "test.log"
        log_file.write_text("existing content\n")
        setup_logging()
        handler = add_file_handler(log_file)
        logger = logging.getLogger("tit")
        logger.info("new content")
        handler.flush()
        content = log_file.read_text()
        assert "existing content" in content
        assert "new content" in content
        handler.close()

    def test_string_path_accepted(self, tmp_path):
        log_file = str(tmp_path / "test.log")
        handler = add_file_handler(log_file)
        assert isinstance(handler, logging.FileHandler)
        handler.close()


# ---------------------------------------------------------------------------
# add_stream_handler
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAddStreamHandler:
    """Tests for add_stream_handler function."""

    def test_returns_stream_handler(self):
        handler = add_stream_handler(logger_name="test_logger_stream")
        assert isinstance(handler, logging.StreamHandler)
        logging.getLogger("test_logger_stream").removeHandler(handler)

    def test_default_level_info(self):
        handler = add_stream_handler(logger_name="test_logger_stream_lvl")
        assert handler.level == logging.INFO
        logging.getLogger("test_logger_stream_lvl").removeHandler(handler)

    def test_custom_level(self):
        handler = add_stream_handler(
            logger_name="test_logger_stream_custom", level="DEBUG"
        )
        assert handler.level == logging.DEBUG
        logging.getLogger("test_logger_stream_custom").removeHandler(handler)

    def test_attaches_to_named_logger(self):
        handler = add_stream_handler(logger_name="test_logger_stream_attach")
        logger = logging.getLogger("test_logger_stream_attach")
        assert handler in logger.handlers
        logger.removeHandler(handler)

    def test_attaches_to_tit_by_default(self):
        handler = add_stream_handler()
        logger = logging.getLogger("tit")
        assert handler in logger.handlers
        logger.removeHandler(handler)

    def test_has_simple_formatter(self):
        handler = add_stream_handler(logger_name="test_logger_stream_fmt")
        assert handler.formatter is not None
        assert handler.formatter._fmt == "%(message)s"
        logging.getLogger("test_logger_stream_fmt").removeHandler(handler)


# ---------------------------------------------------------------------------
# get_file_only_logger
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetFileOnlyLogger:
    """Tests for get_file_only_logger function."""

    def test_returns_logger(self, tmp_path):
        log_file = tmp_path / "test.log"
        logger = get_file_only_logger("test_logger_fol_1", log_file)
        assert isinstance(logger, logging.Logger)

    def test_logger_has_file_handler(self, tmp_path):
        log_file = tmp_path / "test.log"
        logger = get_file_only_logger("test_logger_fol_2", log_file)
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1

    def test_logger_has_no_stream_handler(self, tmp_path):
        log_file = tmp_path / "test.log"
        logger = get_file_only_logger("test_logger_fol_3", log_file)
        stream_handlers = [
            h for h in logger.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        assert len(stream_handlers) == 0

    def test_propagate_false(self, tmp_path):
        log_file = tmp_path / "test.log"
        logger = get_file_only_logger("test_logger_fol_4", log_file)
        assert logger.propagate is False

    def test_default_level_debug(self, tmp_path):
        log_file = tmp_path / "test.log"
        logger = get_file_only_logger("test_logger_fol_5", log_file)
        assert logger.level == logging.DEBUG

    def test_custom_level(self, tmp_path):
        log_file = tmp_path / "test.log"
        logger = get_file_only_logger("test_logger_fol_6", log_file, level="WARNING")
        assert logger.level == logging.WARNING

    def test_writes_to_file(self, tmp_path):
        log_file = tmp_path / "test.log"
        logger = get_file_only_logger("test_logger_fol_7", log_file)
        logger.info("file only message 99")
        for h in logger.handlers:
            h.flush()
        content = log_file.read_text()
        assert "file only message 99" in content

    def test_replaces_handlers_on_repeated_calls(self, tmp_path):
        log_file_1 = tmp_path / "test1.log"
        log_file_2 = tmp_path / "test2.log"
        name = "test_logger_fol_repeat"
        logger = get_file_only_logger(name, log_file_1)
        assert len(logger.handlers) == 1

        logger = get_file_only_logger(name, log_file_2)
        # Old handlers cleared, only new file handler remains
        assert len(logger.handlers) == 1
        # New handler should point to log_file_2
        logger.info("goes to file 2")
        for h in logger.handlers:
            h.flush()
        assert log_file_2.exists()
        assert "goes to file 2" in log_file_2.read_text()

    def test_creates_parent_dirs(self, tmp_path):
        log_file = tmp_path / "a" / "b" / "c" / "test.log"
        get_file_only_logger("test_logger_fol_dirs", log_file)
        assert log_file.parent.exists()

    def test_logger_name_preserved(self, tmp_path):
        log_file = tmp_path / "test.log"
        name = "test_logger_fol_name_check"
        logger = get_file_only_logger(name, log_file)
        assert logger.name == name


# ---------------------------------------------------------------------------
# Third-party logger silencing (at import time)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestThirdPartyLoggerSilencing:
    """Tests that noisy third-party loggers are silenced at import time."""

    def test_matplotlib_silenced_at_import(self):
        mpl_logger = logging.getLogger("matplotlib")
        assert mpl_logger.level >= logging.ERROR

    def test_matplotlib_font_manager_silenced(self):
        fm_logger = logging.getLogger("matplotlib.font_manager")
        assert fm_logger.level >= logging.ERROR

    def test_pil_silenced(self):
        pil_logger = logging.getLogger("PIL")
        assert pil_logger.level >= logging.ERROR
