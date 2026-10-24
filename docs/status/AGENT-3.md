# Agent 3 status: geometry / backend / contracts

Branch: `agent/geometry-backend`

## Checkpoint: tilt-to-keys (W/A/S/D from can tilt)

**Working**
- `shared/contracts/tilt.py`: `TiltUpdate`, `TiltCommand`, `KeyState` v1.0.0, plus JSON Schemas, valid and invalid fixtures, and validation tests.
- `backend/tilt_keys/`: calibration, then One Euro filter, then hysteresis, then edge-triggered output, plus safety (axis loss, 200 ms stale watchdog, exit/signal/crash release, enable/disable).
- Backends: `log` (default), `pynput` (real presses), `websocket` (`key_state` on `/ws/keys`).
- Simulator: scripted, with noise and bias, and interactive (curses, sends over WebSocket).

**Commands**
```bash
python -m pytest tests -q
python -m backend.tilt_keys.simulator scripted --noise 0.5 --bias-forward 2 --bias-right -1 | python -m backend.tilt_keys.run --input stdin
python -m backend.tilt_keys.run --simulate
```

**Tests:** 79 passed. This includes a subprocess pipe smoke test and a WebSocket round-trip smoke test.

**Measured (simulation, 30 Hz, default filter):** a 0→20° step presses in 66 ms, a step back to 0° releases in 66 ms, and the stale release fires at 200–220 ms.

**Not verified:** real pynput presses on this machine. Accessibility is not granted to this terminal (`AXIsProcessTrusted() == False`). The pynput backend is unit-tested against a fake controller only.

**Blockers**
- The remote had no `main` branch when this work started, so there was nothing to pull.

**Next:** integrate with the vision agent's real `tilt_update` stream; world-state contracts (CameraCalibration, WorldState, …).
