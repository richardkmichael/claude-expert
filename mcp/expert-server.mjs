#!/usr/bin/env bun
// Claude Code Analysis — expert MCP server.
//
// Exposes a single tool, ask_claude_code_expert, that answers questions about
// Claude Code internals by running a nested headless Claude session (`claude -p`)
// with its working directory set to this repository. The nested session inherits
// this project's CLAUDE.md and skills, so it explores the prettified sources under
// work/<version>/ and the curated docs under analysis/ on its own, and — per this
// repo's own "Documenting findings" loop — writes back what it confirms so the
// same research is never paid for twice. It delegates the actual git commit to a
// git-committing subagent rather than committing itself; see the system prompt.
//
// Runtime: bun. The MCP protocol is handled by @modelcontextprotocol/sdk, imported
// with its version pinned in the specifier so bun's auto-install resolves it into
// its global cache on first run — no package.json, no node_modules, no build step.
// Everything else is Node built-ins. Bump the SDK by editing the pinned version in
// the three import specifiers below (check `mise outdated` / npm for the latest).
//
// Transport: MCP over stdio. stdout is the protocol channel and carries nothing but
// protocol messages; all diagnostics go to stderr.
//
// Billing note: from 2026-06-15, `claude -p` on a subscription draws from the
// separate monthly Agent SDK credit pool, not your interactive usage limits.
//
// Configuration (environment variables):
//   CLAUDE_CODE_ANALYSIS_DIR  Repo root the expert explores (default: parent of this file)
//   CLAUDE_BIN                Path to the claude binary (default: "claude" on PATH)
//   EXPERT_ALLOWED_TOOLS      Comma-separated tool allowlist (default: research + write-back set)
//   EXPERT_TIMEOUT_MS         Per-question wall-clock budget (default: 1500000)
//   EXPERT_MODEL              Optional model override passed to `claude --model`

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
const ALLOWED_TOOLS =
  process.env.EXPERT_ALLOWED_TOOLS || "Read,Grep,Glob,Bash,WebFetch,Write,Edit,Agent";
// 25 minutes. Researching a question against a 25MB bundle routinely runs past five,
// and the expert's own write-back adds a doc rewrite and a delegated commit on top. The
// ceiling is the calling client's patience, not ours: Claude Code aborts a stdio server
// that has been silent for 30 minutes (CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT), so a budget
// under that bound holds without asking every caller to reconfigure their end.
const TIMEOUT_MS = Number(process.env.EXPERT_TIMEOUT_MS || 1500000);
const MODEL = process.env.EXPERT_MODEL || "";

const SERVER_INFO = { name: "claude-code-expert", version: "0.1.0" };

// The nested session's CLAUDE.md already explains the repo, including the
// "Documenting findings" loop (research a question, then write it back to
// analysis/ so it isn't re-derived next time). This prompt keeps that loop in
// force — it does not override it read-only — and adds the write-back
// mechanics specific to being invoked headlessly by another project.
const SYSTEM_PROMPT = [
  [
    "You are an expert on Claude Code's internals being consulted by another Claude",
    "Code session in a different project. Answer the question precisely from the",
    "evidence in THIS repository: the prettified sources under work/<version>/ and",
    "the curated analysis docs under analysis/. Cite file:line for concrete claims.",
    "Prefer the highest-numbered work/<version>. Be direct and concrete.",
  ].join(" "),
  [
    "Follow this repository's normal 'Documenting findings' loop from CLAUDE.md:",
    "when your research confirms, corrects, or discovers a durable fact — not for",
    "trivial or purely exploratory questions — update the matching analysis/ doc (or",
    "add a new one) in landmark style and restamp its verified version, exactly as",
    "an interactive session here would.",
  ].join(" "),
  [
    "You may create and edit files yourself. You may NOT run `git add`, `git commit`,",
    "or any other git write command yourself, even via Bash. Once your doc edit is",
    "ready, use the Agent tool to delegate the commit to a git-committing subagent,",
    "invoked synchronously (do not set run_in_background — this process exits as soon",
    "as you finish, so a backgrounded commit would be silently orphaned). This",
    "repository's memory names the specific subagent to use and any trailer",
    "conventions it follows; consult it. Tell that subagent exactly which file(s) you",
    "changed and why, and require it to include a `Consulted-by: claude-code-expert`",
    "trailer on the commit so these commits are identifiable and revertible later.",
  ].join(" "),
  [
    "Before writing anything, run `git status --short` yourself and confirm the only",
    "dirty paths are ones you are about to touch. If the working tree already has",
    "unrelated modified or staged files, do not write or commit anything this turn —",
    "just answer the question, and mention in your answer that the repo had",
    "unrelated pending changes so the write-back was skipped.",
  ].join(" "),
].join("\n\n");

const log = (...a) => process.stderr.write(`[cc-expert] ${a.join(" ")}\n`);

