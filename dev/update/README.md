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

`build_plan.py` validates the generic `release-build.yml` inputs. Internal handoffs use the same prepared
`internal-*` cohort tag in compose and the wheel fallback; an explicit differing tag is
rejected. Export-only builds may use source-SHA tags; stable release mode
requires a matching `vX.Y.Z` tag and consistent package, lock, metadata, compose and installed-wheel fallback versions. Every mode requires agreement among Python runtime, desktop package and both lockfile root versions; development builds preserve public metadata.
`verify_release_assets.py` requires all seven nonempty installer/archive assets while the
GitHub Release is still a draft.
