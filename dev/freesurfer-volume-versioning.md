# FreeSurfer volume versioning

## Problem

The FreeSurfer install (`/usr/local/freesurfer/`) is shared into the simnibs
container through a Docker named volume. Docker only seeds a volume from the
image **once**, when the volume is first created empty. The volume had a fixed
name (`ti-toolbox_freesurfer_data`), so once a user created it, it was never
refreshed — even after pulling a newer freesurfer image. Users who installed
before the image gained the MATLAB runtime (MCR) kept an MCR-less volume, which
broke `segmentThalamicNuclei.sh` / `segmentHA_T1.sh` (GitHub issue #123).

## Fix

1. **Version the volume name by the freesurfer image tag**
   (`ti-toolbox_freesurfer_data_v7.4.1`). Bumping the image bumps the name, so a
   new empty volume is created and re-seeded from the new image.
2. **Make the volume compose-managed (not `external`)** so `docker compose up`
   creates and seeds it automatically — no launcher pre-step, and a raw
   `docker compose up` works too.
3. **Launchers derive the name** from the compose image tag, pass it as
   `FREESURFER_VOLUME`, and prune stale older-version volumes (best-effort).

`docker compose down` keeps the volume; only `down -v` removes it.

## Files changed

| File | Change |
|------|--------|
| `docker-compose.yml` | `freesurfer_data` volume: drop `external`, `name: ${FREESURFER_VOLUME:-ti-toolbox_freesurfer_data_v7.4.1}` |
| `package/docker/docker-compose.yml` | same |
| `dev/loader/docker-compose.dev.yml` | same |
| `loader.py` | `get_freesurfer_volume_name()` + `prune_old_freesurfer_volumes()`; set `FREESURFER_VOLUME`; removed manual volume create |
| `dev/loader/loader_dev.py` | same |
| `package/src/backend/docker-manager.js` | `computeFreesurferVolume()` + `pruneOldVolumes()`; inject `FREESURFER_VOLUME`; removed `ensureVolume()` |

## When bumping the FreeSurfer image

Update the freesurfer `image:` tag **and** the matching `${FREESURFER_VOLUME:-...}`
default in all three compose files. The launchers read the tag automatically; the
default only matters for a bare `docker compose up`.

## Existing users (one-time)

Their old `ti-toolbox_freesurfer_data` volume is replaced automatically on next
launch (new versioned volume is seeded fresh; the launcher prunes the old one).
A manual reset also works:

```bash
docker rm -f simnibs_container freesurfer_container
docker volume rm ti-toolbox_freesurfer_data
```
