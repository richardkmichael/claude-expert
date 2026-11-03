#!/usr/bin/env bun
// Claude expert MCP server.
//
// Exposes two tools that answer questions by running a nested headless Claude session
// (`claude -p`) inside this repository:
//
//   ask_claude_code_expert     runs in code/: Claude Code internals, from the prettified
//                              sources under code/work/<version>/ and the docs under
//                              code/analysis/.
//   ask_claude_desktop_expert  runs in desktop/: Claude Desktop internals, from the extracted
//                              app under desktop/work/<app-version>/ and the docs under
//                              desktop/analysis/. It also reads code/, because Desktop
//                              downloads and runs a pinned Claude Code version.
//
// Each nested session starts in its product's subtree, so it loads the root CLAUDE.md and
// that subtree's CLAUDE.md, and finds the root .claude/skills. Per the repo's "Documenting
// findings" rules it writes back what it confirms, so the same research is never paid for
// twice. It delegates the git commit to a git-committing subagent rather than committing
// itself; see the system prompt.
//
// Runtime: bun. The MCP protocol is handled by @modelcontextprotocol/sdk, imported with its
// version pinned in the specifier so bun's auto-install resolves it into its global cache on
// first run — no package.json, no node_modules, no build step. Everything else is Node
// built-ins. Bump the SDK by editing the pinned version in the three import specifiers below.
//
// Transport: MCP over stdio. stdout is the protocol channel and carries nothing but protocol
// messages; all diagnostics go to stderr.
//
// Configuration (environment variables):
//   CLAUDE_EXPERT_DIR         Repo root the experts explore (default: parent of this file).
//                             A relative path resolves against the server's working
//                             directory, which is the calling project's.
//   CLAUDE_BIN                Path to the claude binary (default: "claude" on PATH)
//   EXPERT_ALLOWED_TOOLS      Comma-separated built-in tool allowlist (default: research +
//                             write-back set). Each expert's MCP servers are added to it.
//   EXPERT_TIMEOUT_MS         Per-question wall-clock budget (default: 1500000)
//   EXPERT_MODEL              Model the nested session runs on (default: opus). Without an
//                             explicit --model the nested session resolves the `model` setting
//                             from the caller's own settings.json — whatever `/model` last
//                             wrote — so every question would bill at the rate the calling
//                             session happens to be set to. Pinning it here keeps the cost of
//                             a consultation independent of the caller.
//   EXPERT_EFFORT             Effort level the nested session runs at (default: medium). Pinned
//                             for the same reason as EXPERT_MODEL: without --effort the nested
//                             session takes the caller's `effortLevel` setting or
//                             CLAUDE_CODE_EFFORT_LEVEL.

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { Server } from "@modelcontextprotocol/sdk@1.30.0/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk@1.30.0/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk@1.30.0/types.js";

const log = (...a) => process.stderr.write(`[claude-expert] ${a.join(" ")}\n`);

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(process.env.CLAUDE_EXPERT_DIR || resolve(HERE, ".."));
const CLAUDE_BIN = process.env.CLAUDE_BIN || "claude";
const BASE_ALLOWED_TOOLS =
  process.env.EXPERT_ALLOWED_TOOLS || "Read,Grep,Glob,Bash,WebFetch,Write,Edit,Agent,Skill";
// Shell commands the nested session may not run even though Bash is allowed: the ones that
// discard work or rewrite history. The prompt forbids git writes outright, but a prompt is
// guidance; these rules are enforced. `git add` and `git commit` stay allowed because the
// committing subagent runs under the same session rules and needs them.
const DISALLOWED_TOOLS = [
  "Bash(git push:*)",
  "Bash(git reset:*)",
  "Bash(git rebase:*)",
  "Bash(git checkout:*)",
  "Bash(git switch:*)",
  "Bash(git restore:*)",
  "Bash(git clean:*)",
  "Bash(git stash:*)",
  "Bash(git branch -D:*)",
  "Bash(git branch -d:*)",
  "Bash(rm:*)",
].join(",");
// 25 minutes. Researching a question against a 25MB bundle routinely runs past five, and the
// expert's own write-back adds a doc rewrite and a delegated commit on top. The ceiling is the
// calling client's patience, not ours: Claude Code aborts a stdio server that has been silent
// for 30 minutes (CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT), so a budget under that bound holds
// without asking every caller to reconfigure their end.
const TIMEOUT_MS = Number(process.env.EXPERT_TIMEOUT_MS || 1500000);
// How long a child gets to exit after SIGTERM before its process group is killed.
const KILL_GRACE_MS = 10000;
// How long to wait for the output pipes to drain after the child exits. A process the child
// left running in the background can hold the pipes open indefinitely.
const DRAIN_GRACE_MS = 2000;

