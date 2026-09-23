#!/usr/bin/env python3
"""
Maintain the Claude Code session transcript JSON schema against real data and source.

The schema (analysis/schemas/transcript.schema.json) is source-authoritative: its record
types, fields, required lists and enum domains come from reading the Claude Code bundle.
Real transcripts are a floor.  They prove what the schema must accept, but not whether a
field is required, what the complete enum domain is, or what a field means.  This script
measures the gap between the two and applies only the part of the gap that data alone can
settle.

How it works
------------

1. Discover transcripts.  Every *.jsonl under ~/.claude/projects/, main sessions and
   subagent transcripts alike.  Workflow journals (subagents/workflows/*/journal.jsonl)
   use a different record format and are skipped.

2. Derive the schema's shape.  Nothing is hardcoded; three discriminated families are
   read from the schema itself:

     family       discriminator            where the payload sits      schema source
     ------------ ------------------------ --------------------------- ------------------------------
     record       record `type`            the JSONL line               top-level `oneOf` $refs
     attachment   attachment `type`        record.attachment            if/then entries in the
                                                                        attachment payload's `allOf`
     block        content block `type`     message.content[] items      $defs reachable from the
                                                                        user/assistant `message`
                                                                        property with a `type` const

   For each member $def, the enum-valued fields (inline `enum`, a one-level $ref to an
   enum $def, or nested inside object properties) are also derived.

3. Observe.  Every line of every file is parsed, in parallel.  For each family member
   the script records the top-level fields of the payload with their JSON types, and the
   values seen for every enum-valued field.

4. Validate.  Every record is validated against the schema, in parallel.  Failures are
   grouped by record type/subtype with one sample error each.  This is the only check
   that sees below a payload's top level, so nested changes surface here, not in step 5.

5. Compare and report.  Observations are compared with the schema:

     ADD    new enum value on a known field          auto-applied by --apply
     TYPE   record type with no $def                  source review
     SUB    attachment or block subtype with no $def  source review
     FIELD  field absent from the member's $def       source review
     WIDEN  JSON type outside the declared `type`     source review

   Review items are never written automatically, because their rules (required or
   optional, the full enum domain, the description) have to come from the bundle.

6. Apply (--apply).  Append new enum values, patch-bump x-schema-version when any were
   appended, and set x-claude-code.validated-min/max to the observed version range.  The
   file is rewritten in its canonical layout (see format_schema), so a small change is a
   small diff.

Refresh workflow
----------------

  1. Run the script, optionally with --report DELTA.json for a machine-readable delta.
  2. For each review item, read work/<version>/package/cli.prettier.js for the writer,
     then hand-edit the schema: add the $def (new record types also need a top-level
     `oneOf` entry; new attachment subtypes need an if/then entry in the attachment
     payload's `allOf`; new blocks need a $ref in the relevant content union), and set
     x-claude-code.analyzed to the bundle version read.
  3. Re-run until validation reports zero failures and no review items remain.
  4. Bump x-schema-version by hand: minor for new record types, subtypes or fields.
     --apply bumps patch for enum-only changes.
  5. Run with --apply to fold in enum values and coverage, and to normalize the layout.

Usage
-----

    uv run --with jsonschema python3 bin/generate-transcript-schema.py             # dry run
    uv run --with jsonschema python3 bin/generate-transcript-schema.py --report D.json
    uv run --with jsonschema python3 bin/generate-transcript-schema.py --apply
    uv run --with jsonschema python3 bin/generate-transcript-schema.py --format-only

The exit status is 1 when any record fails validation.
"""

import argparse
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent.parent / "analysis" / "schemas" / "transcript.schema.json"

FAMILIES = ("record", "attachment", "block")


# ---------------------------------------------------------------------------
# Versions and JSON types


def version_key(version):
    """Sort key for a Claude Code version string ("2.1.98" < "2.1.281")."""
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return (0,)


