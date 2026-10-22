# Roadmap

Priorities and completion criteria live here; [RELEASING.md](RELEASING.md) owns the release
procedure and [TESTING.md](TESTING.md) owns validation strategy and gaps. Remove completed
work; retain consequential rationale in [DECISIONS.md](DECISIONS.md).

v3.1.1 (2026-10-20) is the current release; its application image is `idossha/ti-toolbox:v3.1.1`
([release notes](../releases/v3.1.1.md)). The current checkout is available for manual testing
through the standard development loader. The table lists acceptance work still open for the next
release.

| Open acceptance work | Completion criterion |
|---|---|
| Manual workflow testing | Colleagues exercise representative copied projects and report output/result behavior |
| Rebuild the distribution candidate | Bake current source and renderer; verify the separately installed native TetraVox package and record immutable identities |
| Clean image and loader acceptance | Test without checkout mounts; verify Python/Bash launchers, packaged cross-project Attach/Recreate, project switching and Electron close-stop on each supported host |
| Hosted review | Run CI/security review on the actual candidate head; older results do not cover later fixes |
| Platform and publication checks | Verify intended platforms, macOS signing/notarization and registry access before public promotion |
| Native viewer lifecycle | Complete automatic setup and TI-owned updates: TetraVox 0.6.2 (2026-09-23) carries the managed update handshake; run the packaged macOS arm64/x64, Windows x64 and Linux x64 (Wayland and X11) install-update-foreground matrix in ARCHITECTURE §7.1 — Settings Update and the in-TetraVox popup on each leg (only macOS arm64 has been checked, from a branch build) |

Distribution candidates are rebuilt from the repository Dockerfile. Source-mounted testing does
not establish what a published image contains. Current verification evidence and its limits
belong in [TESTING.md](TESTING.md).

### Product follow-ups

These are scoped improvements, not blanket blockers for a release. Recheck the relevant
source before scheduling them; remove a row when it ships.

| Area | Follow-up |
|---|---|
| Optimizer | Ex symmetric-bucket controls; consistent naming for Flex `output_folder` and Ex `run_name`; mixed-kind group submission; prove interrupted candidate recording remains parseable and complete; validate full optimization → candidate → preview → simulation → analysis provenance, including cancellation, retry and all-invalid histories |
| Analyzer | Expose Python multi-sphere ROI union in the config and UI |
| Jobs | Running-job ETA and bulk retry; current elapsed time and single-job Rerun remain available |
| Notebooks | Detect outdated seeded examples without overwriting user edits; variable explorer and interactive plots |
| Viewer | TetraVox 0.6.0 (2026-09-20) released PR #44's [generic scene API](../../dev/upstream/tetravox-live-scene/README.md); validate edited native snapshot/reopen, existing-file refusal, unchanged originals and macOS minimized/no-window activation. A TetraVox older than 0.6.0 cannot save live scenes through TI. |
| Test harness | Avoid tracked smoke-payload churn while preserving UI/HTTP replay equivalence |
| CI | Put the mock e2e suite back on every `main` push: `desktop-e2e-mock` is opt-in (`run_e2e_mock`) until it is sharded, has its fonts and its five Linux-only spec failures are fixed ([TESTING.md](TESTING.md)) |
| Maintenance | Assess OpenSSF practices and extend integration coverage for selected colleague workflows |

For older implementation plans and retired TODO references, see [DECISIONS.md](DECISIONS.md).

### Native Apple GPU preprocessing

Managed installation, project-session consent and sandboxed FastSurfer execution are implemented for local Apple Silicon desktop sessions. Keep native execution opt-in while collecting cross-machine installation and segmentation-quality evidence. Linux/Windows GPU workers and browser-only native host integration are outside this increment.
