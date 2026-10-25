# Fixed box object controller

Choose **Fixed boxes · WASD**, start the overhead camera, and show/move an object briefly so the tracker acquires it. The first selected detection permanently fixes its measured center and bounding box, padded by 30%. The five adjacent boxes form a cross: W above, S below, A left, D right, with a neutral center.

Click **Map and arm game module** to send native keys. Membership uses the object's measured center: a direction box holds exactly one key; the center, corners, outside all boxes and tracking loss release every key. There is no tilt estimate, directional extension, automatic recentering or prediction for this controller. **Stop game controls** releases output.

**Show fixed zones on camera (debug overlay)** toggles the five bounds, fixed yellow crosshair, pink measured object center and green active box. Lost tracking leaves the bounds visible with no active box. **Zone size** scales each box from 50% to 300% of its first bounds. Changes disarm output; map and arm again to apply them.

The anchor survives movement, loss, remapping and page reloads in the same browser session and camera. **Reset first-scan anchor** explicitly clears it so the next detection establishes a new center. A changed tracking ID requires choosing that current track and arming it; it does not move the fixed anchor. Moving the camera requires resetting the anchor.

For Subway City choose **Subway City · slide D-pad / arrow swipes**, which uses the same fixed boxes with arrows. In the Mac app enable Settings → Touch Alternatives → On. Arrows generate swipes for lanes, jump and roll; WASD generates virtual device tilt. Keep the dashboard running and focus the target app. Tracking freshness checks, token ownership and a 350 ms heartbeat watchdog protect native output. macOS Accessibility is required for the app running the server.

Implementation: `vision/web/game-controls.js` defines fixed geometry, session anchor, profiles and overlay; `flat-input.js` uses measured positions and immediately drops missing input; `fusion.js` composes the camera overlay. The existing native keyboard backend handles key delivery and release.

Verification: `node tests/test_game_modules.cjs` tests all five zones, shared edges, corners, positions outside the cross, loss, immutable origin and session restoration. Keyboard regression tests: `.venv/bin/python -m pytest -q tests/test_keyboard.py tests/test_commands.py`. Physical motion and game response still require a live operator.

The Subway City slide profile includes the observed camera mounting rotation: camera-right → Up, camera-left → Down, camera-up → Left, camera-down → Right. These bindings compensate for physical up previously producing Right and physical left producing Up. WASD fixed boxes retain the camera-view axes.

## Subway movement swipes

Subway City movement-triggered swipes fires from measured displacement anywhere in the camera view. About six camera pixels triggers a 90 ms arrow-key pulse, with a 220 ms cooldown. Holding still releases the key and never repeats it. Continued travel can send another swipe after the cooldown; no return to a box or fixed center is required. The saved boxes remain an optional visual reference, and the overlay labels this movement mode. Loss resets the motion baseline so reacquisition cannot trigger a jump swipe. The observed camera rotation is preserved. Fixed boxes · WASD retains zone-held keys.

The Subway two-axis slider now accumulates signed horizontal/vertical travel rather than resetting displacement during cooldown. Default travel is 12 camera pixels per keystroke, adjustable from 3 to 80. The dominant axis sends an 80 ms arrow pulse with a 140 ms minimum trigger interval. Holding still never triggers deferred pulses. Travel during that interval contributes to the next stroke once movement continues. The overlay shows the configured threshold and stroke count.

Subway single-swipe mode supersedes continuous repeated strokes: once travel crosses the threshold, that gesture latches after one 80 ms pulse. Continued movement cannot fire again. Settling within 15% of the trigger distance for 180 ms re-arms the next gesture. No fixed-center return is required.

Current user-selected behavior: continuous accumulated slider restored; stop-to-rearm latch removed. Default movement threshold increased to 24 camera pixels for lower sensitivity. Corrected camera rotation and 80 ms key pulses are retained.

## Current Subway flick detector

The flick detector replaces repeated distance strokes. READY uses net measured travel within a rolling 180 ms window (default 24 pixels). Crossing that threshold fires exactly one 80 ms arrow pulse and enters MOVING. Continued travel cannot repeat. Stable samples spanning at least 110 ms within a 150 ms window and a 15%-of-threshold position band re-arm READY after the 160 ms minimum separation. A full-threshold reversal from the furthest point of the previous flick can fire once without settling; orthogonal jitter is rejected. Only the dominant direction is sent for a diagonal flick. Missing/stale frames reset the baseline, so reacquisition never fires a swipe. The overlay shows READY / MOVING / SETTLING and the swipe count.
