# Tabletop camera frame: 3× Logitech C270

A self-standing box frame, 1.0 m wide × 0.6 m deep × 0.5 m tall, that sits on the table and carries all three webcams:
- **`cam_1`** looks straight down from a crossbar.
- **`cam_2` and `cam_3`** are clamped near the two back top corners and look down at about 43° toward the centre.
- **The front is open**, so you can reach in.

Because all three cameras are on one rigid frame, **you calibrate once and can move the whole frame without recalibrating**, as long as no clamp or joint moves.

![rig overview](renders/rig_overview.png)

| back-left mount (`cam_2`) | overhead mount (`cam_1`) |
|---|---|
| ![](renders/mount_closeup_back_left.png) | ![](renders/mount_closeup_overhead.png) |

All geometry comes from [`camera/config/rig_c270.json`](../../config/rig_c270.json), and the calibration software reads the same file. If you change the frame size or a camera position there, regenerate the mounts.

## What each camera sees (nominal, before calibration)
| camera | lens position (m) | aim | table coverage |
|---|---|---|---|
| `cam_1` overhead | (0, 0, 0.49) | straight down | ≈ 0.44 × 0.25 m |
| `cam_2` back-left | (−0.40, 0.25, 0.49) | 43° down, toward (0, 0, 0.05) | whole centre area, obliquely |
| `cam_3` back-right | (0.40, 0.25, 0.49) | 43° down, toward (0, 0, 0.05) | whole centre area, obliquely |

The C270 has a narrow lens (55° diagonal), so at 0.5 m the overhead camera only sees about 44 × 25 cm. Objects must stay inside that patch to be seen by all three cameras.

| frame height | overhead coverage |
|---|---|
| 0.5 m (current) | 0.44 × 0.25 m |
| 0.6 m | 0.53 × 0.30 m |
| 0.7 m | 0.62 × 0.35 m |

If you need a bigger work area, set `frame.height_m` (and each mount's `tube_point_m` z) to 0.6–0.7 and regenerate.

## Parts list
| item | qty | notes |
|---|---|---|
| 3/4" schedule 40 PVC pipe (OD 26.7 mm) | about 7.5 m | or any rigid round tube; set `tube_od_mm` and regenerate the mounts |
| 3/4" 3-way corner fittings (side-outlet elbows, "furniture" fittings) | 8 | one for each corner of the box |
| 3/4" tee | 2 | hold the overhead crossbar on the two side top rails |
| Logitech C270 | 3 | label them `cam_1`..`cam_3` |
| Printed mounts | 3 | `stl/print_cam_*.stl` |
| M4 × 20 bolt + M4 nut | 3 | clamps each mount's ring onto the tube; a zip tie works in a pinch |
| Zip ties (≤ 4.5 mm wide) | 6 | two per camera, through the grooves on the sleeve |
| Paracord or strong string | about 4 m | diagonal cross-bracing, see below |
| Powered USB hub (USB-A ports → USB-C to the Mac) | 1 | all three cameras on one cable |

## Cut list (centre-to-centre spans)
For each fitting, push a pipe fully in and measure the distance from the fitting's centre to the pipe end. Call that `A` (often 20–30 mm). **Cut each pipe to its span − 2·A.**

| piece | span | qty |
|---|---|---|
| front/back rails (top and bottom) | 1.000 m | 4 |
| side rails, bottom | 0.600 m | 2 |
| side rails, top, front piece (corner → tee) | 0.355 m | 2 |
| side rails, top, back piece (tee → corner) | 0.245 m | 2 |
| legs | 0.500 m | 4 |
| overhead crossbar (tee → tee, 55 mm behind the middle) | 1.000 m | 1 |

## Assembly
1. **Frame:** dry-fit the box. Put one self-tapping screw through each fitting into its pipe so joints can't twist. Don't glue anything you may want to take apart.
2. **Bracing:** run paracord diagonals as an X on the back and both sides, tied tight at the corners. A 4-leg box racks (sways sideways) without bracing, and a 0.1° camera tilt moves 3D points by about 1.5 mm.
3. **Mounts:** clamp the mounts on with their rings, leaving the bolts finger-tight.
   - `cam_1`: on the crossbar, centred.
   - `cam_2` / `cam_3`: on the back top rail, 0.10 m in from each corner.
4. **Cameras:**
   - Fold each C270's clip back and slide the camera into its sleeve from the open end, lens centred.
   - Strap it with two zip ties in the grooves.
   - Route the cable through the notch in the closed end.
5. **Aiming:** open the diagnostics page (`python -m camera serve`, see `camera/README.md`). Rotate each ring on its tube until the orange work-area patch is centred in all three views, then tighten the bolts.
6. **Calibration:** run intrinsics and then extrinsics (`calibration/README.md`). Re-run extrinsics after any bump.

## Printing (Cal Hacks queue)
The `stl/print_*.stl` files are already oriented: each clamp ring stands on the bed and the mounts need supports.

**Settings:** PLA, 0.2 mm layers, 3 walls, 20 % gyroid infill, **organic/tree supports**, 4 mm brim.

**Estimated times:** from PrusaSlicer 2.7 with generic fast-printer settings. These are probably pessimistic for a P1S; use Bambu Studio's own estimate on the form.

| submission | file | estimate | filament |
|---|---|---|---|
| 1 | `print_cam_1_overhead.stl` | ~1 h 55 m | ~36 g |
| 2 | `print_cam_2_back_left.stl` | ~1 h 40 m | ~30 g |
| 3 | `print_cam_3_back_right.stl` | ~1 h 40 m | ~30 g |
| (all three) | `print_plate_all_mounts.stl` | ~5 h 15 m, **over the 3.5 h cap** | ~96 g |

- **Submit three jobs:** submit each mount as its own job. Ideally three teammates submit one each so they print at the same time, because each person can only have one job in the queue.
- **Filament:** Black first, since a dark mount reflects less light into the lenses.

## Verify before relying on it (not yet measured)
- **C270 body size:** set as 73 × 32 × 30 mm in `camera_model.body_mm`, from published specs. Measure your camera with calipers. If it differs, edit the JSON, regenerate, and reprint only that mount.
- **Tube OD:** set to 26.7 mm, which is nominal 3/4" sch 40 PVC. Measure your actual tube.
- **Test fit:** print `cam_2` first and check the fit before printing the others.

## Regenerate
```bash
pip install manifold3d trimesh numpy
python camera/hardware/c270_frame/generate_c270_mounts.py    # STLs into stl/
python -m pytest -q camera/hardware/c270_frame                # fit and keep-out checks
```
