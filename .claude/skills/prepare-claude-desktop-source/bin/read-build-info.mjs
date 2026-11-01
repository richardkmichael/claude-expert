#!/usr/bin/env node
// Given an extracted Claude Desktop app.asar directory, print a JSON manifest describing the build:
// the app's own build info and the Claude Code version the build pins.
//
// Both are embedded in the main-process bundle as `JSON.parse('<json>')` literals, recognized by
// their keys rather than by file or symbol names, which change every build:
//   - build info: the object with "appVersion", "buildType" and "commitHash"
//   - Claude Code pin: the object whose "manifest" carries "manifestSignatureEnforcement"
//
// The extracted files are data. They are read and pattern-matched, never evaluated.

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const [appDir] = process.argv.slice(2);
if (!appDir) {
  console.error("Usage: read-build-info.mjs <extracted-app-dir>");
  process.exit(1);
}
const buildDir = join(appDir, ".vite", "build");

function* jsFiles(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) yield* jsFiles(path);
    else if (name.endsWith(".js")) yield path;
  }
}

// Undo JavaScript single-quoted string escapes so the literal's body can go to JSON.parse.
function unescapeJsString(body) {
  return body.replace(/\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|[\s\S])/g, (_, e) => {
    if (e[0] === "u" && e.length === 5) return String.fromCharCode(parseInt(e.slice(1), 16));
    if (e[0] === "x" && e.length === 3) return String.fromCharCode(parseInt(e.slice(1), 16));
    return { n: "\n", r: "\r", t: "\t", b: "\b", f: "\f", v: "\v", 0: "\0" }[e] ?? e;
  });
}

const LITERAL = /JSON\.parse\('((?:[^'\\]|\\[\s\S])*)'\)/g;

let buildInfo = null;
let claudeCode = null;
const files = [...jsFiles(buildDir)];
for (const file of files) {
  const text = readFileSync(file, "utf8");
  if (!text.includes("appVersion") && !text.includes("manifestSignatureEnforcement")) continue;
  for (const [, body] of text.matchAll(LITERAL)) {
    let value;
    try {
      value = JSON.parse(unescapeJsString(body));
    } catch {
      continue;
    }
    if (value === null || typeof value !== "object") continue;
    if (!buildInfo && "appVersion" in value && "commitHash" in value) {
      buildInfo = { ...value, foundIn: relative(appDir, file) };
    }
    if (!claudeCode && value.manifest && "manifestSignatureEnforcement" in value.manifest) {
      claudeCode = {
        version: value.version,
        commit: value.manifest.commit,
        buildDate: value.manifest.buildDate,
        platforms: Object.keys(value.manifest.platforms ?? {}),
        foundIn: relative(appDir, file),
      };
    }
  }
}

// Count top-level build files by family: the part of the name before ".chunk-", else the name.
const families = {};
for (const name of readdirSync(buildDir)) {
  if (!name.endsWith(".js")) continue;
  const family = name.includes(".chunk-") ? `${name.split(".chunk-")[0]}.chunk-*` : "entry";
  families[family] = (families[family] ?? 0) + 1;
}

if (!buildInfo) console.error("Warning: no build-info literal with appVersion and commitHash found");
if (!claudeCode) console.error("Warning: no Claude Code pin with manifestSignatureEnforcement found");

console.log(
  JSON.stringify(
    { buildInfo, claudeCode, buildFiles: { total: files.length, topLevel: families } },
    null,
    2,
  ),
);
