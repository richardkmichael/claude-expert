#!/usr/bin/env python3
"""
Maintain the Claude Code session transcript JSON schema against real data and source.

Reads JSONL files from ~/.claude/projects/, samples across Claude Code versions
for coverage, and reports newly observed record types, fields, enum values, and
type widenings against the current schema. The record-type and enum-field maps
are derived from the schema itself (no hardcoded lists to drift).

Observed data is only a floor: it shows what exists, not whether a field is
required, the complete enum domain, or what a field means. Those are
source-authoritative and come from reading the bundle. So the tool splits work:

    - Auto-applied by --apply: new enum VALUES appended to existing enums, plus an
      x-schema-version patch bump and an x-claude-code coverage refresh.
    - Reported for source-authoritative review (NOT auto-written): new record
      types, new fields, and type widenings. Resolve required/optional, the full
      enum domain, and descriptions from work/<version>/package/cli.prettier.js
      (an LLM step), hand-edit the schema, then re-run with --validate-all.

Usage:
    # Dry run (default): show what would change, validate the sample
    uv run --with jsonschema python3 bin/generate-transcript-schema.py

    # Validate every record in every file; exit non-zero on any failure
    uv run --with jsonschema python3 bin/generate-transcript-schema.py --validate-all

    # Write a machine-readable delta report for the source/LLM resolution step
    uv run --with jsonschema python3 bin/generate-transcript-schema.py --report /tmp/delta.json

    # Apply the safe automatic changes (enum values, version, coverage)
    uv run --with jsonschema python3 bin/generate-transcript-schema.py --apply

    # Scan a specific directory / limit files per version
    uv run --with jsonschema python3 bin/generate-transcript-schema.py --projects-dir DIR --per-version 5

Version bumping (x-schema-version, semver):
    - New enum values appended:  patch bump (done automatically by --apply)
    - New record types / fields:  minor bump, done by hand as part of the curated edit
    - No automatic changes:       no bump
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent.parent / "analysis" / "schemas" / "transcript.schema.json"


def derive_type_to_def(schema):
    """Map each record `type` const to its $defs name, read from the schema.

    Avoids a hardcoded list that drifts as record types are added."""
    out = {}
    for defname, defn in schema.get("$defs", {}).items():
        if not isinstance(defn, dict):
            continue
        const = defn.get("properties", {}).get("type", {}).get("const")
        if isinstance(const, str):
            out[const] = defname
    return out


def derive_enum_fields(schema, type_to_def):
    """For each record type, find its enum-valued fields by walking the $def.

    Returns {record_type: {dotted_data_key: schema_enum_path}}. Handles enums
    declared inline on a property and enums reached through a one-level $ref to a
    shared $def (e.g. permissionMode). Nested object properties (e.g. message.*)
    are followed so dotted keys like "message.stop_reason" resolve. A field that
    is no longer an enum (e.g. attachment.type) simply isn't discovered."""
    defs = schema.get("$defs", {})

    def walk(node_props, data_prefix, schema_prefix, acc):
        for prop, sub in node_props.items():
            if not isinstance(sub, dict):
                continue
            data_key = data_prefix + prop
            ref = sub.get("$ref")
            if ref and ref.startswith("#/$defs/"):
                target = defs.get(ref.split("/")[-1], {})
                if isinstance(target, dict) and "enum" in target:
                    acc[data_key] = ref[2:]  # "#/$defs/permissionMode" -> "$defs/permissionMode"
                continue
            if "enum" in sub:
                acc[data_key] = schema_prefix + "/properties/" + prop
                continue
            if sub.get("type") == "object" and isinstance(sub.get("properties"), dict):
                walk(sub["properties"], data_key + ".", schema_prefix + "/properties/" + prop, acc)

    out = {}
    for rtype, defname in type_to_def.items():
        props = defs.get(defname, {}).get("properties", {})
        acc = {}
        walk(props, "", "$defs/" + defname, acc)
        if acc:
            out[rtype] = acc
    return out


def documented_props(schema, defname):
    """Property names documented for a $def, including envelope fields pulled in
    via an allOf $ref."""
    defs = schema.get("$defs", {})
    defn = defs.get(defname, {})
    props = set(defn.get("properties", {}).keys())
    for sub in defn.get("allOf", []):
        ref = isinstance(sub, dict) and sub.get("$ref")
        if ref and ref.startswith("#/$defs/"):
            target = defs.get(ref.split("/")[-1], {})
            props |= set(target.get("properties", {}).keys())
    return props


