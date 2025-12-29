# TI-Toolbox Documentation Development

This README explains how to set up and run the TI-Toolbox documentation website locally for development and testing.

## Prerequisites

- **Ruby** (version 2.6+ recommended)
- **Bundler** gem
- **Git** (for version control)

### Check Your Ruby Version
```bash
ruby --version
```

## Quick Start

### 1. Navigate to Documentation Directory
```bash
cd docs/
```

### 2. Install Dependencies (First Time Only)
```bash
bundle install
```

### 3. Start Development Server
You have two options:

**Option A: Use the provided script (recommended)**
```bash
./serve.sh
```

**Option B: Manual command**
```bash
bundle exec jekyll serve --livereload --host=127.0.0.1 --port=4000
```

### 4. Access Your Site
Once the server starts successfully, open your browser to:
- **Local URL**: http://127.0.0.1:4000/TI-Toolbox/
- **Wiki Section**: http://127.0.0.1:4000/TI-Toolbox/wiki/

## Features

### Live Reload
The server includes `--livereload` which means:
- ✅ Automatic browser refresh when you save markdown files
- ✅ CSS changes appear instantly
- ✅ No need to manually refresh

### What to Test
- **Sidebar navigation** - Click between different wiki guides
- **Responsive design** - Resize browser window to test mobile view
- **Images** - Verify all images load correctly with proper sizing
- **Asset paths** - Ensure all links and resources work

## Troubleshooting

### Common Issues

#### 1. Ruby Compatibility Issues
**Problem**: `LoadError: cannot load such file -- ffi_c` or similar native extension errors

**Solution**: The project uses a simplified Gemfile that avoids problematic native extensions. If you still encounter issues:

```bash
# Clean everything and reinstall
rm -rf Gemfile.lock vendor/ .bundle/
bundle install
```

#### 2. Bundle Command Not Found
**Problem**: `command not found: bundle`

**Solution**: Install Bundler
```bash
gem install bundler
```

#### 3. Permission Issues
**Problem**: Gem installation requires sudo/admin access

**Solution**: Install gems locally
```bash
bundle config set --local path 'vendor/bundle'
bundle install
```

#### 4. Port Already in Use
**Problem**: `Address already in use - bind(2) for "127.0.0.1" port 4000`

**Solution**: Kill existing Jekyll process
```bash
# Find and kill Jekyll process
lsof -ti:4000 | xargs kill
# Then restart
./serve.sh
```

#### 5. Site Not Loading
**Problem**: Server starts but site doesn't load

**Solutions**:
- Wait 10-30 seconds for full startup
- Check terminal for build errors
- Try accessing http://localhost:4000/TI-Toolbox/ instead
- Clear browser cache

## Site Architecture

### Visual Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        JEKYLL BUILD                             │
│                                                                 │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │  Markdown   │ ──▶ │   Layouts   │ ──▶ │    HTML     │       │
│  │   Files     │     │  (default)  │     │   Output    │       │
│  └─────────────┘     └─────────────┘     └─────────────┘       │
│                             │                                   │
│                             ▼                                   │
│                      ┌─────────────┐                           │
│                      │  style.scss │ ──▶ style.css             │
│                      │  (unified)  │                           │
│                      └─────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
```

### Layout Hierarchy

```
_layouts/default.html          ◀── Base template (includes head.html, header.html)
       │
       ├── _layouts/home.html      ◀── Index page (page-layout)
       ├── _layouts/about.html     ◀── About page (page-layout)
       ├── _layouts/wiki.html      ◀── Wiki pages (wiki-layout + sidebar)
       ├── _layouts/installation.html
       ├── _layouts/gallery.html
       └── _layouts/releases.html
```

### Stylesheet Flow

```
┌──────────────────────────────────────────────────────────────┐
│                    assets/css/style.scss                      │
├──────────────────────────────────────────────────────────────┤
│  1. @import "minima"     ──▶  Base Jekyll theme styles       │
│  2. Variables            ──▶  $primary-color, $dark-bg, etc  │
│  3. Wrapper styles       ──▶  max-width: 1050px (all pages)  │
│  4. Header styles        ──▶  Flexbox nav + search           │
│  5. Page layouts         ──▶  .page-layout, .wiki-layout     │
│  6. Components           ──▶  .hero, .features, .carousel    │
│  7. Wiki styles          ──▶  Sidebar, content, images       │
│  8. Carousel styles      ──▶  Image slider component         │
│  9. Responsive           ──▶  Mobile breakpoints             │
└──────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Aspect | Choice | Reason |
|--------|--------|--------|
| **Single CSS file** | `style.scss` only | Reduced complexity, no conflicts |
| **Unified width** | 1050px max-width | Consistent reading experience |
| **Custom layouts** | home, page, wiki | Override minima defaults |
| **Flexbox header** | `display: flex` | Search box inline with nav |

