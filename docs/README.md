# Documentation (Jekyll + MkDocs)

Two static-site generators, one GitHub Pages deployment.

## Open the docs locally

From the **repository root**:

```bash
bash docs/serve.sh
```

Wait for **Server running**, then open **http://127.0.0.1:4000/**.
Leave the terminal running. Saved documentation changes rebuild automatically; refresh the
browser to see them. Press **Ctrl+C** in that terminal to stop.

The script finds its own directory, selects Homebrew Ruby 3.3 when installed, and installs
missing bundled gems. It serves only on your machine and disables analytics by default.
You can also run `bash serve.sh` from inside `docs/`.

### First-time setup

On macOS, install Ruby once:

```bash
brew install ruby@3.3
bash docs/serve.sh
```

On Linux, install Ruby 3.3+ and Bundler (`gem install bundler`), then run the same script.

### If port 4000 is already in use

Keep the existing server running and use another port:

```bash
bash docs/serve.sh --port 4001
```

Then open **http://127.0.0.1:4001/**. The script never stops another server.
For usage, run `bash docs/serve.sh --help`.

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

The repository currently includes a generated `docs/api/` snapshot for local preview; deployment
regenerates it from the API sources and current `tit` code. Do not edit generated API HTML by hand. GitHub Pages source is set to **GitHub Actions** (not legacy branch-based).

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

## API reference preview (optional)

The main preview includes the existing API pages. To work on the API generator itself,
install `docs/api_mkdocs/requirements.txt` in a Python environment, then run from the repository root:

```bash
python -m mkdocs serve -f docs/api_mkdocs/mkdocs.yml
```

Open the address MkDocs prints (normally http://127.0.0.1:8000/).
