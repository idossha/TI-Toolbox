# Subject Info Viewer — parity checklist

Qt source: `tit/gui/extensions/subject_info_viewer.py` (454 lines, `EXTENSION_NAME = "Subject Info
Viewer"`). Contract: `GET /api/subjects/{id}/info` → `SubjectInfo` — the server now does the
directory walking that `scan_subjects()` and `get_detailed_subject_info()` did in the GUI process.

The Qt dialog did two things at once: a project-wide presence grid, and a per-subject JSON dump
behind "Export Selected Subjects". v3 splits them, and the split is the point — the grid is the
**Overview** page (DESIGN.md §9: a second project-wide answer that can disagree with the first is
worse than none), and the per-subject inventory, which nothing in v3 had, is this page.

- [x] Project-wide status table (Subject ID, Raw Data, FreeSurfer, SimNIBS, Simulations,
      Flex-Search, Analysis) → **Overview**, plus this page's `SubjectsField` list, whose readiness
      chips (`raw`/`fastsurfer`/`freesurfer`/`m2m`/`dwi`/`ct`) are the same vocabulary every other
      page's subject list uses rather than a seventh table.
- [x] `get_detailed_subject_info()`'s `sourcedata_files` / `anat_files` → the "Source data" and
      "Anatomical files" tables, with sizes the Qt version did not show (a 0-byte T1 is a state a
      name alone cannot express). `anat_modalities` (T1w/T2w/CT) is derived server-side.
- [x] `m2m_dirs` → the "m2m directories" row of the summary.
- [x] `simulation_dirs` → the Simulations table, one row per simulation, with TI/mTI presence and
      mesh count — the Qt version had a bare count.
- [x] `flex_search {count, dirs}` → "Flex-search" chips; ex-search and mEx-search are listed too
      (the Qt extension predates both).
- [x] `analysis {count, by_simulation}` → per-simulation `Analyses` cell (count, names in its
      tooltip) plus the summary's total, instead of a nested dict printed as JSON.
- [x] `fastsurfer_complete` → the `fastsurfer` chip.
- [x] "Refresh" → `refetch()` on the query (the error Callout's Retry); the list itself is
      React Query's, so switching subjects re-reads without a button.
- [x] "Export Selected Subjects" (timestamped JSON under
      `derivatives/ti-toolbox/subjects-viewer/`) → "Export JSON", which downloads the exact body
      the server returned. Deliberately **not** written into the project: the Qt version buried a
      snapshot in the derivatives tree where nothing ever read it again, and a download is what the
      user was going to do with it anyway.
- [x] "Project Directory" line → dropped; the project is Settings ▸ Project, and it is a property
      of the connection, not of a subject.

## Known gaps

- No multi-subject export. The Qt version exported a dict of selected subjects; `SubjectsField`'s
  `single` mode is what makes this page honest about reading one subject, and one JSON per subject
  is the same information. If batch export is wanted it is a page-level action over the list, not a
  change to this contract.
- Free-hand sets and reports are listed by name only — opening them is the Simulator's and the
  Results page's job, and a second route into them from here would be a third place to maintain.
