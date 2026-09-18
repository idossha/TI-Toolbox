"""Display filtering is anatomical, not an atlas-independent numeric ID list."""

from tit.scene.volume_surfaces import default_visible
import pytest


@pytest.mark.parametrize(
    "name", ["Left-Hippocampus", "Right-Thalamus-Proper", "Brain-Stem", "Left-Amygdala"]
)
def test_subcortical_names_visible(name):
    assert default_visible(name)


@pytest.mark.parametrize(
    "name",
    [
        "Background",
        "Left-Lateral-Ventricle",
        "CSF",
        "Left-Cerebral-Cortex",
        "Left-Cerebral-White-Matter",
    ],
)
def test_whole_head_nuisance_hidden(name):
    assert not default_visible(name)


def test_dedicated_atlas_context_preserves_nucleus_abbreviations():
    assert default_visible("Left-AV", "ThalamicNuclei.v13.T1.mgz")
    assert not default_visible("Background", "ThalamicNuclei.v13.T1.mgz")
