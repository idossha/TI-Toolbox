# v3 overview / batch / terminal / guide / viewer — lane brief (2026-09-05)

Plan of record: `desktop/IMPLEMENTATION_PLAN.md` (R1–R5, gate tests). Read it fully first, then
`desktop/DESIGN.md`, `docs/ARCHITECTURE.md`, `dev/notes/v3-scene-ia-plan.md`, `dev/notes/v3-pipelines/RUNBOOK.md`.

## Rules for every lane
- Work IN THIS worktree (`.claude/worktrees/v3-electron-gui`), branch `feature/v3-electron-gui`. `desktop/` and
  `tit/server/` are untracked WIP: **do not commit, stash, checkout, reset, or revert anything.** Never touch
  files outside your ownership list below; if you must, write the exact change you need into your lane note
  and stop at that boundary.
- Five lanes run concurrently in the same tree. A typecheck/lint/test failure inside another lane's files is
  not yours to fix — note it and move on. Always report the commands you ran and their actual results.
- Desktop: `cd desktop && pnpm run typecheck && pnpm run lint && pnpm run test` (vitest), e2e against the mock
  server: `pnpm run e2e -- <spec>` (offscreen/headless by default — never open windows on the user's screen).
  Python: `python -m pytest tests/ -q -x -k <yours>` from repo root (host pytest works; conftest mocks simnibs).
  Shared dev container `ti-toolbox-fad740e5-tit-1` (port 8765, worktree mounted at /ti-toolbox, `--reload`
  on tit/): a broken import in tit/ takes the server down for everyone — import-guard `dev/route_import_guard.py`.
  Dataset 000 at `/Users/idohaber/datasets/000` (sub-ernie has m2m; sub-101/102 partial).
- Contracts: `contracts/openapi.v1.json|yaml` are the frozen API; a change needs a `contracts/SCHEMA-CHANGES.md`
  line and `pnpm run gen:api` (regenerates `desktop/src/renderer/api/schema.d.ts`). Only edit the contract
  sections named in your lane.
- Architecture records: do NOT edit `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/ROADMAP.md`,
  `tracks/active/v3-electron-gui.md`, or `desktop/DESIGN.md`. Instead put the exact proposed entries
  (intent, contract amendment, decision, roadmap line, DESIGN §9/§10 rewording) in your lane note; the
  consolidation lane lands them.
- Deliverable: your lane note `dev/notes/v3-overview-batch-viewer/<LANE>.md` with: what changed (file list),
  the gate test from the plan and the exact command + output proving it, open items, proposed record entries.
