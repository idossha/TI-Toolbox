# Version updates

The procedure of record is [docs/dev/RELEASING.md](../../docs/dev/RELEASING.md).
`update_version.py` separates runtime versioning from public release documentation:

```sh
python3 dev/update/update_version.py --version X.Y.Z-dev.N --development --dry-run
python3 dev/update/update_version.py --version X.Y.Z --dry-run
python3 dev/update/update_version.py --version X.Y.Z --publish-notes --notes-file notes.md --dry-run
```

Remove `--dry-run` after reviewing its proposed files. Development mode updates only
`tit/__init__.py`, `desktop/package.json` and the lockfile root package; it preserves public
metadata and image defaults. Stable mode updates release metadata but does not write release
pages unless both documentation flags are supplied. Existing authored version pages and
changelog entries are preserved. The helper never commits, tags or publishes.

`build_plan.py` validates the generic `release-build.yml` inputs. Every mode uses the reusable
`vX.Y.Z` application image tag; `internal` pushes it without creating a GitHub release.
Compose and the installed-wheel fallback must agree with the runtime version's base image tag.
Stable release mode additionally requires a matching Git tag and consistent public metadata.
Every mode requires agreement among Python runtime, desktop package and both lockfile root
versions. Development builds preserve public metadata. Updating the application version leaves
the separately dated FreeSurfer image unchanged.
`verify_release_assets.py` requires all seven nonempty installer/archive assets while the
GitHub Release is still a draft.
