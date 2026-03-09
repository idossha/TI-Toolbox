# Track: Fix CI/CD Pipeline (MkDocs + Codecov)

## Context
Two CI/CD issues need fixing:
1. **MkDocs API docs are not auto-deploying** — GitHub Pages serves from `/docs` on `main` (legacy mode). The MkDocs API docs require manual `build-api.sh` + commit. No automation exists.
2. **Codecov dashboard not updating** — CircleCI runs tests with `--coverage` and attempts upload via `codecov-cli`, but the dashboard shows no updates. Likely causes: wrong `codecovcli` command syntax, missing/misconfigured `CODECOV_TOKEN` in CircleCI env vars, or path issues.

## Root Cause Analysis

### MkDocs
- GitHub Pages: legacy mode, serves `/docs` on `main`
- Jekyll site lives at `docs/` (main site)
- MkDocs API docs build into `docs/api/` via `docs/build-api.sh`
- **No GitHub Actions workflow** triggers the MkDocs build on push to main
- The `gh-pages` branch exists but has stale Sphinx-era content

### Codecov
- CircleCI config (`.circleci/config.yml`) uses `codecovcli do-upload`
- Token referenced as `${CODECOV_TOKEN}` — must be set in CircleCI project env vars
- GitHub secret is named `CODECOV` (not `CODECOV_TOKEN`) — CircleCI uses its own env vars
- Coverage XML generated inside Docker at `/tmp/coverage/coverage.xml`, volume-mounted to host
- Path fix: `sed -i 's|/ti-toolbox/||g'` strips Docker absolute paths — correct approach
- `codecov-cli` package may have API changes; `do-upload` may need `--slug` or other flags

## Phase 1: Fix Codecov Upload in CircleCI

### Files to modify:
- `.circleci/config.yml`

### Changes:
1. Replace `codecovcli do-upload` with the standard `codecovcli upload-process` command (or verify `do-upload` is correct for current version)
2. Add `--slug idossha/TI-toolbox` flag explicitly
3. Add diagnostic echo to print whether coverage.xml exists and its size before upload
4. Pin `codecov-cli` version to avoid future breakage
5. Add `--commit-sha ${CIRCLE_SHA1}` and `--branch ${CIRCLE_BRANCH}` for explicit commit association
6. Verify the upload step runs even if tests fail (`when: always` is already set — good)

### Verification:
- Push a commit and watch CircleCI logs for the upload step
- Check Codecov dashboard for the new upload

## Phase 2: Add GitHub Actions Workflow for MkDocs Auto-Deploy

### Files to create:
- `.github/workflows/deploy-docs.yml`

### Design:
```yaml
name: Deploy API Docs
on:
  push:
    branches: [main]
    paths:
      - 'tit/**'           # Rebuild when source code changes (docstrings)
      - 'docs/api_mkdocs/**'  # Rebuild when docs config changes
  workflow_dispatch: {}     # Manual trigger

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r docs/api_mkdocs/requirements.txt
      - name: Build MkDocs API docs
        run: mkdocs build -f docs/api_mkdocs/mkdocs.yml --clean
      - name: Deploy to docs/api on main
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add docs/api/
          if git diff --staged --quiet; then
            echo "No changes to API docs"
          else
            git commit -m "docs: auto-update API reference"
            git push
          fi
```

### Notes:
- Since GitHub Pages serves from `/docs` on `main`, we commit the built docs back to `main`
- Only triggers when `tit/` source or docs config changes — avoids infinite loops
- The workflow does NOT trigger on changes to `docs/api/` (the output dir) to prevent loops

### Verification:
- Push a docstring change to any `tit/` module
- Confirm GitHub Actions runs and commits updated `docs/api/`
- Confirm the site at https://idossha.github.io/TI-Toolbox/api/ reflects the change

## Phase 3: Quality Gates

### Checklist:
- [ ] CircleCI build passes with coverage upload
- [ ] Codecov dashboard shows new coverage data
- [ ] GitHub Actions workflow triggers on push to main
- [ ] MkDocs API site reflects latest docstrings
- [ ] No infinite commit loops from the docs workflow
- [ ] Clean PR with descriptive commit messages