def json_type_of(value):
    """Return the JSON Schema type name for a Python value."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


# ---------------------------------------------------------------------------
# Schema introspection


def def_name(ref):
    """"#/$defs/userRecord" -> "userRecord"; None for anything else."""
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        return ref.split("/")[-1]
    return None


def type_const(defn):
    const = defn.get("properties", {}).get("type", {}).get("const") if isinstance(defn, dict) else None
    return const if isinstance(const, str) else None


def derive_record_defs(schema):
    """Record `type` -> $def name, from the top-level oneOf."""
    defs = schema.get("$defs", {})
    out = {}
    for entry in schema.get("oneOf", []):
        name = def_name(entry.get("$ref"))
        const = name and type_const(defs.get(name))
        if const:
            out[const] = name
    return out


def attachment_payload_node(schema):
    """The schema node for attachmentRecord.properties.attachment, or {}."""
    return schema.get("$defs", {}).get("attachmentRecord", {}).get("properties", {}).get("attachment", {})


def derive_attachment_defs(schema):
    """Attachment `type` -> $def name, from the payload's allOf if/then entries."""
    out = {}
    for entry in attachment_payload_node(schema).get("allOf", []):
        const = entry.get("if", {}).get("properties", {}).get("type", {}).get("const")
        name = def_name(entry.get("then", {}).get("$ref"))
        if isinstance(const, str) and name:
            out[const] = name
    return out


def derive_block_defs(schema):
    """Content block `type` -> $def name: every $def with a `type` const reachable from
    the user/assistant `message` property."""
    defs = schema.get("$defs", {})
    out, seen = {}, set()

    def walk(node):
        if isinstance(node, dict):
            name = def_name(node.get("$ref"))
            if name and name not in seen:
                seen.add(name)
                target = defs.get(name, {})
                const = type_const(target)
                if const:
                    out.setdefault(const, name)
                walk(target)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for record in ("userRecord", "assistantRecord"):
        walk(defs.get(record, {}).get("properties", {}).get("message", {}))
    return out


def derive_enum_fields(schema, defname):
    """Enum-valued fields of a $def: {dotted_data_key: schema_path}.

    Handles an inline `enum`, a one-level $ref to an enum $def (e.g. permissionMode), and
    enums nested inside object properties (dotted keys like "message.stop_reason")."""
    defs = schema.get("$defs", {})
    acc = {}

    def walk(props, data_prefix, schema_prefix):
        for prop, sub in props.items():
            if not isinstance(sub, dict):
                continue
            data_key = data_prefix + prop
            name = def_name(sub.get("$ref"))
            if name:
                if "enum" in defs.get(name, {}):
                    acc[data_key] = "$defs/" + name
                continue
            if "enum" in sub:
                acc[data_key] = schema_prefix + "/properties/" + prop
            elif sub.get("type") == "object" and isinstance(sub.get("properties"), dict):
                walk(sub["properties"], data_key + ".", schema_prefix + "/properties/" + prop)

    walk(defs.get(defname, {}).get("properties", {}), "", "$defs/" + defname)
    return acc


def derive_families(schema):
    """{family: {discriminator: $def name}} for record, attachment and block."""
    return {
        "record": derive_record_defs(schema),
        "attachment": derive_attachment_defs(schema),
        "block": derive_block_defs(schema),
    }


def documented_props(schema, defname):
    """Property names documented for a $def, including those pulled in via allOf $refs."""
    defs = schema.get("$defs", {})
    defn = defs.get(defname, {})
    props = set(defn.get("properties", {}).keys())
    for sub in defn.get("allOf", []):
        name = isinstance(sub, dict) and def_name(sub.get("$ref"))
        if name:
            props |= set(defs.get(name, {}).get("properties", {}).keys())
    return props


def field_allowed_types(schema, defname, field):
    """Best-effort set of JSON types a documented top-level field allows, or None if it
    can't be judged simply ($ref, oneOf/anyOf, const).  Records list envelope fields as
    empty stubs, so the real node is resolved from the allOf $ref."""
    defs = schema.get("$defs", {})
    defn = defs.get(defname, {})
    node = defn.get("properties", {}).get(field)
    if node in (None, {}):
        for sub in defn.get("allOf", []):
            name = isinstance(sub, dict) and def_name(sub.get("$ref"))
            if name:
                candidate = defs.get(name, {}).get("properties", {}).get(field)
                if candidate:
                    node = candidate
                    break
    if not isinstance(node, dict) or not node:
        return None
    if "$ref" in node or "oneOf" in node or "anyOf" in node or "const" in node:
        return None
    declared = node.get("type")
    if isinstance(declared, str):
        return {declared}
    if isinstance(declared, list):
        return set(declared)
    return None


