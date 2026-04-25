#!/usr/bin/env bash

set -euo pipefail

# Check required dependencies
for cmd in npm tar npx chmod uname mktemp; do
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
readonly CLI_PRETTIER_JS="${WORK_VERSION_DIR}/package/cli.prettier.js"

# Check if version already prepared
if [[ -f "${CLI_PRETTIER_JS}" ]]; then
    echo "Error: version ${VERSION} already prepared at ${CLI_PRETTIER_JS}" >&2
    exit 1
fi

# All extraction happens in a temp directory; only cli.prettier.js lands in the work dir.
TEMP_DIR="$(mktemp -d)"
readonly TEMP_DIR
trap 'rm -rf "${TEMP_DIR}"' EXIT
trap 'echo "Error occurred, cleaning up..." >&2; rm -rf "${WORK_VERSION_DIR}"' ERR

mkdir -p "${PATCHES_VERSION_DIR}" || {
    echo "Error: failed to create patches directory: ${PATCHES_VERSION_DIR}" >&2
    exit 1
}

mkdir -p "${WORK_VERSION_DIR}/package" || {
    echo "Error: failed to create work directory: ${WORK_VERSION_DIR}" >&2
    exit 1
}

readonly CLI_JS="${TEMP_DIR}/package/cli.js"

# Download the wrapper package.
npm --silent pack --pack-destination "${TEMP_DIR}" "@anthropic-ai/claude-code@${VERSION}" > /dev/null || {
    echo "Error: failed to download @anthropic-ai/claude-code@${VERSION}" >&2
    exit 1
}

tar xf "${TEMP_DIR}/anthropic-ai-claude-code-${VERSION}.tgz" -C "${TEMP_DIR}" || {
    echo "Error: failed to extract wrapper tarball for ${VERSION}" >&2
    exit 1
}

# Pre-bun-native releases (≤ 2.1.116) ship cli.js inside the wrapper tarball.
# Bun-native releases (≥ 2.1.117) ship a wrapper that resolves to a platform-specific
# native binary via optionalDependencies; cli.js must be unpacked from the binary.
if [[ ! -f "${CLI_JS}" ]]; then
    case "$(uname -s)" in
        Darwin) PLATFORM="darwin" ;;
        Linux)  PLATFORM="linux" ;;
        *)
            echo "Error: unsupported OS for native unpack: $(uname -s)" >&2
            exit 1
            ;;
    esac

    case "$(uname -m)" in
        arm64|aarch64) ARCH="arm64" ;;
        x86_64|amd64)  ARCH="x64" ;;
        *)
            echo "Error: unsupported architecture for native unpack: $(uname -m)" >&2
            exit 1
            ;;
    esac

    LIBC_SUFFIX=""
    if [[ "${PLATFORM}" == "linux" ]] && ldd --version 2>&1 | grep -qi musl; then
        LIBC_SUFFIX="-musl"
    fi

    readonly NATIVE_PKG="@anthropic-ai/claude-code-${PLATFORM}-${ARCH}${LIBC_SUFFIX}"
    readonly NATIVE_DIR="${TEMP_DIR}/native"
    readonly NATIVE_TGZ="${NATIVE_DIR}/anthropic-ai-claude-code-${PLATFORM}-${ARCH}${LIBC_SUFFIX}-${VERSION}.tgz"
    readonly NATIVE_BIN="${NATIVE_DIR}/package/claude"

    mkdir -p "${NATIVE_DIR}" || {
        echo "Error: failed to create native directory: ${NATIVE_DIR}" >&2
        exit 1
    }

    npm --silent pack --pack-destination "${NATIVE_DIR}" "${NATIVE_PKG}@${VERSION}" > /dev/null || {
        echo "Error: failed to download ${NATIVE_PKG}@${VERSION}" >&2
        exit 1
    }

    tar xf "${NATIVE_TGZ}" -C "${NATIVE_DIR}" || {
        echo "Error: failed to extract ${NATIVE_TGZ}" >&2
        exit 1
    }

    [[ -f "${NATIVE_BIN}" ]] || {
        echo "Error: native binary not found at ${NATIVE_BIN}" >&2
        exit 1
    }

    npx --yes tweakcc unpack "${CLI_JS}" "${NATIVE_BIN}" || {
        echo "Error: failed to unpack cli.js from ${NATIVE_BIN}" >&2
        exit 1
    }
fi

npx --yes prettier --ignore-path /dev/null "${CLI_JS}" > "${CLI_PRETTIER_JS}" || {
    echo "Error: failed to prettify ${CLI_JS}" >&2
    exit 1
}

chmod +x "${CLI_PRETTIER_JS}" || {
    echo "Error: failed to make ${CLI_PRETTIER_JS} executable" >&2
    exit 1
}

echo "Prettified source code for version ${VERSION} has been prepared: ${CLI_PRETTIER_JS}"
