# Tilt a can → W/A/S/D

Code: `backend/tilt_keys/`. Contract: `shared/contracts/tilt.py` ([protocol](protocol.md#tilt-contract-v100-sharedcontractstiltpy)).
This module does no computer vision. It turns `tilt_update` angles from the vision
agent into held keys.

| can tilts            | keys held |
|----------------------|-----------|
| forward (away from you) | W |
| back (toward you)    | S |
| left                 | A |
| right                | D |
| forward + left, etc. | both (W+A) |
| upright              | none |

## Sign conventions

- `forward_deg`: `+` means the top of the can leans **away** from the user, `-` means it leans toward the user.
- `right_deg`: `+` means the top leans **right**, `-` means it leans left.
- `null` or `can_found:false` means unavailable. It is never treated as 0°.

If the camera setup makes an axis come out mirrored, set `invert_forward` /
`invert_right` in the config instead of changing the producer.

## Pipeline

Each stage is a small pure function or class with its own tests:

```
tilt_update ─► calibration offset ─► invert ─► One Euro filter ─► hysteresis per key ─► edge-triggered output ─► backend
             (calibration.py)                  (one_euro.py)      (hysteresis.py)       (output.py)            (backends.py)
                              orchestration + safety rules: controller.py
```

1. **Neutral calibration.** On start, and on a `recalibrate` command, the first 2 s of
   readings (`calibration_duration_ms`) are averaged and become the zero for each axis.
   No keys are pressed during this time. If either axis has a std dev above 1.5°, or a
   peak-to-peak range above 5°, the can was moving. Calibration is then rejected with a
   logged reason (`calibration_failed`) and collection starts again. It is also rejected
   if the can was missing in more than 20% of readings. Use `--no-calibrate` to skip it.
2. **Smoothing.** A One Euro filter runs on each axis (`filter_min_cutoff_hz`,
   `filter_beta`, `filter_d_cutoff_hz`). Lower `min_cutoff` means less jitter at rest
   but more lag. Higher `beta` means less lag on fast tilts. The filter resets
   whenever an axis becomes unavailable.
3. **Hysteresis per key.** A key is pressed when its angle is `> on_threshold_deg`
   (15°) and released only when the angle is `< off_threshold_deg` (10°). W uses
   +forward, S uses −forward, D uses +right, and A uses −right. The axes are evaluated
   independently, so diagonals hold two keys.
4. **Edge-triggered output.** key-down is sent only when a key starts and key-up only
   when it stops. Releases are sent before presses, so W and S are never held at the
   same time.
5. **Safety. None of these rules can be skipped:**
   - When `can_found:false` or an angle is null, that axis's keys are released on the
     same message.
   - When no valid `tilt_update` arrives for more than `stale_timeout_ms` (200 ms),
     **all** keys are released. A 20 ms watchdog checks this. Invalid messages don't
     count as updates.
   - Exit, Ctrl+C, SIGTERM, SIGHUP, or an exception in the run loop **releases all
     keys** via try/finally and signal handlers, with `atexit` as a last resort. The
     pynput backend also releases anything it pressed when it closes.
   - Global enable/disable (`tilt_command` `enable`/`disable`/`toggle`): disabling
     releases all keys and sends nothing until re-enabled.

Semantic events are logged (and available through `on_event`) for narration or
the UI: `calibration_started`, `calibration_complete`, `calibration_failed`,
`tracking_lost`, `tracking_restored`, `stale_release`, `key_state`, `enabled`,
`disabled`, `shutdown`.

## Setup (macOS Apple Silicon; same on Linux/Windows)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run the tests

```bash
python -m pytest tests -q
```

## Run the simulator (no camera, no real key presses)

```bash
# one process: built-in scripted sequence -> log backend
python -m backend.tilt_keys.run --simulate --noise 0.5

# two processes over a pipe (the same path a real producer could use)
python -m backend.tilt_keys.simulator scripted --noise 0.5 --bias-forward 2 --bias-right -1 \
  | python -m backend.tilt_keys.run --input stdin --backend log

# interactive: arrow keys tilt, space = upright, l = can lost, c = recalibrate, e = enable/disable
python -m backend.tilt_keys.run --input ws --backend log          # terminal 1
python -m backend.tilt_keys.simulator interactive --noise 0.3     # terminal 2
```

The scripted sequence is upright (calibration) → forward 20° → 12° → 8° → left 25° →
forward+left → can lost → upright. Expected key events: `W down`, `W up`, `A down`,
`W down`, then `A up` and `W up` when the can is lost.

`--bias-forward/--bias-right` adds a constant lean, so you can check that calibration
removes it. `--noise` adds Gaussian jitter in degrees.

## Switch to real key presses

```bash
python -m backend.tilt_keys.run --input ws --backend pynput
# or
TILT_KEYS_BACKEND=pynput python -m backend.tilt_keys.run --input ws
# real presses + browser/frontend view of held keys on ws://127.0.0.1:8765/ws/keys
python -m backend.tilt_keys.run --input ws --backend pynput,websocket
```

The real backend calls `pynput.keyboard.Controller().press(key)` / `.release(key)`
(tested against pynput 1.8.2).

**macOS requirement:** open System Settings → Privacy & Security → **Accessibility**
and enable the app that runs this command (Terminal, iTerm2, or Visual Studio Code if
you use its built-in terminal). Then restart that app. **Without this, macOS blocks
synthetic key presses silently:** there is no error, and nothing gets typed. At
startup the pynput backend calls `AXIsProcessTrusted()` and logs an error if
permission is missing.

**Some games ignore synthetic key events.** This is common with games that read
raw input or run anti-cheat. Test first in a **text editor** (you should see
`wwww…` while the can tilts forward) or in a simple **browser game**. Move on to
the target game only after that works. Also remember that real key presses go to
whichever window has focus.

## Config

All tunables are in `TiltKeyConfig` (`backend/tilt_keys/config.py`). The commented
defaults are in `backend/tilt_keys/tilt_keys.example.toml`. To load a config:

```bash
python -m backend.tilt_keys.run --config my_keys.toml      # or TILT_KEYS_CONFIG=my_keys.toml
```

Key bindings accept single characters or pynput `Key` names (`up`, `down`, `left`,
`right`, `space`, `shift`, …). For example, to drive arrow keys:

```toml
[keys]
forward = "up"
back = "down"
left = "left"
right = "right"
```

## Feeding real data (vision agent)

Connect to `ws://<laptop>:8765/ws/tilt` and send `tilt_update` JSON at the camera
rate, or call `TiltKeyController.handle_message(...)` in-process. Send
`can_found:false` rather than going silent when the can is lost. Run the receiving
side with `--host 0.0.0.0` if the producer is on another machine.

## Known limits

- The stale watchdog uses the receive time on this laptop, not the producer's
  timestamp, so clock skew between machines does not cause false releases. As a
  result, a producer that sends old buffered frames on time is not detected as late.
- The 200 ms stale timeout plus filter lag sets the worst-case "key stuck after the
  camera dies" time at about 220 ms.
- Filter lag measured with default settings at 30 Hz, in simulation, plus whatever
  latency the camera adds:

  | step         | press after       | release after (step back to 0°) |
  |--------------|-------------------|---------------------------------|
  | 0° → 30°     | 1 frame (33 ms)   | 2 frames (66 ms)                |
  | 0° → 20°     | 2 frames (66 ms)  | 2 frames (66 ms)                |
  | 0° → 16°     | 4 frames (132 ms) | 2 frames (66 ms)                |