// Per-call overrides come from another agent, not a person, so they are checked against a
// fixed set rather than forwarded to the CLI as given. EXPERT_MODEL and EXPERT_EFFORT are set
// by whoever registers the server and stay free-form, so they can name a full model id, or
// xhigh or max.
const MODEL = process.env.EXPERT_MODEL || "opus";
const CALLABLE_MODELS = ["opus", "sonnet", "haiku"];
const EFFORT = process.env.EXPERT_EFFORT || "medium";
const CALLABLE_EFFORTS = ["low", "medium", "high"];
const chooseModel = (model) => (CALLABLE_MODELS.includes(model) ? model : MODEL);
const chooseEffort = (effort) => (CALLABLE_EFFORTS.includes(effort) ? effort : EFFORT);

// A session_id is a UUID. Anything else is refused: the value becomes a CLI argument, and a
// value starting with "-" would otherwise be parsed as a flag of its own.
const SESSION_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Set on every nested session. A copy of this server started inside one (for example from a
// user-scope registration) sees it and offers no tools, so an expert never consults itself.
// The nested sessions also run with --strict-mcp-config, which already keeps this server out;
// the marker covers any path that does not.
const NESTED_MARKER = "CLAUDE_EXPERT_NESTED";
const NESTED = process.env[NESTED_MARKER] === "1";

// The nested sessions load MCP servers from this file only: the repo's own documentation
// servers, and none of the caller's.
const MCP_CONFIG = resolve(REPO_ROOT, ".mcp.json");

const SERVER_INFO = { name: "claude-expert", version: "0.3.0" };

const SERVER_INSTRUCTIONS = [
  "Experts on Claude Code and Claude Desktop internals, backed by a local repository of",
  "extracted sources and analysis docs.",
  "",
  "For a Claude Code question, if a `claude-code-guide` subagent is available, consult it",
  "first: it answers from the published documentation. Call ask_claude_code_expert when the",
  "guide has no answer, gives too little detail, or seems wrong, or when the question is about",
  "undocumented behavior that only the source settles.",
  "",
  "For a Claude Desktop question, call ask_claude_desktop_expert directly.",
  "",
  "Each call can take many minutes. Pass the session_id from a previous answer to continue",
  "that line of research with its context retained.",
].join("\n");

// Shared rules for the answer, the delegated commit and the dirty-tree check. Pathspecs use
// the `:/` prefix so they are relative to the repository root whatever the working directory.
const commonRules = (trailer, writablePaths) => {
  const pathspecs = writablePaths.map((p) => `':/${p}'`).join(" ");
  return [
    [
      "Cite file:line in your answer for concrete claims. In the analysis docs, anchor on",
      "strings instead, as CLAUDE.md requires: never write line numbers or minified names",
      "into a doc.",
    ].join(" "),
    [
      "You may create and edit files yourself. You may NOT run `git add`, `git commit`, or any",
      "other git write command yourself, even via Bash. Once your doc edit is ready, use the",
      "Agent tool to delegate the commit to a git-committing subagent, invoked synchronously",
      "(do not set run_in_background — this process exits as soon as you finish, so a",
      "backgrounded commit would be silently orphaned). If your instructions name a subagent",
      "for git operations, use it, with any trailer conventions they give; otherwise use the",
      "general-purpose subagent. Tell that",
      "subagent exactly which file(s) you changed and why, the commit subject in the format the",
      "root CLAUDE.md gives, to commit only those paths (`git commit --only -- <paths>`), and",
      `to add a \`${trailer}\` trailer so these commits are identifiable and revertible later.`,
    ].join(" "),
    [
      `Before writing anything, run \`git status --short -- ${pathspecs}\` and`,
      "`git diff --cached --quiet`. Write only if the status lists no paths other than ones",
      "you are about to touch and nothing is staged. Otherwise do not write or commit anything",
      "this turn — just answer the question, and say in your answer that the repo had pending",
      "changes so the write-back was skipped.",
    ].join(" "),
  ];
};

const EXPERTS = [
  {
    name: "ask_claude_code_expert",
    subdir: "code",
    addDirs: [],
    writablePaths: ["code/"],
    mcpServers: ["claude-code-docs", "claude-platform-docs"],
    trailer: "Consulted-by: claude-code-expert",
    description:
      "Ask an expert about Claude Code's internals, behavior, or source. A nested Claude " +
      "session researches the answer in a local repository of prettified Claude Code sources " +
      "and analysis docs, then returns its findings. Durable findings are committed back into " +
      "that repository, so asking the same or a similar question later is faster and cheaper. " +
      "If a `claude-code-guide` subagent is available, consult it first; use this tool when the " +
      "guide has no answer, gives too little detail, or seems wrong — e.g. how an undocumented " +
      "feature, flag, prompt, tool, or subagent mechanism actually works. To continue a prior " +
      "line of questioning with the research context intact, pass the session_id returned by " +
      "the previous call.",
    instructions: () => [
      [
        "You are an expert on Claude Code's internals being consulted by another Claude",
        "session in a different project. Your working directory is the repository's code/",
        "subtree. Answer the question precisely from the evidence here: the prettified",
        "sources under work/<version>/ and the curated analysis docs under analysis/. Use the",
        "version the question names; otherwise the highest-numbered work/<version>. If the",
        "version is not prepared, prepare it with the prepare-claude-code-source skill first.",
        "Be direct and concrete.",
      ].join(" "),
      [
        "Record what you find as code/CLAUDE.md and the root CLAUDE.md's 'Documenting",
        "findings' section require: when your research confirms, corrects, or discovers",
        "behavior, update the matching analysis/ doc (or add a new one), exactly as an",
        "interactive session would.",
      ].join(" "),
    ],
  },
  {
    name: "ask_claude_desktop_expert",
    subdir: "desktop",
    addDirs: ["code"],
    writablePaths: ["desktop/", "code/analysis/"],
    mcpServers: [
      "claude-code-docs",
      "claude-platform-docs",
      "mcp-specification",
      "fastmcp_documentation",
      "prefab_documentation",
    ],
    trailer: "Consulted-by: claude-desktop-expert",
    description:
      "Ask an expert about Claude Desktop's internals: the macOS app's process model, config " +
      "stores, environment variables, MCP and MCP Apps hosting, feature flags, and the Claude " +
      "Code version it runs. A nested Claude session researches the answer in the installed " +
      "app's extracted code and a local repository of analysis docs, then returns its " +
      "findings. Durable findings are committed back into that repository, so asking the same " +
      "or a similar question later is faster and cheaper. To continue a prior line of " +
      "questioning with the research context intact, pass the session_id returned by the " +
      "previous call.",
    instructions: () => [
      [
        "You are an expert on Claude Desktop's internals being consulted by another Claude",
        "session in a different project. Your working directory is the repository's desktop/",
        "subtree; the code/ subtree is also available to you. Start by running the",
        "prepare-claude-desktop-source skill: it prepares the installed app under",
        "work/<app-version>/ if needed and prints its manifest. Answer the question precisely",
        "from that extracted code and the curated docs under analysis/. Be direct and concrete.",
      ].join(" "),
      [
        "Claude Desktop runs the Claude Code version its manifest pins (claudeCode.version).",
        "For anything about that Claude Code, research that exact version, not the newest one",
        "in code/work/: prepare it with the prepare-claude-code-source skill if",
        "code/work/<version>/ is missing, and follow code/CLAUDE.md.",
      ].join(" "),
      [
        "Record what you find as step 5 of desktop/CLAUDE.md ('Record what you found') and the",
        "root CLAUDE.md's 'Documenting findings' section require: Desktop findings go in",
        "desktop/analysis/, and findings about Claude Code itself go in code/analysis/,",
        "following code/CLAUDE.md and code/analysis/GUIDELINES.md, including its rule that",
        "version stamps only move forward.",
      ].join(" "),
    ],
  },
];

const systemPrompt = (expert) =>
  [...expert.instructions(), ...commonRules(expert.trailer, expert.writablePaths)].join("\n\n");

const inputSchema = (toolName) => ({
  type: "object",
  properties: {
    question: {
      type: "string",
      description:
        "The question. Be specific; the expert can read source and docs but cannot see your " +
        "project's context.",
    },
    session_id: {
      type: "string",
      description:
        `Optional. The session_id from a previous ${toolName} call, to continue that research ` +
        "conversation with its context retained.",
    },
    model: {
      type: "string",
      enum: CALLABLE_MODELS,
      description:
        `Optional. The model the research session runs on. Defaults to ${MODEL}. Pass sonnet ` +
        "for a simple lookup (a flag name, a setting key, a string that is either present or " +
        "absent).",
    },
    effort: {
      type: "string",
      enum: CALLABLE_EFFORTS,
      description:
        `Optional. The effort (thinking) level the research session runs at. Defaults to ` +
        `${EFFORT}. Pass high for a question that needs tracing behavior across many modules, ` +
        "or low for a simple lookup.",
    },
  },
  required: ["question"],
  additionalProperties: false,
});

// Live children, so a signal to the server can stop them instead of leaving them orphaned.
const children = new Set();

// Children run in their own process group (spawned detached), so a signal reaches the whole
// tree: the claude process and any shell commands, ripgrep runs or formatters it started.
function terminateGroup(child) {
  const signalGroup = (signal) => {
    try {
      process.kill(-child.pid, signal);
    } catch {
      // The group is already gone.
    }
  };
  signalGroup("SIGTERM");
  setTimeout(() => signalGroup("SIGKILL"), KILL_GRACE_MS).unref();
}

// The answer from `claude -p --output-format json`: normally one result object, but a verbose
// setting in the inherited user settings turns it into an array of every message.
function readResult(stdout) {
  let parsed;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    return undefined;
  }
  if (Array.isArray(parsed)) parsed = parsed.findLast((m) => m?.type === "result");
  return parsed && typeof parsed === "object" ? parsed : undefined;
}

