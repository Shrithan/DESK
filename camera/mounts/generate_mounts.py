"""Generate 3D-printable iPhone cradles with a 1/4"-20 tripod nut trap.

One cradle per phone model in phone_models.json. Each cradle is a back plate
with a bottom cup (side walls + front lips) that holds the phone by its
USB-C end, an open corner so the rear camera module is never covered, a
captive 1/4"-20 hex nut for any tripod / ball head / clamp arm, and posts
for an elastic band near the top.

Mount frame (all mm, right-handed): +X across the phone width viewed from the
FRONT (screen), +Y from the USB-C end toward the camera end, +Z out of the
screen. The phone back sits on z = 0. The rear camera (top-left seen from the
back) is therefore at x ~ W, y ~ H, on the same edge as the side button and
the 16 Pro Camera Control.

Usage:
    pip install manifold3d trimesh numpy
    python camera/mounts/generate_mounts.py            # writes STLs to camera/mounts/stl/
    python camera/mounts/generate_mounts.py --case 1.5 # extra room for a thin case
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import Manifold

HERE = Path(__file__).resolve().parent

# Print-tuned constants (PETG/PLA, 0.4 mm nozzle).
CLEARANCE = 0.4  # per side, between phone body and cradle
PLATE_T = 3.0  # back plate thickness
WALL_T = 2.6  # side / bottom wall thickness
LIP = 2.4  # how far the front lips overlap the screen edge
LIP_T = 2.0  # front lip thickness
CUP_H = 24.0  # side wall height measured from the bottom edge of the phone
USBC_SLOT_W = 16.0  # cable relief in the bottom wall

# 1/4"-20 tripod thread: standard hex nut is 7/16" (11.11 mm) across flats, ~5.6 mm thick.
NUT_AF = 11.11 + 0.3
NUT_T = 5.6 + 0.3
BOLT_D = 6.6
BOSS_R = 13.0
BOSS_H = 9.0  # how far the boss protrudes behind the back plate
NUT_FLOOR = 2.0  # material between the nut and the outer boss face

BAND_POST = (5.0, 4.0)  # (x protrusion, y length) of the elastic band posts
BAND_GAP = 6.0  # channel the band sits in

# Optional edge mount: a second 1/4"-20 nut on the long edge opposite the camera, so the
# cradle can hang from a boom arm with the camera looking straight down at the table.
EDGE_BLOCK = (12.0, 28.0)  # (x protrusion beyond the wall, y length)
EDGE_BLOCK_BACK = 6.0  # how far the block extends behind the back plate
EDGE_RIB_X = 25.0  # rib behind the plate that ties the block into it


@dataclass(frozen=True)
class Phone:
    name: str
    height: float
    width: float
    depth: float
    notch_w: float
    notch_h: float
    control_side_wall: float
    edge_mount: bool = False

    @classmethod
    def from_json(cls, name: str, d: dict) -> "Phone":
        return cls(
            name=name,
            height=d["height_mm"],
            width=d["width_mm"],
            depth=d["depth_mm"],
            notch_w=d["camera_notch_w_mm"],
            notch_h=d["camera_notch_h_mm"],
            control_side_wall=d["control_side_wall_mm"],
            edge_mount=d.get("edge_mount", False),
        )


def box(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> Manifold:
    return Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def cylinder(x: float, y: float, z0: float, h: float, r: float, segments: int = 64) -> Manifold:
    return Manifold.cylinder(h, r, r, segments).translate([x, y, z0])


def build_cradle(phone: Phone, case_t: float = 0.0) -> Manifold:
    # Pocket the phone (plus case and clearance) occupies.
    w = phone.width + 2 * (case_t + CLEARANCE)
    h = phone.height + 2 * (case_t + CLEARANCE)
    d = phone.depth + 2 * case_t + CLEARANCE
    z_front = d + LIP_T

    plate = box(-WALL_T, -WALL_T, -PLATE_T, w + WALL_T, h, 0)
    # Open the camera corner completely, through the side wall too.
    notch = box(w - phone.notch_w, h - phone.notch_h, -PLATE_T - 1, w + WALL_T + 1, h + 1, 1)
    plate = plate - notch

    bottom_wall = box(-WALL_T, -WALL_T, -PLATE_T, w + WALL_T, 0, z_front)
    # x = w is the side-button edge (incl. 16 Pro Camera Control): keep that wall short.
    control_wall = box(w, -WALL_T, -PLATE_T, w + WALL_T, phone.control_side_wall, z_front)
    far_wall = box(-WALL_T, -WALL_T, -PLATE_T, 0, CUP_H, z_front)

    lips = (
        box(-WALL_T, -WALL_T, d, w + WALL_T, LIP, z_front)
        + box(w - LIP, -WALL_T, d, w + WALL_T, phone.control_side_wall, z_front)
        + box(-WALL_T, -WALL_T, d, LIP, CUP_H, z_front)
    )
    cradle = plate + bottom_wall + control_wall + far_wall + lips

    # USB-C cable relief through the bottom wall and lip.
    cradle = cradle - box(w / 2 - USBC_SLOT_W / 2, -WALL_T - 1, -0.5, w / 2 + USBC_SLOT_W / 2, LIP + 0.5, z_front + 1)

    # Tripod boss near the plate's centre of area (below the camera notch).
    bx, by = w / 2, (h - phone.notch_h) * 0.55
    boss = cylinder(bx, by, -PLATE_T - BOSS_H, BOSS_H, BOSS_R)
    # Teardrop toward -Y so the boss prints without supports when standing on the USB-C end.
    tip = cylinder(bx, by - BOSS_R * math.sqrt(2), -PLATE_T - BOSS_H, BOSS_H, 0.01, segments=8)
    cradle = cradle + (boss + tip).hull()
    nut_r = NUT_AF / 2 / math.cos(math.pi / 6)
    z_floor = -PLATE_T - BOSS_H + NUT_FLOOR
    # Hex channel open toward the phone side: drop the nut in, the phone keeps it captive.
    cradle = cradle - cylinder(bx, by, z_floor, -z_floor + 1, nut_r, segments=6)
    cradle = cradle - cylinder(bx, by, -PLATE_T - BOSS_H - 1, BOSS_H + PLATE_T + 2, BOLT_D / 2)

    # Elastic band posts on both long edges just below the camera notch.
    py = h - phone.notch_h - 4 - BAND_GAP - BAND_POST[1]
    for y0 in (py, py + BAND_POST[1] + BAND_GAP):
        cradle = cradle + box(-WALL_T - BAND_POST[0], y0, -PLATE_T, -WALL_T, y0 + BAND_POST[1], 0)
        cradle = cradle + box(w + WALL_T, y0, -PLATE_T, w + WALL_T + BAND_POST[0], y0 + BAND_POST[1], 0)

    if phone.edge_mount:
        cradle = add_edge_mount(cradle, h, z_front)

    return cradle


def add_edge_mount(cradle: Manifold, h: float, z_front: float) -> Manifold:
    """Nut block on the x = 0 edge; the bolt axis is along +X, the nut slides in from the back."""
    ex, ey = EDGE_BLOCK
    x_out = -WALL_T - ex
    y0 = h * 0.30
    y1 = y0 + ey
    z0 = -PLATE_T - EDGE_BLOCK_BACK
    cradle = cradle + box(x_out, y0, z0, 0, y1, z_front) + box(0, y0, z0, EDGE_RIB_X, y1, -PLATE_T)
    # 45-degree gussets under the block and rib so they print without supports standing on the USB-C end.
    cradle = cradle + (box(x_out, y0, z0, -WALL_T, y0 + 0.01, z_front) + box(-WALL_T, y0 - ex, z0, -WALL_T + 0.01, y0 + 0.01, z_front)).hull()
    cradle = cradle + (box(x_out, y0, z0, EDGE_RIB_X, y0 + 0.01, -PLATE_T) + box(x_out, y0 - EDGE_BLOCK_BACK, -PLATE_T - 0.01, EDGE_RIB_X, y0 + 0.01, -PLATE_T)).hull()

    yc, zc = (y0 + y1) / 2, (z0 + z_front) / 2
    nut_r = NUT_AF / 2 / math.cos(math.pi / 6)
    nut_x = x_out + NUT_FLOOR + 0.5
    # Hex prism with its axis along X; flats face +/-Y so the slot below can be exactly NUT_AF wide.
    hex_pocket = Manifold.cylinder(NUT_T, nut_r, nut_r, 6).rotate([0, 90, 0]).translate([nut_x, yc, zc])
    slot = box(nut_x, yc - NUT_AF / 2, z0 - 1, nut_x + NUT_T, yc + NUT_AF / 2, zc)
    # Blind hole: stops 1 mm short of the wall so a long tripod screw can never touch the phone.
    bolt = Manifold.cylinder(-x_out - WALL_T, BOLT_D / 2, BOLT_D / 2, 64).rotate([0, 90, 0]).translate([x_out - 1, yc, zc])
    return cradle - hex_pocket - slot - bolt


def print_oriented(m: Manifold) -> Manifold:
    """Stand the cradle on its USB-C end (mount +Y becomes build +Z), sitting on the bed at z = 0."""
    m = m.rotate([90, 0, 0])
    x0, y0, z0, x1, y1, _ = m.bounding_box()
    return m.translate([-(x0 + x1) / 2, -(y0 + y1) / 2, -z0])


def print_plate(parts: list[Manifold], gap: float = 12.0) -> Manifold:
    """Lay print-oriented parts side by side along X, centred on the bed origin."""
    plate, x = Manifold(), 0.0
    for part in parts:
        x0, _, _, x1, _, _ = part.bounding_box()
        plate = plate + part.translate([x - x0, 0, 0])
        x += (x1 - x0) + gap
    x0, y0, _, x1, y1, _ = plate.bounding_box()
    return plate.translate([-(x0 + x1) / 2, -(y0 + y1) / 2, 0])


def to_trimesh(m: Manifold) -> trimesh.Trimesh:
    mesh = m.to_mesh()
    verts = np.asarray(mesh.vert_properties)[:, :3]
    faces = np.asarray(mesh.tri_verts)
    return trimesh.Trimesh(vertices=verts, faces=faces, process=True)


def load_phones(path: Path = HERE / "phone_models.json") -> dict[str, Phone]:
    data = json.loads(path.read_text())
    return {name: Phone.from_json(name, d) for name, d in data["models"].items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", type=float, default=0.0, help="case wall thickness in mm (0 = bare phone)")
    ap.add_argument("--out", type=Path, default=HERE / "stl")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    suffix = f"_case{args.case:g}mm" if args.case else ""
    phones = load_phones()
    cradles = {name: build_cradle(phone, args.case) for name, phone in phones.items()}
    outputs = {f"cradle_{name}{suffix}.stl": c for name, c in cradles.items()}

    # Ready-to-slice plates, one per printer-queue submission (parts already standing upright).
    rig = json.loads((HERE / "phone_models.json").read_text())["rig"]
    count = {name: sum(cam["model"] == name for cam in rig.values()) for name in phones}
    for name, n in count.items():
        for k in sorted({1, n} - {0}):
            outputs[f"print_plate_{k}x_{name}{suffix}.stl"] = print_plate([print_oriented(cradles[name])] * k)

    for filename, m in outputs.items():
        mesh = to_trimesh(m)
        path = args.out / filename
        mesh.export(path)
        ext = mesh.bounding_box.extents
        print(f"{path.relative_to(HERE.parent.parent)}  watertight={mesh.is_watertight}  "
              f"size={ext[0]:.1f}x{ext[1]:.1f}x{ext[2]:.1f} mm  volume={mesh.volume / 1000:.1f} cm^3")


if __name__ == "__main__":
    main()
