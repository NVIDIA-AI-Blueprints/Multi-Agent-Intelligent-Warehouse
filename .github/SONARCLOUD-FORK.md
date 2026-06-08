# Sonar on the T-DevH mirror

## What runs today

| Integration | Trigger | Status on T-DevH |
|-------------|---------|------------------|
| `.github/workflows/sonarqube.yml` | Manual only | Fork-safe notice job (no NVIDIA reusable workflow) |
| **SonarCloud GitHub App** | Every push to `main` | Fails if no SonarCloud project exists for this repo |

## Why SonarCloud checks fail

The **SonarCloud Code Analysis** check is posted by the [SonarCloud GitHub App](https://github.com/apps/sonarqubecloud), not by `sonarqube.yml`. The project key inferred for this repository (`T-DevH_Multi-Agent-Intelligent-Warehouse`) is not set up on SonarCloud for the T-DevH organization, so automatic analysis fails (often after ~14 minutes) with "SonarQube Cloud analysis failed".

`sonar-project.properties` in this repo targets NVIDIA upstream SonarQube settings and does not define `sonar.organization` / `sonar.projectKey` for T-DevH.

## Recommended for this fork (disable)

1. Open **GitHub** → **T-DevH/Multi-Agent-Intelligent-Warehouse** → **Settings** → **Integrations** → **GitHub Apps** → **SonarCloud** → **Configure**.
2. Remove access to this repository (or uninstall the app for this repo only).

No workflow change can disable the app; it must be turned off in GitHub or SonarCloud.

## If you want SonarCloud on T-DevH (enable)

1. Create an organization and project on [SonarCloud](https://sonarcloud.io) for `T-DevH/Multi-Agent-Intelligent-Warehouse`.
2. Add to `sonar-project.properties`:

   ```properties
   sonar.organization=<your-sonarcloud-org-key>
   sonar.projectKey=<your-project-key>
   ```

3. Ensure the SonarCloud GitHub App is installed on the repo and automatic analysis (or CI-based analysis) is configured in SonarCloud.

NVIDIA internal SonarQube (TEGRASW / `sonarqube-workflows`) remains upstream-only.
