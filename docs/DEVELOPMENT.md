# Development Guide

## Version Control & Release Management

This project uses conventional commits and semantic versioning for automated releases.

### Commit Message Format

We follow the [Conventional Commits](https://conventionalcommits.org) specification:

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

#### Types:
- `feat`: A new feature
- `fix`: A bug fix
- `docs`: Documentation only changes
- `style`: Changes that do not affect the meaning of the code
- `refactor`: A code change that neither fixes a bug nor adds a feature
- `perf`: A code change that improves performance
- `test`: Adding missing tests or correcting existing tests
- `build`: Changes that affect the build system or external dependencies
- `ci`: Changes to our CI configuration files and scripts
- `chore`: Other changes that don't modify src or test files
- `revert`: Reverts a previous commit

#### Examples:
```bash
feat(api): add equipment status endpoint
fix(ui): resolve evidence panel rendering issue
docs: update API documentation
refactor(agents): improve error handling
```

### Making Commits

Use the interactive commit tool:
```bash
npm run commit
```

This will guide you through creating a properly formatted commit message.

### Release Process

Releases are automatically generated based on commit messages:

- `feat:` → Minor version bump
- `fix:` → Patch version bump
- `BREAKING CHANGE:` → Major version bump

### Manual Release

To create a release manually:
```bash
npm run release
```

### Changelog

The changelog is automatically generated from commit messages and can be found in `CHANGELOG.md`.

## Phase 1: Conventional Commits + Semantic Release 

### Completed:
- [x] Installed semantic-release and related tools
- [x] Configured conventional commits with commitlint
- [x] Set up Husky for git hooks
- [x] Created semantic release configuration
- [x] Added commitizen for interactive commits
- [x] Created initial CHANGELOG.md
- [x] Updated package.json with release scripts

### Files Created/Modified:
- `.commitlintrc.json` - Commit message linting rules
- `.releaserc.json` - Semantic release configuration
- `.husky/commit-msg` - Git hook for commit validation
- `CHANGELOG.md` - Automated changelog
- `package.json` - Updated with release scripts

## Phase 2: Version Injection & Build Metadata 

### Completed:
- [x] Created comprehensive version service for backend
- [x] Enhanced health router with version endpoints
- [x] Created frontend version service and API integration
- [x] Built VersionFooter component with detailed version display
- [x] Integrated version footer into main application
- [x] Added database service for health checks
- [x] Tested version endpoints and functionality

### Files Created/Modified:
- `chain_server/services/version.py` - Backend version service
- `chain_server/services/database.py` - Database connection service
- `chain_server/routers/health.py` - Enhanced health endpoints
- `ui/web/src/services/version.ts` - Frontend version service
- `ui/web/src/components/VersionFooter.tsx` - Version display component
- `ui/web/src/App.tsx` - Integrated version footer

### API Endpoints Added:
- `GET /api/v1/version` - Basic version information
- `GET /api/v1/version/detailed` - Detailed build information
- `GET /api/v1/health` - Enhanced health check with version info
- `GET /api/v1/ready` - Kubernetes readiness probe
- `GET /api/v1/live` - Kubernetes liveness probe

### Features:
- **Version Tracking**: Git version, SHA, build time, environment
- **Health Monitoring**: Database, Redis, Milvus connectivity checks
- **UI Integration**: Version footer with detailed information dialog
- **Kubernetes Ready**: Readiness and liveness probe endpoints
- **Error Handling**: Graceful fallbacks for missing information

## Phase 3: Docker & Helm Versioning 

### Completed:
- [x] Created multi-stage Dockerfile with version injection
- [x] Built comprehensive build script with version tagging
- [x] Created Helm chart with version management
- [x] Set up Docker Compose with version support
- [x] Successfully tested Docker build with version injection
- [x] Created build info tracking and metadata

### Files Created/Modified:
- `Dockerfile` - Multi-stage build with version injection
- `scripts/build-and-tag.sh` - Automated build and tagging script
- `requirements.docker.txt` - Docker-optimized dependencies
- `docker-compose.versioned.yaml` - Version-aware Docker Compose
- `helm/warehouse-assistant/` - Complete Helm chart
  - `Chart.yaml` - Chart metadata and version info
  - `values.yaml` - Configurable values with version support
  - `templates/deployment.yaml` - Kubernetes deployment with version injection
  - `templates/service.yaml` - Service definition
  - `templates/serviceaccount.yaml` - Service account
  - `templates/_helpers.tpl` - Template helpers

### Features:
- **Multi-stage Build**: Optimized frontend and backend builds
- **Version Injection**: Git SHA, build time, and version baked into images
- **Multiple Tags**: Version, latest, git SHA, and short SHA tags
- **Helm Integration**: Kubernetes-ready with version management
- **Build Metadata**: Comprehensive build information tracking
- **Security**: Non-root user and proper permissions
- **Health Checks**: Built-in health monitoring

### Docker Images Created:
- `warehouse-assistant:3058f7f` (version tag)
- `warehouse-assistant:latest` (latest tag)
- `warehouse-assistant:3058f7fa` (short SHA)
- `warehouse-assistant:3058f7fabf885bb9313e561896fb254793752a90` (full SHA)

## Phase 4: CI/CD Pipeline with Semantic Release 

### Completed:
- [x] Created comprehensive GitHub Actions CI/CD workflow
- [x] Set up automated testing and quality checks
- [x] Implemented security scanning with Trivy and CodeQL
- [x] Created Docker build and push automation
- [x] Set up semantic release automation
- [x] Created staging and production deployment workflows
- [x] Added issue and PR templates
- [x] Set up Dependabot for dependency updates
- [x] Created release notes template

### Files Created/Modified:
- `.github/workflows/ci-cd.yml` - Main CI/CD pipeline
- `.github/workflows/release.yml` - Manual release workflow
- `.github/workflows/codeql.yml` - Security analysis
- `.github/dependabot.yml` - Dependency updates
- `.github/ISSUE_TEMPLATE/` - Issue templates
- `.github/pull_request_template.md` - PR template
- `.github/release_template.md` - Release notes template
- `docker-compose.ci.yml` - CI environment setup

### Features:
- **Automated Testing**: Python and Node.js tests with coverage
- **Code Quality**: Linting, formatting, and type checking
- **Security Scanning**: Trivy vulnerability scanning and CodeQL analysis
- **Docker Automation**: Multi-platform builds and registry pushes
- **Semantic Release**: Automated versioning and changelog generation
- **Multi-Environment**: Staging and production deployment workflows
- **Dependency Management**: Automated dependency updates with Dependabot
- **Issue Management**: Structured templates for bugs and features

### Workflow Triggers:
- **Push to main/develop**: Full CI pipeline
- **Pull Requests**: Testing and quality checks
- **Releases**: Production deployment
- **Manual**: Release creation and deployment

### Next Phase:
Phase 5: Database Versioning and Migration Tracking
