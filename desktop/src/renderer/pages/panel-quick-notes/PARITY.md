# Quick Notes — parity checklist

Qt source: `tit/gui/extensions/quick_notes.py` (320 lines, `EXTENSION_NAME = "Quick Notes"`).

The Qt version and the v1 contract model notes differently, and the contract wins (R2 — typed
JSON contract, not a UI-invented shape): Qt keeps a **list** of timestamped note blocks in
`derivatives/ti-toolbox/notes.txt`, added one at a time and never edited in place.
`GET|PUT /api/catalog/notes` → `{text, updated_at}` models a **single free-text blob** instead —
closer to a project notepad than a log. This panel follows the contract: one autosaving textarea,
not an append-only list.

- [x] "Notes are saved to: …" info line → replaced with `updated_at` ("Saved just now" / a
      timestamp), since the contract has no path to display and the interesting fact for an
      autosaving field is *when* it last saved, not where.
- [x] "Add Note" (timestamped) → dropped; the contract has no per-entry model. An "Insert
      timestamp" toolbar action gives the same "when did I write this" affordance inside the one
      blob.
- [x] "Clear All Notes" (confirm dialog) → `AlertDialog` "Clear notes" that PUTs `{text: ""}`.
- [x] "Copy All to Clipboard" → "Copy" toolbar action, `navigator.clipboard.writeText`.
- [x] Autosave on change (debounced `PUT`), not a manual save button — matches "GET/PUT
      /api/catalog/notes autosave" in the P8 spec.
- [x] Monospace display font (`FONT_MONOSPACE` in Qt) → `.mono` on the textarea.

## Known gaps

- No per-entry timestamps or history — the contract is a single text blob. If per-entry notes are
  wanted back, that is a schema change for whoever owns `contracts/generated/config.schema.json`/`Notes`, not a
  workaround here.
