# Help — parity checklist

Qt sources: `tit/gui/help_tab.py` (740 lines), `tit/gui/acknowledgments_tab.py` (145 lines),
`tit/gui/contact_tab.py` (198 lines). Replaces the placeholder `pages/about` (F2's Stage-0
stand-in — `desktop/src/renderer/pages/about/` removed by this change).

## help_tab.py

- [x] "TI-Toolbox Help Center" + intro — **not** ported verbatim: `help_tab.py`'s 740 lines are
      static rich-text (BIDS directory layout, per-tool walkthroughs) that TODO.md §2.9 explicitly
      retires in favor of the bundled docs site (`docs/` rendered into `desktop/resources/docs/`,
      served at `/docs` by `tit.server`). Reproducing that text a second time inside the app would
      immediately drift from the real docs. Instead: a **Docs** tab that iframes `/docs` when the
      bundle is present, falling back to a link list (the published wiki) — the literal ask in
      `dev/notes/v3-build-plan.md`'s P8 row ("offline docs (iframe to /docs if present else
      links)").
- [x] Presence check for `/docs` — `HEAD`-style `fetch("/docs/")`, not a hardcoded assumption.

## acknowledgments_tab.py

- [x] All 12 citation blocks ported verbatim (TI-Toolbox, SimNIBS CHARM, Flex-Search, Grossman et
      al. 2017, FreeSurfer, FSL (3 references), dcm2niix, BIDS, Docker, Gmsh, Blender) — same
      titles, same reference text, same order.
- [x] Closing note ("If you're using TI-Toolbox in academic work, please cite the appropriate
      references above.").

## contact_tab.py

- [x] "Main Developer" card: Name, Email, Affiliation, GitHub — same values.
- [x] "Contribute on GitHub" section: the three items (Discussions, Issues, Pull requests) with
      their descriptions, each an `ExternalLinkButton` instead of a static row (the Qt version has
      no working links at all — `QIcon.fromTheme` glyphs, no `openUrl` calls).
- [x] "Communication Best Practices" — the three bulleted lists (bug reports, feature requests,
      pull requests), same copy.

## New: Cite tab

Not a Qt tab (P8 spec: "Cite (DOI)"). Sources the DOI from the acknowledgments' own first entry
(`https://doi.org/10.1101/2025.10.06.680781`) rather than inventing a second citation string —
full reference text + a "copy citation" button + an external link to the DOI.

## New: Keyboard tab (v3, lane B6)

Not a Qt tab — the PyQt help center had no app-wide shortcut reference, only the NIfTI Viewer's
own "Tips and Shortcuts" section (mouse wheel, right-click-drag, `Ctrl+Wheel`, …), which does not
carry over: that viewer, and the external Freeview/Gmsh flow it half-described, are both gone in
v3 (D3). This tab is new copy, sourced from `dev/notes/v3-ui-program/u0-design-notes.md` §4 (Q5,
confirmed): a `⌘`-number per workflow page in nav order (`⌘1`–`⌘9` today, Overview through Jobs),
`⌘0` Settings, `?` this page, plus `⌘K`, `⌘J`, `⌘⇧I` and `⌘⇧V`. It complements rather than replaces
the `?` overlay (`app/KeyboardSheet.tsx`) — a page you can browse to versus a sheet you need to
already know to open. Both derive the rows from `app/registry.ts`'s `NAV_ORDER`, so adding a rail
row (Pipeline did, in 2026-09) moves the numbers in both places at once.

## New: About tab

- [x] App version (Electron `appVersion()`), platform, mode (Electron/browser) — the client half
      of the retired `pages/about`; the server half (tit/schema/simnibs version, capabilities)
      moved to Settings → "About the server" (P8's own page, not duplicated here).
- [x] "View releases" link (GitHub Releases) in place of an automatic update-check banner — no
      `/api` endpoint exists in the v1 contract to check for updates from the renderer (TODO.md
      §2.9 describes this as a launcher-screen concern fed by the GitHub Releases API from the
      main process, which is P9's surface, not a page under `pages/help`). Reported as a gap.

## Known gaps (reported, not hacked around)

- No update-check endpoint/banner wiring — see About tab note above.
- **Round 2:** the mock server (`tests/mock-server/server.mjs`) now serves a stub `/docs/` page
  (ra_13 finding #16 — the "not served by the mock" note above was stale by this round), so the
  iframe branch is what `help.spec.ts` exercises by default; the fallback (link list) branch is
  now exercised by routing `**/docs/` to a 404 for that one test instead. Both branches are
  E2E-covered against the mock; real-bundle-present behaviour is still also confirmed against
  `tit.server` in Stage 3.
