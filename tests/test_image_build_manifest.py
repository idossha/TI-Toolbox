"""The published image must be a plain linux/amd64 manifest, never an OCI index.

Pins: `container/blueprint/build.sh` (the only image build the release procedure uses, see
docs/dev/RELEASING.md) passes `--platform linux/amd64 --provenance=false --sbom=false`. Without
the last two, BuildKit attaches attestations and `docker push` publishes an index; an unpinned
pull of that index on Apple Silicon fails with "no matching manifest for linux/arm64/v8"
(the v3.0.0 re-release, 2026-09-23). Source-reading guard; running the build is out of scope.
"""

from pathlib import Path
import re

BUILD_SH = Path(__file__).resolve().parents[1] / "container/blueprint/build.sh"


def test_build_script_produces_a_plain_amd64_manifest():
    args = re.search(r"^build_args=\((.*?)^\)", BUILD_SH.read_text(), re.M | re.S)
    assert args, "build.sh no longer defines build_args"
    flags = args.group(1).split()
    for flag in ("--provenance=false", "--sbom=false"):
        assert flag in flags
    assert flags[flags.index("--platform") + 1] == "linux/amd64"
