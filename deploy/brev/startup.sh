#!/usr/bin/env bash
set -e

TARGET_BRANCH="${TARGET_BRANCH:-main}"
PROJECT_DIR="${HOME}/Multi-Agent-Intelligent-Warehouse"
BREV_DIR="${PROJECT_DIR}/deploy/brev"

# SWITCH TO TARGET BRANCH
cd "$PROJECT_DIR"
git fetch origin "$TARGET_BRANCH" || true
if git rev-parse --verify "origin/${TARGET_BRANCH}" >/dev/null 2>&1; then
  git switch -C "$TARGET_BRANCH" "origin/${TARGET_BRANCH}"
else
  git switch "$TARGET_BRANCH"
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
