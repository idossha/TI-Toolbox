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

## Site Theme

The Jekyll site uses its own theme (no minima layouts/CSS):

| Piece | Where |
|-------|-------|
| Section sidebars (Installation / Wiki / Releases / Gallery) | `docs/_data/nav.yml` — add a page there and it appears in the sidebar |
| Top navbar links | `header_pages` in `docs/_config.yml` |
| Three-column docs layout | `docs/_includes/docs.html` (sidebar / article / "On this page") |
| All styling | `docs/assets/css/style.scss` — colours and widths are CSS variables at the top |
| Behaviour | `docs/assets/js/site.js` (mobile menus), `toc.js` (on-this-page) |

Content pages keep `layout: wiki|installation|releases|gallery` in their front matter; those layouts are one-liners that include `docs.html` with the matching nav key.

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
