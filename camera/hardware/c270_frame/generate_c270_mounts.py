"""Generate printable Logitech C270 mounts for the tabletop frame in camera/config/rig_c270.json.

Each mount is one part: a split clamp ring around the frame tube, a strut, and a sleeve that
grips the C270 body by its top and bottom faces. The aim (yaw and pitch) is baked into the
part from the rig config, so a camera clamped at its marked spot already points at the work
area; calibration measures the exact pose afterwards.

Mount geometry is built in frame axes (mm) with the tube centre at the origin, then laid flat
for printing with the clamp ring on the bed.

Usage:
    pip install manifold3d trimesh numpy
    python camera/hardware/c270_frame/generate_c270_mounts.py
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import Manifold

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from camera.rig import DEFAULT_RIG_CONFIG, CameraSpec, load_rig  # noqa: E402

# Clamp ring around the tube.
TUBE_CLEARANCE = 0.4  # radial
RING_WALL = 4.5
RING_LEN = 24.0  # along the tube
SLOT = 3.0  # split gap
EAR = (10.0, 12.0)  # (radial extent, thickness across the slot) of each bolt ear
BOLT_D = 4.5  # M4 bolt or a zip tie through the ears
M4_NUT_AF = 7.0 + 0.3
M4_NUT_T = 3.2 + 0.3

# Sleeve around the C270 body (camera frame: +x image right, +y image down, +z optical axis).
CAM_CLEARANCE = 0.5
SLEEVE_WALL = 2.6
SLEEVE_DEPTH = 20.0  # how far back from the front face the sleeve grips
END_WALL = 2.6  # closes the -x end so the top and bottom walls form one C-channel
CABLE_NOTCH = (8.0, 14.0)  # (height, depth) relief in the end wall for the cable
LIP = 3.0  # front lips over the top and bottom edges of the face
LIP_T = 1.6
TIE_GROOVE = (5.0, 1.2)  # (width, depth) grooves that locate the two zip ties
TIE_X = 19.0  # zip ties at x = +/-19 mm, clear of the lens

PAD = 12.0  # strut cross-section at both ends


def box(x0, y0, z0, x1, y1, z1) -> Manifold:
    return Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def transform(m: Manifold, R: np.ndarray, t: np.ndarray) -> Manifold:
    """Apply x' = R x + t (R is 3x3)."""
    M = np.hstack([R, np.asarray(t, float).reshape(3, 1)])
    return m.transform(M.tolist())


def axis_basis(tube_axis: str) -> np.ndarray:
    """Rotation whose third column is the tube axis (used to build the ring along local z)."""
    a = {"x": np.array([1.0, 0, 0]), "y": np.array([0, 1.0, 0]), "z": np.array([0, 0, 1.0])}[tube_axis]
    u = np.array([0, 0, 1.0]) if tube_axis != "z" else np.array([1.0, 0, 0])
    v = np.cross(a, u)
    return np.stack([u, v, a], axis=1)


def sleeve(body: dict[str, float]) -> tuple[Manifold, Manifold]:
    """Sleeve in camera coordinates, plus the keep-out envelope of the camera body and view."""
    hy = body["height"] / 2 + CAM_CLEARANCE
    hx = body["width"] / 2 + CAM_CLEARANCE
    w = SLEEVE_WALL
    x0, x1 = -hx - END_WALL, hx - 6.0  # camera slides in from +x; its last 6 mm stay outside for grip
    top = box(x0, -hy - w, -SLEEVE_DEPTH, x1, -hy, LIP_T)
    bottom = box(x0, hy, -SLEEVE_DEPTH, x1, hy + w, LIP_T)
    end = box(x0, -hy - w, -SLEEVE_DEPTH, -hx, hy + w, LIP_T)
    lips = box(x0, -hy - w, 0, x1, -hy + LIP, LIP_T) + box(x0, hy - LIP, 0, x1, hy + w, LIP_T)
    s = top + bottom + end + lips
    nh, nd = CABLE_NOTCH
    s = s - box(x0 - 1, -nh / 2, -SLEEVE_DEPTH - 1, -hx + 1, nh / 2, -SLEEVE_DEPTH + nd)
    for sx in (-TIE_X, TIE_X):  # zip tie grooves on the outside of both walls
        gw, gd = TIE_GROOVE
        s = s - box(sx - gw / 2, -hy - w - 1, -SLEEVE_DEPTH - 1, sx + gw / 2, -hy - w + gd, LIP_T + 1)
        s = s - box(sx - gw / 2, hy + w - gd, -SLEEVE_DEPTH - 1, sx + gw / 2, hy + w + 1, LIP_T + 1)
    body_env = box(-hx, -hy, -body["depth"] - 25, hx, hy, 0)  # body + folded clip behind it
    # Field of view keep-out: a generous box in front of the lens (C270 dFOV 55 deg).
    view = box(-hx, -hy + LIP, LIP_T, hx, hy - LIP, 200)
    return s, body_env + view


