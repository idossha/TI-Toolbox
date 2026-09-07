# Level A pipeline smoke harness

`docs/dev/HISTORY.md § 2026-09-03 (pipelines program)` §3, decisions **P4–P8**. One HTTP test per pipeline kind,
run against a live `tit.server` and a real BIDS project.

## Run it

```bash
dev/smoke.sh                     # the whole matrix against the running dev container
dev/smoke.sh sim analyzer_mesh   # one or more rows (row id, or a kind -> all its rows)
dev/smoke.sh --keep              # keep everything the run created, for inspection
dev/smoke.sh --full              # run the long kinds to completion instead of cancelling
```

`dev/smoke.sh` finds the container by its labels (`tit.stack=ti-toolbox-v3`,
`tit.service=tit`) and reads the published port, `TIT_SERVER_TOKEN` and the host project
directory out of `docker inspect`. **No token is ever typed, pasted or written to disk.** Its
exit codes are `0` green, `1` a row failed, `2` could not check (no container, no token, no
`python3`) — a `2` is never a pass.

Under pytest directly:

```bash
TIT_SMOKE_SERVER_URL=http://127.0.0.1:8765 \
TIT_SMOKE_TOKEN=<token> \
TIT_SMOKE_PROJECT_HOST=/Users/you/datasets/000 \
python3 -m pytest -m smoke tests/smoke -p no:cacheprovider
```

## Why it never runs by accident

Two independent mechanisms, because they prevent different failures:

| Mechanism | Where | Prevents |
|---|---|---|
| Marker `smoke` deselected by default (`addopts = … -m "not smoke"`) | `pytest.ini` | the 35 s host suite silently becoming a 40-minute one; `-m smoke` overrides it (last `-m` wins) |
| Env gate on `TIT_SMOKE_SERVER_URL` + `TIT_SMOKE_TOKEN`, skip with a printed reason | `conftest.py` | a flag alone reaching a real dataset, or a wall of connection errors on a machine with no container |

`tests/smoke/test_harness_selftest.py` is deliberately **not** marked `smoke`: it is ~30 ms of
ordinary unit tests over the matrix, the cleanup manifest and the payload loader, so a broken
harness is red in `python3 -m pytest -q` before anyone starts a container.

## The behaviour contract (P4)

| Behaviour | What is asserted | Budget |
|---|---|---|
| `accepted` | `POST /api/validate/{kind}` ok, `POST /api/plan/{kind}` ≥ 1 job and **no** lock conflicts, `POST /api/jobs` (or `/api/jobs/groups` for `pre`) → 201 | ≤ 10 s |
| `started` | the job leaves `queued` and its log **or** its events carry the runner's own banner / first stage event | ≤ 120 s |
| `completed` | `succeeded` inside the row's budget; every artifact the job reports exists on disk **and** the server's own `/api/files/artifact` serves it; every claimed output directory is non-empty; the matching catalog route lists it | per row |
| `cancelled` | after a cancel: state `cancelled` and **no** process in `GET /api/system` whose command line still names the job id | ≤ 15 s |
| `refused` | the job `failed` with a human-readable message, **no** Python traceback in `error.message`, and a refusal sentence in the runner's own output | per row |

Artifact existence is read by two different readers — the host filesystem through the bind
mount and the server's jailed file route — so neither reader is checked against itself
(`agentic-rules` principle 9).

## Namespacing and cleanup (P6)

Every row names its outputs `smoke-<runid>-<suffix>`. Before a job is submitted, each path the
row may create is **claimed**, and the claim records whether the path already existed. At the
end of the session, `Manifest.remove_created()` deletes **only** the claims that did not
pre-exist; a pre-existing path is left alone and reported. The manifest is written to
`tests/smoke/artifacts/manifest-<utc>-<runid>.json` on every run, `--keep` or not.

A row's `accepted` leg additionally asserts that the plan reports `exists: false` for every
output — a namespacing typo fails the test instead of overwriting data. `m2m_101`,
`m2m_ernie` and `m2m_MNI152` are never written by any row.

## One heavy job at a time (P7)

Before a heavy row (FEM class: `sim`, `flex`, `leadfield`, `source`, `blender`, charm,
FastSurfer) or any `completed` row, the test waits for `GET /api/jobs` to show nothing
running or queued — other lanes and the maintainer share this container, and two emulated FEM
solves fight for the same cores until both time out.

## Files

```
matrix.py                one Row per kind of §3: subject + why, config builder, behaviour,
                         budget, banner, claimed paths, catalog check
client.py                stdlib-urllib HTTP client (bearer auth: cookies are CSRF-checked)
cleanup.py               the created-path manifest
conftest.py              the env gate, the session fixtures, --smoke-kinds/--smoke-keep/--smoke-full
test_kinds.py            one parametrized test per row + the payload loader
test_harness_selftest.py the harness's own unit tests (not marked smoke)
payloads/                lane S2's recorded UI request bodies; replayed in preference to the
                         built-in config (see payloads/README.md)
artifacts/               per-run manifests (git-ignored output of a run)
```

## Where the configs come from

Not invented. Every row mirrors either one of the maintainer's own succeeded job specs
(`code/ti-toolbox/jobs/<id>/spec.json`), a run config the pipeline itself wrote
(`ex-search/*/run_config.json`, `Simulations/*/documentation/config.json`), or the field list of
the matching dataclass in `contracts/generated/config.schema.json`. Where lane S2 has recorded the UI's exact
`POST` body under `payloads/`, that wins — the `source` column of the results table says which
one ran.
