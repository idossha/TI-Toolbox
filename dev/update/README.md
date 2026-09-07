# `dev/update/` — the version bump

One script, `update_version.py`. It rewrites every place a version number is written — `version.py`,
`tit/__init__.py`, `desktop/package.json`, the image tag default in
`desktop/docker/docker-compose.v3.yml`, the docs — and writes the release pages under
`docs/releases/`, so a tag and the artifacts built from it agree.

```bash
python dev/update/update_version.py --version X.Y.Z --dry-run   # read the list first
python dev/update/update_version.py --version X.Y.Z             # then write
```

`--dry-run` prints every file that *would* change and touches nothing, which is how you check the
script has been taught about a newly added version site without dirtying the tree.

**The release procedure of record is [`docs/dev/RELEASE.md`](../../docs/dev/RELEASE.md)** — what to
change before tagging, how to dry-run the pipeline, what each job of
`.github/workflows/release-v3.yml` proves and what only a real run can prove. Do not follow a
release recipe from anywhere else.
