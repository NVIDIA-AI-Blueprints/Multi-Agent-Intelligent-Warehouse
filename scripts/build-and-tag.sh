#!/bin/bash
# Build and Tag Script for Warehouse Operational Assistant
# This script builds Docker images with proper version tagging

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
print_status "Checking prerequisites..."

if ! command_exists docker; then
    print_error "Docker is not installed or not in PATH"
    exit 1
fi

if ! command_exists git; then
    print_error "Git is not installed or not in PATH"
    exit 1
fi

# Get version information
print_status "Gathering version information..."

# Get version from git tag or fallback
VERSION=$(git describe --tags --always 2>/dev/null || echo "0.0.0-dev")
GIT_SHA=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
BUILD_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Clean version string (remove 'v' prefix if present)
VERSION=${VERSION#v}

print_status "Version: $VERSION"
print_status "Git SHA: $GIT_SHA"
print_status "Build Time: $BUILD_TIME"

# Get Docker registry info
REGISTRY=${DOCKER_REGISTRY:-""}
IMAGE_NAME=${DOCKER_IMAGE_NAME:-"warehouse-assistant"}

if [ -n "$REGISTRY" ]; then
    FULL_IMAGE_NAME="$REGISTRY/$IMAGE_NAME"
else
    FULL_IMAGE_NAME="$IMAGE_NAME"
fi

print_status "Image Name: $FULL_IMAGE_NAME"

# Build arguments
BUILD_ARGS="--build-arg VERSION=$VERSION --build-arg GIT_SHA=$GIT_SHA --build-arg BUILD_TIME=$BUILD_TIME"

# Build Docker image
print_status "Building Docker image..."

if ! docker build $BUILD_ARGS -t "$FULL_IMAGE_NAME:$VERSION" .; then
    print_error "Docker build failed"
    exit 1
fi

print_success "Docker image built successfully: $FULL_IMAGE_NAME:$VERSION"

# Tag additional versions
print_status "Tagging additional versions..."

# Tag as latest
docker tag "$FULL_IMAGE_NAME:$VERSION" "$FULL_IMAGE_NAME:latest"
print_success "Tagged as latest: $FULL_IMAGE_NAME:latest"

# Tag with git SHA
docker tag "$FULL_IMAGE_NAME:$VERSION" "$FULL_IMAGE_NAME:$GIT_SHA"
print_success "Tagged with git SHA: $FULL_IMAGE_NAME:$GIT_SHA"

# Tag with short SHA (first 8 characters)
SHORT_SHA=${GIT_SHA:0:8}
docker tag "$FULL_IMAGE_NAME:$VERSION" "$FULL_IMAGE_NAME:$SHORT_SHA"
print_success "Tagged with short SHA: $FULL_IMAGE_NAME:$SHORT_SHA"

# Tag with branch name if not main
BRANCH_NAME=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
if [ "$BRANCH_NAME" != "main" ] && [ "$BRANCH_NAME" != "master" ]; then
    docker tag "$FULL_IMAGE_NAME:$VERSION" "$FULL_IMAGE_NAME:$BRANCH_NAME"
    print_success "Tagged with branch: $FULL_IMAGE_NAME:$BRANCH_NAME"
fi

# Show all tags
print_status "Available tags:"
docker images "$FULL_IMAGE_NAME" --format "table {{.Repository}}\t{{.Tag}}\t{{.CreatedAt}}\t{{.Size}}"

# Optional: Push to registry
if [ "$PUSH_TO_REGISTRY" = "true" ]; then
    print_status "Pushing images to registry..."
    
    # Push main version
    if ! docker push "$FULL_IMAGE_NAME:$VERSION"; then
        print_error "Failed to push $FULL_IMAGE_NAME:$VERSION"
        exit 1
    fi
    
    # Push latest
    if ! docker push "$FULL_IMAGE_NAME:latest"; then
        print_error "Failed to push $FULL_IMAGE_NAME:latest"
        exit 1
    fi
    
    # Push git SHA
    if ! docker push "$FULL_IMAGE_NAME:$GIT_SHA"; then
        print_error "Failed to push $FULL_IMAGE_NAME:$GIT_SHA"
        exit 1
    fi
    
    print_success "All images pushed to registry successfully"
fi

# Create build info file
print_status "Creating build info file..."
cat > build-info.json << EOF
{
  "version": "$VERSION",
  "git_sha": "$GIT_SHA",
  "build_time": "$BUILD_TIME",
  "branch": "$BRANCH_NAME",
  "image_name": "$FULL_IMAGE_NAME",
  "tags": [
    "$VERSION",
    "latest",
    "$GIT_SHA",
    "$SHORT_SHA"
  ]
}
EOF

print_success "Build info saved to build-info.json"

# Summary
print_success "Build completed successfully!"
print_status "Summary:"
echo "  - Version: $VERSION"
echo "  - Git SHA: $GIT_SHA"
echo "  - Build Time: $BUILD_TIME"
echo "  - Image: $FULL_IMAGE_NAME:$VERSION"
echo "  - Tags: $VERSION, latest, $GIT_SHA, $SHORT_SHA"

if [ "$PUSH_TO_REGISTRY" = "true" ]; then
    echo "  - Pushed to registry: Yes"
else
    echo "  - Pushed to registry: No (set PUSH_TO_REGISTRY=true to push)"
fi
