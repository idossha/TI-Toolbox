# Project Initialization (`tit/project_init/`)

This package handles new-project scaffolding, the first-time user experience,
and example-data setup for TI-Toolbox.

## Modules

| Module | Responsibility |
|--------|----------------|
| `initializer.py` | BIDS directory scaffolding, metadata files, and **single source of truth** for `project_status.json` |
| `example_data_manager.py` | Copies bundled example subjects (ernie, MNI152) into a new project |

## Ownership of `project_status.json`

All reads and writes to `project_status.json` go through two functions in
`initializer.py`:

```
load_project_status(project_dir)   → dict  (returns {} if file missing; never writes)
update_project_status(project_dir, updates) → bool  (read → deep-merge → write)
```

The file is **created once** by `initialize_project_status()`, which is called
inside `initialize_project_structure()`. It is idempotent — if the file
already exists it is left untouched.

No other module creates or overwrites this file.

## Lifecycle

### 1. Project creation (host → container)

The host-side `loader.py` starts the Docker container and runs an inline
Python snippet:

```
loader.py
  └─ run_project_init_in_container()
       ├─ is_new_project(project_dir)          # checks for markers / data
       │    └─ True → initialize_project_structure(project_dir)
       │         ├─ creates BIDS directories
       │         ├─ writes README, dataset_description.json (per derivative)
       │         ├─ initialize_project_status()   ← CREATES project_status.json
       │         └─ touches .initialized marker
       └─ setup_example_data(toolbox_root, project_dir)
            └─ ExampleDataManager.copy_example_data()
                 ├─ checks is_new_project() (subjects exist? status flag?)
                 ├─ copies NIfTI files into sub-ernie/, sub-MNI152/
                 └─ update_project_status(…, {example_data_copied: True})
```

### 2. UI startup

The desktop app reads the status file (never writes it) to decide whether to
show its welcome screen, and calls `update_project_status()` only to record
preferences such as `user_preferences.show_welcome`.

Key invariant: the UI **never creates** `project_status.json`. If the file
is missing (e.g. manual deletion), the user is treated as new and the
welcome screen is shown, but nothing is written to disk.

## `project_status.json` Schema

```json
{
  "project_created": "2025-01-15T10:30:00",
  "last_updated": "2025-01-15T10:31:00",
  "config_created": true,
  "example_data_copied": true,
  "example_data_timestamp": "2025-01-15T10:30:05+00:00",
  "example_subjects": ["sub-ernie", "sub-MNI152"],
  "user_preferences": {
    "show_welcome": false
  },
  "project_metadata": {
    "name": "my_project",
    "path": "/mnt/my_project",
    "version": "unknown"
  }
}
```

## BIDS Directory Structure

`initialize_project_structure()` creates:

```
project/
├── README
├── dataset_description.json
├── sourcedata/
├── derivatives/
│   ├── ti-toolbox/
│   │   └── dataset_description.json
│   ├── SimNIBS/
│   │   └── dataset_description.json
│   └── freesurfer/
│       └── dataset_description.json
└── code/ti-toolbox/config/
    ├── .initialized
    └── project_status.json
```

## Example Data

For new projects, these subjects are copied automatically:

| Subject | Files |
|---------|-------|
| `sub-ernie` | `sub-ernie_T1w.nii.gz`, `sub-ernie_T2w.nii.gz` |
| `sub-MNI152` | `sub-MNI152_T1w.nii.gz` |

Example data is only copied when:
- No `sub-*` directories exist
- `example_data_copied` is not `true` in the status file
- No user NIfTI files or DICOM data are present

## Design Principles

1. **Create once** — `project_status.json` is written by one function,
   one time, during scaffolding.
2. **Read-or-default** — `load_project_status()` returns `{}` when the file
   is missing; callers handle the empty case gracefully.
3. **Merge-on-write** — `update_project_status()` deep-merges updates so
   nested keys (e.g. `user_preferences.show_welcome`) don't clobber siblings.
4. **UI is read-only** — the desktop app reads status and updates
   preferences but never creates the file from scratch.
