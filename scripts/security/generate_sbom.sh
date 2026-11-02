#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Generate and validate CycloneDX SBOMs for what MAIW builds.
#
#   scripts/security/generate_sbom.sh [OUT_DIR]      (default: sbom/)
#
# Builds the three images from this checkout (backend, frontend, MCP) and
# writes, for the checked-out commit:
#   maiw-backend.cdx.json    Dockerfile.backend image: OS packages + Python
#   maiw-mcp.cdx.json        Dockerfile.mcp image (equipment; the four MCP
#                            images differ only in server code)
#   maiw-frontend.cdx.json   Dockerfile.frontend image: OS packages + nginx
#   maiw-ui-bundle.cdx.json  src/ui/web production npm dependencies. They are
#                            compiled into the frontend's static bundle, where
#                            an image scan cannot see them.
# Each file is stamped with the git SHA, release version and image ID, and
# validated against the CycloneDX schema (scripts/security/validate_sbom.py).
#
# Requires docker and python3 with cyclonedx-python-lib[json-validation].
# Same Trivy version as CI (aquasecurity/trivy-action v0.36.0 = Trivy 0.70.0).
# See docs/security/sbom-generation.md.

set -euo pipefail

TRIVY_IMAGE="aquasec/trivy:0.70.0@sha256:be1190afcb28352bfddc4ddeb71470835d16462af68d310f9f4bca710961a41e"

cd "$(git rev-parse --show-toplevel)"
OUT="${1:-sbom}"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"

git_sha="$(git rev-parse HEAD)"
version="$(git describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null || echo v0.0.0)"
version="${version#v}"
cache="${TRIVY_CACHE_DIR:-$HOME/.cache/trivy}"
mkdir -p "$cache"

trivy() {
  # As the invoking user, so the SBOMs and the cache are not root-owned; the
  # socket's group grants image access.
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    --group-add "$(stat -c %g /var/run/docker.sock)" \
    -e HOME=/tmp \
    -e TRIVY_CACHE_DIR=/cache \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$cache:/cache" \
    -v "$OUT:/out" \
    -v "$PWD:/src:ro" \
    "$TRIVY_IMAGE" "$@"
}

declare -A DOCKERFILE=([backend]=Dockerfile.backend [frontend]=Dockerfile.frontend [mcp]=Dockerfile.mcp)
declare -A MIN=([backend]=100 [frontend]=20 [mcp]=60)

for name in backend frontend mcp; do
  tag="maiw-${name}:sbom"
  build_args=()
  [ "$name" = mcp ] && build_args=(--build-arg MCP_DOMAIN=equipment)
  echo "== Building ${tag}"
  docker build --quiet "${build_args[@]}" -f "${DOCKERFILE[$name]}" -t "$tag" . >/dev/null
  image_id="$(docker image inspect --format '{{.Id}}' "$tag")"
  trivy image --quiet --format cyclonedx --output "/out/maiw-${name}.cdx.json" "$tag"
  python3 scripts/security/validate_sbom.py "$OUT/maiw-${name}.cdx.json" \
    --artifact "maiw-${name}" --git-sha "$git_sha" --version "$version" \
    --artifact-digest "$image_id" --min-components "${MIN[$name]}"
done

echo "== UI bundle (production npm dependencies)"
trivy fs --quiet --format cyclonedx --output /out/maiw-ui-bundle.cdx.json /src/src/ui/web/package-lock.json
python3 scripts/security/validate_sbom.py "$OUT/maiw-ui-bundle.cdx.json" \
  --artifact maiw-ui-bundle --git-sha "$git_sha" --version "$version" --min-components 50

echo "SBOMs for ${git_sha} (version ${version}) in ${OUT}"
echo "Remove the local images when done: docker rmi maiw-backend:sbom maiw-frontend:sbom maiw-mcp:sbom"
