#!/usr/bin/env node
//
// Extract the JavaScript modules embedded in a bun-compiled Claude Code binary.
//
// The binary ends with a bun standalone container: a data blob holding every embedded module's
// bytes, followed by a 32-byte offsets header and the literal trailer "\n---- Bun! ----\n".  The
// header's first field is the header's own offset within the blob, which is what pins the blob's
// start; deriving it from the blob length instead is off by the header and trailer.
//
// Up to 2.1.241 the whole application sat in one module named "cli", so extracting that module
// alone was enough.  From 2.1.242 it is split across a thousand-odd "/$bunfs/root/chunk-*.js"
// modules behind a small "cli" entry module, and stopping at the entry recovers only a few hundred
// lines of bootstrap.  This walks the whole module table instead.
//
// Usage: extract-bun-modules.mjs <binary> <output-directory>
//
// Writes one file per JavaScript module, named "NNNN__<basename>" so that lexical order matches
// the binary's own module order.  Non-JavaScript modules (native .node addons, markdown, assets)
// and zstd-compressed vendor bundles are skipped: they are not source, and prettier rejects them.
// Prints the number of files written to stdout.

import fs from "node:fs";

const TRAILER = Buffer.from("\n---- Bun! ----\n");
const ZSTD_MAGIC = Buffer.from([0x28, 0xb5, 0x2f, 0xfd]);
const MODULE_STRUCT_SIZE = 52; // 6 (offset, length) pairs plus 4 flag bytes; older bun omits 2 pairs

const [, , binPath, outDir] = process.argv;
if (!binPath || !outDir) {
  console.error("Usage: extract-bun-modules.mjs <binary> <output-directory>");
  process.exit(2);
}

const file = fs.readFileSync(binPath);

const trailerPos = file.lastIndexOf(TRAILER);
if (trailerPos < 0) {
  console.error("Error: bun trailer not found; this is not a bun-compiled binary");
  process.exit(1);
}

const headerPos = trailerPos - 32;
const headerOffsetInBlob = Number(file.readBigUInt64LE(headerPos));
const blob = file.subarray(headerPos - headerOffsetInBlob);

const modulesOffset = blob.readUInt32LE(headerOffsetInBlob + 8);
const modulesLength = blob.readUInt32LE(headerOffsetInBlob + 12);

const structSize = modulesLength % MODULE_STRUCT_SIZE === 0 ? MODULE_STRUCT_SIZE : 36;
const moduleCount = Math.floor(modulesLength / structSize);
if (moduleCount === 0) {
  console.error("Error: bun module table is empty");
  process.exit(1);
}

fs.mkdirSync(outDir, { recursive: true });

let written = 0;
for (let i = 0; i < moduleCount; i++) {
  const entry = modulesOffset + i * structSize;
  const nameOffset = blob.readUInt32LE(entry);
  const nameLength = blob.readUInt32LE(entry + 4);
  const contentsOffset = blob.readUInt32LE(entry + 8);
  const contentsLength = blob.readUInt32LE(entry + 12);

  if (contentsLength === 0 || nameLength === 0 || nameLength > 4096) continue;

  const name = blob.subarray(nameOffset, nameOffset + nameLength).toString("utf8");
  const basename = name.split("/").pop();
  // The entry module is named "cli" (or "claude") with no extension; everything else that is
  // source carries a JavaScript extension.
  const isEntry = basename === "cli" || basename === "claude";
  if (!isEntry && !/\.[cm]?js$/.test(basename)) continue;

  const contents = blob.subarray(contentsOffset, contentsOffset + contentsLength);
  if (contents.subarray(0, 4).equals(ZSTD_MAGIC)) continue;

  let safe = "";
  for (const ch of basename) safe += /[A-Za-z0-9._-]/.test(ch) ? ch : "_";
  const suffix = /\.[cm]?js$/.test(safe) ? "" : ".js";
  fs.writeFileSync(`${outDir}/${String(i).padStart(4, "0")}__${safe.slice(0, 60)}${suffix}`, contents);
  written++;
}

if (written === 0) {
  console.error("Error: no JavaScript modules found in the bun module table");
  process.exit(1);
}

console.log(written);
