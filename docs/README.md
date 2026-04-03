# Documentation (Jekyll + MkDocs)

Two static-site generators, one GitHub Pages deployment.

## Architecture

| Component | Source | URL |
|-----------|--------|-----|
| **Jekyll** (project site) | `docs/` (wiki, gallery, installation, etc.) | `idossha.github.io/TI-Toolbox/` |
| **MkDocs** (API reference) | `docs/api_mkdocs/` | `idossha.github.io/TI-Toolbox/api/` |

## How Deployment Works

GitHub Actions (`.github/workflows/deploy-docs.yml`) runs on every push to `main` that touches `tit/` or `docs/`:

1. **Build MkDocs** API docs → outputs to `docs/api/`
2. **Build Jekyll** site from `docs/` (which now includes the fresh API docs)
3. **Deploy** the combined artifact to GitHub Pages via `actions/deploy-pages`

No build artifacts are committed to the repo. GitHub Pages source is set to **GitHub Actions** (not legacy branch-based).

## Local Preview

**Jekyll** (main site):
```bash
cd docs && bash serve.sh
```

**MkDocs** (API reference):
```bash
pip install -r docs/api_mkdocs/requirements.txt
mkdocs serve -f docs/api_mkdocs/mkdocs.yml
```

### Jekyll Setup (macOS)

```bash
brew install ruby@3.3
cd docs && bundle install && bash serve.sh
```

For other systems: install Ruby 3.3+, then `gem install bundler && bundle install`.
