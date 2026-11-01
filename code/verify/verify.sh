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

function check_tool_error() {
  local test_name="$1"
  local output_file="$2"
  local expected_error_pattern="$3"
  local expected_item="$4"

  local error_content
  error_content=$(jq --slurp --raw-output '.[] | select(.type == "user") | .message.content[] | select(.is_error == true) | .content' < "$output_file")

  if [[ -z "$error_content" ]]; then
    echo "ERROR: No tool error detected - expected error for ${expected_item}"
    echo "INFO: The tool may not be working correctly or hooks are not functioning."
    exit 1
  elif echo "$error_content" | grep -q "$expected_error_pattern"; then
    echo "SUCCESS: Found expected ${test_name} error for ${expected_item}"
    echo "INFO: Tool and patches are working correctly"
    return 0
  else
    echo "ERROR: ${error_content}"
    echo "INFO: Expected error about '${expected_item}' not found, but got different error."
    echo "INFO: This likely indicates a problem with the patch - the tool is now broken. Debug the patch."
    exit 1
  fi
}

function symlink_claude() {
  ln -sf ${VERSION}/package/${CLI_PRETTIER} claude
}

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

function test_claude() {
  # Check if database exists
  if [[ ! -f "${TOOL_MONITOR_DB}" ]]; then
    echo "Error: Tool monitor database does not exist at ${TOOL_MONITOR_DB}"
    exit 1
  fi

  # Run tests
  #   TODO: Add hooks and test each was called; how to do so for test `./claude` only?

  # Generate random filename and command name to avoid conflicts
  RANDOM_FILENAME="does-not-exist-$(date +%s)-$RANDOM.txt"
  RANDOM_COMMAND="does-not-exist-$(date +%s)-$RANDOM.sh"

  # Test 1: PreToolUse with Read tool - `Read` has implicit permission
  ./claude \
    --verbose \
    --output-format=stream-json \
    --print "Read '${RANDOM_FILENAME}'.  STOP immediately if Read does not work." > "${VERSION}/verify-pretooluse-read-command-claude-session.json"

  check_tool_error "file-not-found" "${VERSION}/verify-pretooluse-read-command-claude-session.json" "File does not exist" "$RANDOM_FILENAME"

# sqlite3 -header -cmd ".parameter set :filename ${RANDOM_FILENAME}" ${TOOL_MONITOR_DB} < verify/verify-pretooluse-hook-modification.sql
  # Expected:
  #
  #   hook|has_schema_validation|has_input_validation|file_path|created_at_l
  #   PreToolUse|1|1|/path/to/claude-code-analysis/does-not-exist-4.txt|2025-09-25 17:25:59


  # Test 2: PostToolUse with Bash tool - `Bash` requires permission
  ./claude \
    --verbose \
    --allowed-tools Bash \
    --output-format=stream-json \
    --print "Use the Bash tool to run the command: '${RANDOM_COMMAND}'.  STOP immediately if Bash does not work." > "${VERSION}/verify-posttooluse-bash-command-claude-session.json"

  check_tool_error "command-not-found" "${VERSION}/verify-posttooluse-bash-command-claude-session.json" "$RANDOM_COMMAND" "$RANDOM_COMMAND"

# sqlite3 -header -cmd ".parameter set :command ${RANDOM_COMMAND}" ${TOOL_MONITOR_DB} < verify/verify-posttooluse-hook-modification.sql
  # Expected:
  #
  #   hook|has_tool_execution|error|created_at_l
  #   PostToolUse|1|/opt/homebrew/opt/bash/bin/bash: line 1: does-not-exist.sh: command not found|2025-09-25 18:21:42

  echo "SUCCESS: All verification tests passed"
}

echo "Verifying: $( ./claude --version )"

# Assert
[[ -f "${VERSION}/package/${CLI_PRETTIER}" ]] || { echo "Missing ${VERSION} ${CLI_PRETTIER}, exiting" ; exit 1 ; }

if [[ "${TEST_ONLY}" == "true" ]]; then
  test_claude
else
  symlink_claude

  patch_claude

  test_claude
fi
