# Project Initialization (`tit/project_init/`)

This package handles new-project scaffolding and `project_status.json` for
TI-Toolbox. The example subject (`ernie`, with its head model) is
`tit.examples.fetch`, reached through `POST /api/example-data/{sample_id}` — a plain route and a
background thread, never a job, and with no dependency on anything in this package.

## Modules

| Module | Responsibility |
|--------|----------------|
| `initializer.py` | BIDS directory scaffolding, metadata files, and **single source of truth** for `project_status.json` |

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

### 1. Project creation

`POST /api/project/init` submits a `project_init` job
(`simnibs_python -m tit.project_init spec.json`):

```
tit.project_init.__main__
  └─ initialize_project_structure(project_dir)
       ├─ creates BIDS directories
       ├─ writes README, dataset_description.json (per derivative)
       ├─ initialize_project_status()   ← CREATES project_status.json
       └─ touches .initialized marker
       (each step reports itself only when it actually created something; an established
        project prints one line, `Project structure verified: <dir>`)

Example data is a separate path entirely -- no job, no dependency on any of the above:

POST /api/example-data/{sample_id}   (tit.server.routes.example_data, background thread)
  └─ tit.examples.fetch(sample_id, project_dir)
       └─ update_project_status(…, {example_subjects: ["ernie"], …})   ← recording only
```

### 2. UI startup

The desktop app reads the status file through `GET /api/project/status` and
records answers to one-time prompts through `PATCH /api/project/status`
(for example `example_subject_prompted` — the "Add the example subject?"
dialog the Overview page shows once per project). Both go through
`load_project_status` / `update_project_status`; the PATCH creates the file
if it is missing, because an answer that is not persisted is asked again.

## `project_status.json` Schema

```json
{
  "project_created": "2025-01-15T10:30:00",
  "last_updated": "2025-01-15T10:31:00",
  "config_created": true,
  "example_subjects": ["ernie"],
  "example_subject_source": "https://github.com/simnibs/example-dataset/releases/download/v4.1/simnibs4_examples.zip",
  "example_subject_prompted": true,
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

Older projects may still carry `example_data_copied` / `example_data_timestamp`
from the removed bundled-example-data path; they are ignored.

## Design Principles

1. **Create once** — `project_status.json` is written by one function,
   one time, during scaffolding.
2. **Read-or-default** — `load_project_status()` returns `{}` when the file
   is missing; callers handle the empty case gracefully.
3. **Merge-on-write** — `update_project_status()` deep-merges updates so
   nested keys (e.g. `user_preferences.show_welcome`) don't clobber siblings.
4. **UI writes through the API** — the desktop app never touches the file
   itself; it reads and patches it through `/api/project/status`.