function runExpert(expert, { question, sessionId, model, effort }) {
  const allowedTools = [BASE_ALLOWED_TOOLS, ...expert.mcpServers.map((s) => `mcp__${s}`)].join(
    ",",
  );
  // The question goes on stdin, not on the command line, so a question that starts with "-"
  // is not parsed as a flag. Every value below is the server's own, except the session_id,
  // which is checked against SESSION_ID and attached with "=" for the same reason.
  const args = [
    "-p",
    "--output-format",
    "json",
    "--allowedTools",
    allowedTools,
    "--disallowedTools",
    DISALLOWED_TOOLS,
    "--append-system-prompt",
    systemPrompt(expert),
    "--strict-mcp-config",
    "--mcp-config",
    MCP_CONFIG,
    "--model",
    chooseModel(model),
    "--effort",
    chooseEffort(effort),
  ];
  for (const dir of expert.addDirs) args.push("--add-dir", resolve(REPO_ROOT, dir));
  if (sessionId) args.push(`--resume=${sessionId}`);

  // Start the nested session clean: drop the markers that tell a process it is running inside
  // a Claude Code session, so the child behaves like a fresh CLI invocation. Auth is read from
  // on-disk credentials, not these vars. Other inherited variables, such as
  // CLAUDE_CODE_SUBAGENT_MODEL, still apply to the nested session and its subagents.
  const env = { ...process.env, [NESTED_MARKER]: "1" };
  delete env.CLAUDECODE;
  delete env.CLAUDE_CODE_ENTRYPOINT;
  delete env.CLAUDE_CODE_SSE_PORT;
  // CLAUDE_CODE_EFFORT_LEVEL outranks --effort, so an inherited value would override the effort
  // chosen above.
  delete env.CLAUDE_CODE_EFFORT_LEVEL;
  // An --add-dir directory's CLAUDE.md loads only with this set. Set it here rather than rely
  // on the caller's settings, so the desktop expert always has code/'s instructions.
  if (expert.addDirs.length > 0) env.CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD = "1";

  return new Promise((resolveRun) => {
    const child = spawn(CLAUDE_BIN, args, {
      cwd: resolve(REPO_ROOT, expert.subdir),
      env,
      detached: true,
      stdio: ["pipe", "pipe", "pipe"],
    });
    children.add(child);
    let stdout = "";
    let stderr = "";
    let finished = false;
    let drainTimer;

    const finish = (value) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      clearTimeout(drainTimer);
      children.delete(child);
      resolveRun(value);
    };

    const stderrTail = () => stderr.trim().split("\n").slice(-20).join("\n");

    const report = (code) => {
      try {
        const result = readResult(stdout);
        if (result === undefined) {
          finish({
            isError: true,
            text:
              `claude exited with code ${code} without a JSON result.` +
              (stderrTail() ? `\n\n${stderrTail()}` : ""),
          });
          return;
        }
        const answer =
          typeof result.result === "string" ? result.result : JSON.stringify(result, null, 2);
        const footer =
          typeof result.session_id === "string"
            ? `\n\n---\nResearch session_id: ${result.session_id}\n` +
              `(Pass this as session_id to ${expert.name} for a follow-up that keeps this context.)`
            : "";
        finish({ isError: Boolean(result.is_error), text: answer + footer });
      } catch (err) {
        finish({ isError: true, text: `Could not read the expert's answer: ${err.message}` });
      }
    };

    const timer = setTimeout(() => {
      terminateGroup(child);
      finish({
        isError: true,
        text: `Expert timed out after ${TIMEOUT_MS} ms. Try a narrower question.`,
      });
    }, TIMEOUT_MS);

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    // A closed pipe (the child exiting before it reads the question) is reported through
    // `exit`; ignore the write error itself.
    child.stdin.on("error", () => {});
    child.stdin.end(question);

    child.on("error", (err) => {
      const where = existsSync(resolve(REPO_ROOT, expert.subdir))
        ? `'${CLAUDE_BIN}'`
        : `'${CLAUDE_BIN}' in ${resolve(REPO_ROOT, expert.subdir)}`;
      finish({ isError: true, text: `Failed to launch ${where}: ${err.message}` });
    });

    // Report on `exit`, after giving the pipes a short time to drain: waiting for `close`
    // alone would hang on a background process that inherited the child's stdout.
    // Anything the child left running in its process group is stopped too.
    child.on("exit", (code) => {
      children.delete(child);
      terminateGroup(child);
      drainTimer = setTimeout(() => report(code), DRAIN_GRACE_MS);
    });
    child.on("close", (code) => report(code));
  });
}

