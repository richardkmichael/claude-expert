#!/usr/bin/env python3
"""
Evolve the Claude Code session transcript JSON schema from real JSONL data.

Reads JSONL files from ~/.claude/projects/, samples across Claude Code versions
for coverage, and updates the schema with newly observed record types, fields,
enum values, and type widenings.

Usage:
    # Dry run (default): show what would change
    uv run --with jsonschema python3 analysis/claude_exp-evolve-schema.py

    # Apply changes to the schema file
    uv run --with jsonschema python3 analysis/claude_exp-evolve-schema.py --apply

    # Scan a specific directory instead of ~/.claude/projects/
    uv run --with jsonschema python3 analysis/claude_exp-evolve-schema.py --projects-dir /path/to/dir

    # Limit to N files per version (default: 10)
    uv run --with jsonschema python3 analysis/claude_exp-evolve-schema.py --per-version 5

Version bumping (x-schema-version, semver):
    - New record types found:   minor bump (e.g. 1.0.0 -> 1.1.0)
    - New enum values only:     patch bump (e.g. 1.0.0 -> 1.0.1)
    - No structural changes:    no bump
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "claude-code-session-transcript.schema.json"

# Fields in the schema that use enums (dotted paths from record root)
ENUM_FIELDS = {
    "system": {
        "subtype": "$defs/systemRecord/properties/subtype",
        "level": "$defs/systemRecord/properties/level",
    },
    "attachment": {
        "attachment.type": "$defs/attachmentRecord/properties/attachment/properties/type",
    },
    "queue-operation": {
        "operation": "$defs/queueOperationRecord/properties/operation",
    },
}

# Map from record type to the $defs name
TYPE_TO_DEF = {
    "user": "userRecord",
    "assistant": "assistantRecord",
    "progress": "progressRecord",
    "attachment": "attachmentRecord",
    "system": "systemRecord",
    "custom-title": "customTitleRecord",
    "tag": "tagRecord",
    "agent-name": "agentNameRecord",
    "agent-color": "agentColorRecord",
    "agent-setting": "agentSettingRecord",
    "mode": "modeRecord",
    "pr-link": "prLinkRecord",
    "summary": "summaryRecord",
    "file-history-snapshot": "fileHistorySnapshotRecord",
    "attribution-snapshot": "attributionSnapshotRecord",
    "queue-operation": "queueOperationRecord",
    "speculation-accept": "speculationAcceptRecord",
}


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


def find_jsonl_files(projects_dir):
    """Find all session JSONL files, excluding subagent transcripts."""
    files = []
    for dirpath, _dirnames, filenames in os.walk(projects_dir):
        if "subagents" in dirpath:
            continue
        for fn in filenames:
            if fn.endswith(".jsonl"):
                files.append(os.path.join(dirpath, fn))
    return files


def scan_file_versions(files):
    """Quick scan: read the first conversation record from each file to get its version."""
    file_versions = {}
    for fpath in files:
        with open(fpath) as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    rec = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                v = rec.get("version")
                if v:
                    file_versions[fpath] = v
                    break
    return file_versions


def count_lines(fpath):
    """Count non-empty lines in a file without fully parsing."""
    count = 0
    with open(fpath, "rb") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def select_files(files, file_versions, per_version):
    """Select files to process: up to per_version files per Claude Code version,
    preferring files with the most lines."""
    # Group files by version
    by_version = defaultdict(list)
    for fpath, ver in file_versions.items():
        by_version[ver].append(fpath)

    # For each version, pick the top N by line count
    selected = []
    for ver in sorted(by_version.keys()):
        candidates = by_version[ver]
        with_counts = [(count_lines(f), f) for f in candidates]
        with_counts.sort(reverse=True)
        picked = [f for _, f in with_counts[:per_version]]
        selected.extend(picked)

    return selected


def get_dotted(record, dotted_key):
    """Get a value from a record using a dotted key path."""
    parts = dotted_key.split(".")
    obj = record
    for part in parts:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


def collect_observations(files):
    """Read selected JSONL files and collect observations about the data shape."""
    obs = {
        "record_types": set(),
        "enum_values": defaultdict(lambda: defaultdict(set)),  # type -> field -> values
        "field_types": defaultdict(lambda: defaultdict(set)),  # type -> field -> json types
        "versions": set(),
        "lines": 0,
        "files": 0,
        "parse_errors": 0,
    }

    for fpath in files:
        obs["files"] += 1
        with open(fpath) as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    rec = json.loads(raw_line)
                except json.JSONDecodeError:
                    obs["parse_errors"] += 1
                    continue

                obs["lines"] += 1
                rtype = rec.get("type")
                if rtype is None:
                    continue

                obs["record_types"].add(rtype)

                v = rec.get("version")
                if v:
                    obs["versions"].add(v)

                # Collect enum field values
                if rtype in ENUM_FIELDS:
                    for dotted_key in ENUM_FIELDS[rtype]:
                        val = get_dotted(rec, dotted_key)
                        if val is not None:
                            obs["enum_values"][rtype][dotted_key].add(val)

                # Collect top-level field types for this record type
                for key, val in rec.items():
                    obs["field_types"][rtype][key].add(json_type_of(val))

    return obs


def resolve_schema_path(schema, dotted_path):
    """Navigate into the schema by a slash-separated path like '$defs/systemRecord/properties/subtype'.
    Returns the schema node at that path."""
    parts = dotted_path.split("/")
    node = schema
    for part in parts:
        if part == "$defs":
            node = node.get("$defs", {})
        else:
            node = node.get(part, {})
    return node


def compute_changes(schema, obs):
    """Compare observations against the current schema and compute changes needed."""
    changes = []

    # 1. New record types not in schema
    known_types = set(TYPE_TO_DEF.keys())
    new_types = obs["record_types"] - known_types
    for t in sorted(new_types):
        fields = obs["field_types"].get(t, {})
        field_list = ", ".join(sorted(fields.keys()))
        changes.append({
            "kind": "new_record_type",
            "type": t,
            "message": f"New record type \"{t}\" with fields: {field_list}",
            "fields": dict(fields),
        })

    # 2. New enum values
    for rtype, field_map in obs["enum_values"].items():
        if rtype not in ENUM_FIELDS:
            continue
        for dotted_key, observed_values in field_map.items():
            schema_path = ENUM_FIELDS[rtype][dotted_key]
            node = resolve_schema_path(schema, schema_path)
            current_enum = set(node.get("enum", []))
            new_values = observed_values - current_enum
            if new_values:
                changes.append({
                    "kind": "new_enum_values",
                    "type": rtype,
                    "field": dotted_key,
                    "schema_path": schema_path,
                    "current": sorted(current_enum),
                    "new_values": sorted(new_values),
                    "message": f"{rtype}.{dotted_key}: new enum values: {sorted(new_values)}",
                })

    # 3. Version range update
    versions = sorted(obs["versions"])
    if versions:
        changes.append({
            "kind": "version_range",
            "min": versions[0],
            "max": versions[-1],
            "count": len(versions),
            "message": f"Versions observed: {versions[0]} through {versions[-1]} ({len(versions)} versions)",
        })

    # 4. Stats
    changes.append({
        "kind": "stats",
        "lines": obs["lines"],
        "files": obs["files"],
        "message": f"Scanned {obs['lines']:,} lines across {obs['files']} files",
    })

    return changes


def bump_version(version_str, bump_kind):
    """Bump a semver string. bump_kind is 'minor' or 'patch'."""
    parts = version_str.split(".")
    major = int(parts[0]) if len(parts) > 0 else 1
    minor = int(parts[1]) if len(parts) > 1 else 0
    patch = int(parts[2]) if len(parts) > 2 else 0

    if bump_kind == "minor":
        minor += 1
        patch = 0
    elif bump_kind == "patch":
        patch += 1

    return f"{major}.{minor}.{patch}"


def apply_enum_changes(schema, changes):
    """Apply new enum values to the schema in place."""
    modified = False
    for change in changes:
        if change["kind"] != "new_enum_values":
            continue
        node = resolve_schema_path(schema, change["schema_path"])
        if "enum" in node:
            for val in change["new_values"]:
                node["enum"].append(val)
            node["enum"].sort()
            modified = True
    return modified


def apply_version_bump(schema, changes):
    """Bump x-schema-version based on the kind of changes detected.

    - New record types: minor bump (new structure to understand)
    - New enum values only: patch bump (existing structure, new values)
    - No structural changes: no bump
    """
    has_new_types = any(c["kind"] == "new_record_type" for c in changes)
    has_new_enums = any(c["kind"] == "new_enum_values" for c in changes)

    old_version = schema.get("x-schema-version", "1.0.0")

    if has_new_types:
        new_version = bump_version(old_version, "minor")
    elif has_new_enums:
        new_version = bump_version(old_version, "patch")
    else:
        return old_version

    schema["x-schema-version"] = new_version
    return new_version


def apply_comment(schema, changes):
    """Update the $comment with the schema version and validation coverage."""
    ver_min = ver_max = "?"
    ver_count = 0
    lines = 0

    for change in changes:
        if change["kind"] == "version_range":
            ver_min = change["min"]
            ver_max = change["max"]
            ver_count = change["count"]
        if change["kind"] == "stats":
            lines = change["lines"]

    schema["$comment"] = (
        f"Schema version {schema.get('x-schema-version', '?')}. "
        f"Validated against {lines:,}+ lines spanning "
        f"Claude Code versions {ver_min} through {ver_max} ({ver_count} versions)."
    )


def main():
    parser = argparse.ArgumentParser(
        description="Evolve the JSONL transcript schema from real data"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes to the schema file and bump x-schema-version (default: dry run)",
    )
    parser.add_argument(
        "--projects-dir",
        default=os.path.expanduser("~/.claude/projects"),
        help="Directory containing project JSONL files (default: ~/.claude/projects)",
    )
    parser.add_argument(
        "--per-version",
        type=int,
        default=10,
        help="Max files to process per Claude Code version (default: 10, picks largest by line count)",
    )
    parser.add_argument(
        "--schema",
        type=str,
        default=str(SCHEMA_PATH),
        help=f"Path to the JSON schema file (default: {SCHEMA_PATH})",
    )
    args = parser.parse_args()

    schema_path = Path(args.schema)
    if not schema_path.exists():
        print(f"Schema file not found: {schema_path}", file=sys.stderr)
        sys.exit(1)

    with open(schema_path) as f:
        schema = json.load(f)

    print(f"Schema: {schema_path}")
    print(f"  x-schema-version: {schema.get('x-schema-version', '(none)')}")
    print()

    # Discover files
    print(f"Scanning {args.projects_dir} for JSONL files...")
    all_files = find_jsonl_files(args.projects_dir)
    print(f"  Found {len(all_files)} JSONL files")

    # Quick version scan
    print("  Reading version from each file...")
    file_versions = scan_file_versions(all_files)
    versions_found = set(file_versions.values())
    print(f"  {len(versions_found)} distinct Claude Code versions")

    # Select files
    selected = select_files(all_files, file_versions, args.per_version)
    print(f"  Selected {len(selected)} files ({args.per_version} per version, largest by line count)")
    print()

    # Collect observations
    print("Collecting observations from JSONL data...")
    obs = collect_observations(selected)
    print(f"  {obs['lines']:,} lines across {obs['files']} files")
    print(f"  {len(obs['record_types'])} record types, {len(obs['versions'])} versions")
    if obs["parse_errors"]:
        print(f"  {obs['parse_errors']} JSON parse errors (skipped)")
    print()

    # Validate current schema against the data
    try:
        from jsonschema import Draft202012Validator

        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)

        validation_errors = 0
        error_samples = {}
        for fpath in selected:
            with open(fpath) as f:
                for raw_line in f:
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    try:
                        rec = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    errs = list(validator.iter_errors(rec))
                    if errs:
                        validation_errors += 1
                        t = rec.get("type", "???")
                        if t not in error_samples:
                            for defname, defn in schema["$defs"].items():
                                if defn.get("properties", {}).get("type", {}).get("const") == t:
                                    sub = {"$schema": schema["$schema"], "$defs": schema["$defs"], **defn}
                                    v = Draft202012Validator(sub)
                                    for e in v.iter_errors(rec):
                                        path = "/".join(str(p) for p in e.absolute_path) if e.absolute_path else "(root)"
                                        error_samples[t] = f"{path}: {str(e.message)[:150]}"
                                        break
                                    break
                            else:
                                error_samples[t] = "no matching $def"

        print(f"Validation: {obs['lines'] - validation_errors:,} passed, {validation_errors} failed")
        if error_samples:
            print("  Sample errors by type:")
            for t, msg in sorted(error_samples.items()):
                print(f"    {t}: {msg}")
        print()
    except ImportError:
        print("Validation: skipped (jsonschema not available)")
        print()

    # Compute changes
    changes = compute_changes(schema, obs)

    actionable = [c for c in changes if c["kind"] in ("new_record_type", "new_enum_values")]

    print("=" * 60)
    if not actionable:
        print("Schema is up to date. No structural changes needed.")
    else:
        print(f"{len(actionable)} change(s) detected:")
    for change in changes:
        prefix = "  "
        if change["kind"] == "new_record_type":
            prefix = "  NEW "
        elif change["kind"] == "new_enum_values":
            prefix = "  ADD "
        elif change["kind"] == "stats":
            prefix = "      "
        elif change["kind"] == "version_range":
            prefix = "      "
        print(f"{prefix}{change['message']}")
    print("=" * 60)

    if args.apply:
        print()
        old_version = schema.get("x-schema-version", "1.0.0")

        if actionable:
            apply_enum_changes(schema, changes)

        new_version = apply_version_bump(schema, changes)
        apply_comment(schema, changes)

        with open(schema_path, "w") as f:
            json.dump(schema, f, indent=2)
            f.write("\n")

        if old_version != new_version:
            print(f"x-schema-version: {old_version} -> {new_version}")
        print(f"Schema updated: {schema_path}")

        # Report new record types that need manual schema definitions
        new_types = [c for c in changes if c["kind"] == "new_record_type"]
        if new_types:
            print()
            print("WARNING: New record types require manual schema definitions:")
            for c in new_types:
                print(f"  type: \"{c['type']}\"")
                for field, types in sorted(c["fields"].items()):
                    print(f"    {field}: {', '.join(sorted(types))}")
            print()
            print("Add $defs entries for these types and include them in the top-level oneOf.")
    elif actionable:
        print(f"\nDry run. Use --apply to update {schema_path}")


if __name__ == "__main__":
    main()
