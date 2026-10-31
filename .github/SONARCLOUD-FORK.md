# SonarQube / SonarCloud status

## What runs today

| Integration | Trigger | Status |
|-------------|---------|--------|
| `.github/workflows/sonarqube.yml` | Manual only (`workflow_dispatch`) | Notice job only — prints that SonarQube is not wired and runs **no** analysis |
| **SonarCloud GitHub App** | Every push, if the app is installed on the repository | Fails unless a SonarCloud project exists for that repository |

No workflow in `.github/workflows/` runs SonarQube or SonarCloud analysis, so CI produces no Sonar results for this repository. `sonarqube.yml` does not call the NVIDIA `sonarqube-workflows` reusable workflow.

`sonar-project.properties` (sources `src`, tests `tests`, Python and frontend coverage paths) is kept for a future analysis job; it does not define `sonar.organization` / `sonar.projectKey`.

## Why SonarCloud checks fail on forks and mirrors

The **SonarCloud Code Analysis** check is posted by the [SonarCloud GitHub App](https://github.com/apps/sonarqubecloud), not by `sonarqube.yml`. If the app is installed on a fork or mirror (for example `T-DevH/Multi-Agent-Intelligent-Warehouse`) but no SonarCloud project exists for it, automatic analysis fails (often after ~14 minutes) with "SonarQube Cloud analysis failed".

### Disable

1. Open **GitHub** → the repository → **Settings** → **Integrations** → **GitHub Apps** → **SonarCloud** → **Configure**.
2. Remove access to this repository (or uninstall the app for this repo only).

No workflow change can disable the app; it must be turned off in GitHub or SonarCloud.

### Enable

1. Create an organization and project on [SonarCloud](https://sonarcloud.io) for the repository.
2. Add to `sonar-project.properties`:

   ```properties
   sonar.organization=<your-sonarcloud-org-key>
   sonar.projectKey=<your-project-key>
   ```

3. Ensure the SonarCloud GitHub App is installed on the repo and automatic analysis (or CI-based analysis) is configured in SonarCloud.

## Restoring SonarQube analysis in CI

To get Sonar results from CI again, `sonarqube.yml` (or another workflow) must call a scanner — for example the NVIDIA-AI-Blueprints `sonarqube-workflows` reusable workflow (TEGRASW; not callable from forks such as T-DevH). No such job exists today.
