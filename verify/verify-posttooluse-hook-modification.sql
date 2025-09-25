-- Verify PostToolUse modification:
--
--   claude -p 'Use the Bash tool to run the command: `does-not-exist.sh`'
--
-- PostToolUse received tool execution status (Bash ran, but failed).

SELECT
  hook_event_name AS hook,
  -- SQLite casts JSON `true` and `false` to integers.
  json_extract(payload, '$.tool_execution.success') = 0 AS has_tool_execution,
  created_at
  FROM tool_events
  WHERE tool_name = 'Bash' AND hook_event_name = 'PostToolUse'
  ORDER BY created_at DESC
  LIMIT 1
;
