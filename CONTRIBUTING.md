# Contributing to TI-Toolbox

Thank you for your interest in contributing to TI-Toolbox! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Types of Contributions](#types-of-contributions)
  - [New Features](#new-features)
  - [Bug Fixes](#bug-fixes)
- [Development Workflow](#development-workflow)
- [Testing Requirements](#testing-requirements)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Documentation](#documentation)
- [Getting Help](#getting-help)

## Code of Conduct

We are committed to providing a welcoming and inclusive environment. Please be respectful and professional in all interactions.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR-USERNAME/TI-Toolbox.git
   cd TI-Toolbox
   ```
3. **Add upstream remote**:
   ```bash
   git remote add upstream https://github.com/idossha/TI-Toolbox.git
   ```
4. **Set up your development environment** following the [installation guide](https://idossha.github.io/TI-Toolbox/installation/)

## Types of Contributions

### New Features

**Before starting development** on a new feature:

1. **Open a Discussion** on GitHub to propose your feature
2. **Explain the use case** and how it benefits the project
3. **Wait for maintainer feedback** to ensure the feature is:
   - Within the project scope
   - Aligned with project goals
   - A desirable addition
4. **Get approval** before starting development

> ⚠️ **Important**: Feature PRs submitted without prior discussion may be declined, even if well-implemented. Starting a discussion first saves everyone time and effort.

**Why we require discussion for new features:**
- Ensures feature aligns with project roadmap
- Prevents duplicate work
- Allows design feedback before implementation
- Helps maintain project coherence and quality

### Bug Fixes

**Bug fixes do NOT require prior discussion**, but please:

1. **Document the bug** clearly:
   - What is the expected behavior?
   - What is the actual (weird/incorrect) behavior?
   - Steps to reproduce
   - System information (OS, Docker version, SimNIBS version, etc.)
   - Error messages or logs (if applicable)

2. **Open an Issue** describing the bug before submitting the PR (or include the description in the PR if urgent)

3. **Include test cases** that demonstrate the bug is fixed

## Development Workflow

All contributions must follow this workflow:

### 1. Create a Feature Branch

**Always work on a separate branch** - never commit directly to `main`.

```bash
# Update your local main branch
git checkout main
git pull upstream main

# Create a new branch (use descriptive names)
git checkout -b feature/your-feature-name    # For new features
git checkout -b fix/bug-description          # For bug fixes
git checkout -b docs/what-you-are-documenting  # For documentation
```

**Branch naming conventions:**
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `refactor/` - Code refactoring
- `test/` - Adding or updating tests

### 2. Make Your Changes

- Write clear, readable code
- Follow existing code style and patterns
- Add or update tests as needed
- Update documentation if necessary
- Keep commits focused and atomic

### 3. Test Locally

**All tests must pass before submitting a PR.**

```bash
# Run quick unit tests during development
./tests/test.sh --unit-only

# Run full test suite before creating PR
./tests/test.sh --verbose
```

See the [Testing Guide](tests/README_TESTING.md) for detailed information.

### 4. Commit Your Changes

Write clear, descriptive commit messages:

```bash
git add .
git commit -m "Add feature: brief description of what was added"
# or
git commit -m "Fix: brief description of what was fixed"
```

**Good commit messages:**
- `Add support for custom electrode configurations`
- `Fix incorrect voxel intensity calculations in mesh analyzer`
- `Update documentation for flex-search parameters`
- `Refactor group analyzer for better performance`

### 5. Push to Your Fork

```bash
git push origin your-branch-name
```

### 6. Submit a Pull Request

1. Go to your fork on GitHub
2. Click "Compare & pull request"
3. Fill out the PR template completely
4. Link any related issues
5. Wait for CI/CD tests to pass
6. Address any review feedback

## Testing Requirements

### Local Testing

**Before submitting a PR, ensure all tests pass locally:**

```bash
# Quick validation (recommended during development)
./tests/test.sh --unit-only

# Full test suite (REQUIRED before PR submission)
./tests/test.sh
```

### Continuous Integration

- **CircleCI** automatically runs all tests on every PR
- All tests must pass before the PR can be merged
- Test results appear on your PR page on GitHub

### Writing New Tests

When adding new features or fixing bugs:

1. **Add unit tests** in the appropriate `tests/test_*.py` file
2. **Add integration tests** if the feature requires end-to-end testing
3. **Ensure tests are deterministic** (no random failures)
4. **Follow existing test patterns** in the codebase

## Pull Request Process

1. **Ensure all tests pass** locally before submitting
2. **Fill out the PR template** completely
3. **Link related issues** using GitHub keywords (e.g., "Fixes #123")
4. **Keep PRs focused** - one feature or fix per PR
5. **Respond to feedback** promptly and professionally
6. **Update your PR** if requested by maintainers
7. **Wait for approval** - a maintainer will review your PR

### PR Checklist

Before submitting, verify:

- [ ] Tests pass locally (`./tests/test.sh`)
- [ ] Code follows project style and conventions
- [ ] Documentation is updated (if applicable)
- [ ] Commit messages are clear and descriptive
- [ ] PR description explains what and why
- [ ] Related issues are linked
- [ ] No merge conflicts with main branch

## Coding Standards

### Python Code

- **Follow PEP 8** style guidelines
- **Use meaningful variable names**
- **Add docstrings** to functions and classes
- **Keep functions focused** (single responsibility)
- **Avoid magic numbers** (use named constants)

Example:
```python
def calculate_field_intensity(mesh_data, electrode_positions):
    """
    Calculate electromagnetic field intensity at each mesh point.
    
    Parameters
    ----------
    mesh_data : dict
        Mesh data containing node positions and field values
    electrode_positions : np.ndarray
        Array of electrode coordinates in MNI space
        
    Returns
    -------
    np.ndarray
        Field intensity values at each mesh node
    """
    # Implementation here
    pass
```

### Shell Scripts

- **Use bash shebang**: `#!/bin/bash`
- **Add error handling**: `set -euo pipefail`
- **Add help messages**: `-h` or `--help` flags
- **Use meaningful variable names**
- **Add comments** for complex sections

### General Guidelines

- **DRY Principle**: Don't Repeat Yourself
- **KISS Principle**: Keep It Simple, Stupid
- **Write self-documenting code**: Code should be readable without comments
- **Add comments only when necessary**: Explain "why", not "what"
- **Test edge cases**: Consider boundary conditions and error cases

## Documentation

Documentation updates are highly valued! When contributing:

### Code Documentation

- Add docstrings to all public functions and classes
- Update inline comments when changing complex logic
- Include usage examples in docstrings

### User Documentation

Documentation lives in the `docs/` directory and is published at [https://idossha.github.io/TI-Toolbox/](https://idossha.github.io/TI-Toolbox/)

When adding features:
- Update relevant wiki pages
- Add examples to the gallery if applicable
- Update the appropriate markdown files in `docs/`

### README Updates

Update the main README.md or module-specific READMEs when:
- Adding new command-line tools
- Changing default behavior
- Adding new dependencies
- Modifying installation procedures

## Getting Help

If you need assistance:

1. **Check existing documentation**:
   - [Project Wiki](https://idossha.github.io/TI-Toolbox/)
   - [Testing Guide](tests/README_TESTING.md)
   - Existing issues and discussions

2. **Search for similar issues** on GitHub

3. **Open a Discussion** on GitHub for:
   - Feature proposals
   - Design questions
   - General help

4. **Open an Issue** for:
   - Bug reports
   - Documentation errors
   - Build problems

5. **Contact the maintainer**:
   - Email: ihaber@wisc.edu
   - For sensitive topics or specific questions

## Thank You!

Your contributions make TI-Toolbox better for everyone. We appreciate your time and effort in improving this project!

---

## Quick Reference

### For New Features:
1. **Open Discussion** → Get approval
2. Create branch → Develop → Test locally
3. Submit PR → Address feedback → Merge

### For Bug Fixes:
1. Document bug → Create branch
2. Fix bug → Add tests → Test locally
3. Submit PR → Address feedback → Merge

### Testing:
```bash
./tests/test.sh --unit-only    # Quick tests
./tests/test.sh                # Full tests before PR
```

### Questions?
- Open a [Discussion](https://github.com/idossha/TI-Toolbox/discussions)
- Email: ihaber@wisc.edu