def field_allowed_types(schema, defname, field):
    """Best-effort set of JSON types a documented top-level field allows, or None
    if it can't be judged simply ($ref, oneOf/anyOf, const). Records list envelope
    fields as empty stubs, so the real node is resolved from the envelope."""
    defs = schema.get("$defs", {})
    defn = defs.get(defname, {})
    node = defn.get("properties", {}).get(field)
    if node in (None, {}):
        for sub in defn.get("allOf", []):
            ref = isinstance(sub, dict) and sub.get("$ref")
            if ref and ref.startswith("#/$defs/"):
                cand = defs.get(ref.split("/")[-1], {}).get("properties", {}).get(field)
                if cand:
                    node = cand
                    break
    if not isinstance(node, dict) or not node:
        return None
    if "$ref" in node or "oneOf" in node or "anyOf" in node or "const" in node:
        return None
    t = node.get("type")
    if isinstance(t, str):
        return {t}
    if isinstance(t, list):
        return set(t)
    return None


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


def collect_all_versions(files):
    """Full pass over every record's `version` (resumed sessions span versions, so
    the first record understates the range). Returns a sorted list."""
    versions = set()
    for fpath in files:
        with open(fpath, errors="replace") as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    rec = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict) and rec.get("version"):
                    versions.add(rec["version"])
    return sorted(versions)


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


def collect_observations(files, enum_fields):
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
                if rtype in enum_fields:
                    for dotted_key in enum_fields[rtype]:
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


def compute_changes(schema, obs, type_to_def, enum_fields):
    """Compare observations against the current schema and compute changes needed."""
    changes = []

    # 1. New record types not in schema (report-only; needs a hand-written $def)
    known_types = set(type_to_def.keys())
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

    # 2. New enum values (auto-appendable)
    for rtype, field_map in obs["enum_values"].items():
        if rtype not in enum_fields:
            continue
        for dotted_key, observed_values in field_map.items():
            schema_path = enum_fields[rtype][dotted_key]
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

    # 3. New fields and type widenings on known record types (report-only)
    for rtype in sorted(obs["field_types"]):
        if rtype not in type_to_def:
            continue
        defname = type_to_def[rtype]
        documented = documented_props(schema, defname)
        for field in sorted(obs["field_types"][rtype]):
            jtypes = obs["field_types"][rtype][field]
            if field not in documented:
                changes.append({
                    "kind": "new_field",
                    "type": rtype,
                    "field": field,
                    "json_types": sorted(jtypes),
                    "message": f"{rtype}: new field \"{field}\" ({', '.join(sorted(jtypes))})",
                })
                continue
            allowed = field_allowed_types(schema, defname, field)
            if allowed is not None:
                effective = set(jtypes)
                if "number" in allowed:
                    effective.discard("integer")  # JSON Schema number accepts integers
                extra = effective - allowed
                if extra:
                    changes.append({
                        "kind": "type_change",
                        "type": rtype,
                        "field": field,
                        "allowed": sorted(allowed),
                        "observed_extra": sorted(extra),
                        "message": f"{rtype}.{field}: observed {sorted(extra)} outside schema {sorted(allowed)}",
                    })

    # 4. Version range
    versions = sorted(obs["versions"])
    if versions:
        changes.append({
            "kind": "version_range",
            "min": versions[0],
            "max": versions[-1],
            "count": len(versions),
            "message": f"Versions observed: {versions[0]} through {versions[-1]} ({len(versions)} versions)",
        })

    # 5. Stats
    changes.append({
        "kind": "stats",
        "lines": obs["lines"],
        "files": obs["files"],
        "message": f"Scanned {obs['lines']:,} lines across {obs['files']} files",
    })

    return changes