def build_mount(cam: CameraSpec, tube_od: float, body: dict[str, float]) -> Manifold:
    m = cam.mount
    offset = np.asarray(m["lens_offset_from_tube_mm"], float)
    R_cam_to_world = cam.R_world_to_camera.T

    # Clamp ring along the tube axis, centred at the origin.
    B = axis_basis(m["tube_axis"])
    r_in = tube_od / 2 + TUBE_CLEARANCE
    r_out = r_in + RING_WALL
    ring_local = Manifold.cylinder(RING_LEN, r_out, r_out, 96).translate([0, 0, -RING_LEN / 2])
    # Split + ears on the side facing away from the camera.
    away = -offset / np.linalg.norm(offset)
    away_local = B.T @ away
    ang = np.degrees(np.arctan2(away_local[1], away_local[0]))
    ears = box(r_in, -EAR[1] - SLOT / 2, -RING_LEN / 2, r_out + EAR[0], EAR[1] + SLOT / 2, RING_LEN / 2)
    bolt = Manifold.cylinder(2 * EAR[1] + SLOT + 2, BOLT_D / 2, BOLT_D / 2, 32).rotate([90, 0, 0])
    bolt = bolt.translate([r_out + EAR[0] / 2, EAR[1] + SLOT / 2 + 1, 0])
    nut_r = M4_NUT_AF / 2 / np.cos(np.pi / 6)
    nut = Manifold.cylinder(M4_NUT_T + 1, nut_r, nut_r, 6).rotate([90, 0, 0])
    nut = nut.translate([r_out + EAR[0] / 2, -EAR[1] - SLOT / 2 + M4_NUT_T, 0])
    slot = box(r_in - 1, -SLOT / 2, -RING_LEN / 2 - 1, r_out + EAR[0] + 1, SLOT / 2, RING_LEN / 2 + 1)
    ring_local = (ring_local + ears - bolt - nut - slot).rotate([0, 0, float(ang)])
    bore_local = Manifold.cylinder(RING_LEN + 2, r_in, r_in, 96).translate([0, 0, -RING_LEN / 2 - 1])
    ring = transform(ring_local, B, [0, 0, 0])
    bore = transform(bore_local, B, [0, 0, 0])

    # Sleeve placed at the lens offset with the camera orientation.
    s_cam, keep_cam = sleeve(body)
    s = transform(s_cam, R_cam_to_world, offset)
    keep = transform(keep_cam, R_cam_to_world, offset)

    # Strut: hull of a pad on the ring surface and the sleeve face that points most toward the
    # tube: the top wall (-y), bottom wall (+y) or closed end (-x, used by portrait cameras).
    to_tube_cam = cam.R_world_to_camera @ (-offset)
    to_tube_cam /= np.linalg.norm(to_tube_cam)
    hy = body["height"] / 2 + CAM_CLEARANCE
    hx = body["width"] / 2 + CAM_CLEARANCE
    faces = {"top": np.array([0, -1.0, 0]), "bottom": np.array([0, 1.0, 0]), "end": np.array([-1.0, 0, 0])}
    face = max(faces, key=lambda k: float(faces[k] @ to_tube_cam))
    if face == "end":
        x0 = -hx - END_WALL
        wall_cam = box(x0 - 0.01, -hy * 0.8, -SLEEVE_DEPTH, x0 + 1.0, hy * 0.8, LIP_T)  # overlaps the end wall
    else:
        sign = -1.0 if face == "top" else 1.0
        wall_cam = box(-hx * 0.6, -0.01, -SLEEVE_DEPTH, hx * 0.6, 0.01, LIP_T).translate([0, sign * (hy + SLEEVE_WALL), 0])
    wall = transform(wall_cam, R_cam_to_world, offset)
    toward_cam = offset - np.dot(offset, B[:, 2]) * B[:, 2]
    toward_cam /= np.linalg.norm(toward_cam)
    pad_c = toward_cam * (r_out - 1.0)
    pad = transform(box(-PAD / 2, -PAD / 2, -0.5, PAD / 2, PAD / 2, 0.5).scale([1, RING_LEN / PAD, 1]),
                    _basis_with_normal(toward_cam, B[:, 2]), pad_c)
    strut = (wall + pad).hull()

    part = ring + s + strut - keep - bore
    if face == "end":  # keep the cable path through the strut
        nh, nd = CABLE_NOTCH
        x0 = -hx - END_WALL
        channel = box(x0 - 40, -nh / 2, -SLEEVE_DEPTH - 1, -hx + 1, nh / 2, -SLEEVE_DEPTH + nd)
        part = part - transform(channel, R_cam_to_world, offset)
    return part