// ---- Startup checks -------------------------------------------------------------------------

function configError() {
  if (!Number.isInteger(TIMEOUT_MS) || TIMEOUT_MS <= 0 || TIMEOUT_MS > 2 ** 31 - 1)
    return `EXPERT_TIMEOUT_MS must be a whole number of milliseconds between 1 and 2147483647, not '${process.env.EXPERT_TIMEOUT_MS}'`;
  for (const path of [MCP_CONFIG, ...EXPERTS.map((e) => resolve(REPO_ROOT, e.subdir))])
    if (!existsSync(path)) return `${path} does not exist; check CLAUDE_EXPERT_DIR`;
  return undefined;
}

if (!NESTED) {
  const problem = configError();
  if (problem) {
    log(problem);
    process.exit(1);
  }
}

// ---- MCP server -----------------------------------------------------------------------------

const server = new Server(SERVER_INFO, {
  capabilities: { tools: {} },
  ...(NESTED ? {} : { instructions: SERVER_INSTRUCTIONS }),
});

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: NESTED
    ? []
    : EXPERTS.map((e) => ({
        name: e.name,
        description: e.description,
        inputSchema: inputSchema(e.name),
      })),
}));

const failure = (text) => ({ isError: true, content: [{ type: "text", text }] });

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const expert = NESTED ? undefined : EXPERTS.find((e) => e.name === req.params.name);
  if (!expert) return failure(`Unknown tool: ${req.params.name}`);
  const { question, session_id: sessionId, model, effort } = req.params.arguments ?? {};
  if (typeof question !== "string" || question.trim() === "")
    return failure("Missing required 'question'.");
  if (sessionId !== undefined && (typeof sessionId !== "string" || !SESSION_ID.test(sessionId)))
    return failure("'session_id' must be the session_id a previous answer returned.");
  log(
    `${expert.name}: question (${question.length} chars)` +
      (sessionId ? ` [resume ${sessionId}]` : "") +
      ` [model ${chooseModel(model)}] [effort ${chooseEffort(effort)}]`,
  );
  const out = await runExpert(expert, { question, sessionId, model, effort });
  return { isError: out.isError, content: [{ type: "text", text: out.text }] };
});

