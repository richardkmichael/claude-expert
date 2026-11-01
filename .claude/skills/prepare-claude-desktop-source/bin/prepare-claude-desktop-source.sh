#!/usr/bin/env bash
#
# Given a Claude Desktop app bundle (default: the installed /Applications/Claude.app), extract its
# app.asar into desktop/work/<app-version>/app, format the bundled JavaScript, and write
# desktop/work/<app-version>/manifest.json describing the build and the Claude Code version it pins.
#
# A version that is already prepared is reported and left alone, so the script is safe to run at the
# start of every desktop question.

set -euo pipefail

for cmd in npx node mktemp; do
    command -v "$cmd" >/dev/null 2>&1 || {
        echo "Error: required command '$cmd' not found" >&2
        exit 1
    }
done

readonly APP="${1:-/Applications/Claude.app}"
readonly ASAR="${APP}/Contents/Resources/app.asar"
readonly INFO_PLIST="${APP}/Contents/Info.plist"

if [[ ! -f "${ASAR}" || ! -f "${INFO_PLIST}" ]]; then
    echo "Error: ${APP} has no Contents/Resources/app.asar or Contents/Info.plist" >&2
    exit 1
fi

VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "${INFO_PLIST}")" || {
    echo "Error: could not read CFBundleShortVersionString from ${INFO_PLIST}" >&2
    exit 1
}
readonly VERSION

# Anchor the output to the repository, not to the caller's working directory. Layout is
# <repo>/.claude/skills/<skill>/bin/<this script>, so the root is four levels above bin/.
SCRIPT_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -P -- "${SCRIPT_DIR}/../../../.." && pwd)"
DESKTOP_ROOT="${REPO_ROOT}/desktop"
readonly SCRIPT_DIR REPO_ROOT DESKTOP_ROOT

if [[ ! -d "${DESKTOP_ROOT}/analysis" ]]; then
    echo "Error: expected ${DESKTOP_ROOT} to hold analysis/, but it does not" >&2
    echo "       (derived from this script's location: ${SCRIPT_DIR})" >&2
    exit 1
fi

readonly WORK_VERSION_DIR="${DESKTOP_ROOT}/work/${VERSION}"
readonly MANIFEST="${WORK_VERSION_DIR}/manifest.json"

if [[ -f "${MANIFEST}" ]]; then
    echo "Claude Desktop ${VERSION} is already prepared at ${WORK_VERSION_DIR}"
    cat "${MANIFEST}"
    exit 0
fi

if [[ -e "${WORK_VERSION_DIR}" ]]; then
    echo "Error: ${WORK_VERSION_DIR} exists without a manifest.json; remove it and run again" >&2
    exit 1
fi

TEMP_DIR="$(mktemp -d)"
readonly TEMP_DIR

COMPLETED=0
cleanup() {
    rm -rf "${TEMP_DIR}"
    if (( ! COMPLETED )); then
        echo "Preparation of Claude Desktop ${VERSION} failed; removing partial output." >&2
        rm -rf "${WORK_VERSION_DIR}"
    fi
}
trap cleanup EXIT

# @electron/asar is pinned so every prepared version is extracted the same way.
readonly ASAR_VERSION="4.3.1"
npx --yes "@electron/asar@${ASAR_VERSION}" extract "${ASAR}" "${TEMP_DIR}/app" || {
    echo "Error: failed to extract ${ASAR}" >&2
    exit 1
}

# Read the build info before formatting: the embedded JSON literals are matched in their shipped
# form.
node "${SCRIPT_DIR}/read-build-info.mjs" "${TEMP_DIR}/app" > "${TEMP_DIR}/build-info.json" || {
    echo "Error: failed to read build info from the extracted app" >&2
    exit 1
}

# Formatting uses the same pinned oxfmt as the Claude Code pipeline, with the same Prettier-default
# config. `--ignore-path /dev/null` stops oxfmt from skipping files that .gitignore lists.
readonly OXFMT_VERSION="0.73.0"
BUILD_JS=()
while IFS= read -r js_file; do BUILD_JS+=("${js_file}"); done \
    < <(find "${TEMP_DIR}/app/.vite/build" -type f -name '*.js' | sort)
npx --yes "oxfmt@${OXFMT_VERSION}" -c "${SCRIPT_DIR}/oxfmt.json" --ignore-path /dev/null \
    "${BUILD_JS[@]}" > /dev/null || {
    echo "Error: failed to format the files under .vite/build" >&2
    exit 1
}

mkdir -p "${WORK_VERSION_DIR}"
mv "${TEMP_DIR}/app" "${WORK_VERSION_DIR}/app"

node --input-type=module -e '
import { readFileSync, writeFileSync } from "node:fs";
const [infoPath, out, app, plistVersion] = process.argv.slice(1);
const info = JSON.parse(readFileSync(infoPath, "utf8"));
const manifest = { app, infoPlistVersion: plistVersion, ...info };
writeFileSync(out, JSON.stringify(manifest, null, 2) + "\n");
' "${TEMP_DIR}/build-info.json" "${MANIFEST}" "${APP}" "${VERSION}"

COMPLETED=1
echo "Prepared Claude Desktop ${VERSION} at ${WORK_VERSION_DIR}"
cat "${MANIFEST}"
