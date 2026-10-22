"""``examples/scripts/*.py`` import and call the ``tit`` API that actually exists.

These scripts are what a user copies first, and they run SimNIBS at module level, so
they are never executed here. Instead each one is checked off its source text with the
resolver in ``tests/test_docs_code_api.py`` (the same one the wiki and skills use):
every ``from tit... import X`` resolves, and every keyword passed to an imported
callable, a nested config class, or a method of an instance built from an imported
class binds against the real signature. Each script must also have had the calls it is
built on bound -- so a script whose imports stop resolving cannot pass by checking
nothing.

Until 2026-10-22 this file only grepped for names, and preprocess.py/pipeline.py passed
``run_recon``/``parallel_recon``/``run_subcortical_segmentations`` to ``run_pipeline``
(TypeError) while flex.py imported ``FlexConfig`` from ``tit.opt.flex`` (ImportError).

Reproduce: ``.venv/bin/python -m pytest tests/test_scripts.py -q``.
"""

from __future__ import annotations

import pytest

from tests.test_docs_code_api import REPO, check_blocks, script_blocks

SCRIPTS_DIR = REPO / "examples" / "scripts"

#: The calls each script is built on, by qualified name (methods as ``Class.method``).
EXPECTED_CALLS: dict[str, list[str]] = {
    "analyzer.py": ["Analyzer", "Analyzer.analyze_sphere"],
    "blender.py": [
        "MontageConfig",
        "run_montage",
        "VectorConfig",
        "run_vectors",
        "RegionConfig",
        "run_regions",
    ],
    "cluster_permutation.py": [
        "GroupComparisonConfig.load_subjects",
        "GroupComparisonConfig",
        "run_group_comparison",
    ],
    "ex.py": ["ExConfig", "PoolElectrodes", "run_ex_search"],
    "flex.py": ["FlexConfig", "ElectrodeConfig", "SphericalROI", "run_flex_search"],
    "leadfield.py": ["LeadfieldGenerator", "LeadfieldGenerator.generate"],
    "pipeline.py": [
        "run_pipeline",
        "FlexConfig",
        "run_flex_search",
        "load_montages",
        "SimulationConfig",
        "run_simulation",
        "Analyzer",
        "Analyzer.analyze_sphere",
    ],
    "preprocess.py": ["run_pipeline"],
    "simulator.py": ["Montage", "SimulationConfig", "run_simulation"],
}

BLOCKS = {block.path.rsplit("/", 1)[-1]: block for block in script_blocks()}


def test_every_script_is_listed() -> None:
    assert sorted(BLOCKS) == sorted(
        EXPECTED_CALLS
    ), "examples/scripts changed: list the new script's calls in EXPECTED_CALLS"


@pytest.mark.unit
@pytest.mark.parametrize("name", sorted(EXPECTED_CALLS))
def test_script_resolves_against_tit(name: str) -> None:
    block = BLOCKS[name]
    compile(block.source, block.path, "exec")
    problems, _imports, calls = check_blocks([block])
    assert not problems, "\n".join(problems)
    for expected in EXPECTED_CALLS[name]:
        assert any(
            call == expected or call.endswith("." + expected) for call in calls
        ), f"{name}: {expected} was never bound (bound: {sorted(set(calls))})"
