-- Verify PreToolUse modification:
--
--   claude -p 'Read file `does-not-exist.txt`'
--
-- PreToolUse received schema validation passed (well-structured), and input validation failed (no such file).

SELECT
  hook_event_name AS hook,
  -- SQLite casts JSON `true` and `false` to integers.
  json_extract(payload, '$.tool_validation.schema_validation.passed') = 1 AS has_schema_validation,
  json_extract(payload, '$.tool_validation.input_validation.passed') = 0 AS has_input_validation,
  created_at
  FROM tool_events
  WHERE tool_name = 'Read' AND hook_event_name = 'PreToolUse'
  ORDER BY created_at DESC
  LIMIT 1
;
