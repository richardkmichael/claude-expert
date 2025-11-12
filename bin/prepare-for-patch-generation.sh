#!/usr/bin/env bash

set -euo pipefail

# Check required dependencies
for cmd in npm tar npx chmod; do
    command -v "$cmd" >/dev/null 2>&1 || {
        echo "Error: required command '$cmd' not found" >&2
        exit 1
    }
done

if [ $# -eq 0 ]; then
    echo "Error: version argument is required" >&2
    echo "Usage: $0 <version>" >&2
    exit 1
fi

readonly VERSION="$1"

# Validate version format
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Error: invalid version format '$VERSION' (expected: X.Y.Z)" >&2
    exit 1
fi

readonly PATCHES_VERSION_DIR="patches/${VERSION}"
readonly WORK_VERSION_DIR="work/${VERSION}"
readonly CLI_JS="${WORK_VERSION_DIR}/package/cli.js"
readonly CLI_PRETTIER_JS="${WORK_VERSION_DIR}/package/cli.prettier.js"

# Check if version already prepared
if [[ -f "${CLI_PRETTIER_JS}" ]]; then
    echo "Error: version ${VERSION} already prepared at ${CLI_PRETTIER_JS}" >&2
    exit 1
fi

# Set up cleanup trap for errors
trap 'echo "Error occurred, cleaning up..." >&2; rm -rf "${WORK_VERSION_DIR}"' ERR

mkdir -p "${PATCHES_VERSION_DIR}" || {
    echo "Error: failed to create patches directory: ${PATCHES_VERSION_DIR}" >&2
    exit 1
}

mkdir -p "${WORK_VERSION_DIR}" || {
    echo "Error: failed to create work directory: ${WORK_VERSION_DIR}" >&2
    exit 1
}

# Download, extract, prettify and make source code executable

# Despite --silent, npm still emits the downloaded tarball name
npm --silent pack --pack-destination "${WORK_VERSION_DIR}" "@anthropic-ai/claude-code@${VERSION}" > /dev/null || {
    echo "Error: failed to download @anthropic-ai/claude-code@${VERSION}" >&2
    exit 1
}

tar xf "${WORK_VERSION_DIR}/anthropic-ai-claude-code-${VERSION}.tgz" -C "${WORK_VERSION_DIR}" || {
    echo "Error: failed to extract ${WORK_VERSION_DIR}/anthropic-ai-claude-code-${VERSION}.tgz" >&2
    exit 1
}

npx --yes prettier --ignore-path /dev/null "${CLI_JS}" > "${CLI_PRETTIER_JS}" || {
    echo "Error: failed to prettify ${CLI_JS}" >&2
    exit 1
}

chmod +x "${WORK_VERSION_DIR}/package/cli.prettier.js" || {
    echo "Error: failed to make ${CLI_PRETTIER_JS} executable" >&2
    exit 1
}

echo "Prettified source code for version ${VERSION} has been prepared: ${CLI_PRETTIER_JS}"
