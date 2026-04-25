- `cli.prettier.js` is "Claude Code". For versions ≤ 2.1.116 it is a minified
  Node.js application shipped via npm; for ≥ 2.1.117 it is the JavaScript
  extracted from a bun-compiled native binary. Either way the prettified form
  lives at `work/<version>/package/cli.prettier.js`.
- It is self-contained: no `package.json`, lock file, or `node_modules` — all
  dependencies are bundled inline.
- The original unminified source is not available.

# Questions

- When the user asks about claude-code source, explore the highest-numbered
  `work/<version>/package/cli.prettier.js`. Pick the largest version, e.g.
  via `ls work/ | sort -V | tail -1`.
