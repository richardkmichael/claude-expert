#!/usr/bin/env bash

set -euo pipefail

if [ $# -eq 0 ]; then
    echo "Error: version argument is required" >&2
    echo "Usage: $0 <version>" >&2
    exit 1
fi

VERSION="$1"
WORK_DIR="work/${VERSION}"

mkdir -p "${WORK_DIR}"

# Download and prettify source code
npm --silent pack --pack-destination "${WORK_DIR}" "@anthropic-ai/claude-code@${VERSION}"
tar xf "${WORK_DIR}/anthropic-ai-claude-code-${VERSION}.tgz" -C "${WORK_DIR}"
npx prettier "${WORK_DIR}/package/cli.js" > "${WORK_DIR}/package/cli.prettier.js"
chmod +x "${WORK_DIR}/package/cli.prettier.js"
