#!/usr/bin/env python3
"""
Unit tests for TI-Toolbox custom exception classes.

The project defines custom exceptions in various modules rather than a
centralised errors module. This file tests all known custom exceptions.
"""

import pytest

from tit.pre.utils import PreprocessError, PreprocessCancelled
from tit.pre.qsi.docker_builder import DockerBuildError

# ---------------------------------------------------------------------------
# PreprocessError
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPreprocessError:
    """Tests for PreprocessError."""

    def test_is_exception_subclass(self):
        assert issubclass(PreprocessError, Exception)

    def test_is_runtime_error_subclass(self):
        assert issubclass(PreprocessError, RuntimeError)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(PreprocessError):
            raise PreprocessError("step failed")

    def test_message_preserved(self):
        err = PreprocessError("charm failed")
        assert str(err) == "charm failed"

    def test_catchable_as_runtime_error(self):
        with pytest.raises(RuntimeError):
            raise PreprocessError("caught as RuntimeError")

    def test_catchable_as_exception(self):
        with pytest.raises(Exception):
            raise PreprocessError("caught as Exception")

    def test_empty_message(self):
        err = PreprocessError("")
        assert str(err) == ""

    def test_with_args(self):
        err = PreprocessError("fail", 42)
        assert err.args == ("fail", 42)


# ---------------------------------------------------------------------------
# PreprocessCancelled
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPreprocessCancelled:
    """Tests for PreprocessCancelled."""

    def test_is_exception_subclass(self):
        assert issubclass(PreprocessCancelled, Exception)

    def test_is_runtime_error_subclass(self):
        assert issubclass(PreprocessCancelled, RuntimeError)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(PreprocessCancelled):
            raise PreprocessCancelled("user cancelled")

    def test_message_preserved(self):
        err = PreprocessCancelled("cancelled by stop_event")
        assert str(err) == "cancelled by stop_event"

    def test_distinct_from_preprocess_error(self):
        """PreprocessCancelled is not a subclass of PreprocessError."""
        assert not issubclass(PreprocessCancelled, PreprocessError)

    def test_not_caught_by_preprocess_error_handler(self):
        """Catching PreprocessError should not catch PreprocessCancelled."""
        with pytest.raises(PreprocessCancelled):
            try:
                raise PreprocessCancelled("cancel")
            except PreprocessError:
                pass  # Should not land here


# ---------------------------------------------------------------------------
# DockerBuildError
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDockerBuildError:
    """Tests for DockerBuildError."""

    def test_is_exception_subclass(self):
        assert issubclass(DockerBuildError, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(DockerBuildError):
            raise DockerBuildError("docker build failed")

    def test_message_preserved(self):
        err = DockerBuildError("missing Dockerfile")
        assert str(err) == "missing Dockerfile"

    def test_not_runtime_error(self):
        """DockerBuildError inherits from Exception, not RuntimeError."""
        assert not issubclass(DockerBuildError, RuntimeError)
