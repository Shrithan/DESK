"""OpenCV overlay: camera view with mask/anchor/arrow + virtual joystick + WASD keycaps + readouts."""
from __future__ import annotations

import math
import time

import cv2
import numpy as np

GREEN, RED, WHITE, GREY, YELLOW, CYAN = (80, 220, 80), (60, 60, 230), (240, 240, 240), (110, 110, 110), (40, 220, 240), (230, 200, 60)
PANEL_W = 280


class Overlay:
    def __init__(self, keys_cfg) -> None:
        self.kc = keys_cfg
        self.knob = np.zeros(2)
        self.t = time.perf_counter()

    def draw(self, frame, det, estimator, state, held, paused, stats: dict) -> np.ndarray:
        img = frame.copy()
        if det is not None:
            cv2.polylines(img, [np.round(det.polygon).astype(np.int32)], True,
                          GREEN if det.kind == 'seg' else (YELLOW if det.kind == 'box' else CYAN), 2)
        if estimator.anchor is not None:
            ax, ay = map(int, estimator.anchor)
            cv2.circle(img, (ax, ay), int(estimator.r0), CYAN, 1)
            cv2.drawMarker(img, (ax, ay), CYAN, cv2.MARKER_CROSS, 14, 2)
            if state.valid:  # arrow = joystick vector drawn in image space (x4 so small tilts are visible)
                tip = (int(ax + state.raw_img[0] * estimator.r0 * 4), int(ay + state.raw_img[1] * estimator.r0 * 4))
                cv2.arrowedLine(img, (ax, ay), tip, RED, 3, tipLength=.25)
        scale = 480 / img.shape[0]
        img = cv2.resize(img, (int(img.shape[1] * scale), 480))
        prompt = 'PAUSED (space to resume)' if paused else (state.prompt or ('LOST: keys released' if state.status == 'lost' else ''))
        if prompt:
            cv2.rectangle(img, (0, 0), (img.shape[1], 40), (0, 0, 0), -1)
            cv2.putText(img, prompt, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, .75, RED if state.status == 'lost' or paused else WHITE, 2)
        return np.hstack([img, self.panel(state, held, stats)])

    def panel(self, state, held, stats) -> np.ndarray:
        p = np.full((480, PANEL_W, 3), 28, np.uint8)
        now = time.perf_counter()
        dt, self.t = now - self.t, now
        target = np.array([state.x, state.y]) if state.valid else np.zeros(2)
        self.knob += (target - self.knob) * min(1.0, dt * 30)  # eased at display rate
        c, R = (PANEL_W // 2, 140), 100
        cv2.circle(p, c, R, WHITE, 2)
        cv2.circle(p, c, int(R * self.kc.press), GREY, 1)
        cv2.circle(p, c, int(R * self.kc.release), GREY, 1, cv2.LINE_AA)
        for k in range(8 if self.kc.diagonals else 4):  # sector boundaries
            a = math.radians((k + .5) * (45 if self.kc.diagonals else 90))
            cv2.line(p, (int(c[0] + R * self.kc.press * math.sin(a)), int(c[1] - R * self.kc.press * math.cos(a))),
                     (int(c[0] + R * math.sin(a)), int(c[1] - R * math.cos(a))), (60, 60, 60), 1)
        kp = (int(c[0] + R * self.knob[0]), int(c[1] - R * self.knob[1]))
        cv2.line(p, c, kp, GREY, 2)
        cv2.circle(p, kp, 14, GREEN if held else (WHITE if state.valid else RED), -1)
        caps = {self.kc.up: (1, 0), self.kc.left: (0, 1), self.kc.down: (1, 1), self.kc.right: (2, 1)}
        for key, (gx, gy) in caps.items():
            x, y = 70 + gx * 48, 262 + gy * 48
            on = key in held
            cv2.rectangle(p, (x, y), (x + 42, y + 42), GREEN if on else (70, 70, 70), -1)
            cv2.putText(p, key.upper(), (x + 12, y + 30), cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 0, 0) if on else WHITE, 2)
        lines = [f"{state.status}   mag {state.mag:.2f}   conf {state.confidence:.2f}",
                 f"fps {stats.get('fps', 0):.1f}   e2e {stats.get('e2e_ms', 0):.0f} ms (p95 {stats.get('e2e_p95', 0):.0f})",
                 f"model {stats.get('model_ms', 0):.0f} ms (off path)  flow {stats.get('flow_ms', 0):.1f} ms",
                 "space pause  c neutral  r W/D dir  q quit"]
        for i, text in enumerate(lines):
            cv2.putText(p, text, (10, 378 + i * 24), cv2.FONT_HERSHEY_SIMPLEX, .45, WHITE, 1, cv2.LINE_AA)
        return p
