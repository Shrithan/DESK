# Can joystick with a tilted overhead camera

A tilted camera can make an upright can look elongated and slanted. The web joystick now learns the actual neutral image instead of treating a circular silhouette or a vertical image axis as upright.

## Use

1. Keep the camera fixed. Move the can briefly so it is acquired, and choose **Use my can as joystick** (or add it as a joystick).
2. Stand the can upright at its intended base position. Hold still for one second while the card learns neutral. **Calibrate upright (1s)** restarts this at any time and immediately releases virtual keys.
3. Click **Learn W**, lean forward with the base fixed and hold for half a second. Return upright.
4. Click **Learn D**, lean right with the base fixed and hold for half a second. Return upright. The two measured image directions define the controls, even when perspective makes them nonorthogonal or the camera is mirrored.
5. Lean to control W/A/S/D in the dashboard. Twisting/yaw stays a separate surface measurement. The web page sends no real OS keys.

Calibration resets if the can moves during the neutral sample window. Repeated renders of the same frame cannot complete calibration. Hands or merged silhouettes that change the mask area too much are rejected. Missing observations go through the existing bounded dropout hold/decay. A recalibration immediately clears prior input.

Move the camera or change the can's base location? Recalibrate upright and repeat W/D learning. Only complete direction pairs are used; nearly parallel W/D examples are rejected. No calibration from another camera/device is silently reused.

## What it measures

The backend supplies measured segmented-mask centroid, area and central moments. Upright calibration averages a second of fresh, stable measurements, including the non-round neutral shape and centroid noise. The control vector is **centroid displacement relative to that neutral, normalized by apparent radius**, with a learned noise dead zone and responsive filtering. W/D calibration fits a local two-axis image-to-control mapping and scales each direction by the demonstrated lean. It is a local relative joystick estimate, not measured physical pitch/yaw or a full perspective 3D reconstruction. Sliding the entire can can also create input: keep its base fixed for tilt use.

Neutral calibration removes constant viewing-angle bias. It cannot recover hidden geometry or make an almost side-on camera reliable for both lean axes. Raise/straighten the camera if the two demonstrated directions look almost identical. This calibration is separate from checkerboard-based metric tabletop mapping.

The side silhouette is still available for diagnostics and spatial Z; it is not mixed into the calibrated can joystick because its uncalibrated axis could reintroduce a bias or conflict with learned W/D directions.

## Validation

`node tests/test_neutral_stick.cjs` checks slanted/elongated neutral projections, noisy rest, distinct-frame and stillness requirements, skewed W/D learning, return-to-neutral gating, occlusion and immediate release on recalibration. `tests/test_fast_motion.py` also checks measured overhead features and rejection of a different distant can when the original detection is missed.
