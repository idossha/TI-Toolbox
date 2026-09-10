"""Deprecated ``PreprocessConfig`` keys are still read, with a warning.

Covers the migration path a project config JSON written before FastSurfer
replaced FreeSurfer ``recon-all`` takes through
:func:`tit.pre.config.migrate_legacy_keys` and ``tit.pre.__main__``.
"""

from unittest.mock import MagicMock

import pytest

from tit.pre.config import LEGACY_KEYS, PreprocessConfig, migrate_legacy_keys


class TestMigrateLegacyKeys:
    def test_current_config_is_returned_unchanged(self):
        data = {"subject_ids": ["001"], "run_fastsurfer": True}
        assert migrate_legacy_keys(data) is data

    def test_run_recon_becomes_run_fastsurfer(self):
        logger = MagicMock()
        out = migrate_legacy_keys(
            {"subject_ids": ["001"], "run_recon": True}, logger=logger
        )
        assert out == {"subject_ids": ["001"], "run_fastsurfer": True}
        message = logger.warning.call_args[0][0]
        assert "run_recon" in message
        assert "deprecated" in message

    def test_dropped_keys_are_removed_with_a_warning(self):
        data = {
            "subject_ids": ["001"],
            "parallel_recon": True,
            "parallel_cores": 8,
            "run_subcortical_segmentations": True,
        }
        logger = MagicMock()
        out = migrate_legacy_keys(data, logger=logger)
        assert out == {"subject_ids": ["001"]}
        warned = " ".join(call[0][0] for call in logger.warning.call_args_list)
        for key in (
            "parallel_recon",
            "parallel_cores",
            "run_subcortical_segmentations",
        ):
            assert key in warned

    def test_the_input_dict_is_not_mutated(self):
        data = {"subject_ids": ["001"], "run_recon": True}
        migrate_legacy_keys(data)
        assert data == {"subject_ids": ["001"], "run_recon": True}

    def test_explicit_new_key_wins_over_the_old_one(self):
        logger = MagicMock()
        out = migrate_legacy_keys(
            {"subject_ids": ["001"], "run_recon": True, "run_fastsurfer": False},
            logger=logger,
        )
        assert out["run_fastsurfer"] is False
        assert "already set" in logger.warning.call_args[0][0]

    def test_migrated_dict_builds_a_config(self):
        out = migrate_legacy_keys(
            {"subject_ids": ["001"], "run_recon": True, "parallel_cores": 4}
        )
        config = PreprocessConfig(**out)
        assert config.run_fastsurfer is True
        assert config.fastsurfer_threads is None

    def test_warnings_list_collects_the_same_messages_as_the_logger(self):
        # FX3 item 4 / qa-neuro-researcher-notes.md #5: a caller (POST /api/plan/pre) that
        # wants the deprecation surfaced in its own response, not only the server log, passes
        # `warnings=`.
        logger = MagicMock()
        collected: list[str] = []
        out = migrate_legacy_keys(
            {
                "subject_ids": ["001"],
                "run_recon": True,
                "parallel_recon": True,
            },
            logger=logger,
            warnings=collected,
        )
        assert out == {"subject_ids": ["001"], "run_fastsurfer": True}
        logged = [call[0][0] for call in logger.warning.call_args_list]
        assert collected == logged
        assert any("run_recon" in m for m in collected)
        assert any("parallel_recon" in m for m in collected)

    def test_warnings_kwarg_defaults_to_none_and_is_optional(self):
        # No `warnings=` given -> behaves exactly as before (log only, no crash).
        out = migrate_legacy_keys({"subject_ids": ["001"], "run_recon": True})
        assert out == {"subject_ids": ["001"], "run_fastsurfer": True}

    def test_legacy_table_covers_every_removed_key(self):
        assert set(LEGACY_KEYS) == {
            "run_recon",
            "parallel_recon",
            "parallel_cores",
            "run_subcortical_segmentations",
        }


class TestPreprocessConfigFields:
    def test_removed_fields_are_gone(self):
        fields = PreprocessConfig.__dataclass_fields__
        for removed in LEGACY_KEYS:
            assert removed not in fields

    def test_fastsurfer_fields_exist_and_default_off(self):
        config = PreprocessConfig(subject_ids=["001"])
        assert config.run_fastsurfer is False
        assert config.fastsurfer_threads is None

    def test_subject_ids_still_required(self):
        with pytest.raises(ValueError):
            PreprocessConfig(subject_ids=[])