### Developer Protocol

1. **Edit styles** → Only modify `assets/css/style.scss`
2. **Add pages** → Create `.md` file with appropriate `layout:` frontmatter
3. **Test locally** → `./serve.sh` then check http://127.0.0.1:4000/TI-Toolbox/
4. **Build** → `bundle exec jekyll build`
5. **Deploy** → Push to main branch (GitHub Pages auto-deploys)

## File Structure

```
docs/
├── _config.yml          # Jekyll configuration
├── _includes/
│   ├── head.html        # <head> with single style.css link
│   └── header.html      # Navigation + search box
├── _layouts/
│   ├── default.html     # Base layout (all pages inherit)
│   ├── home.html        # Index page layout
│   ├── about.html       # About/simple pages
│   ├── wiki.html        # Wiki with sidebar
│   ├── installation.html
│   ├── gallery.html
│   └── releases.html
├── assets/
│   └── css/
│       └── style.scss   # SINGLE unified stylesheet
├── wiki/                # Wiki documentation
├── installation/        # Installation guides
├── gallery/             # Gallery pages
├── releases/            # Release notes
├── about/               # About page
├── index.md             # Homepage
├── Gemfile              # Ruby dependencies
├── serve.sh             # Development server script
└── README.md            # This file
```

## Development Workflow

### 1. Make Changes
- Edit markdown files in `wiki/`
- Modify layouts in `_layouts/`
- Update styles in `assets/css/`

### 2. Test Locally
- Save your files
- Browser automatically refreshes (livereload)
- Test on different screen sizes

### 3. Commit and Push
```bash
git add docs/
git commit -m "Update documentation"
git push origin main
```

### 4. GitHub Pages Deployment
- Changes automatically deploy to GitHub Pages
- Live site: https://idossha.github.io/TI-Toolbox/

## Google Analytics (Developer Only)

The documentation site includes Google Analytics integration that is **enabled by default** and tracks all users. The analytics data is only accessible to the owner and developers.

### Setup

1. **Get your Google Analytics Measurement ID**
   - Go to [Google Analytics](https://analytics.google.com/)
   - Create a property or use an existing one
   - Copy your Measurement ID (format: `G-XXXXXXXXXX`)

2. **Add it to `_config.yml`**
   ```yaml
   google_analytics: G-XXXXXXXXXX  # Replace with your actual ID
   ```

### Viewing Analytics

To view the analytics data:

1. **Access Google Analytics**
   - Go to [Google Analytics](https://analytics.google.com/)
   - Sign in with the account that owns the property

2. **Navigate to your property**
   - Select the TI-Toolbox property from the property dropdown
   - The dashboard will show real-time and historical data

3. **Key metrics to monitor**
   - **Users**: Total number of unique visitors
   - **Page views**: Total page views across the site
   - **Sessions**: User sessions and engagement
   - **Top pages**: Most visited documentation pages
   - **Traffic sources**: How users are finding the site

### Important Notes

- ✅ Analytics is **enabled by default** on the public site
- ✅ Tracks all user interactions and page views
- ✅ Data is only accessible to the owner and developers
- ✅ Can be disabled locally by setting `ENABLE_ANALYTICS=false`

## Technology Stack

- **Jekyll 3.9** - Static site generator
- **Minima Theme** - Base theme with customizations
- **Kramdown** - Markdown processor
- **Rouge** - Syntax highlighting
- **GitHub Pages** - Hosting platform

## Getting Help

### Successful Server Startup Looks Like:
```
🚀 Starting Temporal Interference Toolbox Documentation Server...
✅ Dependencies already installed
🌐 Starting Jekyll server...
   Local URL: http://localhost:4000/TI-Toolbox/
   Press Ctrl+C to stop

Configuration file: /path/to/docs/_config.yml
            Source: /path/to/docs
       Destination: /path/to/docs/_site
 Incremental build: disabled. Enable with --incremental
      Generating...
                    done in X.XXX seconds.
 Auto-regeneration: enabled for '/path/to/docs'
LiveReload address: http://127.0.0.1:35729
    Server address: http://127.0.0.1:4000/TI-Toolbox/
  Server running... press ctrl-c to stop.
```

### If You Need More Help
1. Check the terminal output for specific error messages
2. Ensure you're in the `docs/` directory when running commands
3. Try the troubleshooting steps above
4. The simplified Jekyll setup should work with most Ruby versions

---

*Last Updated: January 2025*  
*For the TI-Toolbox Project Documentation* 