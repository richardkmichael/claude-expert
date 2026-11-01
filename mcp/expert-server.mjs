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
// findings" loop it writes back what it confirms, so the same research is never paid for
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
//   CLAUDE_CODE_ANALYSIS_DIR  Repo root the experts explore (default: parent of this file)
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

import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { Server } from "@modelcontextprotocol/sdk@1.30.0/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk@1.30.0/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk@1.30.0/types.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = process.env.CLAUDE_CODE_ANALYSIS_DIR || resolve(HERE, "..");
const CLAUDE_BIN = process.env.CLAUDE_BIN || "claude";
const BASE_ALLOWED_TOOLS =
  process.env.EXPERT_ALLOWED_TOOLS || "Read,Grep,Glob,Bash,WebFetch,Write,Edit,Agent,Skill";
// 25 minutes. Researching a question against a 25MB bundle routinely runs past five, and the
// expert's own write-back adds a doc rewrite and a delegated commit on top. The ceiling is the
// calling client's patience, not ours: Claude Code aborts a stdio server that has been silent
// for 30 minutes (CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT), so a budget under that bound holds
// without asking every caller to reconfigure their end.
const TIMEOUT_MS = Number(process.env.EXPERT_TIMEOUT_MS || 1500000);
const MODEL = process.env.EXPERT_MODEL || "opus";
// Per-call overrides come from another agent, not a person, so they are checked against a
// fixed set rather than forwarded to --model as given. EXPERT_MODEL is set by whoever
// registers the server and stays free-form, so it can name a full model id.
const CALLABLE_MODELS = new Set(["opus", "sonnet", "haiku"]);

// Set on every nested session. A copy of this server started inside one (for example from a
// user-scope registration) sees it and offers no tools, so an expert never consults itself.
// The nested sessions also run with --strict-mcp-config, which already keeps this server out;
// the marker covers any path that does not.
const NESTED_MARKER = "CLAUDE_EXPERT_NESTED";
const NESTED = process.env[NESTED_MARKER] === "1";

// The nested sessions load MCP servers from this file only: the repo's own documentation
// servers, and none of the caller's.
const MCP_CONFIG = resolve(REPO_ROOT, ".mcp.json");

const SERVER_INFO = { name: "claude-expert", version: "0.2.0" };

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

// Shared rules for the delegated commit and the dirty-tree check.
const commitRules = (trailer, writablePaths) => [
  [
    "You may create and edit files yourself. You may NOT run `git add`, `git commit`, or any",
    "other git write command yourself, even via Bash. Once your doc edit is ready, use the",
    "Agent tool to delegate the commit to a git-committing subagent, invoked synchronously",
    "(do not set run_in_background — this process exits as soon as you finish, so a",
    "backgrounded commit would be silently orphaned). This repository's memory names the",
    "specific subagent to use and any trailer conventions it follows; consult it. Tell that",
    "subagent exactly which file(s) you changed and why, the commit subject in the format the",
    `root CLAUDE.md gives, and require a \`${trailer}\` trailer on the commit so these commits`,
    "are identifiable and revertible later.",
  ].join(" "),
  [
    "Before writing anything, run `git status --short --",
    `${writablePaths.join(" ")}\` from the repository root and confirm the only dirty paths`,
    "there are ones you are about to touch. If they already hold unrelated modified or staged",
    "files, do not write or commit anything this turn — just answer the question, and mention",
    "in your answer that the repo had unrelated pending changes so the write-back was skipped.",
  ].join(" "),
];

