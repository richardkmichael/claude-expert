-- Verify PreToolUse modification:
--
--   claude -p 'Read file `does-not-exist.txt`'
--
-- PreToolUse received schema validation passed (well-structured), and input validation failed (no such file).
--
-- Requires :filename parameter, e.g.:
--
--   sqlite3 -cmd '.parameter set :filename <FILENAME>' db.sqlite < this.sql

SELECT
  hook_event_name AS hook,
  -- SQLite casts JSON `true` and `false` to integers.
  payload ->> '$.tool_validation.schema_validation.passed' = 1 AS has_schema_validation,
  payload ->> '$.tool_validation.input_validation.passed' = 0 AS has_input_validation,
  payload ->> '$.tool_input.file_path' AS file_path,

  -- Localtime for convenience reading tests
  strftime('%Y-%m-%d %H:%M:%S', created_at, 'localtime') AS created_at_l

  FROM
    tool_events
  WHERE
    tool_name = 'Read'
    AND
    hook_event_name = 'PreToolUse'
    AND

    -- Expected extended hook schema
    payload ->> '$.tool_input.file_path' LIKE '%/' || :filename

    AND
    created_at >= datetime('now', '-1 minutes')
  ORDER BY
    created_at DESC
  LIMIT 1
;
