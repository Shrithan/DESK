# Physical sliders for Mixxx

DESK uses the overhead camera only. Separate objects can simultaneously control
Deck A/B volume, the crossfader, and each deck's low/mid/high EQ. The existing
Cartesia transcription → ASI:One mapping agent can choose these registered targets.

## Run

```sh
.venv/bin/python -m pip install -e '.[ai,dj]'
.venv/bin/python -m vision.live --port 8765 --device mps --model-size x --temporal flow
```

Open http://localhost:8765 and click **Connect Mixxx MIDI**. This creates a local
virtual MIDI input/output named **DESK Spatial DJ**. Install both files from
`mapping/` into Mixxx's **Preferences → Controllers → Open User Mapping Folder**.
Restart Mixxx after adding the files, while DESK's MIDI connection is running.
Select **DESK Spatial DJ**, load the identically named preset, enable it and Apply.
On this Mac the files are already installed and the preset enabled.

**Mixxx connected · feedback live** means actual Mixxx parameter values are coming
back. A MIDI port alone does not count as connected. The collapsed **MIDI test
sliders** change actual mixer faders without a camera; they do not start playback.

## Map the table

1. Start the overhead webcam. Move each object briefly to acquire it. Give each
   fader a distinct object and enough clear travel space; do not overlap them.
2. Choose its detected object and a DJ control, then **Map this slider**. Or say
   “Use this bottle as the Mixxx Deck A volume slider.” Select the voice target
   when several objects are visible. Use “crossfader” for an A/B blend slider.
3. Move the object to the desired minimum and click **Set 0% end** on its mixer
   card. Move to the maximum and click **Set 100% end**. Endpoints must be at least
   3% of the image apart. Up increases vertical faders; right moves the crossfader
   toward B. Reverse inverts this. Calibration changes only that target.
4. Click **Enable DJ controls**, then move each object through its current Mixxx
   value to pick it up. This avoids jumps. You can move multiple sliders together.
5. **Stop DJ controls** or **STOP ALL OUTPUT** stops camera-driven mixer changes.
   Removing or repurposing an input disconnects its DJ mapping.

Load tracks, start playback and set headphone routing in Mixxx yourself. Objects
control the actual mixer even when the browser is unfocused. Keep the dashboard
open and tracking; a stalled browser/camera or missing MIDI feedback disarms the
DJ controls. Re-enable after an interruption.

## Behavior and limits

- Position smoothing uses a 45 ms time constant; output is limited to 30 updates/s
  per fader and 2.5 full-range units/s. These are bounds, not a promised camera FPS
  or measured end-to-end latency.
- Tracking loss holds the last actual mixer value. Recovery and manual mixer
  changes require pickup again. It never snaps volume to zero on loss.
- Mixxx sends real normalized and native parameter feedback. Volume/EQ curves
  follow Mixxx's `setParameter` behavior, so a normalized 50% is not half amplitude.
- Current mappings/calibration are session-only. Restart/reload means remapping.
  This does not create a persistent DJ preset or guarantee arbitrary-object
  identity after a long occlusion. Keep objects well lit and separated.
- No automatic playback, scratching, beat sync, pitch/tempo or effect selection
  is included in this first DJ version. Cover buttons retain their existing
  general action behavior; they are not Mixxx transport controls yet.

Verified on local Mixxx 2.5.6: crossfader, both deck volumes and Deck A low EQ
changed and reported their actual values, then were restored. Automated tests
cover simultaneous faders, pickup, loss, input lease, calibration and MIDI
message validation. Physical multi-object performance still needs a table test.

References: [Mixxx control](https://manual.mixxx.org/2.5/en/chapters/controlling_mixxx.html),
[Mixxx MIDI scripting](https://github.com/mixxxdj/mixxx/wiki/MIDI-Scripting).

Validation notes: the main app suite passed 131 tests before the final extra DJ
HTTP checks were added; the final DJ/planner subset passed 17 tests. All 21
JavaScript checks passed (including the newly added frontend check). A later
live-tracking subset run had two intermittent, unchanged reacquisition failures;
this version does not claim flawless identity recovery. Repository-wide test
collection additionally needs optional `trimesh` and `pydantic` dependencies for
hardware/other joystick modules. Use the DJ panel's Reverse setting for its
faders; camera-display direction checkboxes are separate.

Mapping-retention fix: status polling no longer deletes mappings based on a tab's
local input list. Deletion happens only when an input is explicitly removed,
repurposed, stopped or reset. This prevents a pending bind or a second dashboard
from silently removing another tab's fader. Use one active camera dashboard at a
time: concurrent camera pages share the current tracking session and can mix
observations. Refresh older open dashboards after updating the frontend.

## Guided setup in the dashboard

Use **Start slider setup** after choosing a visible object, destination and axis.
The guide pauses DJ output, captures **Save 0% position** and **Save 100% position**,
and rejects travel shorter than 3% of the image. Endpoint choices define the
increase direction. **Enable this slider** then waits for pickup and confirms
**Your slider is working** from the actual mapping state. **Set up another slider**
keeps existing mappings; starting its calibration pauses mixer output again.
**Pause setup** leaves output stopped. Errors stay visible until your next action.
No voice command or assistant-operated calibration is required.
