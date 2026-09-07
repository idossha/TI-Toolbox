# Development source of truth

Everything a maintainer or an agent needs to know about *how this software is built and why* lives
in this directory. Nothing here is published to the documentation site (`docs/_config.yml` excludes
it) — the user-facing site is `docs/wiki/`, `docs/installation/`, `docs/gallery/` and friends.

There are no per-lane note files anywhere in the repository. A lane records its **numbers** in
`BENCHMARKS.md` and its **decisions** in `DECISIONS.md`, and deletes its scratch notes. That rule
exists because about 120 lane files accumulated in `dev/notes/` in eleven days, every one of them
citing the others, and no reader could tell which of them was still true.

## The map

| File | What belongs in it |
|---|---|
| `ARCHITECTURE.md` | **How it is built** — the contract. Boundaries, lifetimes, the rules a change must not break. Changing a rule here requires a `DECISIONS.md` entry in the same commit. |
| `DECISIONS.md` | **Why** — append-only. One entry per decision, newest last. |
| `ROADMAP.md` | **What is next**, and the gate table: what was verified, by which command, with what result. |
| `BENCHMARKS.md` | **Every measured number, once.** Sizes, timings, frame rates, test counts. A number quoted anywhere else should be a pointer to here. |
| `HISTORY.md` | **What happened**, one section per program, in date order: the ask, what shipped, which decisions survived and where they are recorded, what was reversed, and the gotchas that exist nowhere else. |
| `DESIGN.md` | The **UI contract** for the desktop app: pages, the rail, layout shapes, tokens, per-page behaviour. |
| `ADR.md` | The numbered architecture decision table the codebase cites as "ADR row N". |
| `RUNBOOK.md` | **How to run things** — the two-level smoke harness, cited by the e2e specs. |
| `RELEASE.md` | **How a version is released** — the version sites, the tag-to-publish pipeline, the dry run, and what only a real CI run can prove. `.github/workflows/release-v3.yml` is its executable form. |
| `requirements/` | **Dated asks**, verbatim from the maintainer. Where two conflict, the later one wins. |
| `SPIKES.md` | Verdicts of investigations whose code was never shipped. |
| `design-notes.md`, `wireframes.md` | The verbatim contract signatures and per-page ASCII layouts `DESIGN.md` defers to instead of restating. |
| `v3-implementation-plan.md` | The 2026-09-05 overview/batch/terminal/viewer plan, kept because `HISTORY.md` cites its lettered requirements. |
| `known-issues-2026-08.md`, `qsi-integration.md`, `qsirecon-internal-reference.md`, `flex-search-multicore-analysis.md` | Backend/pipeline references that predate the v3 program. |

## Where a new fact goes

- A **measurement** → `BENCHMARKS.md`. Not into a commit message, not into a code comment.
- A **decision** → `DECISIONS.md`, in the shape **Decision / Why / Cost / Revisit if**, plus the
  `ARCHITECTURE.md` edit if it changes a rule, in the same commit.
- A **gate result** → the `ROADMAP.md` table, with the command that produced it.
- **What happened in a program** → a section in `HISTORY.md`.
- A **trap that cost someone an hour** → the gotchas of that program's `HISTORY.md` section, or
  `AGENTS.md` if every agent must know it before starting.

## Retired paths

On 2026-09-07, `dev/notes/` and `dev/spikes/` were folded into this directory and deleted; `dev/`
now holds scripts only. Older documents and source comments may still cite the old paths.

| Retired path | Now |
|---|---|
| `dev/notes/v3-program-history.md` | `HISTORY.md` |
| `dev/notes/v3-*-plan.md`, `dev/notes/v3-*/​*.md` (every program plan and lane note) | the matching dated section of `HISTORY.md` |
| `dev/notes/v3-pipelines/RUNBOOK.md` | `RUNBOOK.md` |
| `dev/notes/v3-ui-program/u0-design-notes.md`, `.../wireframes.md` | `design-notes.md`, `wireframes.md` |
| `dev/spikes/README.md` and all spike code | `SPIKES.md` |
| `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/ROADMAP.md`, `docs/BENCHMARKS.md` | this directory |
| `docs/requirements/*` | `requirements/` |
| `desktop/DESIGN.md` | `DESIGN.md` |
| `desktop/IMPLEMENTATION_PLAN.md` | `v3-implementation-plan.md` |
| `tracks/active/v3-electron-gui.md` (gitignored, so never in the repository) | `ADR.md` |