def build_report(schema, changes):
    """Machine-readable delta report for the source-authoritative resolution step."""
    pick = lambda k: [c for c in changes if c["kind"] == k]
    vr = next((c for c in changes if c["kind"] == "version_range"), {})
    st = next((c for c in changes if c["kind"] == "stats"), {})
    return {
        "x-schema-version": schema.get("x-schema-version"),
        "needs_source_review": {
            "new_record_types": [
                {"type": c["type"], "observed_fields": {f: sorted(t) for f, t in c["fields"].items()}}
                for c in pick("new_record_type")
            ],
            "new_fields": [
                {"type": c["type"], "field": c["field"], "json_types": c["json_types"]}
                for c in pick("new_field")
            ],
            "type_widenings": [
                {"type": c["type"], "field": c["field"], "schema_allows": c["allowed"],
                 "observed_also": c["observed_extra"]}
                for c in pick("type_change")
            ],
        },
        "auto_appendable": {
            "new_enum_values": [
                {"type": c["type"], "field": c["field"], "schema_path": c["schema_path"],
                 "current": c["current"], "new_values": c["new_values"]}
                for c in pick("new_enum_values")
            ],
        },
        "version_range": {"min": vr.get("min"), "max": vr.get("max"), "count": vr.get("count")},
        "scanned": {"lines": st.get("lines"), "files": st.get("files")},
        "resolve_from_source": (
            "For each needs_source_review item, read work/<version>/package/cli.prettier.js to "
            "determine required-vs-optional, the complete enum domain, and a description; hand-edit "
            "the schema's $defs accordingly, then re-run with --validate-all to confirm zero failures."
        ),
    }


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
    """Append new enum values to the schema in place. Returns True if anything changed."""
    modified = False
    for change in changes:
        if change["kind"] != "new_enum_values":
            continue
        node = resolve_schema_path(schema, change["schema_path"])
        if "enum" in node:
            for val in change["new_values"]:
                if val not in node["enum"]:
                    node["enum"].append(val)
            # Tolerate null in an enum (e.g. stop_reason); avoid None/str compare.
            node["enum"].sort(key=lambda x: (x is None, str(x)))
            modified = True
    return modified


def apply_version_bump(schema, applied_enum):
    """Patch-bump x-schema-version when new enum values were appended. New record
    types and fields are applied by hand (with the version bumped as part of that
    curated edit), so detection alone does not bump here."""
    old_version = schema.get("x-schema-version", "1.0.0")
    if applied_enum:
        new_version = bump_version(old_version, "patch")
        schema["x-schema-version"] = new_version
        return new_version
    return old_version


def apply_coverage(schema, changes):
    """Update x-claude-code.validated-min/max from the observed version range.

    Leaves $comment and x-claude-code.analyzed untouched: the version lives only
    in x-schema-version, and `analyzed` records the source version a human/LLM
    verified against, which this script does not read."""
    for change in changes:
        if change["kind"] == "version_range":
            xcc = schema.setdefault("x-claude-code", {})
            xcc["validated-min"] = change["min"]
            xcc["validated-max"] = change["max"]
            return


def validate_corpus(schema, files):
    """Validate every record in `files`. Returns (total, failures, groups, versions),
    where groups maps "type/subtype" -> {count, sample}."""
    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    total = failures = 0
    groups = {}
    versions = set()
    for fpath in files:
        with open(fpath, errors="replace") as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    rec = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                total += 1
                if rec.get("version"):
                    versions.add(rec["version"])
                errs = sorted(validator.iter_errors(rec), key=lambda e: list(e.path))
                if errs:
                    failures += 1
                    key = f"{rec.get('type')}/{rec.get('subtype')}"
                    g = groups.setdefault(key, {"count": 0, "sample": None})
                    g["count"] += 1
                    if g["sample"] is None:
                        path = "/".join(str(p) for p in errs[0].path) or "(root)"
                        g["sample"] = f"{path}: {str(errs[0].message)[:160]}"
    return total, failures, groups, versions


