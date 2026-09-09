# Help — parity checklist

Qt sources: `tit/gui/help_tab.py` (740 lines), `tit/gui/acknowledgments_tab.py` (145 lines),
`tit/gui/contact_tab.py` (198 lines). Replaces the placeholder `pages/about` (F2's Stage-0
stand-in — `desktop/src/renderer/pages/about/` removed by this change).

## help_tab.py

- [x] "TI-Toolbox Help Center" + intro — **not** ported verbatim: `help_tab.py`'s 740 lines are
      static rich-text (BIDS directory layout, per-tool walkthroughs) that TODO.md §2.9 explicitly
      retires in favor of the documentation site. Reproducing that text a second time inside the
      app would immediately drift from the real docs. Instead: a **Docs** tab that frames the
      published documentation website, <https://idossha.github.io/TI-Toolbox/> (the `url` +
      `baseurl` of `docs/_config.yml`, pinned by `tests/unit/help-docs.test.ts`), with an explicit
      "Open in browser" button (`shell.openExternal` through the preload bridge) and an offline
      fallback card carrying the same links.
- [x] **Never the app's own origin.** The earlier version probed and framed the same-origin path
      `/docs/`, expecting a bundled offline docs copy. `tit.server`'s static route is an SPA
      catch-all (`tit/server/static.py`: only `api`/`ws`/`auth`/`tetravox` are reserved), so
      `/docs/` answers 200 with the app's own `index.html` — the presence check always passed and
      the tab rendered TI-Toolbox inside TI-Toolbox (verified on the dev container: `GET /docs/`
      → the app's index). No offline docs bundle is shipped in the image, so there is nothing to
      fall back to locally and no markdown renderer was added. `help.spec.ts` now asserts the
      iframe's origin differs from the app origin and that the framed document has no
      `[data-nav-id]` rail.
- [x] Reachability probe — `no-cors` `fetch(DOCS_SITE)` with a 5s abort; on failure the tab shows
      one sentence plus the links, never a broken frame.
- [x] CSP — `tit/server/app.py` grants `frame-src`/`connect-src` exactly
      `https://idossha.github.io` (nothing else in the app talks to an outside origin);
      `tests/test_server_skeleton.py::test_csp_header_is_exactly_the_todo_string` pins the string.
      Electron needs no extra allowance: the renderer inherits that server CSP and the main
      process installs no header rewriting of its own.

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
v3 (D3). This tab is new copy, sourced from `docs/dev/ARCHITECTURE.md` §9 (Q5,
confirmed): a `⌘`-number per workflow page in nav order (`⌘0`–`⌘9` today, Overview through Jobs — the
rail counts from zero so ten digits cover ten rows), `⌘,` Settings, `?` this page, plus `⌘K`, `⌘J`,
`⌘⇧I` and `⌘⇧V`. It complements rather than replaces
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
- **Round 3 (2026-09):** the mock server's `/docs/` stub is gone with the code that probed it —
  it existed only to make that presence check pass, and its divergence from the real server (an
  HTML stub vs. the SPA catch-all) is what hid this bug from E2E. Both Docs branches (site framed
  / offline card) are now covered against the mock by routing the docs origin.
- **Round 2:** the mock server (`tests/mock-server/server.mjs`) now serves a stub `/docs/` page
  (ra_13 finding #16 — the "not served by the mock" note above was stale by this round), so the
  iframe branch is what `help.spec.ts` exercises by default; the fallback (link list) branch is
  now exercised by routing `**/docs/` to a 404 for that one test instead. Both branches are
  E2E-covered against the mock; real-bundle-present behaviour is still also confirmed against
  `tit.server` in Stage 3.
