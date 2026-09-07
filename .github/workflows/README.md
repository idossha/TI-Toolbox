# GitHub Actions workflows

| Workflow | Trigger | What it does |
| --- | --- | --- |
| `release-v3.yml` | `v*.*.*` tag push, or `workflow_dispatch` | The release pipeline: image build/push, unsigned per-platform validation, GitHub Release, signed publish. |
| `deploy-docs.yml` | push to `main` touching `docs/**` | Builds and deploys the Jekyll documentation site. |
| `code-ql-analysis.yml` | push / PR / schedule | CodeQL static analysis. |
| `python-security.yml` | push / PR / schedule | Python dependency and code security scanning. |

The release procedure — what to change before tagging, how to dry-run, what each job proves, and
what only a real run can prove — is **[docs/dev/RELEASE.md](../../docs/dev/RELEASE.md)**. That is
the document of record; this table only says which files exist.

`release-build.yml` and `release_bk.yml` were deleted in the v3 release work. They built the
legacy launcher under `package/` (pinned at v2.4.0) with Node 20, so a v3 tag would have published
v2 artifacts under a v3 release title. `release-v3.yml` builds `desktop/` with Node 22 and refuses
to run when the tag and the version sites in the tree disagree.
