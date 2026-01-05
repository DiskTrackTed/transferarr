#!/bin/bash
# Build script for Transferarr Docker image

set -e

# Configuration
IMAGE_NAME="${IMAGE_NAME:-transferarr}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
DOCKERFILE="${DOCKERFILE:-Dockerfile}"

# Get script directory (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# Parse arguments
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
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -t, --tag TAG      Image tag (default: latest)"
            echo "  -n, --name NAME    Image name (default: transferarr)"
            echo "  --no-cache         Build without cache"
            echo "  --push             Push image after building"
            echo "  -h, --help         Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

echo "=========================================="
echo "Building Transferarr Docker Image"
echo "=========================================="
echo "Image: ${FULL_IMAGE}"
echo "Context: ${PROJECT_ROOT}"
echo ""

cd "$PROJECT_ROOT"

# Build the image
docker build \
    ${NO_CACHE:-} \
    -t "${FULL_IMAGE}" \
    -f "${DOCKERFILE}" \
    .

echo ""
echo "✅ Build complete: ${FULL_IMAGE}"

# Push if requested
if [[ "$PUSH" == "true" ]]; then
    echo ""
    echo "Pushing ${FULL_IMAGE}..."
    docker push "${FULL_IMAGE}"
    echo "✅ Push complete"
fi
