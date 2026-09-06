# Maintainer requirements — 2026-09-04

These are hard gates for the v3 tab and visualization polishing pass. Hidden Electron tests use the
mock project and synthetic scenes, with exact state/identity comparisons and measured control
geometry. The real Tetravox embed supplies rendering evidence. These requirements refine
[ARCHITECTURE.md](../ARCHITECTURE.md) §§2–4 and desktop/DESIGN.md §§4.4.2 and 10; where an earlier
plan conflicts, these requirements win and the contract is amended with the implementation.

## Asks, verbatim

1. "users can interact with the pre-processing tab, jump to the simulator tab, make changes, go back to the pre-processing, and everything will be the same."
2. "they could look at the visualizer, move to a different tab and when they're back in the visualizer everything will be the same. This is highly highly important and is a non-negotiable."
3. "there is no clear design philosophy in terms of the button layouts, the different drop downs the subject selection and so on."
4. "we only require the 3D visualization panel. Also, the two sliders that we had earlier for the skin and the gray matter were removed and they were actually good to have. So please bring them back."
5. "once you are done with all update make sure to consolidate such that you and i can test it with pnpm run dev"

## R1 — Return to the exact workflow and viewer state

Retain visited pages through navigation like the production QTabWidget. Draft inputs, selected
subjects, rows, section expansion, nested tabs, scroll, viewer camera, layers and iframe identity
remain intact. Editing another tab must not change a hidden page's subject or view. Explicit
destination links still select the requested result. A project change disposes the old session.

* Gate test: hidden `page-memory.spec.ts` and scene-pane tests modify the mock project, visit other
  workflow tabs, and return; values and iframe nodes compare exactly, scroll uses the existing
  subpixel tolerance, and inactive commands/controls cannot act on the current page.

## R2 — Apply one control grammar across workflows

Subject selection precedes parameters; primary actions occupy the shared action bar. Shared tokens
and primitives govern labels, buttons, dropdowns, checkboxes and sliders. Long labels and blocked
reasons remain readable, with no horizontal overflow or offscreen dropdown options.

* Gate test: shared-control unit and hidden UI tests assert accessible names, keyboard operation,
  computed control dimensions and containment at the existing 1280 × 800 and 1440 × 900 design
  sizes, in both themes; token contrast keeps the existing exact thresholds.

## R3 — Show a focused 3D preview and restore surface opacity

Run-page previews contain the 3D viewport, its essential orientation cues, two surface-opacity
sliders and the interaction hint. The dedicated Viewer keeps its broader controls. Skin and grey
matter each accept 0–100%, mapped exactly to the corresponding live layer; cortical labels use
the grey-matter control. Opacity edits and tab navigation preserve the camera and form selection.

* Gate test: `scene-pane.spec.ts` asserts exact live layer opacity and retained controls on the mock
  protocol. A hidden real-embed rendering test asserts toolbar/panels absent, canvas fills the
  preview, opaque surfaces draw, and zero-opacity surfaces reveal the configured background;
  pixel bounds use the renderer's existing quantization tolerance.

The earlier embed migration required "Mount only the visible pane and tear it down on unmount"
to release its WASM heap. That choice loses camera and layer state on every navigation; R1 explicitly
overrides it. Workers are retained for visited tabs and released at the project/session boundary.

## R4 — One consolidated development checkout

Land the scoped work and the viewport-capable renderer in the existing v3 development environment,
preserving the maintainer's pre-existing edits and runtime configuration. From its `desktop/`
directory, `pnpm run dev` must attach the project stack, start Vite and open the connected app.

* Gate test: run that exact command with an isolated profile and the app's offscreen switch, verify
  the live project connection and retained viewport/sliders, and stop only the smoke-test app.
