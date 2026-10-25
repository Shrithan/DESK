"""HTTP API + diagnostics page for camera ingest.

Endpoints (all read-only):
  GET /                                   diagnostics page: live feeds + health + sync
  GET /api/cameras                        camera inventory (phantom.camera_inventory v1)
  GET /api/health                         compact health summary for agent 4 (poll <= 1 Hz)
  GET /api/sync                           frameset spread / completeness statistics
  GET /api/calibration                    the loaded rig calibration JSON (404 if none)
  GET /api/cameras/{id}/snapshot.jpg      newest frame; timestamps in X-* headers
  GET /api/cameras/{id}/stream.mjpg       MJPEG preview (diagnostics only, rate-limited)
  GET /api/frameset                       timestamp-matched frames as JSON + base64 JPEG
High-rate consumers in the same process should use CameraHub directly (camera/README.md).
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from .frame import CameraFrame
from .ingest import CameraHub


def _encode(img: np.ndarray, max_width: int | None, quality: int) -> bytes:
    if max_width and img.shape[1] > max_width:
        s = max_width / img.shape[1]
        img = cv2.resize(img, (max_width, int(round(img.shape[0] * s))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("jpeg encode failed")
    return buf.tobytes()


def _frame_headers(f: CameraFrame) -> dict[str, str]:
    return {
        "X-Camera-Id": f.camera_id,
        "X-Frame-Index": str(f.frame_index),
        "X-Capture-Time-Monotonic-Ns": str(f.capture_time_monotonic_ns),
        "X-Receive-Time-Monotonic-Ns": str(f.receive_time_monotonic_ns),
        "X-Capture-Time-Unix-Ms": str(f.capture_time_unix_ms),
        "X-Frame-Width": str(f.frame_size[0]),
        "X-Frame-Height": str(f.frame_size[1]),
        "X-Calibration-Version": f.calibration_version or "",
        "Cache-Control": "no-store",
    }


def create_app(hub: CameraHub, calibration_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="Phantom camera ingest", version="1.0.0")

    def worker_or_404(camera_id: str):
        try:
            return hub.worker(camera_id)
        except KeyError as e:
            raise HTTPException(404, str(e)) from None

    @app.get("/", response_class=HTMLResponse)
    def diagnostics() -> str:
        return DIAGNOSTICS_HTML.replace("__CAMERAS__", json.dumps(list(hub.workers)))

    @app.get("/api/cameras")
    def cameras() -> dict:
        return hub.inventory()

    @app.get("/api/health")
    def health() -> dict:
        return hub.health()

    @app.get("/api/sync")
    def sync(tolerance_ms: float | None = None) -> dict:
        fs = hub.frameset(tolerance_ms)
        return {"latest_frameset": {k: v for k, v in fs.metadata().items() if k != "frames"}, "stats": hub.sync_monitor.summary()}

    @app.get("/api/calibration")
    def calibration() -> JSONResponse:
        if calibration_path is None or not Path(calibration_path).exists():
            raise HTTPException(404, "no calibration loaded; run `python -m calibration` (see calibration/README.md)")
        return JSONResponse(json.loads(Path(calibration_path).read_text()))

    @app.get("/api/cameras/{camera_id}/snapshot.jpg")
    def snapshot(camera_id: str, max_width: int | None = Query(None, ge=32), quality: int = Query(90, ge=10, le=100)) -> Response:
        f = worker_or_404(camera_id).latest()
        if f is None:
            raise HTTPException(503, f"{camera_id} has no frame yet")
        return Response(_encode(f.image, max_width, quality), media_type="image/jpeg", headers=_frame_headers(f))

    @app.get("/api/cameras/{camera_id}/stream.mjpg")
    def stream(camera_id: str, fps: float = Query(10.0, gt=0, le=30), max_width: int = Query(640, ge=32)) -> StreamingResponse:
        w = worker_or_404(camera_id)

        def gen() -> Iterator[bytes]:
            last = -1
            while True:
                f = w.latest()
                if f is not None and f.frame_index != last:
                    last = f.frame_index
                    jpg = _encode(f.image, max_width, 75)
                    yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n"
                time.sleep(1.0 / fps)

        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.get("/api/cameras/{camera_id}/board_check")
    def board_check(camera_id: str, cols: int = 9, rows: int = 6) -> dict:
        """Is the whole calibration board visible? Used while aiming cameras (diagnostics page)."""
        from calibration.board import Checkerboard

        f = worker_or_404(camera_id).latest()
        if f is None:
            raise HTTPException(503, f"{camera_id} has no frame yet")
        return {"camera_id": camera_id, "frame_index": f.frame_index, **Checkerboard(cols, rows).quick_check(f.image)}

    @app.get("/api/frameset")
    def frameset(tolerance_ms: float | None = None, max_width: int | None = Query(None, ge=32), quality: int = Query(90, ge=10, le=100)) -> dict:
        fs = hub.frameset(tolerance_ms)
        out = fs.metadata()
        for cid, f in fs.frames.items():
            out["frames"][cid]["jpeg_base64"] = base64.b64encode(_encode(f.image, max_width, quality)).decode()
            if max_width and f.frame_size[0] > max_width:
                out["frames"][cid]["note"] = "image downscaled: scale intrinsics by max_width / width before using pixels"
        return out

    return app


DIAGNOSTICS_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Camera Diagnostics</title><style>
:root{--bg:#f6f7f9;--card:#fff;--fg:#1b1f24;--mut:#5b6470;--ok:#1a7f37;--warn:#9a6700;--bad:#cf222e;--line:#d8dee4}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--card:#161b22;--fg:#e6edf3;--mut:#8b949e;--ok:#3fb950;--warn:#d29922;--bad:#f85149;--line:#30363d}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif}
header{padding:12px 16px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}
h1{font-size:18px;margin:0}#status{font-weight:600}
main{padding:16px;display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}
.card img{width:100%;display:block;background:#000;aspect-ratio:16/9;object-fit:contain}
.meta{padding:8px 12px;display:grid;grid-template-columns:auto 1fr;gap:2px 12px;font-variant-numeric:tabular-nums}
.meta span:nth-child(odd){color:var(--mut)}.title{padding:8px 12px;font-weight:600;display:flex;justify-content:space-between}
.streaming{color:var(--ok)}.stalled,.connecting{color:var(--warn)}.disconnected,.stopped{color:var(--bad)}
#sync{padding:0 16px 16px;color:var(--mut)}code{font-size:12px}
</style></head><body>
<header><h1>Camera diagnostics</h1><span id="status">…</span><span id="calib" style="color:var(--mut)"></span>
<span style="color:var(--mut)">Tip: cover one lens at a time to confirm each id matches the physical camera.</span></header>
<main id="grid"></main><div id="sync"></div>
<script>
const ids = __CAMERAS__;
const grid = document.getElementById('grid');
for (const id of ids) {
  const c = document.createElement('div'); c.className = 'card';
  c.innerHTML = `<div class="title"><span>${id}</span><span id="st-${id}">…</span></div>
  <img src="/api/cameras/${id}/stream.mjpg?fps=10&max_width=640" alt="live feed ${id}">
  <div class="meta"><span>calibration board</span><span id="b-${id}">–</span></div>
  <div class="meta" id="m-${id}"></div>`;
  grid.appendChild(c);
}
const row = (k, v) => `<span>${k}</span><span>${v ?? '–'}</span>`;
async function tick() {
  try {
    const [inv, h] = await Promise.all([fetch('/api/cameras').then(r => r.json()), fetch('/api/sync').then(r => r.json())]);
    let streaming = 0;
    for (const cam of inv.cameras) {
      const x = cam.health, st = document.getElementById('st-' + cam.camera_id);
      st.textContent = x.state; st.className = x.state; if (x.state === 'streaming') streaming++;
      const src = cam.source || {};
      document.getElementById('m-' + cam.camera_id).innerHTML =
        row('role', cam.role) + row('size', cam.frame_size ? cam.frame_size.width + '×' + cam.frame_size.height : null) +
        row('fps', x.fps + ' / ' + x.nominal_fps) + row('frame age', x.last_frame_age_ms + ' ms') +
        row('pipeline latency', x.pipeline_latency_ms + ' ms') + row('missed / dropped', x.missed_frames + ' / ' + x.dropped_by_consumers) +
        row('reconnects', x.reconnects) + row('source', src.kind + (src.stable_identity === false ? ' (unstable id!)' : '')) +
        row('error', x.last_error);
    }
    const s = document.getElementById('status');
    s.textContent = `${streaming}/${inv.cameras.length} streaming` + (streaming < inv.cameras.length ? (streaming >= 2 ? ' (degraded: fewer views)' : ' (multiview unavailable)') : '');
    s.style.color = streaming === inv.cameras.length ? 'var(--ok)' : streaming >= 2 ? 'var(--warn)' : 'var(--bad)';
    document.getElementById('calib').textContent = 'calibration: ' + (inv.calibration_version || 'none loaded');
    const st = h.stats, sp = st.spread_ms;
    document.getElementById('sync').innerHTML = `<b>Sync</b> (free-running cameras, not frame-perfect): ` +
      (sp ? `spread mean ${sp.mean} ms, p95 ${sp.p95} ms, max ${sp.max} ms; ` : '') +
      `complete framesets ${st.complete_ratio ?? '–'}; latest missing: ${h.latest_frameset.missing.join(', ') || 'none'}`;
  } catch (e) { document.getElementById('status').textContent = 'server unreachable'; }
}
async function boards() {
  for (const id of ids) {
    try {
      const b = await fetch(`/api/cameras/${id}/board_check`).then(r => r.json());
      const el = document.getElementById('b-' + id);
      el.textContent = b.detected ? (b.comfortable ? 'fully visible ✓' : 'visible, too close to the edge') : 'not visible';
      el.style.color = b.detected ? (b.comfortable ? 'var(--ok)' : 'var(--warn)') : 'var(--mut)';
    } catch (e) {}
  }
}
tick(); setInterval(tick, 1000); boards(); setInterval(boards, 2500);
</script></body></html>"""
