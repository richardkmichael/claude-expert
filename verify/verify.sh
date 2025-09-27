#!/usr/bin/env bash

set -euo pipefail

TOOL_MONITOR_DB=$( readlink -f ~/.claude/tool-monitor.sqlite )

CLI_PRETTIER='cli.prettier.js'

# Parse arguments
TEST_ONLY=false

while [[ $# -gt 0 ]]; do
  case $1 in
    -t|--test)
      TEST_ONLY=true
      shift
      ;;
    -*)
      echo "Unknown option $1"
      echo "Usage: $0 [-t|--test] <version>"
      exit 1
      ;;
    *)
      VERSION=$1
      shift
      ;;
  esac
done

# Validate VERSION parameter
if [[ -z "${VERSION:-}" ]]; then
  echo "Error: VERSION parameter is required"
  echo "Usage: $0 [-t|--test] <version>"
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
  #   TODO: Generate a random filename and command name

  # `Read` has implicit permission
  ./claude -p 'Read `does-not-exist-4.txt`'

  sqlite3 -header -cmd '.parameter set :filename does-not-exist-4.txt' ${TOOL_MONITOR_DB} < verify/verify-pretooluse-hook-modification.sql
  # Expected:
  #
  #   hook|has_schema_validation|has_input_validation|file_path|created_at_l
  #   PreToolUse|1|1|/path/to/claude-code-analysis/does-not-exist-4.txt|2025-09-25 17:25:59


  # `Bash` requires permission
  ./claude --allowed-tools Bash -p 'Use the Bash tool to run the command: `does-not-exist.sh`'

  sqlite3 -header -cmd '.parameter set :command does-not-exist.sh' ${TOOL_MONITOR_DB} < verify/verify-posttooluse-hook-modification.sql
  # Expected:
  #
  #   hook|has_tool_execution|error|created_at_l
  #   PostToolUse|1|/opt/homebrew/opt/bash/bin/bash: line 1: does-not-exist.sh: command not found|2025-09-25 18:21:42
}

echo "Claude Code: ${VERSION}"

# Assert
[[ -f "${VERSION}/package/${CLI_PRETTIER}" ]] || { echo "Missing ${VERSION} ${CLI_PRETTIER}, exiting" ; exit 1 ; }

if [[ "${TEST_ONLY}" == "true" ]]; then
  test_claude
else
  symlink_claude

  patch_claude

  test_claude
fi
