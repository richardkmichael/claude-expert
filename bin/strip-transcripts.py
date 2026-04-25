#!/usr/bin/env python3
"""Trim toolUseResult.originalFile from JSONL transcripts where filePath contains cli.prettier.js."""

import argparse
import json
import os
import sys
import tempfile


def file_has_targets(path):
    """Fast line scan: return True if any single line has an unprocessed originalFile for cli.prettier.js."""
    with open(path, "rb") as fh:
        for line in fh:
            if b'"originalFile"' in line and b"cli.prettier.js" in line and b'"originalFile":""' not in line:
                return True
    return False


def process_line(line):
    """If line matches, return (modified_line, original_field_len). Otherwise None."""
    if '"originalFile"' not in line or "cli.prettier.js" not in line:
        return None
    obj = json.loads(line)
    tur = obj.get("toolUseResult")
    if not isinstance(tur, dict):
        return None
    fp = tur.get("filePath", "")
    of = tur.get("originalFile", "")
    if "cli.prettier.js" in fp and isinstance(of, str) and len(of) > 1000:
        tur["originalFile"] = ""
        trimmed_line = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"
        return trimmed_line, len(of)
    return None


def process_file(path, dry_run=False):
    """Process a single JSONL file. Returns (occurrences_trimmed, bytes_saved)."""
    original_size = os.path.getsize(path)

    if not file_has_targets(path):
        print(f"  skipped (no targets)")
        return 0, 0

    occurrences = 0
    bytes_saved = 0

    if dry_run:
        with open(path) as fh:
            for i, line in enumerate(fh):
                result = process_line(line)
                if result:
                    _, field_len = result
                    occurrences += 1
                    bytes_saved += field_len
                    print(f"  Line {i}: originalFile len={field_len:,}")
        print(f"  DRY RUN: {occurrences} occurrences, ~{bytes_saved / 1e6:.1f}MB to trim from {original_size / 1e6:.1f}MB")
        return occurrences, bytes_saved

    # Stream to temp file, then atomic rename
    dir_name = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as out, open(path) as fh:
            for i, line in enumerate(fh):
                result = process_line(line)
                if result:
                    trimmed_line, field_len = result
                    occurrences += 1
                    bytes_saved += field_len
                    print(f"  Line {i}: trimmed originalFile ({field_len:,} chars)")
                    out.write(trimmed_line)
                else:
                    out.write(line)
        if occurrences > 0:
            os.replace(tmp_path, path)
        else:
            os.unlink(tmp_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    if occurrences > 0:
        new_size = os.path.getsize(path)
        print(f"  {occurrences} occurrences trimmed, {original_size / 1e6:.1f}MB -> {new_size / 1e6:.1f}MB (saved {(original_size - new_size) / 1e6:.1f}MB)")
    else:
        print(f"  no trimmable targets")
    return occurrences, bytes_saved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", help="JSONL files to process")
    parser.add_argument("-n", "--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--retain", type=int, default=0, metavar="N",
                        help="Skip the N most recent files that have targets")
    args = parser.parse_args()

    if args.retain > 0:
        # Sort by mtime descending, find the N most recent with targets, exclude them
        files_with_mtime = [(p, os.path.getmtime(p)) for p in args.files]
        files_with_mtime.sort(key=lambda x: x[1], reverse=True)
        retained = set()
        for path, _ in files_with_mtime:
            if len(retained) >= args.retain:
                break
            if file_has_targets(path):
                retained.add(path)
        if retained:
            names = [os.path.basename(p) for p in sorted(retained, key=os.path.getmtime, reverse=True)]
            print(f"Retaining {len(retained)} file(s): {', '.join(names)}\n")
    else:
        retained = set()

    total_occ = 0
    total_saved = 0

    for path in args.files:
        print(f"{os.path.basename(path)}:")
        if path in retained:
            print(f"  retained (--retain {args.retain})")
            continue
        occ, saved = process_file(path, dry_run=args.dry_run)
        total_occ += occ
        total_saved += saved

    if len(args.files) > 1:
        print(f"\nTotal: {total_occ} occurrences, ~{total_saved / 1e6:.1f}MB")


if __name__ == "__main__":
    main()
