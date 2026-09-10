"""Build identity and authored-note regressions; temporary trees never change release metadata."""

import ast
import importlib.util
import os
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "dev/update" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


plan = load("build_plan")
update = load("update_version")
assets = load("verify_release_assets")


class InternalPackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in (
            "desktop",
            "tit",
            "docs/releases",
            "resources/dataset_descriptions",
        ):
            (self.root / folder).mkdir(parents=True)
        self.write("desktop/package.json", '{"version": "3.0.0"}')
        self.write(
            "desktop/package-lock.json",
            '{"version": "3.0.0", "packages": {"": {"version": "3.0.0"}, "node_modules/example": {"version": "8.0.0"}}}',
        )
        self.write("tit/__init__.py", '__version__ = "3.0.0"\n')
        self.write(
            "tit/launch.py",
            'BUILTIN_SPEC = StackSpec(\n    image="idossha/ti-toolbox:${TIT_IMAGE_TAG:-v3.0.0}",\n)\n',
        )
        self.write("version.py", '__version__ = "3.0.0"\n')
        self.write(
            "docker-compose.yml", "image: idossha/ti-toolbox:${TIT_IMAGE_TAG:-v3.0.0}\n"
        )
        self.write(
            "docs/releases/v3.0.0.md",
            "Authored science correction: preserve every word.\n",
        )
        self.sha = "a" * 40

    def write(self, path, content):
        (self.root / path).write_text(content)

    def test_changelog_uses_canonical_dev_path_and_preserves_existing_notes(self):
        path = self.root / "docs/dev/CHANGELOG.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            "---\nlayout: releases\ntitle: Changelog\npermalink: /releases/changelog/\n"
            "---\n\nRelease history.\n\n---\n### v2.5.0\nAuthored old notes.\n"
        )
        old = os.getcwd()
        try:
            os.chdir(self.root)
            update.update_changelog_file("3.0.0", "Authored new notes.", "2026-09-09")
            first = path.read_text()
            update.update_changelog_file(
                "3.0.0", "Must not replace notes.", "2026-09-09"
            )
        finally:
            os.chdir(old)
        self.assertIn("Authored new notes.", first)
        self.assertIn("Authored old notes.", first)
        self.assertEqual(path.read_text(), first)
        self.assertFalse((self.root / "docs/releases/changelog.md").exists())

    def test_release_requires_stable_tag(self):
        for ref in (
            "refs/heads/main",
            "refs/tags/v3.0.0-dev.1",
            "refs/tags/v03.0.0",
            "",
        ):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                plan.build_plan(self.root, "release", ref, self.sha)
        self.assertEqual(
            plan.build_plan(self.root, "release", "refs/tags/v3.0.0", self.sha)[
                "image_tag"
            ],
            "v3.0.0",
        )

    def test_release_refuses_version_drift(self):
        self.write(
            "desktop/package-lock.json",
            '{"version":"2.5.0","packages":{"":{"version":"3.0.0"}}}',
        )
        with self.assertRaises(ValueError):
            plan.build_plan(self.root, "release", "refs/tags/v3.0.0", self.sha)

    def test_every_build_mode_refuses_runtime_or_lock_drift(self):
        original_lock = (self.root / "desktop/package-lock.json").read_text()
        cases = (
            ("tit/__init__.py", '__version__ = "2.5.0"\n'),
            ("desktop/package.json", '{"version":"2.5.0"}'),
            (
                "desktop/package-lock.json",
                '{"version":"2.5.0","packages":{"":{"version":"3.0.0"}}}',
            ),
            (
                "desktop/package-lock.json",
                '{"version":"3.0.0","packages":{"":{"version":"2.5.0"}}}',
            ),
        )
        for mode in ("build", "internal"):
            for path, invalid in cases:
                with self.subTest(mode=mode, path=path, invalid=invalid):
                    self.write("tit/__init__.py", '__version__ = "3.0.0"\n')
                    self.write("desktop/package.json", '{"version":"3.0.0"}')
                    self.write("desktop/package-lock.json", original_lock)
                    self.write(path, invalid)
                    with self.assertRaises(ValueError):
                        plan.build_plan(self.root, mode, "refs/heads/main", self.sha)

    def test_stable_version_updates_wheel_fallback_and_compose_together(self):
        old = os.getcwd()
        try:
            os.chdir(self.root)
            update.update_version("3.1.0")
        finally:
            os.chdir(old)
        # Parse the emitted Python independently; no launcher imports or Docker needed.
        tree = ast.parse((self.root / "tit/launch.py").read_text())
        image = next(
            keyword.value.value
            for keyword in tree.body[0].value.keywords
            if keyword.arg == "image"
        )
        self.assertEqual(image, "idossha/ti-toolbox:${TIT_IMAGE_TAG:-v3.1.0}")
        self.assertEqual(
            (self.root / "docker-compose.yml").read_text().strip(), "image: " + image
        )

    def test_version_update_preserves_dated_freesurfer_image(self):
        self.write(
            "version.py",
            '__version__ = "3.0.0"\nIMAGES = [{"tag": "idossha/ti-toolbox:v3.0.0"}, {"tag": "idossha/ti-toolbox:freesurfer-20260910"}]\n',
        )
        self.write(
            "resources/dataset_descriptions/freesurfer.json",
            '{"Tag": "idossha/ti-toolbox:freesurfer-20260910"}',
        )
        old = os.getcwd()
        try:
            os.chdir(self.root)
            update.update_version("3.1.0")
        finally:
            os.chdir(old)
        self.assertIn(
            "idossha/ti-toolbox:v3.1.0", (self.root / "version.py").read_text()
        )
        self.assertIn(
            "idossha/ti-toolbox:freesurfer-20260910",
            (self.root / "version.py").read_text(),
        )
        self.assertEqual(
            (self.root / "resources/dataset_descriptions/freesurfer.json").read_text(),
            '{"Tag": "idossha/ti-toolbox:freesurfer-20260910"}',
        )

    def test_release_refuses_stale_wheel_fallback(self):
        self.write(
            "tit/launch.py",
            'BUILTIN_SPEC = StackSpec(\n    image="idossha/ti-toolbox:${TIT_IMAGE_TAG:-internal-old}",\n)\n',
        )
        with self.assertRaises(ValueError):
            plan.build_plan(self.root, "release", "refs/tags/v3.0.0", self.sha)

    def test_internal_reuses_version_tag_without_public_metadata_lockstep(self):
        self.write("version.py", '__version__ = "2.5.0"\n')
        for mode in ("internal", "build"):
            for sha in (self.sha, "b" * 40):
                self.assertEqual(
                    plan.build_plan(self.root, mode, "refs/heads/main", sha)[
                        "image_tag"
                    ],
                    "v3.0.0",
                )
            for tag in ("latest", "3.0.0", "internal-old", "v3.1.0", "v3.0.0\nlatest"):
                with self.subTest(mode=mode, tag=tag), self.assertRaises(ValueError):
                    plan.build_plan(self.root, mode, "refs/heads/main", self.sha, tag)

    def test_internal_refuses_different_source_image_defaults(self):
        for compose_tag, wheel_tag in (("3.0.0", "v3.0.0"), ("v3.0.0", "internal-old")):
            with self.subTest(compose=compose_tag, wheel=wheel_tag):
                self.write(
                    "docker-compose.yml",
                    f"image: idossha/ti-toolbox:${{TIT_IMAGE_TAG:-{compose_tag}}}\n",
                )
                self.write(
                    "tit/launch.py",
                    f'BUILTIN_SPEC = StackSpec(\n    image="idossha/ti-toolbox:${{TIT_IMAGE_TAG:-{wheel_tag}}}",\n)\n',
                )
                with self.assertRaisesRegex(ValueError, "defaults must both equal"):
                    plan.build_plan(self.root, "internal", "refs/heads/main", self.sha)

    def test_development_runtime_uses_stable_base_image(self):
        old = os.getcwd()
        try:
            os.chdir(self.root)
            update.update_development_version("3.0.0-dev.2")
        finally:
            os.chdir(old)
        self.assertEqual(
            plan.build_plan(self.root, "internal", "refs/heads/main", self.sha)[
                "image_tag"
            ],
            "v3.0.0",
        )

    def test_packaged_default_is_bound_to_its_build_image(self):
        source = "image: idossha/ti-toolbox:${TIT_IMAGE_TAG:-dev}\n"
        self.assertEqual(
            plan.stage_compose(source, "v3.0.0"),
            "image: idossha/ti-toolbox:${TIT_IMAGE_TAG:-v3.0.0}\n",
        )
        for content in ("", "services: {}", source + source):
            with self.assertRaises(ValueError):
                plan.stage_compose(content, "v3.0.0")

    def test_empty_or_unknown_plan_input_fails(self):
        for mode, sha in (("", self.sha), ("publish", self.sha), ("build", "")):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                plan.build_plan(self.root, mode, "refs/heads/main", sha)

    def test_development_version_preserves_public_metadata_and_dependencies(self):
        before = {
            str(p.relative_to(self.root)): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        # Use real cwd only within this test process; every output is under the temporary fixture.
        import os

        old = os.getcwd()
        try:
            os.chdir(self.root)
            update.update_development_version("3.0.0-dev.1")
        finally:
            os.chdir(old)
        for path in ("version.py", "docker-compose.yml", "docs/releases/v3.0.0.md"):
            self.assertEqual((self.root / path).read_bytes(), before[path])
        lock = json.loads((self.root / "desktop/package-lock.json").read_text())
        self.assertEqual(lock["packages"][""]["version"], "3.0.0-dev.1")
        self.assertEqual(lock["packages"]["node_modules/example"]["version"], "8.0.0")

    def test_authored_release_page_is_never_overwritten(self):
        import os

        old = os.getcwd()
        try:
            os.chdir(self.root)
            before = Path("docs/releases/v3.0.0.md").read_bytes()
            update.create_individual_version_file("3.0.0", "- N/A", "today")
            self.assertEqual(Path("docs/releases/v3.0.0.md").read_bytes(), before)
        finally:
            os.chdir(old)

    def test_asset_inventory_refuses_empty_missing_or_public_release(self):
        names = [
            "TI-Toolbox-3.0.0.dmg",
            "TI-Toolbox-3.0.0-arm64.dmg",
            "TI-Toolbox-3.0.0-mac.zip",
            "TI-Toolbox-3.0.0-arm64-mac.zip",
            "TI-Toolbox-3.0.0.exe",
            "TI-Toolbox-3.0.0.AppImage",
            "ti-toolbox_3.0.0_amd64.deb",
        ]
        release = {
            "isDraft": True,
            "assets": [{"name": name, "size": 5} for name in names],
        }
        assets.verify_assets("3.0.0", release)
        for invalid in (
            {"isDraft": True, "assets": []},
            {**release, "isDraft": False},
            {"isDraft": True, "assets": release["assets"][:-1]},
        ):
            with self.assertRaises(ValueError):
                assets.verify_assets("3.0.0", invalid)
        release["assets"][0]["size"] = 0
        with self.assertRaises(ValueError):
            assets.verify_assets("3.0.0", release)


if __name__ == "__main__":
    unittest.main()
