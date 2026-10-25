# EdgeTAM with fast optical flow

Run the optional hybrid mode locally:

```sh
PYTHONPATH=outputs/research/edgetam-deps:. .venv/bin/python -m vision.live --port 8765 --device mps --model-size x --temporal edgetam
```

The current Mac already has the source, checkpoint and isolated dependencies prepared. Other checkouts must obtain the official [EdgeTAM source](https://github.com/facebookresearch/EdgeTAM) at revision `7711e012a30a2402c4eaab637bdb00a521302c91`, including `checkpoints/edgetam.pt`, under `outputs/research/EdgeTAM`. Install its Python requirements and `timm==1.0.15` in a compatible environment (the project's existing torch/torchvision are used on this Mac). `--edgetam-source` and `--edgetam-checkpoint` override those paths. Model weights, upstream source and isolated dependencies are ignored and are not shipped in Git. No CUDA extension is required; optional hole-filling postprocessing is disabled.

YOLOE discovers objects and refreshes recognition about once a second. EdgeTAM follows enrolled masks between refreshes; optical flow updates each received camera frame while these models work on a background thread. The camera previews keep their original capture settings. This does not create 60 independent visual measurements from a 30 fps camera.

Both cameras share model weights and a GPU lock, but have separate temporal memories. Up to four enrolled objects per camera receive temporal corrections; other objects retain detection plus optical flow. Temporal masks carry existing object IDs and cannot enroll objects themselves. Existing spatial/appearance gates still reject implausible matches. Enrollment masks are not counted as fresh tracking evidence. Previously enrolled objects can continue receiving temporal tracking after optical flow loses them.

One inference job per camera prevents queued old frames. Corrections older than 600 ms from submission are discarded. Existing motion compensation shifts accepted results toward the current tracked position. Camera resets and resolution changes invalidate outstanding results. Memory is periodically re-enrolled and bounded to 24 sampled frames (usually earlier at the next YOLO refresh). Runtime failures disable EdgeTAM for that camera, retain asynchronous discovery/flow and display an error. Starting or resetting a camera retries it. Missing model files/dependencies fail startup explicitly.

The dashboard's model label identifies hybrid mode; each frame response also includes `temporal_tracking.enabled`, `status` and `correction_ms`. `--temporal flow` restores the original pipeline. Hybrid mode requires YOLOE and asynchronous inference.

Measured unoptimized EdgeTAM MPS propagation is about 190 ms for one object, with additional costs for enrollment and discovery. Two cameras and multiple objects share processing capacity, so correction rate will vary. Fast control output between corrections is based on optical flow, not additional AI measurements. Live physical camera accuracy and end-to-end control latency still require testing; this mode does not guarantee perfect occlusion recovery or identity.
