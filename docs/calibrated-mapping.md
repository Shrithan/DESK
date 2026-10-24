# Calibrated mapping: overhead camera → metres on the table

This branch merges agent 1's camera and calibration code (`camera/`, `calibration/`, mounts and stands under `camera/hardware/`) into the spatial-controls studio. It adds **metric table X/Y** for every object the overhead (`top`) camera tracks.

## Steps
```sh
# 1. calibrate the overhead webcam (needs the ingest server running for live capture)
python -m camera --rig camera/config/rig_c270_boom.json serve                        # :8100, check the view
python -m calibration board --out board.png --square-mm 20                           # print at 100 %, measure the squares
python -m calibration intrinsics --rig camera/config/rig_c270_boom.json --camera cam_1 --square-mm <measured>
python -m calibration extrinsics --rig camera/config/rig_c270_boom.json --square-mm <measured>   # board flat under the camera
# stop the ingest server (it holds the camera), then:
# 2. run the studio with the calibration
.venv/bin/python -m vision.live --calibration calibration/data/rig_calibration_boom.json --top-camera cam_1
#    with a calibrated side camera as well:  --front-camera cam_2   (enables calibrated 3D in /api/world)
```

## What you get
- **Live results:** every tracked object in the `top` session's result carries `table_xy_m: [x, y]` (metres), plus a `table_plane` block that names the calibration version.
- **Cards and map:** these switch to **absolute X/Y in cm from the calibration board's centre**, smoothed by the existing One Euro filter and prediction. Z stays relative to the side view.
- **Without `--calibration`:** behaviour is unchanged (percentages of the image).
- **Posting calibration:** `POST /api/calibration` accepts either format: agent 1's `phantom.rig_calibration` (optionally with `top_camera`, `front_camera` and `plane_height_m` keys) or the existing stereo `{front, top}` payload.

## Limits (stated honestly)
- **One camera, no depth:** X/Y is a **table-plane estimate**. The mask centroid's viewing ray is intersected with the table plane.
- **Tall objects:** for these the visible top sits above the table, so the estimate is pushed outward by about r·h/H. That's roughly 1 cm for a 5 cm object 20 cm off-centre under a 0.9 m camera.
- **Known height:** use `--plane-height-m` if all objects share a known height.
- **Real 3D height** needs a second calibrated view (`--front-camera`).
- **Re-calibrate:** the webcam must not move after calibration. Re-run `python -m calibration verify` after any bump.
- **Resolution changes:** frames analysed at a different resolution are rescaled automatically; a different aspect ratio is rejected.
