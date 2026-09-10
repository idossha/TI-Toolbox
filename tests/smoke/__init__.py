"""Level A pipeline smoke harness (docs/dev/HISTORY.md § 2026-09-03 (pipelines program) §3, decisions P4-P8).

A package, not a bare directory, because ``tests/`` is a package: ``tests.smoke.matrix`` only
imports under pytest's default prepend import mode when every directory on the path has an
``__init__.py``.
"""
