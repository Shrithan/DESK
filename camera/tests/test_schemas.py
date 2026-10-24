"""Live outputs must match the proposed contract schemas."""

import json

import pytest

from calibration.synthetic import ground_truth_rig
from camera.ingest import CameraHub
from camera.rig import REPO_ROOT, load_rig

jsonschema = pytest.importorskip("jsonschema")


def schema(path):
    return json.loads((REPO_ROOT / path).read_text())


def test_inventory_and_health_match_schemas():
    rig = load_rig(overrides={c: {"kind": "synthetic"} for c in ("cam_1", "cam_2", "cam_3")})
    with CameraHub(rig) as hub:
        hub.wait_until_streaming(5)
        hub.frameset()
        jsonschema.validate(hub.inventory(), schema("camera/schema/camera_inventory.schema.json"))
        jsonschema.validate(hub.health(), schema("camera/schema/camera_health.schema.json"))


def test_calibration_matches_schema():
    jsonschema.validate(ground_truth_rig().to_dict(), schema("calibration/schema/rig_calibration.schema.json"))
