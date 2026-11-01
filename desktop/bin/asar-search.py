#!/usr/bin/env python3
"""Given a byte string, list the files inside an app.asar archive that contain it.

Searches the archive in place, without extracting it, and prints one line per matching file: its
path inside the archive, its size, and the match count. Useful for finding which of several hundred
code-split chunks holds a string.

Usage: asar-search.py <needle> [app.asar]   (default: the installed Claude Desktop's app.asar)

Format: an 8-byte pickle header whose second word is the header size, then the string framing
and a JSON directory, then the concatenated file bodies starting at 8 + header size. Entries
flagged `unpacked` have no body in the archive; they live beside it in app.asar.unpacked/.
"""

import json
import struct
import sys

DEFAULT_ASAR = "/Applications/Claude.app/Contents/Resources/app.asar"


def walk(node, path=""):
    for name, entry in node.get("files", {}).items():
        child = f"{path}/{name}"
        if "files" in entry:
            yield from walk(entry, child)
        else:
            yield child, entry


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__.split("\n\n")[2])
    needle = sys.argv[1].encode()
    asar = sys.argv[2] if len(sys.argv) == 3 else DEFAULT_ASAR
    with open(asar, "rb") as f:
        header_size = struct.unpack("<II", f.read(8))[1]
        json_size = struct.unpack("<II", f.read(8))[1]
        directory = json.loads(f.read(json_size).decode())
        base = 8 + header_size
        for path, entry in walk(directory):
            if not entry.get("size") or "offset" not in entry:
                continue
            f.seek(base + int(entry["offset"]))
            body = f.read(int(entry["size"]))
            count = body.count(needle)
            if count:
                print(f"{path}\t{entry['size']}\t{count}")


if __name__ == "__main__":
    main()