// ---- Shutdown -------------------------------------------------------------------------------
//
// A stdio client normally shuts a server down by closing stdin once it is idle: the event loop
// empties and the process exits. Claude Code also signals the server (SIGINT, then SIGTERM) on
// session exit and on a /mcp reconnect. The children run in their own process groups, so they
// would outlive the server and its timeouts; on a signal, each child's group gets SIGTERM, which
// lets a nested claude session stop cleanly, then SIGKILL after KILL_GRACE_MS. A write-back cut
// off this way can leave the tree dirty, which only makes later calls skip their own write-back.

let shuttingDown = false;
const shutDown = (signal) => {
  if (shuttingDown) return;
  shuttingDown = true;
  log(`${signal}: stopping ${children.size} running expert session(s)`);
  for (const child of children) terminateGroup(child);
  const deadline = Date.now() + KILL_GRACE_MS + 1000;
  const waitForChildren = () => {
    if (children.size === 0 || Date.now() > deadline) process.exit(0);
    setTimeout(waitForChildren, 200);
  };
  waitForChildren();
};
process.on("SIGINT", () => shutDown("SIGINT"));
process.on("SIGTERM", () => shutDown("SIGTERM"));

await server.connect(new StdioServerTransport());
log(
  NESTED
    ? `inside a nested expert session (${NESTED_MARKER}=1): offering no tools`
    : `ready — repo ${REPO_ROOT}, claude '${CLAUDE_BIN}', tools [${BASE_ALLOWED_TOOLS}]`,
);