def _basis_with_normal(n: np.ndarray, along: np.ndarray) -> np.ndarray:
    """Columns: x across, y along the tube, z = n."""
    n = n / np.linalg.norm(n)
    y = along - np.dot(along, n) * n
    y /= np.linalg.norm(y)
    return np.stack([np.cross(y, n), y, n], axis=1)


def print_orientation(m: Manifold, tube_axis: str) -> Manifold:
    """Stand the ring on the bed (tube axis vertical) and pick the spin with the least overhang."""
    B = axis_basis(tube_axis)
    base = transform(m, B.T, [0, 0, 0])  # tube axis -> +z
    best, best_score = None, None
    for flip, spin in itertools.product((0, 180), range(0, 360, 30)):
        cand = base.rotate([float(flip), 0, 0]).rotate([0, 0, float(spin)])
        x0, y0, z0, x1, y1, z1 = cand.bounding_box()
        cand = cand.translate([-(x0 + x1) / 2, -(y0 + y1) / 2, -z0])
        score = overhang_area(cand)
        if best_score is None or score < best_score:
            best, best_score = cand, score
    return best


def overhang_area(m: Manifold, limit_deg: float = 45.0) -> float:
    mesh = to_trimesh(m)
    n = mesh.face_normals
    c = mesh.triangles_center
    bad = (n[:, 2] < -np.cos(np.radians(limit_deg))) & (c[:, 2] > 0.3)
    return float(mesh.area_faces[bad].sum())


def to_trimesh(m: Manifold) -> trimesh.Trimesh:
    mesh = m.to_mesh()
    return trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts), process=True)


def print_plate(parts: list[Manifold], gap: float = 8.0, bed: float = 210.0) -> Manifold:
    """Shelf-pack parts so the plate fits a 220 mm bed (Adventurer 5M) with margin.

    Tries every order and a 0/90 degree spin per part; keeps the layout with the smallest
    longest side.
    """
    best, best_size = None, None
    for order in itertools.permutations(range(len(parts))):
        for spins in itertools.product((0, 90), repeat=len(parts)):
            plate = _shelf_pack([parts[i].rotate([0, 0, float(sp)]) for i, sp in zip(order, spins)], gap, bed)
            x0, y0, _, x1, y1, _ = plate.bounding_box()
            size = max(x1 - x0, y1 - y0)
            if best_size is None or size < best_size:
                best, best_size = plate, size
    return best


def _shelf_pack(parts: list[Manifold], gap: float, bed: float) -> Manifold:
    plate, x, y, row_h = Manifold(), 0.0, 0.0, 0.0
    for p in parts:
        x0, y0, _, x1, y1, _ = p.bounding_box()
        if x > 0 and x + (x1 - x0) > bed:
            x, y, row_h = 0.0, y + row_h + gap, 0.0
        plate = plate + p.translate([x - x0, y - y0, 0])
        x += (x1 - x0) + gap
        row_h = max(row_h, y1 - y0)
    x0, y0, _, x1, y1, _ = plate.bounding_box()
    return plate.translate([-(x0 + x1) / 2, -(y0 + y1) / 2, 0])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rig", type=Path, default=DEFAULT_RIG_CONFIG)
    ap.add_argument("--out", type=Path, default=HERE / "stl")
    args = ap.parse_args()

    rig = load_rig(args.rig)
    data = json.loads(Path(args.rig).read_text())
    body = data["camera_model"]["body_mm"]
    tube_od = float(rig.frame["tube_od_mm"])
    args.out.mkdir(parents=True, exist_ok=True)

    printable = []
    for cam in rig.cameras:
        part = build_mount(cam, tube_od, body)
        mesh = to_trimesh(part)
        mesh.export(args.out / f"mount_{cam.id}_{cam.role}.stl")
        oriented = print_orientation(part, cam.mount["tube_axis"])
        printable.append(oriented)
        to_trimesh(oriented).export(args.out / f"print_{cam.id}_{cam.role}.stl")
        d = cam.R_world_to_camera[2]
        pitch = np.degrees(np.arcsin(-d[2]))
        yaw = np.degrees(np.arctan2(d[0], d[1]))
        print(f"{cam.id} ({cam.role}): watertight={mesh.is_watertight} volume={mesh.volume / 1000:.1f} cm^3 "
              f"lens at {np.round(cam.lens_position_m, 3).tolist()} m, looks {pitch:.0f} deg down, heading {yaw:.0f} deg")
    plate = to_trimesh(print_plate(printable))
    plate.export(args.out / "print_plate_all_mounts.stl")
    ext = plate.bounding_box.extents
    print(f"print_plate_all_mounts.stl: {ext[0]:.0f} x {ext[1]:.0f} x {ext[2]:.0f} mm, {plate.volume / 1000:.1f} cm^3, "
          f"watertight={plate.is_watertight}")


if __name__ == "__main__":
    main()
