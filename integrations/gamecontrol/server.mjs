#!/usr/bin/env node
/**
 * Local proxy that turns a gesture into a REAL OS-level keystroke, sent to
 * whatever window/app currently has focus (System Events has no concept of
 * "the game" — it just presses the key).
 *
 * Two independent safety gates, both required for a real keystroke to fire:
 *   1. The frontend must be "armed" (user explicitly flipped the HUD toggle).
 *   2. This process must be started with GAME_CONTROL_ALLOW_INJECT=1.
 * Without both, every request responds {mocked: true} and nothing is sent.
 *
 * macOS only (uses `osascript` + System Events key codes). First real
 * keystroke will prompt for Accessibility permission for whatever process
 * runs this (Terminal, iTerm, etc.) under System Settings > Privacy &
 * Security > Accessibility.
 */
import http from "node:http";
import { execFile } from "node:child_process";
import { platform } from "node:os";

const PORT = process.env.GAME_CONTROL_PROXY_PORT ? Number(process.env.GAME_CONTROL_PROXY_PORT) : 8788;
const ALLOW_INJECT = process.env.GAME_CONTROL_ALLOW_INJECT === "1" || process.env.GAME_CONTROL_ALLOW_INJECT === "true";
const IS_MACOS = platform() === "darwin";

// macOS System Events key codes.
const KEY_CODES = {
  ArrowLeft: 123,
  ArrowRight: 124,
  ArrowDown: 125,
  ArrowUp: 126,
};

function pressKeyMac(keyCode) {
  return new Promise((resolve, reject) => {
    execFile("osascript", ["-e", `tell application "System Events" to key code ${keyCode}`], (err) => {
      if (err) reject(err);
      else resolve();
    });
  });
}

async function handlePress(req, res) {
  let body = "";
  for await (const chunk of req) body += chunk;

  let key;
  try {
    key = JSON.parse(body || "{}").key;
  } catch {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "invalid JSON body" }));
    return;
  }

  const keyCode = KEY_CODES[key];
  if (keyCode === undefined) {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: `unknown key '${key}', expected one of ${Object.keys(KEY_CODES).join(", ")}` }));
    return;
  }

  if (!ALLOW_INJECT || !IS_MACOS) {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(
      JSON.stringify({
        mocked: true,
        key,
        reason: !IS_MACOS ? "non-macOS host, injection not implemented" : "GAME_CONTROL_ALLOW_INJECT not set",
      }),
    );
    return;
  }

  try {
    await pressKeyMac(keyCode);
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ mocked: false, key }));
  } catch (err) {
    console.warn("[gamecontrol-proxy] osascript failed (check Accessibility permission):", err.message);
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ mocked: true, key, fallbackReason: err.message }));
  }
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

  if (req.method === "POST" && req.url === "/press") {
    handlePress(req, res);
    return;
  }

  res.writeHead(404, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: "not found" }));
});

server.listen(PORT, () => {
  console.log(
    `[gamecontrol-proxy] listening on :${PORT} (inject: ${ALLOW_INJECT && IS_MACOS ? "LIVE — real keystrokes will fire" : "mock"})`,
  );
});
