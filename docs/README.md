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

## File Structure

```
docs/
├── _config.yml          # Jekyll configuration
├── _layouts/            # Custom page layouts
│   └── wiki.html       # Wiki sidebar layout
├── assets/
│   └── css/
│       ├── style.scss  # Main site styles
│       └── wiki.css    # Wiki-specific styles
├── wiki/               # Wiki documentation
│   ├── wiki.md        # Main wiki page
│   ├── flex-search.md # Guide pages
│   └── assets/        # Wiki images
├── Gemfile             # Ruby dependencies
├── serve.sh           # Development server script
└── README.md          # This file
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