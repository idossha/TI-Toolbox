# GitHub Actions workflows

The build and release procedure is [docs/dev/RELEASING.md](../../docs/dev/RELEASING.md).

| Workflow | Trigger | What it does |
| --- | --- | --- |
| `release-build.yml` | Stable tag, manual dispatch, or reusable call | `build` exports unsigned installers; `release` verifies a manually published image manifest, stages verified executables and promotes the draft only after inventory/checksum verification. Docker build/push is manual. |
| `deploy-docs.yml` | push to `main` or PR touching `docs/**`, `tit/**` or another file that links to the docs | Builds the MkDocs API reference and the Jekyll documentation site, and checks its assets, published files and links; deploys from `main` only. |
| `code-ql-analysis.yml` | push / PR / schedule | CodeQL static analysis. |
| `python-security.yml` | push / PR touching `tit/**`, `tests/**`, `pyproject.toml` or the workflow; weekly schedule; manual dispatch | Bandit scan of `tit/` (high confidence, medium+ severity). The JSON results go to the job summary, not the Security tab (CodeQL covers that), and it runs with `--exit-zero`, so findings never fail the job. |
| `host-paths.yml` | push / PR touching the host-path rules | Runs `tests/test_host_path_table.py` and `desktop/tests/unit/paths.test.ts` on Linux, macOS and Windows runners. |

The generic build pipeline packages `desktop/` with Node 22.12.0. Both modes pin the packaged app to
`idossha/ti-toolbox:vX.Y.Z` from the runtime version (`verify-package.mjs --expect-image-tag`). Rebuilding and pushing replaces
that tag so patch images do not require a new version. Source launchers and the installed-wheel
fallback must agree with it. The source SHA is retained in image labels.

There is no `internal` mode: `build` exports unsigned installers and `release` publishes. No mode
promotes a Docker `latest` tag.
Only `release` on a stable Git tag publishes a GitHub release after artifact verification.
TetraVox is installed separately on the user host; the image build contains no viewer bundle.
