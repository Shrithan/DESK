#!/usr/bin/env node
/**
 * Cartesia proxy: TTS narration (/speak) + STT relay (/stt). Keeps the API
 * key server-side only — the browser never sees it, for either direction.
 *
 * Verified against current Cartesia docs (2026-10-24), not guessed:
 *   TTS: POST https://api.cartesia.ai/tts/bytes
 *        Authorization: Bearer <key>, Cartesia-Version: 2026-08-14
 *   STT: wss://api.cartesia.ai/stt/websocket?model=...&encoding=...&sample_rate=...&cartesia_version=...
 *        X-API-Key: <key> (server-side auth)
 * Both confirmed working with a real key before this was written.
 *
 * Mock mode (no CARTESIA_API_KEY): /speak echoes {mocked:true}; /stt accepts
 * the connection but never reaches Cartesia, so the UI can still be demoed.
 */
import http from "node:http";
import { WebSocketServer, WebSocket } from "ws";

const PORT = process.env.CARTESIA_PROXY_PORT ? Number(process.env.CARTESIA_PROXY_PORT) : 8787;
const API_KEY = process.env.CARTESIA_API_KEY;
const CARTESIA_VERSION = "2026-08-14";
const DEFAULT_VOICE_ID = process.env.CARTESIA_VOICE_ID ?? "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"; // "Skylar", en-US
const STT_MODEL = "ink-whisper";
const STT_SAMPLE_RATE = 16000;
const STT_ENCODING = "pcm_s16le";

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
    const upstream = await fetch("https://api.cartesia.ai/tts/bytes", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${API_KEY}`,
        "Cartesia-Version": CARTESIA_VERSION,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model_id: "sonic-3",
        transcript: text,
        voice: { id: DEFAULT_VOICE_ID },
        output_format: { container: "wav", encoding: "pcm_s16le", sample_rate: 24000 },
      }),
    });

    if (!upstream.ok) throw new Error(`Cartesia responded ${upstream.status}: ${await upstream.text()}`);

    res.writeHead(200, { "Content-Type": "audio/wav" });
    for await (const chunk of upstream.body) res.write(chunk);
    res.end();
  } catch (err) {
    console.warn("[cartesia-proxy] TTS call failed, falling back to mock:", err.message);
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

// --- STT relay: browser <-> this proxy <-> Cartesia, key never leaves the server ---
const wss = new WebSocketServer({ server, path: "/stt" });

wss.on("connection", (client) => {
  if (!API_KEY) {
    client.send(JSON.stringify({ type: "error", message: "mocked: CARTESIA_API_KEY not set on proxy" }));
    client.close();
    return;
  }

  const upstreamUrl =
    `wss://api.cartesia.ai/stt/websocket?model=${STT_MODEL}&encoding=${STT_ENCODING}` +
    `&sample_rate=${STT_SAMPLE_RATE}&cartesia_version=${CARTESIA_VERSION}`;
  const upstream = new WebSocket(upstreamUrl, { headers: { "X-API-Key": API_KEY } });

  // Buffer client audio/commands that arrive before the upstream handshake finishes.
  const pending = [];
  let upstreamOpen = false;

  upstream.on("open", () => {
    upstreamOpen = true;
    for (const msg of pending) upstream.send(msg);
    pending.length = 0;
  });

  upstream.on("message", (data, isBinary) => {
    if (client.readyState === WebSocket.OPEN) client.send(data, { binary: isBinary });
  });

  upstream.on("error", (err) => {
    console.warn("[cartesia-proxy] STT upstream error:", err.message);
    if (client.readyState === WebSocket.OPEN) {
      client.send(JSON.stringify({ type: "error", message: err.message }));
    }
  });

  upstream.on("close", () => {
    if (client.readyState === WebSocket.OPEN) client.close();
  });

  client.on("message", (data, isBinary) => {
    const payload = isBinary ? data : data; // ws delivers text frames as Buffer too; forward as-is.
    if (upstreamOpen) upstream.send(payload, { binary: isBinary });
    else pending.push(payload);
  });

  client.on("close", () => {
    if (upstream.readyState === WebSocket.OPEN) upstream.close();
  });
});

server.listen(PORT, () => {
  console.log(`[cartesia-proxy] listening on :${PORT} (mode: ${API_KEY ? "live" : "mock"}) — POST /speak, WS /stt`);
});
