# Tracking smoothness: what was changed and why

Benchmark: `python tests/bench_tracking.py`. A can-like object on a wood texture follows a circle and figure-eight at up to about 2500 px/s, with motion blur, analysed at 15 Hz. The model is ideal (true masks), so this isolates **tracker** behaviour. A frame counts as "inside" when ≥ 90 % of the can is inside the box **as drawn**.

| model every 0.12 s (live rate while moving) | before | after |
|---|---|---|
| can inside the box, all frames | 92.8 % | **96.1 %** |
| slow < 500 px/s | 100 % | 100 % |
| fast 500–1000 px/s | 100 % | 100 % |
| very fast > 1000 px/s (more than a can-width per frame) | 48 % | **72 %** |
| centre error p95 | 81 px | **9.8 px** |
| processing per frame (median) | 9.4 ms | 11.0 ms |

These numbers are synthetic and not yet measured on the real cameras. Above about 1000 px/s, frame rate and motion blur, not code, limit the result: more light (shorter exposure) and a faster model (higher detection rate) are what help there.

## Changes and why

### Bottlenecks found
1. **The model ran inside every frame request.** Optical-flow tracking takes about 3 ms, but YOLOE-26X segmentation blocked each camera's loop, and both cameras queued on one model lock.
   - **Fix:** a background detector per camera; detections are shifted to each object's current position before use.
   - Also added `--model-size s|m|l|x`, `--sync-detection` and visible errors.
2. **Full-frame SIFT recovery ran on every lost frame**, stalling the loop exactly when an object was lost.
   - **Fix:** when an attempt is slow (> 25 ms), it is skipped for 3× its cost; fast attempts still run every frame.

### Why the box left the can
3. **No motion prior in optical flow.** The flow search started at the old point positions, so fast motion fell outside its range.
   - **Fix:** it is seeded with a constant-velocity guess (`OPTFLOW_USE_INITIAL_FLOW`), falling back to the plain search.
4. **Tracking features were never replenished.** Points only died, so after a few fast or blurred frames too few were left and the can dropped to "predicted" or "lost".
   - **Fix:** features are topped back up inside the current mask after each good frame.
5. **The box froze in the "predicted" state.** The box stayed where the can was while the can moved on.
   - **Fix:** the mask and points coast along the last velocity until flow recovers.
6. **A distant detection was ignored after the flow locked onto the table.** At very high speed the points can stick to the background while a correct detection sits 300 px away.
   - **Fix:** when there is exactly one track and one detection of that kind, they are matched however far apart.
7. **Stale masks dragged the box backwards.** Fixed in step 1 by shifting detections forward.
8. **The box was drawn late.** Results describe a frame already 50–150 ms old.
   - **Fix:** boxes are redrawn every display frame and lead by speed × age (≤ 150 ms).
9. **The drawn box was exactly the can's size**, so a few pixels of jitter or blur put the can's edge outside it.
   - **Fix:** the drawn box has a 6 px / 8 % margin.

### Why the 3D view glitched
10. **The trail broke whenever either view missed an update.**
    - **Fix:** views are paired up to 250 ms apart, and positions are held through dropouts of ≤ 0.7 s.
11. **One bad mask became a spike on the map.**
    - **Fix:** a jump gate holds back a single sample implying > 3 m/s and accepts it if the next one agrees.
12. **Fast moves created new IDs**, which duplicated objects across views.
    - **Fix:** velocity-gated re-acquisition plus cross-view re-linking.

## For best results on the real setup
- **Lighting:** bright, even light. This matters most for fast moves.
- **Model:** `--model-size s` or `m` so detections refresh at ≥ 8 Hz. Check "Tracking updates/sec" on the page; it should be ≥ 15 per camera.
- **Mounting:** keep both cameras still. A camera that moves makes the whole scene look like motion.
