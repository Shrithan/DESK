# Camera setup (Agent 1)

## Hardware
- `cam_1`, `cam_2`: iPhone 14 Pro Max. `cam_3`: iPhone 16 Pro.
- Each phone sits in a printed cradle (`camera/mounts/`) on a tripod or clamp arm via a 1/4"-20 thread.

## Physical layout (recommended starting point)
- Place the three cameras roughly 120° apart around the work area, 0.6–1.0 m from its centre, and 30–45° above the tabletop, all aimed at the centre.
- Use landscape orientation on all three phones, and keep it the same throughout a session.
- Avoid putting two cameras exactly opposite each other, because wide baselines with views from different sides triangulate best. Make sure every part of the work area is seen by at least two cameras.

## Lock the optics before calibrating
- Use the **1× main (wide) camera only**. iPhones switch lenses automatically (for example to macro or ultra-wide at close range), and a switch makes the intrinsics invalid. The sender must select a fixed lens, or the setup must keep the subject far enough away that no switch happens.
- Lock focus and exposure (AE/AF lock), turn off zoom, and turn off video stabilization, since stabilization crops and warps the frame.
- If any of these change, re-run intrinsics for that camera. If any phone is bumped or re-seated in its cradle, re-run extrinsics.
