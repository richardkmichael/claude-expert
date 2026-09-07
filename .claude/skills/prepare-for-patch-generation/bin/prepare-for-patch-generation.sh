#!/usr/bin/env bash

set -euo pipefail

# Check required dependencies
for cmd in npm tar npx node chmod uname mktemp wc; do
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

# Anchor the output directories to the repository, not to the caller's working directory: this
# script is run by a skill, whose shell may be cwd'd anywhere in the tree. Layout is
# <repo>/.claude/skills/<skill>/bin/<this script>, so the root is four levels above bin/.
SCRIPT_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -P -- "${SCRIPT_DIR}/../../../.." && pwd)"
readonly SCRIPT_DIR REPO_ROOT

# Fail loudly if that derivation is wrong. Writing a 24MB tree into an unexpected directory is
# quiet enough to go unnoticed for a whole session.
if [[ ! -d "${REPO_ROOT}/analysis" || ! -d "${REPO_ROOT}/patches" ]]; then
    echo "Error: expected repository root at ${REPO_ROOT}, but it has no analysis/ and patches/" >&2
    echo "       (derived from this script's location: ${SCRIPT_DIR})" >&2
    exit 1
fi

readonly PATCHES_VERSION_DIR="${REPO_ROOT}/patches/${VERSION}"
readonly WORK_VERSION_DIR="${REPO_ROOT}/work/${VERSION}"
readonly CLI_PRETTIER_JS="${WORK_VERSION_DIR}/package/cli.prettier.js"

# Check if version already prepared
if [[ -f "${CLI_PRETTIER_JS}" ]]; then
    echo "Error: version ${VERSION} already prepared at ${CLI_PRETTIER_JS}" >&2
    exit 1
fi

# Record which output directories already exist, so failure cleanup removes only what this run
# created. A patches/<version> directory may already hold real patch work.
PATCHES_DIR_PREEXISTED=0
WORK_DIR_PREEXISTED=0
if [[ -d "${PATCHES_VERSION_DIR}" ]]; then PATCHES_DIR_PREEXISTED=1; fi
if [[ -d "${WORK_VERSION_DIR}" ]]; then WORK_DIR_PREEXISTED=1; fi
readonly PATCHES_DIR_PREEXISTED WORK_DIR_PREEXISTED

# All extraction happens in a temp directory; only cli.prettier.js lands in the work dir.
TEMP_DIR="$(mktemp -d)"
readonly TEMP_DIR

# Cleanup hangs off EXIT rather than ERR: every failure path here is `cmd || { echo …; exit 1; }`,
# which suppresses errexit and so never fires an ERR trap. COMPLETED is set only after the last
# step succeeds, so any other way out of the script counts as a failure.
COMPLETED=0
cleanup() {
    rm -rf "${TEMP_DIR}"

    if (( COMPLETED )); then
        return
    fi

    echo "Preparation of ${VERSION} failed; removing partial output." >&2
    if (( ! WORK_DIR_PREEXISTED )); then
        rm -rf "${WORK_VERSION_DIR}"
    fi
    # rmdir, not rm -rf: leave the directory alone if anything managed to write into it.
    if (( ! PATCHES_DIR_PREEXISTED )); then
        rmdir "${PATCHES_VERSION_DIR}" 2>/dev/null || true
    fi
}
trap cleanup EXIT

mkdir -p "${PATCHES_VERSION_DIR}" || {
    echo "Error: failed to create patches directory: ${PATCHES_VERSION_DIR}" >&2
    exit 1
}

mkdir -p "${WORK_VERSION_DIR}/package" || {
    echo "Error: failed to create work directory: ${WORK_VERSION_DIR}" >&2
    exit 1
}

readonly CLI_JS="${TEMP_DIR}/package/cli.js"
readonly MODULES_DIR="${TEMP_DIR}/modules"

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

    MODULE_COUNT="$(node "${SCRIPT_DIR}/extract-bun-modules.mjs" "${NATIVE_BIN}" "${MODULES_DIR}")" || {
        echo "Error: failed to extract JS modules from ${NATIVE_BIN}" >&2
        exit 1
    }
    echo "Extracted ${MODULE_COUNT} JavaScript module(s) from the native binary"
