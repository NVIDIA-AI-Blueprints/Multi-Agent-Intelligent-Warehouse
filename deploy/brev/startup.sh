#!/usr/bin/env bash
set -euo pipefail

# Brev clones the launchable's source repository before running this script.
# TARGET_BRANCH supports the launchable environment; the first argument is
# convenient when running the script directly.
readonly PROJECT_NAME="Multi-Agent-Intelligent-Warehouse"
TARGET_BRANCH="${TARGET_BRANCH:-${1:-main}}"
PROJECT_DIR="${HOME}/${PROJECT_NAME}"
BREV_DIR="${PROJECT_DIR}/deploy/brev"

if [ ! -d "${PROJECT_DIR}/.git" ]; then
  echo "Expected Brev's pre-cloned repository at ${PROJECT_DIR}." >&2
  exit 1
fi

if ! git check-ref-format --branch "$TARGET_BRANCH" >/dev/null; then
  echo "Invalid target branch: ${TARGET_BRANCH}" >&2
  exit 2
fi

# SWITCH THE PRE-CLONED REPOSITORY TO THE REQUESTED BRANCH
cd "$PROJECT_DIR"
git fetch origin \
  "refs/heads/${TARGET_BRANCH}:refs/remotes/origin/${TARGET_BRANCH}"
git switch -C "$TARGET_BRANCH" "origin/${TARGET_BRANCH}"

if [ ! -d "$BREV_DIR" ]; then
  echo "Branch ${TARGET_BRANCH} does not contain deploy/brev." >&2
  exit 1
fi

# RECONFIGURE DOCKER STORAGE TO EPHEMERAL DRIVE
if [ -d /ephemeral ]; then
  sudo systemctl stop docker.socket || true
  sudo systemctl stop docker || true
  sudo systemctl stop containerd || true

  sudo mkdir -p /ephemeral/docker /ephemeral/containerd

  # conigure docker
  if [ -d /etc/docker ]; then
    sudo tee /etc/docker/daemon.json >/dev/null <<'EOF'
{
  "data-root": "/ephemeral/docker",
  "default-runtime": "nvidia",
  "mtu": 8950,
  "runtimes": {
    "nvidia": {
      "args": [],
      "path": "nvidia-container-runtime"
    }
  }
}
EOF
  fi

  # configure containerd
  if [ -d /etc/containerd ]; then
    sudo tee /etc/containerd/config.toml >/dev/null <<'EOF'
disabled_plugins = ["cri"]

root = "/ephemeral/containerd"
EOF
  fi

  sudo rm -rf /var/lib/containerd
  sudo ln -sfn /ephemeral/containerd /var/lib/containerd

  sudo systemctl start containerd || true
  sudo systemctl start docker.socket || true
  sudo systemctl start docker
fi

# START SERVICES
cd "$BREV_DIR"
mkdir -p generated/entities generated/setup-state
# pull all public containers for the blueprint
docker compose -f docker-compose.maiw.yaml pull --ignore-buildable || true
# run the olivetin dashboard
docker compose -f docker-compose.olivetin.yaml up -d
