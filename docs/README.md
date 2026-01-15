# Documentation (Jekyll + MkDocs)

This repository serves documentation using **two static-site generators**:

## Jekyll (main site)

- **Source**: `docs/` (markdown pages like `docs/wiki/*`, `docs/gallery/*`, etc.)
- **Local preview**:
  - `cd docs && bash serve.sh`

GitHub Pages is configured to serve the Jekyll site from the `docs/` folder.

### Development Setup

The documentation server uses **Ruby 3.3** for compatibility with modern macOS versions (including macOS 15/Sequoia). The `serve.sh` script automatically detects and uses the correct Ruby installation.

#### macOS (Recommended)

```bash
# Install Ruby 3.3 via Homebrew
brew install ruby@3.3

# The serve.sh script will automatically use this Ruby version
cd docs && bash serve.sh
```

#### Other Systems

For Linux/Windows or systems requiring different Ruby configurations:

1. **Install Ruby 3.3+** via your system's package manager (apt, yum, etc.) or use a version manager like `rbenv` or `rvm`
2. **Install Bundler**: `gem install bundler`
3. **Install dependencies**: `cd docs && bundle install`
4. **Run server**: `cd docs && bundle exec jekyll serve`

**Note**: The `serve.sh` script is designed to work across different systems. If you have a custom Ruby setup, you may need to modify the script's `PATH` configuration or run Jekyll commands directly.

#### Troubleshooting

- **Port 4000 already in use**: The script automatically kills existing Jekyll processes
- **Ruby version conflicts**: Check that Ruby 3.3+ is in your PATH
- **Missing gems**: Run `cd docs && bundle install` manually

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

