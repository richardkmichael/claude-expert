-- Verify PostToolUse modification:
--
--   claude -p 'Use the Bash tool to run the command: `does-not-exist.sh`'
--
-- PostToolUse received tool execution status (Bash ran, but failed).
--
-- Requires :command parameter, e.g.:
--
--   sqlite3 -cmd '.parameter set :command <COMMAND>' db.sqlite < this.sql

SELECT
  hook_event_name AS hook,
  -- SQLite casts JSON `true` and `false` to integers.
  payload ->> '$.tool_execution.success' = 0 AS has_tool_execution,
  payload ->> '$.tool_execution.error_message' AS error,

  -- Localtime for convenience reading tests
  strftime('%Y-%m-%d %H:%M:%S', created_at, 'localtime') AS created_at_l

  FROM
    tool_events
  WHERE
    tool_name = 'Bash'
    AND
    hook_event_name = 'PostToolUse'
    AND

    -- Expected extended hook schema
    payload ->> '$.tool_execution.success' = 0
    AND
    payload ->> '$.tool_execution.error_message' LIKE '%' || :command || '%command not found%'

    AND
    created_at >= datetime('now', '-1 minutes')
  ORDER BY
    created_at DESC
  LIMIT 1
;
