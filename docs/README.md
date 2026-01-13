# Documentation (Jekyll + MkDocs)

This repository serves documentation using **two static-site generators**:

## Jekyll (main site)

- **Source**: `docs/` (markdown pages like `docs/wiki/*`, `docs/gallery/*`, etc.)
- **Local preview**:
  - `cd docs && bash serve.sh`

GitHub Pages is configured to serve the Jekyll site from the `docs/` folder.

## MkDocs (Python API reference)

- **Source**: `docs/api_mkdocs/`
  - `docs/api_mkdocs/mkdocs.yml`
  - `docs/api_mkdocs/docs/` (markdown pages with `mkdocstrings` directives like `::: tit.core.paths`)
- **Output (committed)**: `docs/api/`
  - This folder contains the generated static HTML/CSS/JS.
  - We commit it so the API docs can be served **without any CI/CD**.
- **Build/update**:

```bash
./docs/build-api.sh
```

## Why `docs/api/` is committed

We keep CI/CD minimal by **not building docs on GitHub Actions**. Instead:

- you run `./docs/build-api.sh` locally
- it generates the API site into `docs/api/`
- GitHub Pages serves it at `/TI-Toolbox/api/` alongside the Jekyll site

## GitHub Pages settings (recommended)

In the GitHub repo settings:
- **Settings → Pages → Source**: “Deploy from a branch”
- **Branch**: `main`
- **Folder**: `/docs`

