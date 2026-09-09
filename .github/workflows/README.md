# GitHub Actions workflows

The build and release procedure is [docs/dev/RELEASING.md](../../docs/dev/RELEASING.md).

| Workflow | Trigger | What it does |
| --- | --- | --- |
| `release-build.yml` | Stable tag, manual dispatch, or reusable call | `build` exports image and unsigned installers; `internal` additionally pushes only an immutable internal image tag; `release` stages a draft and promotes it only after artifact verification. |
| `deploy-docs.yml` | push to `main` touching `docs/**` | Builds and deploys the Jekyll documentation site. |
| `code-ql-analysis.yml` | push / PR / schedule | CodeQL static analysis. |
| `python-security.yml` | push / PR / schedule | Python dependency and code security scanning. |

The generic build pipeline packages `desktop/` with Node 22.12.0. Internal builds do not
create GitHub Releases, publish updater assets, change public version metadata or move Docker
`latest`. Internal handoffs default to the prepared `internal-*` cohort in both source
image defaults (`docker-compose.yml` and the installed-wheel fallback in `tit/launch.py`).
An explicit differing tag fails: update and commit both defaults first, so main-source loaders
pull the delivered image. Export-only `build` mode may instead use an explicit `internal-*`
tag or default to `internal-<source SHA>`. Existing image tags are rejected.
The image build still requires a compatible published Tetravox embed or a reachable tarball URL
plus SHA256 pin. Local files cannot be used by a hosted runner.

Image tags are immutable, including stable version tags. If a later release job fails after the
image push, rerun only the failed jobs; rerunning the entire workflow will reject the existing
image tag. Recovery that replaces a tag remains a deliberate maintainer action.
