# Camera setup (Agent 1)

## Decision: 3× Logitech C270 over USB instead of iPhones
We looked into three iPhones (14 Pro Max ×2, 16 Pro) first:

| option | finding |
|---|---|
| macOS Continuity Camera | one iPhone at a time |
| Camo, Iriun, NDI HX Camera, RTSP apps (iRTSP, Larix, …) | multiple phones simultaneously not confirmed; everything except a custom iOS app goes over Wi-Fi |
| browser sender (Safari `getUserMedia` → WebRTC) | possible, but it's our own code, needs HTTPS on the LAN and still goes over Wi-Fi |
| venue Wi-Fi | often isolates clients; adds an estimated 100–500 ms latency that varies; three separate phone clocks |

**Chosen:** three USB webcams on one powered hub, because they need no network or apps, all share one host clock, and the C270 is fixed-focus.

**Trade-offs:**
- 720p only.
- A narrow lens (55° diagonal).
- No hardware sync.

The iPhone cradles remain in `camera/hardware/iphone_cradles/` as a fallback.

## Hardware
| cam | camera | position (frame = world axes) | aim |
|---|---|---|---|
| `cam_1` | C270 | overhead crossbar, lens ≈ (0, 0, 0.49) m | straight down |
| `cam_2` | C270 | back top rail, left, lens ≈ (−0.40, 0.25, 0.49) m | ~46° down at the table centre |
| `cam_3` | C270 | back top rail, right, lens ≈ (0.40, 0.25, 0.49) m | ~46° down at the table centre |

- **The frame:** 1.0 × 0.6 × 0.5 m PVC box with printed clamp mounts. Build steps, parts list and print files are in [`camera/hardware/c270_frame/README.md`](../camera/hardware/c270_frame/README.md).
- **The config:** the physical design is [`camera/config/rig_c270.json`](../camera/config/rig_c270.json), which both the mount generator and the software read.

![rig](../camera/hardware/c270_frame/renders/rig_overview.png)

## Connections, ports and formats
- **USB:** each C270 → its own port on a powered USB hub → one USB-C cable to the MacBook. Keep each camera in the same port, because its macOS id encodes the port.
- **Bandwidth:** request **MJPEG** at 1280×720 @ 30 fps (`fourcc` in the rig config). Uncompressed 720p30 needs about 55 MB/s, more than USB 2 carries, so three cameras only fit compressed.
- **Permissions:** macOS camera permission for the terminal app running `python -m camera`.
- **Network:** none required. The ingest HTTP server listens on `127.0.0.1:8100`; bind `--host 0.0.0.0` only if another machine must read it.
- **Latency:** not measured on hardware yet (USB webcams are typically a few tens of ms). `--latency-ms` subtracts a measured constant from the timestamps. Measure it by filming a millisecond clock on the Mac's screen and comparing the clock in the image with the frame's receive time.

## Lock the optics before calibrating
- **Fixed settings:** keep the C270 at 1280×720 and don't use digital zoom or Logitech software effects. If the resolution changes, redo intrinsics.
- **Focus:** fixed on the C270, so nothing to lock. Don't twist the lens ring if your unit has one exposed.
- **Exposure:** set by the camera automatically, and OpenCV on macOS can't reliably lock it. Use steady, bright lighting and avoid sunlight that changes.
- **Recalibrate** when anything moves: if a camera is bumped or re-seated, re-run extrinsics. `python -m calibration verify` detects drift.

## Graceful degradation
| cameras streaming | behaviour |
|---|---|
| 3 | `status: ok` |
| 2 | `degraded`: multiview depth still available from the remaining two |
| fewer than 2 | `unusable` for metric 3D: anything downstream must be labelled monocular/estimated |

Disconnected cameras reconnect automatically and keep their id.

## Procedure
See [`calibration/README.md`](../calibration/README.md): print board → intrinsics per camera → extrinsics → verify.
