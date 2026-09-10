# `contracts/` — the wire contract between `tit.server` and the desktop app

Everything the Electron renderer knows about the server comes from here. TypeScript types are
generated from these files; nothing in `desktop/src` hand-writes a request or response shape.

Architecture: `docs/dev/ARCHITECTURE.md`. Rationale: `docs/dev/DECISIONS.md`.
Change log: [`CHANGES.md`](CHANGES.md).

## Layout

```
contracts/
  openapi.yaml                      ← the only hand-written API contract
  events.schema.json                ← hand-written
  pipeline.schema.json              ← hand-written
  tetravox-viewspec-v2.schema.json  ← hand-written, host-facing
  generated/                        ← never hand-edited
    openapi.json                    ← openapi.yaml + the config dataclass schemas
    config.schema.json              ← the config dataclass schemas
  README.md · CHANGES.md
```

| File | What it is |
|---|---|
| `openapi.yaml` | **The contract of record.** Every path, method, response code and schema the UI may rely on. A schema carrying `x-tit-config: <ConfigName>` is a placeholder replaced at build time by the generated dataclass schema. |
| `events.schema.json` | The job-event envelope streamed over `/ws/jobs` and `/ws/system`. One line of `<job>/events.jsonl` is one `Event`. |
| `pipeline.schema.json` | The pipeline-canvas document (`/api/pipelines*`). |
| `tetravox-viewspec-v2.schema.json` | The ViewSpec v2 document `GET /api/view/{kind}` returns and `POST /api/view/open` writes as `<kind>.tetravox.json`. Documents a subset of Tetravox's own engine-owned type; **its name is load-bearing** — it is the file's public `$id` — so it keeps the `-v2` spelling rather than following the naming of the files around it. |
| `generated/config.schema.json` | Draft 2020-12 schemas for every config dataclass in `tit.config_io.CONFIG_CLASS_REGISTRY`, plus an `x-tit-classes` name → import-path index. |
| `generated/openapi.json` | `openapi.yaml` with `config.schema.json`'s `$defs` merged in over the `x-tit-config` placeholders. This is what `openapi-typescript` reads. |

## The rule

**Edit the sources. Never edit `generated/`. The gate diffs it.**

`generated/` and `desktop/src/renderer/api/schema.d.ts` are build outputs. If you change a config
dataclass or `openapi.yaml`, regenerate and commit the result in the same commit — the gate
regenerates in a temp dir and fails on any byte of difference.

## Regenerating — one command

```bash
cd desktop && npm run gen
```

That runs `python3 dev/build_contracts.py` (which runs `dev/build_schema.py` then
`dev/build_contract.py`) and then `openapi-typescript`, producing exactly three files:

| Output | From |
|---|---|
| `contracts/generated/config.schema.json` | the `tit` config dataclasses |
| `contracts/generated/openapi.json` | `contracts/openapi.yaml` + the above |
| `desktop/src/renderer/api/schema.d.ts` | `contracts/generated/openapi.json` |

Without Node, `python3 dev/build_contracts.py` regenerates the two Python outputs on their own.

`dev/build_schema.py` imports every registered config class, so it needs SimNIBS, `bpy` and
`trimesh`. Inside the container they are real; on a host they are absent, and
`dev/build_contracts.py` installs the same mocks the test suite uses
(`tests/conftest.py`'s `pytest_configure`, the single source of truth for that list). So
`npm run gen` works on a plain host checkout as well as in the container.

Regeneration is idempotent: running it twice produces byte-identical output.

## The gate

```bash
python3 dev/contracts_check.py
```

Two checks, in order:

1. **No drift.** Regenerates everything above into a temp dir and compares byte for byte against
   what is committed. Fails with "run `npm run gen`" on any difference. (`schema.d.ts` is skipped,
   loudly, when `desktop/node_modules` is not installed.)
2. **Live coverage.** Builds the FastAPI app in-process, takes its own OpenAPI document — the same
   object `--dump-openapi` writes and `GET /api/openapi.json` serves — and checks it covers
   `openapi.yaml`. There is no committed dump to go stale.

Every `path + method` (with its response codes and parameters) and every `required` property of
the contract must be present in the live document; extra paths and properties are fine. What the
checker deliberately tolerates, and the open findings it carries in `_KNOWN_FINDINGS`, are
documented in `dev/contracts_check.py`'s module docstring. A finding listed there that stops
occurring also fails the gate, so the list cannot rot.

## Versioning

The contract's version is `info.version` **inside `openapi.yaml`** — not a filename. Bump it when
the document's shape changes; there is no `openapi.v2.yaml`, and history lives in `CHANGES.md` and
in git.

`info.version` is the contract's own version. The live server's `/api/version.tit_version` is the
installed `tit` package version and will normally differ — that is expected, not drift.

## The freeze rule

`openapi.yaml` is a frozen interface. Changing a declared path, method, response code, required
property, type or enum is a contract change, and needs, in the **same commit**:

1. the `openapi.yaml` edit,
2. regenerated `generated/` + `schema.d.ts` (`npm run gen`),
3. an appended entry in `CHANGES.md` (never edit a past entry),
4. a `docs/dev/DECISIONS.md` entry if it changes a rule in `docs/dev/ARCHITECTURE.md`.

Additive changes (a new optional field, a new path) still need 1–3. Deleting or narrowing anything
also needs the renderer callers updated in the same PR — nothing may ship against a shape the
server no longer serves.
