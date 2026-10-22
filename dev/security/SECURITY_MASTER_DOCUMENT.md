# TI-Toolbox security notes

The security policy and how to report a vulnerability are in [SECURITY.md](../../SECURITY.md).
This file holds the server's path sanitizer contract, which `docs/dev/ARCHITECTURE.md` and
`tit/paths.py` cite. The v2.x Bandit audit that used to fill this file described the deleted PyQt5
tree and its retired test commands; it remains in the repository history.

## The path sanitizer contract (v3)

*Current as of 2026-09-18 (docs/dev/DECISIONS.md ADR 33).*

The server binds loopback with a per-session token and the project directory is the only
mounted host path (`docs/dev/ARCHITECTURE.md`), so the filesystem threat is a request that
names a path outside the project — a traversal in a subject id, a simulation name, a notebook
name, a layer path in a viewer body — or a symlink planted inside it. The defence is three
functions in `tit/paths.py`, each written in the one shape CodeQL's `py/path-injection` query
recognises as a barrier (normalise, then `startswith` on *that value* in the true branch), so the
code-scanning alert list is a real signal and not a list to be suppressed.

| Function | What it checks | Where it is applied |
|---|---|---|
| `validate_subject_id(sid)` | `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$` | every `PathManager` accessor that places `sub-<id>`; `tit.server.schemas.SubjectId` on every request field naming a subject |
| `validate_name(value, what)` | `NAME_RE = ^[A-Za-z0-9_-][A-Za-z0-9._ -]{0,127}$`, no `..` — a dot inside (`GSN-HydroCel-185.csv`, `MNI_Glasser_HCP_v1.0`), an inner space (v2 legacy run/net names), never a leading dot, separator, NUL, tab or newline | `PathManager.simulation`, `*_search_run`, `stats_output`, `bids_datatype`, `sourcedata_dicom`; `tit.server.schemas.EntityName` on request fields naming a simulation, run, atlas, EEG net, ROI, montage, analysis or stats type |
| `resolve_under(root, *parts)` | lexical: `normpath(join(root, *parts))` starts with `root/`; refuses `..`, an absolute part, the root itself; no filesystem access, symlinks not followed | every `PathManager.<accessor>` (`self._under`); `tit.viewspec` simulation-derived paths; `tit.pre.utils._find_nifti` |
| `resolve_within(jail, path)` | physical: `realpath(path)` starts with `realpath(jail)/`; returns the resolved path so what is checked is what is opened | `tit.catalog._jailed`, `tit.scene.build.source_path`, `tit.sim.montage_sources._source_path`, `tit.mesh_identity`, `tit.opt.candidate_catalog._safe`, `tit.jobs.eta`, `tit.viewspec._analysis_cursor` |
| `resolve_leaf_within(jail, path)` | as above, but resolves only the parent and keeps the leaf's own name, checking both the entry and the leaf's target — for `replace`/`unlink`, so an alias is replaced and never the file behind it | `tit.jobs.registry._storage_path`, `tit.server.notebooks._checked_notebook_entry`, `tit.server.routes.viewers.checked_viewer_path` |

Rules that follow from the table:

1. **Validate at the boundary, contain at the join, resolve at the I/O.** A request field is
   typed `Annotated[SubjectId, Query()]` / `Annotated[EntityName, Query()]` (a bare
   `x: SubjectId = Query(...)` makes FastAPI drop the validator — `tests/test_request_name_validation.py`
   proves the 422). `PathManager` joins through `resolve_under`. The function that opens,
   lists, stats or writes calls `resolve_within`/`resolve_leaf_within` and uses **the returned
   value**, not the string it passed in.
2. **Boolean helpers do not clear taint.** `is_within`, `_project_paths_safe` and
   `Path.resolve().is_relative_to` are fine for a question; a read that follows must go
   through a returning form. `resolved == root or resolved.startswith(...)` is not recognised:
   handle the equality separately, then `startswith`.
3. **A mutated request document is still the request document.** Build a new dict
   (`{**layer, "path": jailed}`) from checked values; assigning into the incoming one leaves
   it tainted, and rightly so.
4. **Nothing is suppressed.** No `# lgtm`, `# noqa`, or CodeQL path exclusions. If the scanner
   is wrong, the shape of the code is changed until it is right, and the change is a real check.
5. **Proof is local.** `brew install codeql`, then
   `codeql database create /tmp/tit-db --language=python --source-root .` and
   `codeql database analyze /tmp/tit-db codeql/python-queries:Security/CWE-022/PathInjection.ql codeql/python-queries:Security/CWE-730/PolynomialReDoS.ql --format=sarif-latest --output=/tmp/tit.sarif --download`;
   count `results[].ruleId`. 2026-09-18: 178 `py/path-injection` + 1 `py/polynomial-redos` → 0 + 0.

Regexes over request input avoid nested or ambiguous quantifiers; the mask-upload filename is a
character-set walk (`tit/server/routes/files.py::_is_simple_mask_filename`), with a 100 000-dot
adversarial input timed in `tests/test_mask_upload.py`.
