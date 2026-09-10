# Roadmap

Priorities and completion criteria live here; [RELEASING.md](RELEASING.md) owns the release
procedure and [TESTING.md](TESTING.md) owns validation strategy and gaps. Remove completed
work; retain consequential rationale in [DECISIONS.md](DECISIONS.md).

Status reviewed 2026-09-09. Candidate branch: `release/3.0.0`.
The current checkout is available for manual testing through the standard development loader.
The internal image is published on Docker Hub; manual acceptance continues. No stable tag or public release is implied.

| Remaining acceptance work | Completion criterion |
|---|---|
| Manual workflow testing | Colleagues exercise representative copied projects and report output/result behavior |
| Rebuild the distribution candidate | Bake current source, renderer and compatible Tetravox embed; record immutable identities |
| Clean image and loader acceptance | Test without checkout mounts; verify Python/Bash launchers, packaged cross-project Attach/Recreate, project switching and Electron close-stop on each supported host |
| Hosted review | Run CI/security review on the actual candidate head; older results do not cover later fixes |
| Platform and publication checks | Verify intended platforms, macOS signing/notarization and registry access before public promotion |
| Viewer update delivery | Verify compatible published Tetravox assets and update/rollback through the real release index |

Distribution candidates are rebuilt from the repository Dockerfile. Source-mounted testing does
not establish what a published image contains. Current verification evidence and its limits
belong in [TESTING.md](TESTING.md).

### Product follow-ups

These are scoped improvements, not blanket blockers for internal testing. Recheck the relevant
source before scheduling them; remove a row when it ships.

| Area | Follow-up |
|---|---|
| Optimizer | Ex symmetric-bucket controls; consistent naming for Flex `output_folder` and Ex `run_name`; mixed-kind group submission |
| Analyzer | Expose Python multi-sphere ROI union in the config and UI |
| Jobs | Running-job ETA and bulk retry; current elapsed time and single-job Rerun remain available |
| Pipelines | Restore saved configs into forms; replace JSON-only editors where useful; notebook import round trip |
| Notebooks | Detect outdated seeded examples without overwriting user edits; variable explorer and interactive plots |
| Viewer | Decide whether unused per-layer overrides need a client; assess reference-scene marker visibility |
| Test harness | Avoid tracked smoke-payload churn while preserving UI/HTTP replay equivalence |
| Maintenance | Assess OpenSSF practices and extend integration coverage for selected colleague workflows |

For older implementation plans and retired TODO references, see [DECISIONS.md](DECISIONS.md).