def main():
    parser = argparse.ArgumentParser(
        description="Maintain the JSONL transcript schema from real data and source"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the safe automatic changes (enum values, version, coverage). Default: dry run",
    )
    parser.add_argument(
        "--validate-all",
        action="store_true",
        help="Validate every record in every file (not just the sample); exit 1 on any failure",
    )
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Write a JSON delta report to PATH for the source-authoritative resolution step",
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
        help="Max files to sample per Claude Code version (default: 10, picks largest by line count)",
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

    type_to_def = derive_type_to_def(schema)
    enum_fields = derive_enum_fields(schema, type_to_def)

    print(f"Schema: {schema_path}")
    print(f"  x-schema-version: {schema.get('x-schema-version', '(none)')}")
    print()

    # Discover files
    print(f"Scanning {args.projects_dir} for JSONL files...")
    all_files = find_jsonl_files(args.projects_dir)
    print(f"  Found {len(all_files)} JSONL files")

    print("  Reading version from each file...")
    file_versions = scan_file_versions(all_files)
    print(f"  {len(set(file_versions.values()))} distinct Claude Code versions")

    selected = select_files(all_files, file_versions, args.per_version)
    print(f"  Selected {len(selected)} files ({args.per_version} per version, largest by line count)")
    print()

    # Collect observations from the sample
    print("Collecting observations from JSONL data...")
    obs = collect_observations(selected, enum_fields)
    print(f"  {obs['lines']:,} lines across {obs['files']} files")
    print(f"  {len(obs['record_types'])} record types, {len(obs['versions'])} versions")
    if obs["parse_errors"]:
        print(f"  {obs['parse_errors']} JSON parse errors (skipped)")
    print()

    # Validate (full corpus with --validate-all, else the sample)
    failures = 0
    full_versions = None
    validate_files = all_files if args.validate_all else selected
    scope = "full corpus" if args.validate_all else "sample"
    try:
        total, failures, groups, seen_versions = validate_corpus(schema, validate_files)
        print(f"Validation ({scope}): {total - failures:,} passed, {failures} failed")
        if groups:
            print("  Failures by type/subtype:")
            for key in sorted(groups, key=lambda k: -groups[k]["count"])[:15]:
                g = groups[key]
                print(f"    [{g['count']}] {key}  {g['sample']}")
        if args.validate_all:
            full_versions = sorted(seen_versions)
        print()
    except ImportError:
        print("Validation: skipped (jsonschema not available)")
        print()

    # Compute changes against the sampled observations
    changes = compute_changes(schema, obs, type_to_def, enum_fields)

    # An accurate coverage range needs the full corpus (resumed sessions span versions)
    if full_versions is None and args.apply:
        full_versions = collect_all_versions(all_files)
    if full_versions:
        for c in changes:
            if c["kind"] == "version_range":
                c["min"], c["max"], c["count"] = full_versions[0], full_versions[-1], len(full_versions)
                c["message"] = (
                    f"Versions observed (full corpus): {c['min']} through {c['max']} "
                    f"({c['count']} versions)"
                )

    auto = [c for c in changes if c["kind"] == "new_enum_values"]
    review = [c for c in changes if c["kind"] in ("new_record_type", "new_field", "type_change")]

    prefix = {
        "new_enum_values": "  ADD   ",
        "new_record_type": "  TYPE  ",
        "new_field": "  FIELD ",
        "type_change": "  WIDEN ",
    }
    print("=" * 60)
    if not auto and not review:
        print("Schema is up to date. No structural changes needed.")
    else:
        print(f"{len(auto)} auto-appendable, {len(review)} need source review:")
    for change in changes:
        print(f"{prefix.get(change['kind'], '      ')}{change['message']}")
    print("=" * 60)

    if args.report:
        with open(args.report, "w") as f:
            json.dump(build_report(schema, changes), f, indent=2)
            f.write("\n")
        print(f"\nDelta report written: {args.report}")

    if review:
        print()
        print("Source review required (data shows these exist but not their rules):")
        print("  Resolve required/optional, the full enum domain, and a description from")
        print("  work/<version>/package/cli.prettier.js, hand-edit the schema $defs, then")
        print("  re-run with --validate-all. New record types also need a oneOf entry.")

    if args.apply:
        print()
        old_version = schema.get("x-schema-version", "1.0.0")
        applied = apply_enum_changes(schema, changes)
        new_version = apply_version_bump(schema, applied)
        apply_coverage(schema, changes)

        with open(schema_path, "w") as f:
            json.dump(schema, f, indent=2)
            f.write("\n")

        if old_version != new_version:
            print(f"x-schema-version: {old_version} -> {new_version}")
        print(f"Schema updated: {schema_path} (enum values + coverage; review items not written)")
    elif auto or review:
        print(f"\nDry run. --apply appends enum values + coverage to {schema_path}; "
              "review items stay manual.")

    if args.validate_all and failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