const EXPERTS = [
  {
    name: "ask_claude_code_expert",
    subdir: "code",
    addDirs: [],
    mcpServers: ["claude-code-docs"],
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
    prompt: () =>
      [
        [
          "You are an expert on Claude Code's internals being consulted by another Claude",
          "session in a different project. Your working directory is the repository's code/",
          "subtree. Answer the question precisely from the evidence here: the prettified",
          "sources under work/<version>/ and the curated analysis docs under analysis/. Cite",
          "file:line for concrete claims. Prefer the highest-numbered work/<version>; if the",
          "question concerns a newer published version, prepare it with the",
          "prepare-claude-code-source skill first. Be direct and concrete.",
        ].join(" "),
        [
          "Follow the 'Documenting findings' loop from code/CLAUDE.md: when your research",
          "confirms, corrects, or discovers a durable fact — not for trivial or purely",
          "exploratory questions — update the matching analysis/ doc (or add a new one) in",
          "landmark style and restamp its verified version, exactly as an interactive session",
          "would.",
        ].join(" "),
        ...commitRules("Consulted-by: claude-code-expert", ["code/"]),
      ].join("\n\n"),
  },
  {
    name: "ask_claude_desktop_expert",
    subdir: "desktop",
    addDirs: ["code"],
    mcpServers: ["claude-code-docs", "mcp-specification", "fastmcp_documentation", "prefab_documentation"],
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
    prompt: () =>
      [
        [
          "You are an expert on Claude Desktop's internals being consulted by another Claude",
          "session in a different project. Your working directory is the repository's desktop/",
          "subtree; the code/ subtree is also available to you. Start by running the",
          "prepare-claude-desktop-source skill: it prepares the installed app under",
          "work/<app-version>/ if needed and prints its manifest. Answer the question precisely",
          "from that extracted code and the curated docs under analysis/. Cite file:line for",
          "concrete claims. Be direct and concrete.",
        ].join(" "),
        [
          "Claude Desktop runs the Claude Code version its manifest pins (claudeCode.version).",
          "For anything about that Claude Code, research that exact version, not the newest one",
          "in code/work/: prepare it with the prepare-claude-code-source skill if",
          "code/work/<version>/ is missing, and follow code/CLAUDE.md.",
        ].join(" "),
        [
          "Follow the 'Documenting findings' loop: when your research confirms, corrects, or",
          "discovers a durable fact — not for trivial or purely exploratory questions — update",
          "the matching desktop/analysis/ doc (or add a new one) and restamp the build it was",
          "verified against. Findings about Claude Code itself go to code/analysis/, following",
          "code/CLAUDE.md and code/analysis/GUIDELINES.md, including its rule that version",
          "stamps only move forward.",
        ].join(" "),
        ...commitRules("Consulted-by: claude-desktop-expert", ["desktop/", "code/analysis/"]),
      ].join("\n\n"),
  },
];

const log = (...a) => process.stderr.write(`[claude-expert] ${a.join(" ")}\n`);

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
      enum: ["opus", "sonnet", "haiku"],
      description:
        "Optional. The model the research session runs on. Defaults to opus, which handles " +
        "bundle research well. Pass sonnet for a simple lookup (a flag name, a setting key, a " +
        "string that is either present or absent).",
    },
  },
  required: ["question"],
  additionalProperties: false,
});

