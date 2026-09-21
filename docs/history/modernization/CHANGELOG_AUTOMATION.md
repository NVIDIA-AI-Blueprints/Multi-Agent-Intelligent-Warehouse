# CHANGELOG.md Automatic Generation

## Overview

**CHANGELOG.md is now automatically generated** using `@semantic-release/changelog` plugin. The changelog is updated automatically when semantic-release creates a new version based on conventional commit messages.

## How It Works

### Automatic Generation Process

1. **Conventional Commits**: Developers make commits following the [Conventional Commits](https://www.conventionalcommits.org/) specification
2. **Semantic Release**: On push to `main` branch, semantic-release:
   - Analyzes commit messages
   - Determines version bump (patch/minor/major)
   - Generates CHANGELOG.md from commits
   - Creates GitHub release
   - Commits CHANGELOG.md back to repository

### Commit Message Format

The changelog is generated from commit messages:

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

**Types that appear in changelog:**
- `feat:` → New Features section
- `fix:` → Bug Fixes section
- `perf:` → Performance Improvements section
- `refactor:` → Code Refactoring section
- `docs:` → Documentation section (if significant)
- `BREAKING CHANGE:` → Breaking Changes section

### Changelog Sections

The automatically generated changelog includes:

- **New Features** - From `feat:` commits
- **Bug Fixes** - From `fix:` commits
- **Performance Improvements** - From `perf:` commits
- **Code Refactoring** - From `refactor:` commits
- **Breaking Changes** - From commits with `BREAKING CHANGE:` footer

## Configuration

### `.releaserc.json`

```json
{
  "plugins": [
    "@semantic-release/commit-analyzer",
    "@semantic-release/release-notes-generator",
    [
      "@semantic-release/changelog",
      {
        "changelogFile": "CHANGELOG.md",
        "changelogTitle": "# Changelog\n\n..."
      }
    ],
    "@semantic-release/github",
    [
      "@semantic-release/git",
      {
        "assets": ["CHANGELOG.md", "package.json", "package-lock.json"],
        "message": "chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}"
      }
    ]
  ]
}
```

### Manual Generation

To preview the changelog without creating a release:

```bash
npm run changelog
```

This uses `conventional-changelog` to generate/update CHANGELOG.md from existing commits.

## Workflow

### Automatic (Recommended)

1. **Make commits** with conventional commit format:
   ```bash
   git commit -m "feat(api): add new endpoint for equipment status"
   git commit -m "fix(ui): resolve rendering issue in dashboard"
   ```

2. **Push to main branch**:
   ```bash
   git push origin main
   ```

3. **GitHub Actions** automatically:
   - Runs semantic-release
   - Generates CHANGELOG.md
   - Creates GitHub release
   - Commits CHANGELOG.md back to repo

### Manual Release

To create a release manually (for testing or dry-run):

```bash
# Dry run (preview what would be released)
npx semantic-release --dry-run

# Actual release
npm run release
```

## Changelog Format

The generated changelog follows this format:

```markdown
# Changelog

All notable changes to this project will be documented in this file.

## [1.2.0] - 2025-11-16

### Added
- New feature description from commit message

### Changed
- Change description from commit message

### Fixed
- Bug fix description from commit message

### Breaking Changes
- Breaking change description from commit message

## [1.1.0] - 2025-11-15

### Added
- Previous release features
```

## Best Practices

### Writing Commit Messages for Changelog

**Good commit messages:**
```bash
feat(api): add equipment status endpoint
fix(ui): resolve dashboard rendering issue
perf(db): optimize inventory query performance
docs: update API documentation
```

**Better commit messages (with body):**
```bash
feat(api): add equipment status endpoint

Adds new GET /api/v1/equipment/{id}/status endpoint
that returns real-time equipment status including
battery level, location, and maintenance schedule.

Closes #123
```

**Breaking changes:**
```bash
feat(api): change equipment endpoint response format

BREAKING CHANGE: Equipment status endpoint now returns
nested object structure instead of flat structure.
Migration guide available in docs/migration.md.
```

### Commit Message Guidelines

1. **Use present tense**: "add feature" not "added feature"
2. **Use imperative mood**: "fix bug" not "fixes bug"
3. **First line should be concise**: 50-72 characters
4. **Add body for context**: Explain what and why
5. **Reference issues**: "Closes #123" or "Fixes #456"

## Migration from Manual Changelog

### Current State

The existing `CHANGELOG.md` with manual format:
```markdown
## Warehouse Operational Assistant 0.1.0 (16 Nov 2025)

### New Features
- Feature description
```

### After Migration

The changelog will be automatically generated in standard format:
```markdown
## [0.1.0] - 2025-11-16

### Added
- Feature description
```

**Note**: The existing manual changelog entries will be preserved. New entries will be automatically added above them.

## Troubleshooting

### Changelog Not Updating

1. **Check commit format**: Ensure commits follow conventional format
2. **Check semantic-release logs**: Review GitHub Actions logs
3. **Verify plugin configuration**: Ensure `@semantic-release/changelog` is in `.releaserc.json`
4. **Check branch**: Semantic-release only runs on `main` branch

### Preview Changelog

To see what would be generated:

```bash
# Install conventional-changelog-cli if needed
npm install -g conventional-changelog-cli

# Generate changelog from commits
conventional-changelog -p conventionalcommits -i CHANGELOG.md -s
```

### Manual Update

If you need to manually update the changelog:

1. Edit `CHANGELOG.md` directly
2. Commit with `docs: update changelog` message
3. Note: Manual edits may be overwritten on next release

## CI/CD Integration

### GitHub Actions

The changelog is automatically generated in the release workflow:

```yaml
- name: Run semantic-release
  run: npx semantic-release
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

This will:
1. Analyze commits since last release
2. Determine version bump
3. Generate CHANGELOG.md
4. Create GitHub release
5. Commit CHANGELOG.md back to repository

## Benefits

### Automatic Generation
- ✅ No manual changelog maintenance
- ✅ Consistent format across all releases
- ✅ Based on actual commit messages
- ✅ Always up-to-date

### Conventional Commits
- ✅ Standardized commit format
- ✅ Automatic version bumping
- ✅ Clear release notes
- ✅ Better project history

### Integration
- ✅ Works with GitHub releases
- ✅ CI/CD automation
- ✅ Version tagging
- ✅ Release notes generation

## Related Documentation

- [Conventional Commits](https://www.conventionalcommits.org/)
- [Semantic Versioning](https://semver.org/)
- [Semantic Release](https://semantic-release.gitbook.io/)
- [Keep a Changelog](https://keepachangelog.com/)

