#!/usr/bin/env node
/**
 * Held-key injection proxy for voice-assigned object roles (steering wheel,
 * gas pedal, etc). Separate from integrations/gamecontrol's old discrete-tap
 * approach (removed) — this holds keys down while the tracked object stays
 * displaced from its calibrated center, like a real pedal/wheel.
 *
 * Safety, same spirit as Agent 3's tilt_keys (independently implemented,
 * not shared code):
 *   - Every key this process has pressed is tracked server-side.
 *   - A stale watchdog force-releases everything if the frontend goes
 *     quiet for more than STALE_MS (frontend crash / tab close / network
 *     drop must never leave a key stuck held).
 *   - SIGINT/SIGTERM/exit all release everything before the process dies.
 *   - Requires VOICECONTROL_ALLOW_INJECT=1 to touch the OS at all; mock
 *     otherwise (logs + responds, sends nothing real).
 *
 * macOS only (osascript/System Events, same as integrations/cartesia... no,
 * same mechanism as the old gamecontrol proxy). First real key-down prompts
 * for Accessibility permission for whatever process runs this.
 */
import http from "node:http";
import { execFile } from "node:child_process";
import { platform } from "node:os";

const PORT = process.env.VOICECONTROL_PROXY_PORT ? Number(process.env.VOICECONTROL_PROXY_PORT) : 8789;
const ALLOW_INJECT = process.env.VOICECONTROL_ALLOW_INJECT === "1" || process.env.VOICECONTROL_ALLOW_INJECT === "true";
const IS_MACOS = platform() === "darwin";
const STALE_MS = 800;

const SPECIAL_KEYS = { space: "{key code 49}" };
const ALLOWED_KEYS = new Set(["w", "a", "s", "d", "space"]);

function appleScriptTarget(key) {
  return SPECIAL_KEYS[key] ?? `"${key}"`;
}

function runKeyEvent(action, key) {
  return new Promise((resolve, reject) => {
    const script = `tell application "System Events" to ${action} ${appleScriptTarget(key)}`;
    execFile("osascript", ["-e", script], (err) => (err ? reject(err) : resolve()));
  });
}

const heldKeys = new Set();
let lastUpdateAt = Date.now();

async function releaseAll(reason) {
  if (heldKeys.size === 0) return;
  console.log(`[voicecontrol-proxy] releasing all held keys (${reason}):`, [...heldKeys]);
  const keys = [...heldKeys];
  heldKeys.clear();
  if (!ALLOW_INJECT || !IS_MACOS) return;
  for (const key of keys) {
    try {
      await runKeyEvent("key up", key);
    } catch (err) {
      console.warn(`[voicecontrol-proxy] failed to release '${key}':`, err.message);
    }
  }
}

setInterval(() => {
  if (heldKeys.size > 0 && Date.now() - lastUpdateAt > STALE_MS) {
    void releaseAll("stale watchdog");
  }
}, 200);

for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, async () => {
    await releaseAll(sig);
    process.exit(0);
  });
}
process.on("exit", () => {
  // Best-effort synchronous-ish release; async osascript calls may not finish
  // before exit, hence the signal handlers above doing the real work.
  if (heldKeys.size > 0) console.warn("[voicecontrol-proxy] exiting with keys still marked held:", [...heldKeys]);
});

async function handleTransition(req, res) {
  let body = "";
  for await (const chunk of req) body += chunk;

  let key, down;
  try {
    ({ key, down } = JSON.parse(body || "{}"));
  } catch {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "invalid JSON body" }));
    return;
  }

  if (!ALLOWED_KEYS.has(key) || typeof down !== "boolean") {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: `expected {key: one of ${[...ALLOWED_KEYS].join(",")}, down: boolean}` }));
    return;
  }

  lastUpdateAt = Date.now();

  if (down) heldKeys.add(key);
  else heldKeys.delete(key);

  if (!ALLOW_INJECT || !IS_MACOS) {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(
      JSON.stringify({
        mocked: true,
        key,
        down,
        reason: !IS_MACOS ? "non-macOS host, injection not implemented" : "VOICECONTROL_ALLOW_INJECT not set",
      }),
    );
    return;
  }

  try {
    await runKeyEvent(down ? "key down" : "key up", key);
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ mocked: false, key, down }));
  } catch (err) {
    console.warn("[voicecontrol-proxy] osascript failed (check Accessibility permission):", err.message);
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ mocked: true, key, down, fallbackReason: err.message }));
  }
}

async function handleReleaseAll(_req, res) {
  await releaseAll("client request");
  res.writeHead(200, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ ok: true }));
}

const server = http.createServer((req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");

  if (req.method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }

  if (req.method === "POST" && req.url === "/key-transition") {
    handleTransition(req, res);
    return;
  }

  if (req.method === "POST" && req.url === "/release-all") {
    handleReleaseAll(req, res);
    return;
  }

  res.writeHead(404, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: "not found" }));
});

server.listen(PORT, () => {
  console.log(
    `[voicecontrol-proxy] listening on :${PORT} (inject: ${ALLOW_INJECT && IS_MACOS ? "LIVE — real keys will be held" : "mock"})`,
  );
});