// ---- the expert tool ---------------------------------------------------------

const TOOL = {
  name: "ask_claude_code_expert",
  description:
    "Ask an expert about Claude Code's internals, behavior, or source. A nested " +
    "Claude session researches the answer by exploring a local repository of " +
    "prettified Claude Code sources and analysis docs, then returns its findings. " +
    "Durable findings get committed back into that repository, so asking the " +
    "same or a similar question again later is faster and cheaper. " +
    "Use this when the public Claude Code documentation is insufficient — e.g. " +
    "how an undocumented feature, flag, prompt, tool, or subagent mechanism " +
    "actually works. To continue a prior line of questioning with the research " +
    "context intact, pass the session_id returned by the previous call.",
  inputSchema: {
    type: "object",
    properties: {
      question: {
        type: "string",
        description:
          "The question about Claude Code internals. Be specific; the expert can " +
          "read source and docs but cannot see your project's context.",
      },
      session_id: {
        type: "string",
        description:
          "Optional. The session_id from a previous ask_claude_code_expert call, " +
          "to continue that research conversation with its context retained.",
      },
    },
    required: ["question"],
    additionalProperties: false,
  },
};

function runExpert({ question, session_id }) {
  const args = [
    "-p",
    question,
    "--output-format",
    "json",
    "--allowedTools",
    ALLOWED_TOOLS,
    "--append-system-prompt",
    SYSTEM_PROMPT,
  ];
  if (session_id) args.push("--resume", session_id);
  if (MODEL) args.push("--model", MODEL);

  // Start the nested session clean: drop the markers that tell a process it is
  // running inside a Claude Code session, so the child behaves like a fresh CLI
  // invocation. Auth is read from on-disk credentials, not these vars.
  const env = { ...process.env };
  delete env.CLAUDECODE;
  delete env.CLAUDE_CODE_ENTRYPOINT;
  delete env.CLAUDE_CODE_SSE_PORT;

  return new Promise((resolveRun) => {
    const claudeP = spawn(CLAUDE_BIN, args, { cwd: REPO_ROOT, env });
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
      finish({
        isError: true,
        text: `Failed to launch '${CLAUDE_BIN}': ${err.message}`,
      });
    });

    claudeP.on("close", (code) => {
      if (finished) return;
      let parsed;
      try {
        parsed = JSON.parse(stdout);
      } catch {
        finish({
          isError: code !== 0,
          text:
            (stdout.trim() || stderr.trim() || `claude exited with code ${code}`) +
            "",
        });
        return;
      }
      const answer =
        typeof parsed.result === "string" ? parsed.result : JSON.stringify(parsed);
      const sid = parsed.session_id;
      const footer = sid
        ? `\n\n---\nResearch session_id: ${sid}\n(Pass this as session_id to ask_claude_code_expert for a follow-up that keeps this context.)`
        : "";
      finish({ isError: Boolean(parsed.is_error), text: answer + footer });
    });
  });
}

// ---- MCP server --------------------------------

const server = new Server(SERVER_INFO, { capabilities: { tools: {} } });

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: [TOOL] }));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  if (req.params.name !== TOOL.name) {
    return {
      isError: true,
      content: [{ type: "text", text: `Unknown tool: ${req.params.name}` }],
    };
  }
  const question = req.params.arguments?.question;
  if (typeof question !== "string" || question.trim() === "") {
    return {
      isError: true,
      content: [{ type: "text", text: "Missing required 'question'." }],
    };
  }
  const session_id = req.params.arguments?.session_id;
  log(
    `question (${question.length} chars)` +
      (session_id ? ` [resume ${session_id}]` : ""),
  );
  const out = await runExpert({ question, session_id });
  return {
    isError: out.isError,
    content: [{ type: "text", text: out.text }],
  };
});

// No shutdown handling, on purpose. A stdio client signals shutdown by closing
// stdin — at which point it is gone and will not read another response. A
// well-behaved client only closes stdin once it is idle, so the normal path is
// simply: stdin EOF, the event loop empties, the process exits. There is no
// response to "flush" and nothing to track.
//
// If a call is still running when the client vanishes (an abnormal client exit),
// its child process keeps the event loop alive until it finishes, then the
// process exits — bounded by EXPERT_TIMEOUT_MS, which SIGKILLs the child. We let
// it finish rather than kill it on disconnect: the answer text is lost either
// way, but the call's real product is the write-back it commits to the repo, and
// killing it mid-write could leave the tree dirty — which makes later calls skip
// their own write-back (see the system prompt). Letting it complete is cheaper
// than the cleanup a half-done write-back would cost.

await server.connect(new StdioServerTransport());
log(`ready — repo ${REPO_ROOT}, claude '${CLAUDE_BIN}', tools [${ALLOWED_TOOLS}]`);
