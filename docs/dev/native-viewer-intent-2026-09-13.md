# Native viewer intent — 2026-09-13

User direction overrides the former embedded-viewer decision in Architecture §7.1.

> Remove the embedded TetraVox related code from the TI toolbox and instead have the TI toolbox install native Tetravox into the TI toolbox directory on the user's machine.

> If there is bloat on the Tetravox side that was created in order to facilitate that embedded behavior, we can remove it such that Tetravox remains lean and native only.

> Report how much code we were able to remove while maintaining professional, tested, verified and robust code. Refer to how we install FastSurfer on the user system.

## R1 — Managed native installation and scene opening

Main installs verified official OS/architecture packages into userData/runtimes and launches the known
executable with a dedicated profile. A single installation consent explains normal user permissions.
There is no administrator install or claim of a sandbox. Unsupported package targets fail explicitly.

Gate: installer tests reject altered download bytes and incomplete installs; installed macOS package
renders a nonempty PNG offscreen; launch failures surface an error rather than success.

## R2 — Preserve scientific controls

Simulator, Optimizer and Analyzer keep their own WebGL controls. TetraVox volume previews open in a
separate window. Existing scenes export a native copy, leaving originals untouched. Shared resources
inside the image are staged safely under the project before host launch.

Gate: hidden scene/navigation/target-preview tests pass; backend exports preserve dataset state,
reject external/symlink paths and correctly stage reference sidecars.

## R3 — Retire embedding in both projects

Delete dedicated embed transport, installer, update, build and runtime paths. Preserve native
TetraVox rendering, scene file loading, CLI and batch jobs. No new live cross-application bridge.

Gate: native TetraVox unit/type/build and hidden desktop checks pass. Report physical source-line
reduction separately from tests/docs/generated files, including new files in the net count.
