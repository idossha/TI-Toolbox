# `contracts/` — the wire contract between `tit.server` and the desktop app

Everything the Electron renderer knows about the server comes from here. TypeScript types are
generated from these files; nothing in `desktop/src` hand-writes a request or response shape.

Architecture: `docs/dev/ARCHITECTURE.md`. Rationale: `docs/dev/DECISIONS.md`.
Change log: [`SCHEMA-CHANGES.md`](SCHEMA-CHANGES.md).

## What each file is

| File | Hand-written or generated | What it is |
|---|---|---|
| `openapi.v1.yaml` | **hand-written** | The contract of record. Every path, method, response code and schema the UI may rely on. A schema carrying `x-tit-config: <ConfigName>` is a placeholder replaced at build time by the generated dataclass schema. |
| `schema.json` | generated — `python3 dev/build_schema.py` | Draft 2020-12 schemas for every config dataclass in `tit.config_io.CONFIG_CLASS_REGISTRY`, plus an `x-tit-classes` name → import-path index. Must be regenerated in the same commit as any dataclass change (`dev/build_schema.py --check` diffs it). |
| `openapi.v1.json` | generated — `python3 dev/build_contract.py` | `openapi.v1.yaml` with `schema.json`'s `$defs` merged in over the `x-tit-config` placeholders. This is what `desktop/`'s `npm run gen:api` feeds to `openapi-typescript`. |
| `openapi.json` | generated — the **running server's own dump** (`GET /api/openapi.json`, or the server's `--dump-openapi`) | Not a copy of `openapi.v1.json`. It is FastAPI's description of the code as it actually is, and the gate checks that it is a *superset* of the contract. Its path parameters are the route functions' own names (`{job_id}`, `{report_id}`), which `dev/contracts_check.py` normalises. |
| `openapi.v0.yaml` | hand-written, **historical** | The Phase-0 walking-skeleton contract. Every path and schema in it is carried unchanged into `openapi.v1.yaml`. Kept because it is still the default first argument of `dev/contracts_check.py`, so the skeleton subset stays gated. Do not add to it. |
| `events.schema.json` | hand-written | The job-event envelope streamed over `/ws/jobs` and `/ws/system`. |
| `pipeline.schema.json` | hand-written | The pipeline-canvas document (`/api/pipelines*`). |
| `tetravox-viewspec-v2.schema.json` | vendored from the Tetravox project | The ViewSpec v2 document `GET /api/view/{kind}` returns and `POST /api/view/open` writes as `<kind>.tetravox.json`. |

## Regenerating

```bash
python3 -m pytest tests/ -q                 # build_schema needs the mocked heavy libs, or the container
python3 dev/build_schema.py                 # -> contracts/schema.json          (--check to diff only)
python3 dev/build_contract.py               # -> contracts/openapi.v1.json
cd desktop && npm run gen:api               # -> src/renderer/api/schema.d.ts
```

`dev/build_schema.py` imports every registered config class, so run it where SimNIBS, `bpy` and
`trimesh` are importable: inside `simnibs_python` in the container, or on the host under `pytest`,
which mocks them. A bare host `python3` cannot import the blender classes.

## The gate

```bash
python3 dev/contracts_check.py              # openapi.v0.yaml ⊆ openapi.json
```

Every `path + method` (with its response codes and parameters) and every `required` property of
the contract must be present in the server's dump; extra paths and properties in the dump are
fine. What the checker deliberately tolerates — path-parameter aliases, `/ws/*` (FastAPI cannot
describe WebSocket routes), implied 401/403/404, untyped `dict[str, Any]` responses — is
documented in `dev/contracts_check.py`'s module docstring.

## The freeze rule

`openapi.v1.yaml` is a frozen interface. Changing a declared path, method, response code, required
property, type or enum is a contract change, and needs, in the **same commit**:

1. the `openapi.v1.yaml` edit,
2. regenerated `schema.json` / `openapi.v1.json` / `schema.d.ts` if a dataclass moved,
3. an appended entry in `SCHEMA-CHANGES.md` (never edit a past entry),
4. a `docs/dev/DECISIONS.md` entry if it changes a rule in `docs/dev/ARCHITECTURE.md`.

Additive changes (a new optional field, a new path) still need 1–3. Deleting or narrowing anything
also needs the renderer callers updated in the same PR — nothing may ship against a shape the
server no longer serves.