function runExpert(expert, { question, session_id, model }) {
  const allowedTools = [BASE_ALLOWED_TOOLS, ...expert.mcpServers.map((s) => `mcp__${s}`)].join(
    ",",
  );
  const args = [
    "-p",
    question,
    "--output-format",
    "json",
    "--allowedTools",
    allowedTools,
    "--append-system-prompt",
    expert.prompt(),
    "--strict-mcp-config",
    "--mcp-config",
    MCP_CONFIG,
  ];
  for (const dir of expert.addDirs) args.push("--add-dir", resolve(REPO_ROOT, dir));
  if (session_id) args.push("--resume", session_id);
  const chosenModel = model && CALLABLE_MODELS.has(model) ? model : MODEL;
  if (chosenModel) args.push("--model", chosenModel);

  // Start the nested session clean: drop the markers that tell a process it is running inside
  // a Claude Code session, so the child behaves like a fresh CLI invocation. Auth is read from
  // on-disk credentials, not these vars.
  const env = { ...process.env, [NESTED_MARKER]: "1" };
  delete env.CLAUDECODE;
  delete env.CLAUDE_CODE_ENTRYPOINT;
  delete env.CLAUDE_CODE_SSE_PORT;
  // An --add-dir directory's CLAUDE.md loads only with this set. Set it here rather than rely
  // on the caller's settings, so the desktop expert always has code/'s instructions.
  if (expert.addDirs.length > 0) env.CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD = "1";

  return new Promise((resolveRun) => {
    const claudeP = spawn(CLAUDE_BIN, args, { cwd: resolve(REPO_ROOT, expert.subdir), env });
    let stdout = "";
    let stderr = "";
    let finished = false;

    const finish = (value) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      resolveRun(value);
    };

    const timer = setTimeout(() => {
      claudeP.kill("SIGKILL");
      finish({
        isError: true,
        text: `Expert timed out after ${TIMEOUT_MS} ms. Try a narrower question.`,
      });
    }, TIMEOUT_MS);

    claudeP.stdout.on("data", (d) => (stdout += d));
    claudeP.stderr.on("data", (d) => (stderr += d));

    claudeP.on("error", (err) => {
      finish({ isError: true, text: `Failed to launch '${CLAUDE_BIN}': ${err.message}` });
    });

    claudeP.on("close", (code) => {
      if (finished) return;
      let parsed;
      try {
        parsed = JSON.parse(stdout);
      } catch {
        finish({
          isError: code !== 0,
          text: stdout.trim() || stderr.trim() || `claude exited with code ${code}`,
        });
        return;
      }
      const answer = typeof parsed.result === "string" ? parsed.result : JSON.stringify(parsed);
      const sid = parsed.session_id;
      const footer = sid
        ? `\n\n---\nResearch session_id: ${sid}\n(Pass this as session_id to ${expert.name} for a follow-up that keeps this context.)`
        : "";
      finish({ isError: Boolean(parsed.is_error), text: answer + footer });
    });
  });
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

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const expert = NESTED ? undefined : EXPERTS.find((e) => e.name === req.params.name);
  if (!expert) {
    return {
      isError: true,
      content: [{ type: "text", text: `Unknown tool: ${req.params.name}` }],
    };
  }
  const question = req.params.arguments?.question;
  if (typeof question !== "string" || question.trim() === "") {
    return { isError: true, content: [{ type: "text", text: "Missing required 'question'." }] };
  }
  const session_id = req.params.arguments?.session_id;
  const model = req.params.arguments?.model;
  log(
    `${expert.name}: question (${question.length} chars)` +
      (session_id ? ` [resume ${session_id}]` : "") +
      ` [model ${model && CALLABLE_MODELS.has(model) ? model : MODEL}]`,
  );
  const out = await runExpert(expert, { question, session_id, model });
  return { isError: out.isError, content: [{ type: "text", text: out.text }] };
});

// No shutdown handling, on purpose. A stdio client signals shutdown by closing stdin — at
// which point it is gone and will not read another response. A well-behaved client only
// closes stdin once it is idle, so the normal path is simply: stdin EOF, the event loop
// empties, the process exits. There is no response to "flush" and nothing to track.
//
// If a call is still running when the client vanishes (an abnormal client exit), its child
// process keeps the event loop alive until it finishes, then the process exits — bounded by
// EXPERT_TIMEOUT_MS, which SIGKILLs the child. We let it finish rather than kill it on
// disconnect: the answer text is lost either way, but the call's real product is the
// write-back it commits to the repo, and killing it mid-write could leave the tree dirty —
// which makes later calls skip their own write-back (see the system prompt). Letting it
// complete is cheaper than the cleanup a half-done write-back would cost.

await server.connect(new StdioServerTransport());
log(
  NESTED
    ? `inside a nested expert session (${NESTED_MARKER}=1): offering no tools`
    : `ready — repo ${REPO_ROOT}, claude '${CLAUDE_BIN}', tools [${BASE_ALLOWED_TOOLS}]`,
);
