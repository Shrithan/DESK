# Flight simulator joystick module

Select **Flight simulator · held joystick W/S/A/D** in Game module. Start the overhead camera, select the joystick object and hold it centered before clicking **Map and arm game module**. Arming captures the current position as neutral for this flight module, independently of the fixed-box anchor.

With the calibrated camera mounting, physical pull-back holds W, push-forward holds S, left holds A, and right holds D. Deflection can hold both axes simultaneously. Returning to neutral releases the keys. This is held digital keyboard control rather than an analog simulator axis or Subway's flick detector. Tracking loss releases output. The existing keyboard freshness/heartbeat checks remain active. Focus your simulator after arming.

Zone size scales the travel needed for deflection; larger values need more movement. A 25% deflection deadzone prevents neutral jitter. Re-arm while centered to capture a new neutral. Stop game controls releases all keys. General slider/button mappings retain independent activation.

Tests: `node tests/test_game_modules.cjs`. Simulator-specific key bindings must match W/S/A/D; physical response still needs a live check.

Updated technique: selecting the flight module locks a separate first-detection anchor immediately when its object is acquired, before activation. Arming never moves this anchor. The measured top point uses explicit skeleton top coordinates when available, otherwise the overhead mask centroid (an estimate of the visible can top), then the tracked center as a fallback. Horizontal/vertical displacement from the fixed reference controls held keys through a 25% deadzone. The debug overlay draws the fixed point, neutral bounds, top point, connecting line, pixel distance and active keys. Tracking loss removes the live top indicator and releases keys while retaining the reference. Reset first-scan anchor explicitly clears the reference.

Voice setup arms the same native W/S/A/D controller and sends an initial update
immediately. The keyboard status reports whether events are being sent, the
simulator needs focus, or the camera observation is stale. Focus the simulator's
app/window after setup; dashboard form controls suppress native output.

Flight explicitly retains its chosen keyboard assignment across heartbeat gaps
when switching windows. The 350 ms watchdog still releases held keys immediately;
new key events require a new update and a visible tracked source. Stop/Reset still
fully disarm output. This changes connection recovery, not the flight geometry,
mounting-specific bindings, deadzone, or held-key behavior.

Delivery tests: `node tests/test_flight_key_delivery.cjs` checks each direction,
diagonals, neutral, focus gating and stale frames; `tests/test_flight_keyboard_http.py`
checks HTTP arming/update through a recording keyboard backend and release/recovery.
