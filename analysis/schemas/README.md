# Claude Code JSON Schemas

JSON Schema (Draft 2020-12) definitions derived from the `analysis/` documentation, for validating
Claude Code's own files. Two schemas live here:

| Schema file               | Validates                                         | Derived from                       |
| ------------------------- | ------------------------------------------------- | ---------------------------------- |
| `frontmatter.schema.json` | YAML frontmatter in Markdown config files         | `analysis/MARKDOWN_FRONTMATTER.md` |
| `transcript.schema.json`  | One JSON object per session-transcript JSONL line | `analysis/SESSION_TRANSCRIPT.md`   |

The frontmatter schema (covered first below) is verified against `cli.prettier.js` 2.1.143; the
transcript schema is described under "Transcript schema" at the end.

`frontmatter.schema.json` is a schema library, not a single-shot validator.  The
four file types must be selected explicitly because Memory is intentionally permissive and
would otherwise swallow every document.

| File type     | File pattern                          | JSON Pointer entry           |
| ------------- | ------------------------------------- | ---------------------------- |
| Agent         | `.claude/agents/**/*.md`              | `#/$defs/Agent`              |
| Skill         | `.claude/skills/*/SKILL.md`           | `#/$defs/Skill`              |
| Output style  | `.claude/output-styles/*.md`          | `#/$defs/OutputStyle`        |
| Memory        | `CLAUDE.md`, `**/memory/*.md`, etc.   | `#/$defs/Memory`             |

## Coverage and strictness

- Agent, Skill, and OutputStyle schemas use `additionalProperties: false`, matching Claude
  Code's Zod `.strict()` shadow validator (`HGH`).  Unknown keys are an error.
- Skill `@internal` keys (`mcpServers`, `lspServers`, `agents`, `outputStyles`, `themes`,
  `workflows`, `channels`, `monitors`, `settings`, `experimental`, `dependencies`, `metadata`)
  are accepted but unvalidated, matching the runtime's `y.unknown()` slots.
- Memory frontmatter is permissive (extra keys allowed) since Claude Code only reads `paths`.
  The schema still validates `paths` itself as a string.
- Model values are validated against the documented aliases and the `claude-*` ID pattern.
  Unknown strings fail.  Claude Code's runtime resolver is permissive (passes through to the
  resolver, no warn); the schema is intentionally stricter for lint value.

## Wiring up editors and CI

### yaml-language-server (VS Code, Helix, Neovim via LSP)

Add the schemas to `settings.json` (or your client's equivalent), using a `file://` or HTTPS
URL with a fragment pointer to the right `$defs` entry:

```jsonc
{
  "yaml.schemas": {
    "file:///abs/path/to/frontmatter.schema.json#/$defs/Agent":
      [".claude/agents/**/*.md"],
    "file:///abs/path/to/frontmatter.schema.json#/$defs/Skill":
      [".claude/skills/*/SKILL.md"],
    "file:///abs/path/to/frontmatter.schema.json#/$defs/OutputStyle":
      [".claude/output-styles/*.md"],
    "file:///abs/path/to/frontmatter.schema.json#/$defs/Memory":
      ["CLAUDE.md", "**/CLAUDE.md", "**/memory/*.md"]
  }
}
```

yaml-language-server resolves frontmatter inside Markdown files automatically — it strips
the `---` fences and validates the YAML block.  No additional configuration is required to
extract frontmatter from Markdown.

### Per-file modeline (yaml-language-server)

If editing a one-off file, you can pin the schema with a modeline comment at the top of the
YAML block:

```yaml
---
# yaml-language-server: $schema=file:///abs/path/to/frontmatter.schema.json#/$defs/Skill
name: my-skill
description: ...
---
```

### check-jsonschema (CI)

`check-jsonschema` validates YAML against JSON Schema directly but does not extract
frontmatter from Markdown; pre-process with a small shell helper:

```bash
extract_frontmatter() {
  awk '/^---$/{c++; next} c==1' "$1"
}

for f in .claude/agents/*.md; do
  extract_frontmatter "$f" \
    | check-jsonschema --schemafile schemas/agent-ref.json --instance-filetype yaml -
done
```

Where `agent-ref.json` is a one-line wrapper that points to the right `$defs` entry:

```json
{ "$ref": "file:///abs/path/to/frontmatter.schema.json#/$defs/Agent" }
```

Repeat for Skill, OutputStyle, Memory.

### ajv (Node CI)

```javascript
import Ajv from "ajv";
import addFormats from "ajv-formats";
import schema from "./frontmatter.schema.json" with { type: "json" };
import matter from "gray-matter";
import { readFileSync } from "node:fs";

const ajv = new Ajv({ strict: false, allErrors: true });
addFormats(ajv);
ajv.addSchema(schema, "claude-code");

const validateAgent = ajv.getSchema("claude-code#/$defs/Agent");
const { data } = matter(readFileSync(".claude/agents/foo.md", "utf8"));
if (!validateAgent(data)) console.error(validateAgent.errors);
```

## Known divergences from runtime behaviour

The schema is deliberately stricter than the runtime in places where the runtime silently
coerces values that almost certainly indicate a typo.  See the validation-severity table in
`analysis/MARKDOWN_FRONTMATTER.md` for the full list.  Highlights:

- Agent `model` and Skill `model`: schema errors on unknown aliases; runtime passes the
  string through to the model resolver.
- Skill `description` non-string types: schema accepts string/number/boolean only; runtime
  also accepts these but warns on anything else.
- Memory file with unknown key: schema accepts; runtime ignores.  (Memory is the one type
  where the schema does not enforce strict keys.)

## Updating

When `cli.prettier.js` changes, re-verify against the new version using the workflow in
`analysis/MARKDOWN_FRONTMATTER.md`.  The relevant runtime functions are:

- Agent loader: `s87`, agent strict shadow: `Fe1`
- Skill loader: `hrH` (helper `LE8`), skill strict shadow: `ZT8`
- Output-style loader: `k9K`, strict shadow: `ge1`
- Frontmatter parser: `eY`, sanitizer: `BC1`, runtime dispatch: `KzH`
- Hook event names: `mk` (currently 29 events)
- Permission modes: `Tv`/`vjq`
- Effort enum: `Yg`
- Model aliases: `YqH`

## Transcript schema

`transcript.schema.json` validates a single line of a Claude Code session transcript JSONL file
(`~/.claude/projects/<encoded-cwd>/<sessionId>.jsonl`). The top level is a `oneOf` over every record
type (`user`, `assistant`, `progress`, `attachment`, `system`, and the metadata-only records), with
shared `$defs` for the envelope, content blocks, and the usage object. It carries an
`x-schema-version` (semver). Behavioral reference: `analysis/SESSION_TRANSCRIPT.md`.

Unlike the frontmatter schema, this one is evolved from real data rather than hand-written from a
single bundle read. `bin/generate-transcript-schema.py` samples JSONL files from
`~/.claude/projects/` across Claude Code versions and folds in newly observed record types, fields,
and enum values, bumping `x-schema-version` (minor for a new record type, patch for new enum values
only).

```bash
# dry run (show what would change)
uv run --with jsonschema python3 bin/generate-transcript-schema.py

# apply changes to transcript.schema.json
uv run --with jsonschema python3 bin/generate-transcript-schema.py --apply
```