fi

# Prettifying is memory-hungry: a multi-megabyte single-line bundle blows through Node's default
# heap (~2GB) and OOMs. Raise --max-old-space-size when the largest input is large, scaled to the
# machine's RAM (capped below physical RAM, so smaller boxes stay safe). The flag only raises the
# ceiling, so it is harmless when the extra headroom is not needed.
readonly PRETTIER_HEAP_THRESHOLD_BYTES=$((8 * 1024 * 1024))
if [[ -f "${CLI_JS}" ]]; then
    LARGEST_BYTES="$(wc -c < "${CLI_JS}")"
else
    LARGEST_BYTES="$(find "${MODULES_DIR}" -type f -exec wc -c {} + | awk '$2 != "total" { if ($1 > m) m = $1 } END { print m + 0 }')"
fi
PRETTIER_NODE_OPTIONS="${NODE_OPTIONS:-}"
if (( LARGEST_BYTES > PRETTIER_HEAP_THRESHOLD_BYTES )); then
    case "$(uname -s)" in
        Darwin) RAM_MB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 )) ;;
        Linux)  RAM_MB=$(awk '/^MemTotal:/ { print int($2 / 1024) }' /proc/meminfo) ;;
        *)      RAM_MB=0 ;;
    esac
    HEAP_MB=4096
    if (( RAM_MB * 3 / 4 > HEAP_MB )); then
        HEAP_MB=$(( RAM_MB * 3 / 4 ))
    fi
    PRETTIER_NODE_OPTIONS="${PRETTIER_NODE_OPTIONS} --max-old-space-size=${HEAP_MB}"
    echo "Largest input is $(( LARGEST_BYTES / 1024 / 1024 )) MB; raising prettier heap to ${HEAP_MB} MB (physical RAM: ${RAM_MB} MB)"
fi

if [[ -f "${CLI_JS}" ]]; then
    NODE_OPTIONS="${PRETTIER_NODE_OPTIONS}" npx --yes prettier --ignore-path /dev/null "${CLI_JS}" > "${CLI_PRETTIER_JS}" || {
        echo "Error: failed to prettify ${CLI_JS}" >&2
        exit 1
    }
else
    # One list drives both steps, so no module can be concatenated without having been prettified.
    MODULE_FILES=("${MODULES_DIR}"/*)

    # Prettier rewrites the modules in place, one process for the whole set: it holds only the
    # current file, so peak memory tracks the largest module rather than the whole bundle.
    NODE_OPTIONS="${PRETTIER_NODE_OPTIONS}" npx --yes prettier --ignore-path /dev/null --log-level warn --write "${MODULE_FILES[@]}" || {
        echo "Error: failed to prettify the extracted modules in ${MODULES_DIR}" >&2
        exit 1
    }

    # Concatenate into the single file the analysis tooling expects. Each module gets a banner so
    # a match found by grep can be traced back to the module it came from. Every bun binary seen so
    # far carries several, pre-split releases included; the unbannered form is for a hypothetical
    # binary holding exactly one, where a banner would only add noise.
    : > "${CLI_PRETTIER_JS}"
    for module_file in "${MODULE_FILES[@]}"; do
        if (( ${#MODULE_FILES[@]} > 1 )); then
            printf '// ==== bun module: %s ====\n' "$(basename "${module_file}" | sed 's/^[0-9]*__//')" >> "${CLI_PRETTIER_JS}"
        fi
        cat "${module_file}" >> "${CLI_PRETTIER_JS}" || {
            echo "Error: failed to append ${module_file} to ${CLI_PRETTIER_JS}" >&2
            exit 1
        }
        printf '\n' >> "${CLI_PRETTIER_JS}"
    done
fi

chmod +x "${CLI_PRETTIER_JS}" || {
    echo "Error: failed to make ${CLI_PRETTIER_JS} executable" >&2
    exit 1
}

COMPLETED=1
echo "Prettified source code for version ${VERSION} has been prepared: ${CLI_PRETTIER_JS}"
