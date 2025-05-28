# Temporal Interference Toolbox Documentation Website

This directory contains the source files for the Temporal Interference Toolbox documentation website, built with Jekyll and hosted on GitHub Pages..

## Local Development

### Prerequisites

- Ruby 2.7 or higher
- Bundler gem

### Setup

1. Navigate to the docs directory:
   ```bash
   cd docs
   ```

2. Install dependencies:
   ```bash
   bundle install
   ```

3. Run the local server:
   ```bash
   bundle exec jekyll serve
   ```

4. Open http://localhost:4000/TI-Toolbox/ in your browser

### Live Reload

For development with live reload:
```bash
bundle exec jekyll serve --livereload
```

## Structure

- `_config.yml` - Jekyll configuration
- `index.md` - Home page
- `downloads.md` - Downloads page
- `documentation.md` - Main documentation
- `releases.md` - Release history
- `wiki.md` - Wiki index
- `about.md` - About page
- `_wiki/` - Wiki articles
- `assets/css/` - Custom styles
- `assets/images/` - Images and graphics
- `assets/js/` - JavaScript files

## Deployment

The site is automatically deployed to GitHub Pages when changes are pushed to the main branch. 

### Manual Deployment

To build the site manually:
```bash
bundle exec jekyll build
```

The built site will be in the `_site` directory.

## Customization

### Changing Theme Colors

Edit the color variables in `assets/css/style.scss`:
```scss
$primary-color: #2E86AB;
$secondary-color: #A23B72;
```

### Adding New Pages

1. Create a new markdown file in the root directory
2. Add front matter:
   ```yaml
   ---
   layout: page
   title: Your Page Title
   permalink: /your-page-url/
   ---
   ```
3. Add it to navigation in `_config.yml`

### Adding Wiki Articles

1. Create a new markdown file in `_wiki/`
2. Use the wiki layout:
   ```yaml
   ---
   layout: wiki
   title: Article Title
   permalink: /wiki/article-name/
   ---
   ```

## Important Notes

- **Do not edit** files in `_site/` - they are auto-generated
- Test locally before pushing changes
- Keep URLs consistent with existing structure
- Update download links when new releases are published

## GitHub Pages Configuration

To enable GitHub Pages:

1. Go to repository Settings
2. Navigate to Pages section
3. Set Source to "Deploy from a branch"
4. Choose branch: `main` and folder: `/docs`
5. Save changes

The site will be available at: `https://idossha.github.io/TI-Toolbox/`

## Troubleshooting

### Build Errors

If you encounter build errors:
```bash
bundle update
bundle exec jekyll doctor
```

### Permission Issues

On macOS/Linux, you might need to use:
```bash
bundle install --path vendor/bundle
```

## Contributing

See the main repository's CONTRIBUTING.md for guidelines on contributing to the documentation. 