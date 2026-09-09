"""Image pairing on attach: synthetic Docker inspect replies, no live Docker (2026-09-09).

Run ``python3 -m pytest tests/test_launch_image.py -q``. Config.Image is authored input;
the expected outcome is refusal without mutation, or reuse of the matching container.
"""

from unittest.mock import Mock

import pytest

from tit import launch


@pytest.fixture
def running(monkeypatch):
    container = {
        "Name": "/existing",
        "State": {"Running": True},
        "Image": "sha256:" + "a" * 64,
        "Config": {"Image": "idossha/ti-toolbox:internal-fixture"},
    }
    monkeypatch.setattr(launch, "require_docker", lambda: None)
    monkeypatch.setattr(launch, "resolve_project", lambda _: "/fixture/project")
    monkeypatch.setattr(launch, "find_container", lambda _: container)
    monkeypatch.setattr(
        launch, "default_image", lambda: "idossha/ti-toolbox:internal-fixture"
    )
    monkeypatch.setattr(
        launch,
        "container_credentials",
        lambda _: ("http://localhost:8765", "fixture-token"),
    )
    monkeypatch.setattr(launch, "wait_for_health", lambda *a, **k: None)
    mutations = Mock(side_effect=AssertionError("attach must not mutate Docker"))
    monkeypatch.setattr(launch, "_docker", mutations)
    monkeypatch.setattr(launch, "ensure_image", mutations)
    return container, mutations


@pytest.mark.parametrize("explicit", [None, "idossha/ti-toolbox:internal-fixture"])
def test_matching_configured_reference_attaches_despite_content_id(running, explicit):
    _, mutations = running
    assert launch.start(
        launch.LaunchOptions(
            project="/fixture/project", image=explicit, echo=lambda _: None
        )
    ) == ("http://localhost:8765", "fixture-token")
    mutations.assert_not_called()


@pytest.mark.parametrize("explicit", [None, "idossha/ti-toolbox:internal-new"])
def test_old_container_refused_for_default_or_explicit_image(running, explicit):
    container, mutations = running
    container["Config"]["Image"] = "idossha/ti-toolbox:internal-old"
    with pytest.raises(launch.LaunchError, match="Wait for its jobs to finish.*--stop"):
        launch.start(launch.LaunchOptions(project="/fixture/project", image=explicit))
    mutations.assert_not_called()


def test_exact_digest_reference_is_supported(running):
    container, _ = running
    digest = "idossha/ti-toolbox@sha256:" + "b" * 64
    container["Config"]["Image"] = digest
    assert (
        launch.start(
            launch.LaunchOptions(
                project="/fixture/project", image=digest, echo=lambda _: None
            )
        )[0]
        == "http://localhost:8765"
    )


def test_unknown_configured_reference_fails_closed(running):
    container, mutations = running
    container["Config"] = {}
    with pytest.raises(launch.LaunchError, match="uses \\(unknown\\)"):
        launch.start(launch.LaunchOptions(project="/fixture/project"))
    mutations.assert_not_called()
