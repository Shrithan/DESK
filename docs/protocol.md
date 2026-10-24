# DESK protocol (owned by agent 3)

Source of truth for message shapes is `shared/contracts/` (Pydantic models). JSON
Schemas are generated into `shared/contracts/schemas/` with
`python -m shared.contracts.export_schemas`, and a test fails if they drift.
Valid and invalid sample messages live in `shared/contracts/fixtures/`.

Rules: contracts are versioned with semver in `schema_version`. A consumer accepts any
version with the same MAJOR number and ignores unknown fields. Units, sign
conventions, IDs, and field names never change silently. Changes go through a PR
and get announced to all agents.

---

## Tilt contract v1.0.0 (`shared/contracts/tilt.py`)

### Sign conventions

These are angles of the **top of the can** relative to vertical, in **degrees**, as
seen **from the user's seat looking at the can**:

| field         | `+` means                              | `-` means                      |
|---------------|----------------------------------------|--------------------------------|
| `forward_deg` | top leans **away** from the user       | top leans **toward** the user  |
| `right_deg`   | top leans to the user's **right**      | top leans to the user's **left** |

- Upright is about `0, 0` before calibration. The consumer subtracts its own neutral
  calibration, so producers should **not** zero the angles themselves.
- `null` means *unavailable*. It never means 0°.
- `can_found: false` means the whole measurement is unavailable, and both angles are
  ignored even if present.
- Angles must be finite and within ±180°. NaN and Infinity are rejected.
- `timestamp_ms` is Unix epoch milliseconds when the frame was **captured**. It must
  increase strictly per producer. Out-of-order messages are dropped.

### `tilt_update` (vision agent → tilt-to-keys)

```json
{"type":"tilt_update","schema_version":"1.0.0","timestamp_ms":1792820000066,
 "forward_deg":18.5,"right_deg":-22.0,"can_found":true}
```

| field           | type            | required | notes |
|-----------------|-----------------|----------|-------|
| `type`          | `"tilt_update"` | yes      | |
| `schema_version`| string          | no       | defaults to `"1.0.0"`; major must be 1 |
| `timestamp_ms`  | int > 0         | yes      | Unix ms |
| `forward_deg`   | float \| null   | yes      | see sign table |
| `right_deg`     | float \| null   | yes      | see sign table |
| `can_found`     | bool            | yes      | |

Send it at the camera rate (target 30 Hz). **If no `tilt_update` arrives for 200 ms
(configurable), the consumer releases every key.** If you are still tracking but have
no angle, send `can_found:false` instead of going quiet. Releases happen faster and
the reason ends up in the logs.

### `tilt_command` (UI / voice / CLI → tilt-to-keys)

```json
{"type":"tilt_command","schema_version":"1.0.0","timestamp_ms":1792820000200,"command":"recalibrate"}
```

`command` is one of `recalibrate`, `enable`, `disable`, `toggle`.

### `key_state` (tilt-to-keys → frontend/game, optional)

```json
{"type":"key_state","schema_version":"1.0.0","timestamp_ms":1792820000233,
 "held":["a","w"],"enabled":true,"mode":"active"}
```

`held` is sorted. `mode` is one of `calibrating`, `active`, `disabled`.

### Transport

| path                          | direction  | messages |
|-------------------------------|------------|----------|
| `ws://HOST:8765/ws/tilt`      | producer → | `tilt_update`, `tilt_command` |
| `ws://HOST:8765/ws/keys`      | → subscriber | `key_state` on every change |
| stdin of `backend.tilt_keys.run` | producer → | JSON lines, same messages |
| Python: `TiltKeyController.handle_message(dict_or_json)` | in-process | same messages |

Invalid messages are logged and dropped, and they do **not** reset the stale-input
watchdog.

---

## World-state contract (planned)

The `world_state`, `CameraCalibration`, `ObjectObservation`, and related schemas from
the milestone brief will be added under `shared/contracts/` in a later PR.
