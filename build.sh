#!/bin/bash
# Build script for Transferarr Docker image

set -e

# Configuration
IMAGE_NAME="${IMAGE_NAME:-transferarr}"
IMAGE_TAG="${IMAGE_TAG:-dev}"
DOCKERFILE="${DOCKERFILE:-Dockerfile}"

# Get script directory (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# Read version from VERSION file
VERSION=$(cat "$PROJECT_ROOT/VERSION" 2>/dev/null || echo "unknown")

# Parse arguments
RELEASE_MODE=false
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        -n|--name)
            IMAGE_NAME="$2"
            shift 2
            ;;
        --no-cache)
            NO_CACHE="--no-cache"
            shift
            ;;
        --push)
            PUSH=true
            shift
            ;;
        --release)
            RELEASE_MODE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -t, --tag TAG      Image tag (default: dev)"
            echo "  -n, --name NAME    Image name (default: transferarr)"
            echo "  --no-cache         Build without cache"
            echo "  --push             Push image after building"
            echo "  --release          Build release image (requires clean git state and version tag)"
            echo "  -h, --help         Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Handle release mode
if [[ "$RELEASE_MODE" == "true" ]]; then
    # Safety checks for release builds
    if [[ -n $(git status --porcelain) ]]; then
        echo "❌ Error: Working directory not clean. Commit or stash changes first."
        exit 1
    fi
    
    # Check we're on the version tag
    CURRENT_TAG=$(git describe --exact-match --tags HEAD 2>/dev/null || echo "")
    if [[ "$CURRENT_TAG" != "v$VERSION" ]]; then
        echo "❌ Error: HEAD is not tagged as v$VERSION"
        echo "   Current tag: ${CURRENT_TAG:-none}"
        echo "   Expected tag: v$VERSION"
        echo ""
        echo "   Run 'bump2version patch/minor/major' first, then push tags."
        exit 1
    fi
    
    # Override tag for release
    IMAGE_TAG="$VERSION"
    ALSO_TAG_LATEST=true
    
    echo "🚀 Building RELEASE image"
else
    echo "🔧 Building DEV image"
fi

FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

echo "=========================================="
echo "Building Transferarr Docker Image"
echo "=========================================="
echo "Image: ${FULL_IMAGE}"
if [[ "$ALSO_TAG_LATEST" == "true" ]]; then
    echo "Also tagging: ${IMAGE_NAME}:latest"
fi
echo "Version: ${VERSION}"
echo "Context: ${PROJECT_ROOT}"
echo ""

cd "$PROJECT_ROOT"

# Build the image
if [[ "$ALSO_TAG_LATEST" == "true" ]]; then
    docker build \
        ${NO_CACHE:-} \
        --build-arg VERSION="$VERSION" \
        -t "${FULL_IMAGE}" \
        -t "${IMAGE_NAME}:latest" \
        -f "${DOCKERFILE}" \
        .
else
    docker build \
        ${NO_CACHE:-} \
        --build-arg VERSION="$VERSION-dev" \
        -t "${FULL_IMAGE}" \
        -f "${DOCKERFILE}" \
        .
fi

echo ""
echo "✅ Build complete: ${FULL_IMAGE}"
if [[ "$ALSO_TAG_LATEST" == "true" ]]; then
    echo "✅ Also tagged: ${IMAGE_NAME}:latest"
fi

# Push if requested
if [[ "$PUSH" == "true" ]]; then
    echo ""
    echo "Pushing ${FULL_IMAGE}..."
    docker push "${FULL_IMAGE}"
    if [[ "$ALSO_TAG_LATEST" == "true" ]]; then
        echo "Pushing ${IMAGE_NAME}:latest..."
        docker push "${IMAGE_NAME}:latest"
    fi
    echo "✅ Push complete"
fi
