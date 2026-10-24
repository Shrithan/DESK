# Phantom vision — Agent 2

CPU markerless tracking prototype. This branch contains the vision workstream;
camera ingestion, calibration, geometry, backend, and frontend are upstream/downstream work.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
.venv/bin/python -m vision.demo --preview /tmp/phantom-preview.jpg
```

Python 3.10+ with compatible NumPy/OpenCV wheels works on other platforms.
The demo emits real image-derived 2D feature motion from synthetic RGB frames;
it does not produce metric XYZ or claim physical-camera validation.

Recorded input: `.venv/bin/python -m vision.demo --video /path/input.mp4 --click 110 100 --mask /path/first-mask.png`.
The mask is optional; without it, click selection uses restricted color flood-fill.
Recordings and weights are excluded from Git. See [vision integration](docs/vision.md)
and [readiness/status](docs/status/AGENT-2.md).
