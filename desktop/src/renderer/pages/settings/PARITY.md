# Settings — parity checklist

Qt source: `tit/gui/settings_menu.py` (204 lines). Unlike every other v3 page, this one has **no**
one-to-one Qt tab to port: the Qt gear menu only opens Help/Contact/Acknowledgments and a single
"Usage Statistics: Enabled/Disabled" toggle. Everything else on this screen (project, appearance,
feature panels, unsafe overrides, Jupyter, server info) is new surface named directly by
`docs/dev/HISTORY.md § 2026-08-27 (v3 build program)`'s P8 row and `TODO.md` §2.9 — there is nothing to harvest beyond the
telemetry toggle, so this checklist tracks the v3 spec instead of a Qt diff.

## Qt gear menu (settings_menu.py) — items absorbed elsewhere

- [x] "Usage Statistics: ✓ Enabled / ✗ Disabled" toggle (`toggle_privacy`, `tit.telemetry.is_enabled/set_enabled`) → Settings **Telemetry** card.
- [x] "Help" menu item → moved to the **Help** page (`pages/help`), not Settings.
- [x] "Contact" menu item → Help page, Contact tab.
- [x] "Acknowledgments" menu item → Help page, Acknowledgments tab.
- [x] Extensions button / `ExtensionsTab` card list (`tit/gui/extensions.py`) — "Add Tab" per
      extension → Settings **Feature panels** checklist (`settings.panels`, `PUT /api/settings`).

## New surface (TODO.md §2.2, §2.9, §2.8; `Settings` schema in `contracts/openapi.yaml`)

- [x] Project card: container path, host path (Electron-only, read-only), name (read-only —
      no `PUT /api/project` in the v1 contract to rename a project; reported as a gap).
- [x] Project card: image tag override (`settings.image_tag`, nullable — empty = use the image's
      default tag) with help text explaining what pinning does.
- [x] Telemetry card: one Switch ("Send anonymous usage data") with the privacy sentence as its
      help text (design QA finding #14 — two controls, consent checkbox + enabled switch, read
      as one intent and one desynced from the other in testing). Toggling it sets both
      `telemetry.consented` and `telemetry.enabled` together; the schema still carries them
      separately (mirrors `tit/telemetry.py`'s consent-gates-sending model server-side), but the
      Qt source (`toggle_privacy`) only ever exposed one control too, so this is closer parity,
      not a regression.
- [x] Appearance card: system/light/dark radio, applies immediately via `app/theme/store.ts`
      (already deterministic — DESIGN.md §7) and is included in the next `PUT /api/settings` so
      the preference round-trips to the server's `Settings.theme`.
- [x] Feature panels card: one checkbox per optional panel (`source`, `cluster-permutation`,
      `nifti-group-average`, `nilearn-visuals`, `quick-notes` — the `Settings.panels` names, minus
      `subject-info`, whose page R1 deleted: everything it showed is the Overview page's matrix,
      and the app must not offer a second, worse answer to the same question. The server still
      *accepts* the id (`tit/server/routes/settings.py`'s `_VALID_PANELS`), so an existing
      `settings.json` that lists it keeps loading; no page claims it, so it is simply ignored),
      each with its one-line description from the Qt extension's `EXTENSION_DESCRIPTION`.
- [x] "Allow unsafe overrides" toggle (`settings.allow_unsafe_overrides`) with a warning callout
      explaining the effect (lets a job be queued despite non-critical `/api/validate` findings).
- [x] Jupyter card: capability-gated on `capabilities.jupyter`; **no "start Jupyter" endpoint
      exists in the v1 contract** (only the boolean capability flag) — shown as a status line with
      the gap called out in the report, not a fabricated button.
- [x] "About the server" card: `tit_version`, `server_api`, `schema_hash`, `python`, `simnibs`,
      `capabilities` (version/capability half of the retired `pages/about`; the app/update-check
      half moved to Help → About).
- [x] Single "Save changes" action, disabled while the form matches the last-loaded/saved
      settings; toast + (when the panel list changed) a reload so the nav rail — a static read of
      `PageDef.enabled` per `app/registry.ts` — picks up the new panel set. See
      `pages/panels/_shared.ts` for why a reload is needed and the gap this leaves for F2.

- [x] **Viewer engine card** (`TetravoxCard.tsx`, no Qt ancestor at all): the active embed
      bundle's version, protocol and source, the protocol range this build can host, what the
      server's own background check last found, an automatic-updates switch and a "Check now"
      button. It reaches no network itself — it renders what the server already knows, which is
      what keeps rendering Settings from spending one of GitHub's 60 unauthenticated requests per
      hour. (V3 briefly replaced this with a `ViewerCard` describing a host-installed desktop app;
      the maintainer reversed that on 2026-09-06 and the card is this one again.)

## Known gaps (reported, not hacked around)

- No `PUT`/rename endpoint for `Project.name` — shown read-only.
- No Jupyter start/stop endpoint — capability status only.
- `app/registry.ts`/`app/NavRail.tsx` (F2-owned) read `PageDef.enabled` once at module-graph load;
  toggling a panel takes effect on the next full reload, which Settings triggers itself after a
  successful Save. A live settings store fed into `enabledPages`/`navGroups` would remove that.
