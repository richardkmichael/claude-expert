#!/usr/bin/env node
// Claude Code Analysis — expert MCP server.
//
// Exposes a single tool, ask_claude_code_expert, that answers questions about
// Claude Code internals by running a nested headless Claude session (`claude -p`)
// with its working directory set to this repository. The nested session inherits
// this project's CLAUDE.md and skills, so it explores the prettified sources under
// work/<version>/ and the curated docs under analysis/ on its own, and — per this
// repo's own "Documenting findings" loop — writes back what it confirms so the
// same research is never paid for twice. It delegates the actual git commit to
// the git-wright subagent rather than committing itself; see the system prompt.
//
// Transport: MCP over stdio (newline-delimited JSON-RPC). stdout is the protocol
// channel and carries nothing but JSON-RPC messages; all diagnostics go to stderr.
//
// Billing note: from 2026-06-15, `claude -p` on a subscription draws from the
// separate monthly Agent SDK credit pool, not your interactive usage limits.
//
// Configuration (environment variables):
//   CLAUDE_CODE_ANALYSIS_DIR  Repo root the expert explores (default: parent of this file)
//   CLAUDE_BIN                Path to the claude binary (default: "claude" on PATH)
//   EXPERT_ALLOWED_TOOLS      Comma-separated tool allowlist (default: research + write-back set)
//   EXPERT_TIMEOUT_MS         Per-question wall-clock budget (default: 300000)
//   EXPERT_MODEL              Optional model override passed to `claude --model`

import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = process.env.CLAUDE_CODE_ANALYSIS_DIR || resolve(HERE, "..");
const CLAUDE_BIN = process.env.CLAUDE_BIN || "claude";
const ALLOWED_TOOLS =
  process.env.EXPERT_ALLOWED_TOOLS || "Read,Grep,Glob,Bash,WebFetch,Write,Edit,Agent";
const TIMEOUT_MS = Number(process.env.EXPERT_TIMEOUT_MS || 300000);
const MODEL = process.env.EXPERT_MODEL || "";

const SERVER_INFO = { name: "claude-code-expert", version: "0.1.0" };
const DEFAULT_PROTOCOL = "2025-06-18";

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
    "ready, use the Agent tool to delegate the commit to subagent_type: git-wright,",
    "invoked synchronously (do not set run_in_background — this process exits as",
    "soon as you finish, so a backgrounded commit would be silently orphaned). Tell",
    "git-wright exactly which file(s) you changed and why, and require it to ALSO",
    "include a `Consulted-by: claude-code-expert` trailer on the commit, in addition",
    "to (not instead of) its own usual `Curated-by: git-wright` trailer, so these",
    "commits are identifiable and revertible later.",
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

// ---- stdio JSON-RPC plumbing -------------------------------------------------

function send(msg) {
  process.stdout.write(JSON.stringify(msg) + "\n");
}

function reply(id, result) {
  send({ jsonrpc: "2.0", id, result });
}

function replyError(id, code, message) {
  send({ jsonrpc: "2.0", id, error: { code, message } });
}

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
    const child = spawn(CLAUDE_BIN, args, { cwd: REPO_ROOT, env });
    let stdout = "";
    let stderr = "";
    let settled = false;

    const finish = (value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolveRun(value);
    };

    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      finish({
        isError: true,
        text: `Expert timed out after ${TIMEOUT_MS} ms. Try a narrower question.`,
      });
    }, TIMEOUT_MS);

    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));

    child.on("error", (err) => {
      finish({
        isError: true,
        text: `Failed to launch '${CLAUDE_BIN}': ${err.message}`,
      });
    });

    child.on("close", (code) => {
      if (settled) return;
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

// ---- request dispatch --------------------------------------------------------

async function handle(msg) {
  const { id, method, params } = msg;
  const isRequest = id !== undefined && id !== null;

  switch (method) {
    case "initialize": {
      const protocolVersion = params?.protocolVersion || DEFAULT_PROTOCOL;
      reply(id, {
        protocolVersion,
        capabilities: { tools: {} },
        serverInfo: SERVER_INFO,
      });
      return;
    }
    case "notifications/initialized":
      return; // notification, no reply
    case "ping":
      if (isRequest) reply(id, {});
      return;
    case "tools/list":
      reply(id, { tools: [TOOL] });
      return;
    case "tools/call": {
      const name = params?.name;
      if (name !== TOOL.name) {
        replyError(id, -32602, `Unknown tool: ${name}`);
        return;
      }
      const question = params?.arguments?.question;
      if (typeof question !== "string" || question.trim() === "") {
        reply(id, {
          isError: true,
          content: [{ type: "text", text: "Missing required 'question'." }],
        });
        return;
      }
      log(`question (${question.length} chars)` +
        (params.arguments.session_id ? ` [resume ${params.arguments.session_id}]` : ""));
      const out = await runExpert({
        question,
        session_id: params.arguments.session_id,
      });
      reply(id, {
        isError: out.isError,
        content: [{ type: "text", text: out.text }],
      });
      return;
    }
    default:
      if (isRequest) replyError(id, -32601, `Method not found: ${method}`);
      return;
  }
}

// ---- stdin reader (newline-delimited JSON) -----------------------------------

let buffer = "";
let pending = 0;
let stdinEnded = false;
const maybeExit = () => {
  if (stdinEnded && pending === 0) process.exit(0);
};

process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  let nl;
  while ((nl = buffer.indexOf("\n")) !== -1) {
    const line = buffer.slice(0, nl).trim();
    buffer = buffer.slice(nl + 1);
    if (!line) continue;
    let msg;
    try {
      msg = JSON.parse(line);
    } catch (e) {
      log(`parse error: ${e.message}`);
      continue;
    }
    pending++;
    Promise.resolve(handle(msg))
      .catch((e) => {
        log(`handler error: ${e?.stack || e}`);
        if (msg && msg.id !== undefined && msg.id !== null) {
          replyError(msg.id, -32603, `Internal error: ${e?.message || e}`);
        }
      })
      .finally(() => {
        pending--;
        maybeExit();
      });
  }
});
// A client closing stdin signals shutdown, but a long-running expert call may
// still be in flight; drain it before exiting so the response is not lost.
process.stdin.on("end", () => {
  stdinEnded = true;
  maybeExit();
});

log(`ready — repo ${REPO_ROOT}, claude '${CLAUDE_BIN}', tools [${ALLOWED_TOOLS}]`);
