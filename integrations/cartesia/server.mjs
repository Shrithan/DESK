#!/usr/bin/env node
/**
 * Minimal speech-narration proxy. Zero npm dependencies (Node 18+ has global
 * fetch) so it can run standalone during the hackathon.
 *
 * Keeps the Cartesia API key server-side only — the frontend never sees it.
 * Defaults to MOCK mode (no key, no network call, just echoes the text back)
 * unless CARTESIA_API_KEY is set.
 *
 * TODO before claiming real Cartesia integration: verify the current
 * Cartesia TTS endpoint, auth header, and request/response shape against
 * https://docs.cartesia.ai — do not trust the shape below, it is a
 * best-effort placeholder and must not be presented as a working sponsor
 * integration until confirmed against current docs and tested with a real key.
 */
import http from "node:http";

const PORT = process.env.CARTESIA_PROXY_PORT ? Number(process.env.CARTESIA_PROXY_PORT) : 8787;
const API_KEY = process.env.CARTESIA_API_KEY;

async function handleSpeak(req, res) {
  let body = "";
  for await (const chunk of req) body += chunk;

  let text;
  try {
    text = JSON.parse(body || "{}").text;
  } catch {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "invalid JSON body" }));
    return;
  }

  if (typeof text !== "string" || text.length === 0) {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "missing 'text' string" }));
    return;
  }

  if (!API_KEY) {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ mocked: true, text }));
    return;
  }

  try {
    // UNVERIFIED shape — see TODO above. Any failure here falls back to mock
    // rather than crashing narration for the whole demo.
    const upstream = await fetch("https://api.cartesia.ai/tts/bytes", {
      method: "POST",
      headers: {
        "X-API-Key": API_KEY,
        "Cartesia-Version": "2024-06-10",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ transcript: text, model_id: "sonic-english" }),
    });

    if (!upstream.ok) throw new Error(`Cartesia responded ${upstream.status}`);

    res.writeHead(200, { "Content-Type": "audio/mpeg" });
    const reader = upstream.body;
    for await (const chunk of reader) res.write(chunk);
    res.end();
  } catch (err) {
    console.warn("[cartesia-proxy] live call failed, falling back to mock:", err.message);
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ mocked: true, text, fallbackReason: err.message }));
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

  if (req.method === "POST" && req.url === "/speak") {
    handleSpeak(req, res);
    return;
  }

  res.writeHead(404, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: "not found" }));
});

server.listen(PORT, () => {
  console.log(`[cartesia-proxy] listening on :${PORT} (mode: ${API_KEY ? "live" : "mock"})`);
});
