# GitHub Actions workflows

The build and release procedure is [docs/dev/RELEASING.md](../../docs/dev/RELEASING.md).

| Workflow | Trigger | What it does |
| --- | --- | --- |
| `release-build.yml` | Stable tag, manual dispatch, or reusable call | `build` exports image and unsigned installers; `internal` additionally pushes the mutable version image; `release` stages a draft and promotes it only after artifact verification. |
| `deploy-docs.yml` | push to `main` touching `docs/**` | Builds and deploys the Jekyll documentation site. |
| `code-ql-analysis.yml` | push / PR / schedule | CodeQL static analysis. |
| `python-security.yml` | push / PR / schedule | Python dependency and code security scanning. |

The generic build pipeline packages `desktop/` with Node 22.12.0. All modes build
`idossha/ti-toolbox:vX.Y.Z` from the runtime version. Rebuilding and pushing replaces
that tag so patch images do not require a new version. Source launchers and the installed-wheel
fallback must agree with it. The source SHA is retained in image labels.

`internal` is an unsigned delivery mode: it does not create GitHub Releases, publish updater
assets, or change public version metadata. No mode promotes a Docker `latest` tag.
Only `release` on a stable Git tag publishes a GitHub release after artifact verification.
The image build requires a compatible published Tetravox embed or a reachable tarball URL
plus SHA256 pin. Local files cannot be used by a hosted runner.
