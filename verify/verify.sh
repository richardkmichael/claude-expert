#!/usr/bin/env bash

set -euo pipefail

TOOL_MONITOR_DB=$( readlink -f ~/.claude/tool-monitor.sqlite )

CLI_PRETTIER='cli.prettier.js'

VERSION=${1}

# Validate VERSION parameter
if [[ -z "${VERSION}" ]]; then
  echo "Error: VERSION parameter is required"
  echo "Usage: $0 <version>"
  exit 1
fi

function patch_claude() {
  # Check if patch directory exists
  if [[ ! -d "patches/${VERSION}" ]]; then
    echo "Error: Patch directory patches/${VERSION} does not exist"
    exit 1
  fi

  # Check if any patch files exist
  if ! ls patches/${VERSION}/*.patch 1> /dev/null 2>&1; then
    echo "Error: No patch files found in patches/${VERSION}/"
    exit 1
  fi

  for p in patches/${VERSION}/*.patch ; do
    patch -p 1 < ${p}
  done
}

function symlink_claude() {
  ln -sf ${VERSION}/package/${CLI_PRETTIER} claude
}

function test_claude() {
  # Check if database exists
  if [[ ! -f "${TOOL_MONITOR_DB}" ]]; then
    echo "Error: Tool monitor database does not exist at ${TOOL_MONITOR_DB}"
    exit 1
  fi

  # Run tests
  #   TODO: Assert expected output

  # `Read` has implicit permission
  ./claude -p 'Read `does-not-exist.txt`'

  sqlite3 ${TOOL_MONITOR_DB} < verify/verify-pretooluse-hook-modification.sql
  # Expected:
  #   hook|has_schema_validation|has_input_validation|created_at
  #   PreToolUse|1|1|2025-09-25 05:23:07


  # `Bash` requires permission
  ./claude --allowed-tools Bash -p 'Use the Bash tool to run the command: `does-not-exist.sh`'

  sqlite3 ${TOOL_MONITOR_DB} < verify/verify-posttooluse-hook-modification.sql
  # Expected:
  #   hook|has_tool_execution|created_at
  #   PostToolUse|1|2025-09-25 05:30:35
}

echo "Claude Code: ${VERSION}"

# Assert
[[ -f "${VERSION}/package/${CLI_PRETTIER}" ]] || { echo "Missing ${VERSION} ${CLI_PRETTIER}, exiting" ; exit 1 ; }

symlink_claude

patch_claude

test_claude
