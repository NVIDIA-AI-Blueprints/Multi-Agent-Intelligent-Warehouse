#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Print the MAIW version that a build of a commit should be stamped with.
#
#   scripts/security/release_version.sh [REV]     (default: HEAD)
#
# Used for the SBOM `maiw:release_version` property (CI and
# generate_sbom.sh) and the SonarQube projectVersion (run_sonar_scan.sh), so
# all three agree. Run it inside the checkout whose commit is being built.
#
#   MAIW_RELEASE_VERSION set     that version (a leading "v" is dropped). For
#                                release-candidate builds, made before the
#                                tag exists. Must be X.Y.Z or X.Y.Z-pre. If
#                                REV already carries a different v* tag, it
#                                is an error.
#   REV is a v* tag              the tag's version, e.g. 2.1.1
#   otherwise                    <last tag>+<commits since>.g<short sha>,
#                                e.g. 2.1.1+16.g4d2e0c4: semver build
#                                metadata, so a development build is never
#                                mistaken for the release it follows.
#                                0.0.0+g<short sha> when no v* tag is
#                                reachable (for example a shallow clone).
#
# Exit 2 when MAIW_RELEASE_VERSION is malformed or contradicts the tag.

set -euo pipefail

rev="${1:-HEAD}"
release_re='^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$'
tag="$(git describe --tags --exact-match --match 'v[0-9]*' "$rev" 2>/dev/null || true)"

if [ -n "${MAIW_RELEASE_VERSION:-}" ]; then
  version="${MAIW_RELEASE_VERSION#v}"
  if ! [[ "$version" =~ $release_re ]]; then
    echo "MAIW_RELEASE_VERSION=${MAIW_RELEASE_VERSION} is not a release version (X.Y.Z or X.Y.Z-pre)" >&2
    exit 2
  fi
  if [ -n "$tag" ] && [ "${tag#v}" != "$version" ]; then
    echo "MAIW_RELEASE_VERSION=${MAIW_RELEASE_VERSION} contradicts tag ${tag} on ${rev}" >&2
    exit 2
  fi
  echo "$version"
  exit 0
fi

if [ -n "$tag" ]; then
  echo "${tag#v}"
  exit 0
fi

if described="$(git describe --tags --long --abbrev=7 --match 'v[0-9]*' "$rev" 2>/dev/null)"; then
  # v2.1.1-16-g4d2e0c4 -> 2.1.1+16.g4d2e0c4
  if [[ "$described" =~ ^v(.+)-([0-9]+)-g([0-9a-f]+)$ ]]; then
    echo "${BASH_REMATCH[1]}+${BASH_REMATCH[2]}.g${BASH_REMATCH[3]}"
    exit 0
  fi
fi

echo "0.0.0+g$(git rev-parse --short=7 "$rev")"