def resolve_schema_path(schema, path):
    """Navigate into the schema by a slash-separated path like '$defs/systemRecord/properties/subtype'."""
    node = schema
    for part in path.split("/"):
        node = node.get(part, {})
    return node


# ---------------------------------------------------------------------------
# Canonical layout
#
# The schema is read by people as much as by validators, so it is kept in a compact
# layout: short leaf schemas sit on one line, a `properties` block aligns its one-line
# values, and $defs entries are separated by blank lines.  json.dump(indent=2) would
# spread the file over thousands of lines, so --apply writes through this formatter.

MAX_LINE = 200


def _depth(value):
    if isinstance(value, dict):
        return 1 + max((_depth(v) for v in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_depth(v) for v in value), default=0)
    return 0


def _inline(value):
    if isinstance(value, dict):
        if not value:
            return "{}"
        return "{ " + ", ".join(f"{json.dumps(k)}: {_inline(v)}" for k, v in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(_inline(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def _fits_inline(prefix, value, key=None):
    if key in ("oneOf", "anyOf", "allOf") and len(value) > 2:
        return False
    if isinstance(value, dict) and "properties" in value:
        return False
    return _depth(value) <= 3 and len(prefix) + len(_inline(value)) <= MAX_LINE


def _format(value, indent=0, key=None):
    pad = "  " * (indent + 1)
    if isinstance(value, dict):
        if not value:
            return "{}"
        labels = {k: json.dumps(k) + ":" for k in value}
        width = 0

        def inlinable(k, v):
            label = labels[k].ljust(width) if key == "properties" else labels[k]
            return key != "$defs" and k != "properties" and _fits_inline(pad + label + " ", v, k)

        if key == "properties":
            # Padding to the widest one-line key can push a line over MAX_LINE, so the width
            # is measured unpadded, then re-measured with that padding applied.
            width = max((len(labels[k]) for k, v in value.items() if inlinable(k, v)), default=0)
            width = max((len(labels[k]) for k, v in value.items() if inlinable(k, v)), default=0)
        lines = []
        for k, v in value.items():
            if inlinable(k, v):
                label = labels[k].ljust(width) if key == "properties" else labels[k]
                lines.append(f"{pad}{label} {_inline(v)}")
            else:
                lines.append(f"{pad}{labels[k]} {_format(v, indent + 1, k)}")
        separator = ",\n\n" if key == "$defs" else ",\n"
        return "{\n" + separator.join(lines) + "\n" + "  " * indent + "}"
    if isinstance(value, list):
        if all(not isinstance(v, (dict, list)) for v in value):
            return _inline(value)
        items = [pad + (_inline(v) if _fits_inline(pad, v) else _format(v, indent + 1)) for v in value]
        return "[\n" + ",\n".join(items) + "\n" + "  " * indent + "]"
    return _inline(value)


def format_schema(schema):
    """Serialize the schema in its canonical layout (deterministic and idempotent)."""
    return _format(schema) + "\n"


# ---------------------------------------------------------------------------
# Corpus scanning (parallel)


def find_jsonl_files(projects_dir):
    """Every transcript JSONL under projects_dir, including subagent transcripts.
    Workflow journals use a different record format and are skipped."""
    files = []
    for dirpath, _dirnames, filenames in os.walk(projects_dir):
        if f"{os.sep}subagents{os.sep}workflows" in dirpath:
            continue
        files.extend(os.path.join(dirpath, fn) for fn in filenames if fn.endswith(".jsonl"))
    return sorted(files)


def iter_records(fpath):
    with open(fpath, errors="replace") as f:
        for raw_line in f:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                yield None
                continue
            if isinstance(record, dict):
                yield record


def family_payloads(record):
    """Yield (family, payload) for the record and each attachment/block it carries."""
    yield "record", record
    if record.get("type") == "attachment" and isinstance(record.get("attachment"), dict):
        yield "attachment", record["attachment"]
    message = record.get("message")
    if record.get("type") in ("user", "assistant") and isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    yield "block", block


def get_dotted(obj, dotted_key):
    for part in dotted_key.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


_worker = {}


def _init_worker(schema, enum_fields, record_defs, validate):
    """Build per-process state.  A record is validated against its own type's $def rather
    than the top-level oneOf: the record `type` consts are distinct, so the verdict is the
    same, but it avoids trying every branch and yields an error naming the failing field."""
    _worker["enum_fields"] = enum_fields
    _worker["validators"] = None
    if validate:
        from jsonschema import Draft202012Validator

        base = {k: v for k, v in schema.items() if k != "oneOf"}
        _worker["validators"] = {
            rtype: Draft202012Validator({**base, "$ref": f"#/$defs/{name}"}) for rtype, name in record_defs.items()
        }
        _worker["validators"][None] = Draft202012Validator(schema)


def _validator_for(record):
    validators = _worker["validators"]
    return validators.get(record.get("type"), validators[None])


def _scan_file(fpath):
    """Observe and validate one file.  Returns plain dicts/sets for merging."""
    enum_fields = _worker["enum_fields"]
    validate = _worker["validators"] is not None
    fields = {f: {} for f in FAMILIES}  # family -> discriminator -> field -> {json types}
    enums = {f: {} for f in FAMILIES}  # family -> discriminator -> dotted key -> {values}
    versions, failures = set(), {}
    lines = parse_errors = 0
    for record in iter_records(fpath):
        if record is None:
            parse_errors += 1
            continue
        lines += 1
        if record.get("version"):
            versions.add(record["version"])
        for family, payload in family_payloads(record):
            disc = payload.get("type")
            if not isinstance(disc, str):
                continue
            by_field = fields[family].setdefault(disc, {})
            for key, value in payload.items():
                by_field.setdefault(key, set()).add(json_type_of(value))
            for dotted_key in enum_fields[family].get(disc, {}):
                value = get_dotted(payload, dotted_key)
                if value is not None and not isinstance(value, (dict, list)):
                    enums[family].setdefault(disc, {}).setdefault(dotted_key, set()).add(value)
        if validate:
            errors = sorted(_validator_for(record).iter_errors(record), key=lambda e: list(e.path))
            if errors:
                group = f"{record.get('type')}/{record.get('subtype') or (record.get('attachment') or {}).get('type')}"
                entry = failures.setdefault(group, [0, None])
                entry[0] += 1
                if entry[1] is None:
                    path = "/".join(str(p) for p in errors[0].path) or "(root)"
                    entry[1] = f"{path}: {str(errors[0].message)[:160]}"
    return fields, enums, versions, failures, lines, parse_errors


def scan_corpus(schema, families, files, jobs, validate):
    """Parse every record of every file in parallel; merge observations and failures."""
    enum_fields = {
        family: {disc: derive_enum_fields(schema, name) for disc, name in members.items()}
        for family, members in families.items()
    }
    obs = {
        "fields": {f: {} for f in FAMILIES},
        "enums": {f: {} for f in FAMILIES},
        "versions": set(),
        "failures": {},
        "lines": 0,
        "parse_errors": 0,
        "files": len(files),
    }
    initargs = (schema, enum_fields, families["record"], validate)
    with Pool(jobs, initializer=_init_worker, initargs=initargs) as pool:
        for fields, enums, versions, failures, lines, parse_errors in pool.imap_unordered(_scan_file, files, chunksize=4):
            for family in FAMILIES:
                for disc, by_field in fields[family].items():
                    merged = obs["fields"][family].setdefault(disc, {})
                    for key, types in by_field.items():
                        merged.setdefault(key, set()).update(types)
                for disc, by_key in enums[family].items():
                    merged = obs["enums"][family].setdefault(disc, {})
                    for key, values in by_key.items():
                        merged.setdefault(key, set()).update(values)
            obs["versions"] |= versions
            for group, (count, sample) in failures.items():
                entry = obs["failures"].setdefault(group, [0, sample])
                entry[0] += count
            obs["lines"] += lines
            obs["parse_errors"] += parse_errors
    obs["enum_fields"] = enum_fields
    return obs


# ---------------------------------------------------------------------------
# Comparison


def _label(family, disc):
    return disc if family == "record" else f"{family}:{disc}"


def compute_changes(schema, families, obs):
    """Compare observations against the schema.  Returns a list of change dicts."""
    changes = []
    for family in FAMILIES:
        members = families[family]
        for disc in sorted(obs["fields"][family]):
            observed = obs["fields"][family][disc]
            label = _label(family, disc)
            if disc not in members:
                changes.append({
                    "kind": "new_record_type" if family == "record" else "new_subtype",
                    "family": family,
                    "type": disc,
                    "fields": {k: sorted(v) for k, v in sorted(observed.items())},
                    "message": f"{label}: no $def (fields: {', '.join(sorted(observed))})",
                })
                continue
            defname = members[disc]
            documented = documented_props(schema, defname)
            for field in sorted(observed):
                jtypes = observed[field]
                if field not in documented:
                    changes.append({
                        "kind": "new_field",
                        "family": family,
                        "type": disc,
                        "field": field,
                        "json_types": sorted(jtypes),
                        "message": f"{label}: new field \"{field}\" ({', '.join(sorted(jtypes))})",
                    })
                    continue
                allowed = field_allowed_types(schema, defname, field)
                if allowed is None:
                    continue
                effective = set(jtypes)
                if "number" in allowed:
                    effective.discard("integer")  # JSON Schema number accepts integers
                extra = effective - allowed
                if extra:
                    changes.append({
                        "kind": "type_change",
                        "family": family,
                        "type": disc,
                        "field": field,
                        "allowed": sorted(allowed),
                        "observed_extra": sorted(extra),
                        "message": f"{label}.{field}: observed {sorted(extra)} outside schema {sorted(allowed)}",
                    })

        for disc, by_key in sorted(obs["enums"][family].items()):
            for dotted_key, values in sorted(by_key.items()):
                schema_path = obs["enum_fields"][family][disc][dotted_key]
                current = resolve_schema_path(schema, schema_path).get("enum", [])
                new_values = values - set(current)
                if new_values:
                    ordered = sorted(new_values, key=str)
                    changes.append({
                        "kind": "new_enum_values",
                        "family": family,
                        "type": disc,
                        "field": dotted_key,
                        "schema_path": schema_path,
                        "current": list(current),
                        "new_values": ordered,
                        "message": f"{_label(family, disc)}.{dotted_key}: new enum values {ordered}",
                    })
    return changes


def build_report(schema, changes, obs, version_range):
    """Machine-readable delta for the source-authoritative resolution step."""
    def pick(kind):
        return [{k: v for k, v in c.items() if k not in ("kind", "message")} for c in changes if c["kind"] == kind]

    return {
        "x-schema-version": schema.get("x-schema-version"),
        "needs_source_review": {
            "new_record_types": pick("new_record_type"),
            "new_subtypes": pick("new_subtype"),
            "new_fields": pick("new_field"),
            "type_widenings": pick("type_change"),
            "validation_failures": {g: {"count": c, "sample": s} for g, (c, s) in sorted(obs["failures"].items())},
        },
        "auto_appendable": {"new_enum_values": pick("new_enum_values")},
        "version_range": version_range,
        "scanned": {"lines": obs["lines"], "files": obs["files"]},
    }


# ---------------------------------------------------------------------------
# Apply


def bump_patch(version_str):
    major, minor, patch = (list(map(int, version_str.split("."))) + [0, 0, 0])[:3]
    return f"{major}.{minor}.{patch + 1}"


def apply_changes(schema, changes, version_range):
    """Append new enum values, patch-bump when any were appended, refresh coverage.
    Returns True when enum values were appended."""
    appended = False
    for change in changes:
        if change["kind"] != "new_enum_values":
            continue
        node = resolve_schema_path(schema, change["schema_path"])
        for value in change["new_values"]:
            if value not in node["enum"]:
                node["enum"].append(value)
                appended = True
    if appended:
        schema["x-schema-version"] = bump_patch(schema.get("x-schema-version", "1.0.0"))
    if version_range["min"]:
        coverage = schema.setdefault("x-claude-code", {})
        coverage["validated-min"] = version_range["min"]
        coverage["validated-max"] = version_range["max"]
    return appended


# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Maintain the JSONL transcript schema from real data and source")
    parser.add_argument("--apply", action="store_true",
                        help="Append new enum values, refresh coverage, rewrite in canonical layout. Default: dry run")
    parser.add_argument("--report", metavar="PATH", help="Write a JSON delta report to PATH")
    parser.add_argument("--format-only", action="store_true",
                        help="Rewrite the schema in its canonical layout and exit (no scan)")
    parser.add_argument("--projects-dir", default=os.path.expanduser("~/.claude/projects"),
                        help="Directory containing transcript JSONL files (default: ~/.claude/projects)")
    parser.add_argument("--schema", default=str(SCHEMA_PATH), help=f"Schema file (default: {SCHEMA_PATH})")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4, help="Worker processes (default: CPU count)")
    args = parser.parse_args()

    schema_path = Path(args.schema)
    schema = json.loads(schema_path.read_text())

    if args.format_only:
        schema_path.write_text(format_schema(schema))
        print(f"Formatted: {schema_path}")
        return

    try:
        from jsonschema import Draft202012Validator

        Draft202012Validator.check_schema(schema)
        validate = True
    except ImportError:
        validate = False

    families = derive_families(schema)
    print(f"Schema: {schema_path}  (x-schema-version {schema.get('x-schema-version', '(none)')})")
    print("  " + ", ".join(f"{len(families[f])} {f} $defs" for f in FAMILIES))

    files = find_jsonl_files(args.projects_dir)
    print(f"Scanning {len(files)} JSONL files under {args.projects_dir} with {args.jobs} workers...")
    obs = scan_corpus(schema, families, files, args.jobs, validate)
    versions = sorted(obs["versions"], key=version_key)
    version_range = {"min": versions[0] if versions else None, "max": versions[-1] if versions else None,
                     "count": len(versions)}
    print(f"  {obs['lines']:,} records, versions {version_range['min']} through {version_range['max']} "
          f"({version_range['count']} versions)")
    if obs["parse_errors"]:
        print(f"  {obs['parse_errors']} unparseable lines skipped")
    print()

    failures = sum(count for count, _ in obs["failures"].values())
    if validate:
        print(f"Validation: {obs['lines'] - failures:,} passed, {failures:,} failed")
        for group, (count, sample) in sorted(obs["failures"].items(), key=lambda kv: -kv[1][0]):
            print(f"  [{count}] {group}  {sample}")
    else:
        print("Validation: skipped (run under `uv run --with jsonschema`)")
    print()

    changes = compute_changes(schema, families, obs)
    prefix = {"new_enum_values": "ADD  ", "new_record_type": "TYPE ", "new_subtype": "SUB  ",
              "new_field": "FIELD", "type_change": "WIDEN"}
    auto = [c for c in changes if c["kind"] == "new_enum_values"]
    review = [c for c in changes if c["kind"] != "new_enum_values"]
    print("=" * 72)
    if not changes:
        print("No differences between the schema and the observed data.")
    else:
        print(f"{len(auto)} auto-appendable, {len(review)} need source review:")
        for change in changes:
            print(f"  {prefix[change['kind']]} {change['message']}")
    print("=" * 72)

    if args.report:
        Path(args.report).write_text(json.dumps(build_report(schema, changes, obs, version_range), indent=2) + "\n")
        print(f"Delta report written: {args.report}")

    if review or failures:
        print("\nSource review: resolve each item from work/<version>/package/cli.prettier.js and")
        print("hand-edit the schema (see the refresh workflow in this script's docstring).")

    if args.apply:
        old_version = schema.get("x-schema-version")
        apply_changes(schema, changes, version_range)
        schema_path.write_text(format_schema(schema))
        if schema.get("x-schema-version") != old_version:
            print(f"\nx-schema-version: {old_version} -> {schema['x-schema-version']}")
        print(f"Schema updated: {schema_path} (enum values and coverage; review items not written)")
    elif auto:
        print(f"\nDry run. --apply appends the enum values and refreshes coverage in {schema_path}.")

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
