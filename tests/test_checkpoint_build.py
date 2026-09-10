"""Checkpoint cache regressions (2026-09-09): Python tar writer, system tar reader.

Payload bytes are authored ASCII, not model-derived expectations. Run with
``python3 -m unittest discover -s tests -p test_checkpoint_build.py -v``.
Image builds and real FastSurfer execution remain separate integration checks.
"""

import hashlib
import io
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILES = tuple(
    f"aparc_vinn_{plane}_v2.0.0.pkl" for plane in ("axial", "coronal", "sagittal")
)


class CheckpointBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.archive = self.root / "fixture.tgz"
        self.home = self.root / "fastsurfer"
        self.env = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "FASTSURFER_HOME": str(self.home),
            "FASTSURFER_CHECKPOINTS_TGZ": "https://fixture.invalid/weights.tgz",
            "FIXTURE_ARCHIVE": str(self.archive),
            "DOWNLOADER_CALLED": str(self.root / "downloader-called"),
        }
        self.executable(
            "curl",
            'while [ "$1" != "-o" ]; do shift; done\ncp "$FIXTURE_ARCHIVE" "$2"\n',
        )
        self.executable(
            "simnibs_python", 'printf "%s\\n" "$@" > "$DOWNLOADER_CALLED"\n'
        )

    def executable(self, name, body):
        script = self.bin / name
        script.write_text("#!/bin/sh\nset -eu\n" + body)
        script.chmod(0o755)

    def pack(self, names=FILES):
        with tarfile.open(self.archive, "w:gz") as archive:
            for name in names:
                data = ("fixture:" + name).encode()
                member = tarfile.TarInfo(name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        self.env["FASTSURFER_CHECKPOINTS_SHA256"] = hashlib.sha256(
            self.archive.read_bytes()
        ).hexdigest()

    def install(self):
        text = (ROOT / "container/blueprint/Dockerfile.ti-toolbox").read_text()
        start = text.index('RUN if [ -n "$FASTSURFER_CHECKPOINTS_TGZ" ]')
        shell = text[start + 4 : text.index("\n\n", start)].replace("\\\n", " ")
        # The container's fixed scratch file is mapped to this test's private directory.
        shell = shell.replace(
            "/tmp/fastsurfer-checkpoints.tgz", str(self.root / "download.tgz")
        )
        return subprocess.run(
            ["sh", "-c", shell], env=self.env, text=True, capture_output=True
        )

    def test_valid_archive_installs_exact_files_and_records_digest(self):
        self.pack((*FILES, "unrequested.txt"))
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in FILES:
            self.assertEqual(
                (self.home / "checkpoints" / name).read_text(), "fixture:" + name
            )
        self.assertFalse((self.home / "checkpoints/unrequested.txt").exists())
        self.assertEqual(
            (self.home / "checkpoints/cache-archive.sha256").read_text().strip(),
            self.env["FASTSURFER_CHECKPOINTS_SHA256"],
        )
        self.assertFalse((self.root / "downloader-called").exists())

    def test_wrong_digest_fails_before_any_checkpoint_is_extracted(self):
        self.pack()
        self.env["FASTSURFER_CHECKPOINTS_SHA256"] = "0" * 64
        self.assertNotEqual(self.install().returncode, 0)
        self.assertFalse((self.home / "checkpoints").exists())

    def test_missing_checkpoint_fails(self):
        self.pack(FILES[:2])
        self.assertNotEqual(self.install().returncode, 0)

    def test_default_calls_the_existing_official_downloader(self):
        self.env.update(FASTSURFER_CHECKPOINTS_TGZ="", FASTSURFER_CHECKPOINTS_SHA256="")
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.root / "downloader-called").read_text().splitlines(),
            [str(self.home / "FastSurferCNN/download_checkpoints.py"), "--vinn"],
        )

    def test_orphan_digest_is_rejected_even_for_direct_docker_build(self):
        self.env.update(
            FASTSURFER_CHECKPOINTS_TGZ="", FASTSURFER_CHECKPOINTS_SHA256="0" * 64
        )
        self.assertNotEqual(self.install().returncode, 0)
        self.assertFalse((self.root / "downloader-called").exists())

    def test_builder_rejects_incomplete_or_invalid_cache_pair_before_docker(self):
        self.executable("docker", "echo unexpected-docker >&2\nexit 99\n")
        for args in (
            ["--fastsurfer-checkpoints-tgz", "https://fixture.invalid/weights.tgz"],
            ["--fastsurfer-checkpoints-sha256", "0" * 64],
            [
                "--fastsurfer-checkpoints-tgz",
                "file:///weights.tgz",
                "--fastsurfer-checkpoints-sha256",
                "0" * 64,
            ],
        ):
            with self.subTest(args=args):
                result = subprocess.run(
                    ["bash", str(ROOT / "container/blueprint/build.sh"), *args],
                    env=self.env,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotIn("unexpected-docker", result.stderr)


if __name__ == "__main__":
    unittest.main()
