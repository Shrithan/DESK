# CV selection for DESK — 24 October 2026

Recommendation: benchmark YOLOE-26 Small with per-camera OC-SORT association and the existing high-rate optical-flow refinement as the immediate latency baseline. Compare BoT-SORT with appearance matching if identity swaps dominate, rather than assuming a human-trained ReID model understands cans/stickers. Keep MediaPipe for hand evidence. Evaluate EdgeTAM for target-specific arbitrary-object mask propagation, seeded by a detector or registered region; do not assume it automatically recognizes an object from speech. No live model was changed by this research.

## Local timing

M4 Pro, arm64, torch 2.14.1 MPS, ultralytics 8.4.185. Existing prompted `desk-yoloe-{s,m,x}.pt` weights, synthetic fixture resized to 640×480, prediction imgsz 640, same ObjectSegmenter code, three additional warmups and 12 measured calls each, MPS synchronized before/after timing. Includes detector preprocessing/postprocessing, excludes capture/JPEG/HTTP/tracking/rendering. Current live application was not stopped; resource contention can affect timings. Sequential order and short runs are preliminary, not a controlled product benchmark. Sparse synthetic imagery understates some output-mask work and says nothing about detection accuracy.

| Model | Median call | p95 call |
| --- | ---: | ---: |
| YOLOE-26 S | 32.03 ms | 37.62 ms |
| YOLOE-26 M | 60.57 ms | 66.44 ms |
| YOLOE-26 X | 125.57 ms | 131.55 ms |

Source script/results: ignored `outputs/research/benchmark_cv.py` and `outputs/research/m4-model-latency.json`. Small was 3.92× faster than X for this workload. 30fps has a 33.3ms frame interval, so these measurements do not establish two-stream per-frame detection at 30fps for any tested size. The current shared model lock serializes detection between cameras and detection scheduling is ~120ms busy / ~350ms healthy. UI/tracking update FPS therefore is not neural detection FPS and is not measured camera-to-action latency.

## Alternatives

- **YOLOE-26 S/M:** open-vocabulary text/visual prompting and segmentation, useful for ordinary objects. S is the recommended latency baseline; M only if raw scene clips show useful accuracy gains. Existing X should be an acquisition/recovery candidate, not assumed the best control loop merely because it is largest. [Official YOLOE docs](https://docs.ultralytics.com/models/yoloe).
- **OC-SORT:** useful candidate for abrupt/nonlinear motion without additional ReID inference. **ByteTrack** is the simpler speed baseline. **BoT-SORT** supports optional appearance/ReID; assess its cost and tabletop-object appropriateness. These are association algorithms, not replacements for the detector. They do not solve cross-camera identity or calibration on their own. [Current tracking integration](https://docs.ultralytics.com/modes/track), [OC-SORT authors](https://github.com/noahcao/OC_SORT), [BoT-SORT authors](https://github.com/NirAharon/BoT-SORT).
- **EdgeTAM:** strongest Apple-focused arbitrary-object mask-tracking candidate in this review. Authors report 16fps on iPhone 15 Pro Max and provide CoreML export instructions. That is not an M4 Pro two-camera guarantee; assess full temporal-memory behavior and multi-object scaling, not just image encoder speed. It requires prompts and can still drift under occlusion. [Authors' repository](https://github.com/facebookresearch/EdgeTAM), [CoreML instructions](https://github.com/facebookresearch/EdgeTAM/blob/main/coreml/README.md).
- **SAM 3 / 3.1:** compelling open-vocabulary segmentation and tracking research, but official setup targets CUDA GPUs; no verified low-latency M4 deployment in this review. Not the immediate live-control recommendation. Could help offline annotation/teacher-assisted training. [Official repository](https://github.com/facebookresearch/sam3).
- **CoreML:** worthwhile deployment experiment for S/M, not an automatic speed win or guaranteed Neural Engine execution. Validate the exact YOLOE export, masks and compute placement; current upstream docs note macOS/coremltools execution limitations. No CoreML model was exported or benchmarked here. [Official CoreML export docs](https://docs.ultralytics.com/integrations/coreml).

## Required benchmark before switching production defaults

Use raw synchronized camera clips rather than screen recordings, with repeated fast slides, abrupt reversals, hand covers, object exits/re-entry, similar-object crossings and exposure changes. Label target IDs/masks and event times. Compare S/M/X with identical prompts, thresholds and capture settings, per-camera association, and tracker variants. Measure median/p95 camera-to-action age, detection recall, ID switches, reacquisition time, static-center jitter, missed/false cover presses, CPU/GPU load and steady-state two-camera throughput. Keep the latest frame and discard obsolete queued frames. Calibrate the camera geometry separately: model upgrades cannot turn uncalibrated image percentages into accurate metric 3D.

For broadly arbitrary objects, combine automatic detection with visual target enrollment/segmentation; a detector's class label alone is insufficient identity. Fine-tuning a small model on the actual tabletop lighting, transparent bottles, hands and stickers is a candidate improvement, not yet demonstrated evidence. No model can reconstruct information hidden by complete occlusion; inactive output on uncertain measurements remains preferable to invented control motion.

## EdgeTAM trial on the user's can clip (2026-10-24)

Tested the official EdgeTAM checkpoint with its video-memory predictor on MPS, float32, postprocessing disabled. Input: IMG_4448.mp4 sampled to 58 portrait frames at 480×854 and 8 fps. The model performs its own configured resize. One manually supplied initial box [176,225,299,510] enrolled the can; this experiment does not test automatic discovery or cross-camera association. All dependencies and the official source/checkpoint were isolated under ignored outputs/research, preserving the live environment. The backbone's redundant pretrained download was disabled; the complete checkpoint loaded strictly afterward.

After excluding the first two propagation outputs, median synchronized propagation time was **190.41 ms**, p95 **207.60 ms**, approximately **5.25 updates/s** at the median. These are per-frame propagation measurements, excluding model loading, initial enrollment, capture, transport, rendering and desktop actions. They are not directly comparable accuracy or end-to-end benchmarks against the earlier synthetic YOLOE detector timings. No CoreML or reduced-precision deployment was tested.

Visual spot checks at frames 20,35,45,57 showed masks following the visible can, including partial exits at the top and right edges. There is no annotated ground truth, no quantitative accuracy score, and this single-object clip does not establish recovery after full occlusion, identity across similar objects or multi-camera reliability.

Decision: do not replace the live tracker with this unoptimized MPS EdgeTAM implementation. Its measured update rate would add visible control lag. A fast per-frame tracker with periodic detector/segmentation corrections remains the practical architecture; EdgeTAM could be evaluated as a slower correction source only after proving it improves recovery. CoreML acceleration requires a separate measured experiment.

Artifacts: outputs/research/benchmark_edgetam.py (runner), edgetam-can.json (all timings and boxes), edgetam-can-preview.mp4 (mask visualization). Reproduce from the repository root with:

```sh
PYTHONPATH=outputs/research/edgetam-deps:outputs/research/EdgeTAM:. .venv/bin/python outputs/research/benchmark_edgetam.py
```

Source: [official EdgeTAM repository](https://github.com/facebookresearch/EdgeTAM). Live app configuration was not changed by this trial.
