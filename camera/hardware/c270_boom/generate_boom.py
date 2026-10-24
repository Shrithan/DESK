"""Printable 1 m camera boom: weighted base, 1 m leg, 0.5 m arm, C270 looking straight down.

Every part fits a 220 x 220 x 220 mm bed (Flashforge Adventurer 5M; Bambu P1S is bigger), so the
stand prints one part per job. Parts slot together with spigot joints and are pinned with an
M4 bolt through each joint; the bolt holes also fix the rotation, so when all holes line up the
arm points away from the leg and the camera points straight down.

    base  ->  5 x tube segment (leg)  ->  elbow  ->  2 x tube segment (arm)  ->  camera head

World axes for the assembled stand: +Z up, leg axis on the Z axis, arm along +X.
Camera: optical axis -Z (straight down); long image axis along Y (across the arm), so the
leg and base stay out of the picture.

    pip install manifold3d trimesh numpy
    python camera/hardware/c270_boom/generate_boom.py
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import Manifold

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
sys.path.insert(0, str(HERE.parent / "c270_frame"))
from generate_c270_mounts import CABLE_NOTCH, CAM_CLEARANCE, END_WALL, SLEEVE_DEPTH, SLEEVE_WALL, sleeve  # noqa: E402

from camera.rig import DEFAULT_RIG_CONFIG  # noqa: E402

# Tube and joints (mm). One segment design is reused 7 times (5 leg + 2 arm).
TUBE_OD = 40.0
WALL = 2.4
BORE = TUBE_OD - 2 * WALL  # 35.2: the female end of every joint
FIT = 0.25  # radial clearance in a joint
SPIGOT_OD = BORE - 2 * FIT  # 34.7
SPIGOT_ID = SPIGOT_OD - 2 * WALL  # 29.9: hollow all the way through (cable or weight)
SPIGOT_LEN = 30.0
SEG_LEN = 180.0  # body length; printed height = SEG_LEN + SPIGOT_LEN = 210 mm (fits a 220 mm bed)
PIN_D = 4.4  # M4 x 50 bolt + nut through every joint
PIN_Z = SPIGOT_LEN / 2  # pin 15 mm into the joint

N_LEG = 5
N_ARM = 2

# Base: hub + 4 rings that hold drink cans as ballast (cans stand on the ring floors).
HUB_OD = 52.0
HUB_H = 40.0
CAN_D = 67.0  # standard 355 ml can is ~66 mm
RING_WALL = 2.4
RING_H = 16.0
RING_FLOOR = 2.4
RING_FLOOR_W = 9.0  # width of the annular floor the can stands on
# Ring centres: shifted toward +X (under the arm) because the arm puts the stand's centre of mass
# ~13 cm out from the leg; this moves the tipping edge out to x = +121 mm.
RING_CENTRES = [(-20.0, -60.0), (-20.0, 60.0), (84.0, -60.0), (84.0, 60.0)]
SPOKE_W, SPOKE_H = 12.0, 8.0
CABLE_SLOT = (12.0, 16.0)  # (width, height) cable exit in the hub, at the bottom

# Head: socket for the arm's last spigot, then the C270 sleeve hanging below it.
HEAD_LEN = 80.0  # socket (30) + body; hollow with a closed end
HEAD_CAM_X = 42.0  # camera centre measured from the head's open (socket) end (centred under the cap)
CAM_DROP = 10.0  # gap from the bottom of the arm tube to the top of the camera's keep-out


@dataclass(frozen=True)
class Assembly:
    """Where each part sits in world coordinates (mm)."""

    base_top: float = HUB_H  # leg segment 1 starts here (on the hub's spigot)

    @property
    def leg_top(self) -> float:
        return self.base_top + N_LEG * SEG_LEN

    @property
    def arm_axis_z(self) -> float:
        return self.leg_top + SPIGOT_LEN + TUBE_OD / 2 + 5.0

    @property
    def arm_start_x(self) -> float:  # where arm segment 1's body starts (elbow spigot shoulder)
        return TUBE_OD / 2 + 5.0

    @property
    def head_start_x(self) -> float:
        return self.arm_start_x + N_ARM * SEG_LEN

    @property
    def lens(self) -> np.ndarray:
        body = _body()
        top_of_keepout = body["depth"] + 25.0  # body + folded clip behind the lens
        z = self.arm_axis_z - TUBE_OD / 2 - CAM_DROP - top_of_keepout
        return np.array([self.head_start_x + HEAD_CAM_X, 0.0, z])


def _body() -> dict:
    return json.loads(DEFAULT_RIG_CONFIG.read_text())["camera_model"]["body_mm"]


def box(x0, y0, z0, x1, y1, z1) -> Manifold:
    return Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def cyl(r: float, z0: float, z1: float, seg: int = 96) -> Manifold:
    return Manifold.cylinder(z1 - z0, r, r, seg).translate([0, 0, z0])


def tube(r_out: float, r_in: float, z0: float, z1: float) -> Manifold:
    return cyl(r_out, z0, z1) - cyl(r_in, z0 - 1, z1 + 1)


def pin_hole(z: float, axis: str = "x", length: float = 80.0) -> Manifold:
    h = Manifold.cylinder(length, PIN_D / 2, PIN_D / 2, 32).translate([0, 0, -length / 2])
    h = h.rotate([0, 90, 0]) if axis == "x" else h.rotate([90, 0, 0])
    return h.translate([0, 0, z])


def transform(m: Manifold, R: np.ndarray, t) -> Manifold:
    return m.transform(np.hstack([R, np.asarray(t, float).reshape(3, 1)]).tolist())


# ---- parts (each built in its own print-friendly frame, z up) ------------------------------

def segment() -> Manifold:
    """Tube: female socket at the bottom (z = 0), male spigot on top. Pin holes along local x."""
    body = tube(TUBE_OD / 2, BORE / 2, 0, SEG_LEN)
    shoulder = tube(TUBE_OD / 2, SPIGOT_ID / 2, SEG_LEN - 3.0, SEG_LEN)  # ties the spigot to the wall
    spig = tube(SPIGOT_OD / 2, SPIGOT_ID / 2, SEG_LEN - 3.0, SEG_LEN + SPIGOT_LEN)
    return body + shoulder + spig - pin_hole(PIN_Z) - pin_hole(SEG_LEN + PIN_Z)


def base() -> Manifold:
    hub = tube(HUB_OD / 2, HUB_OD / 2 - 4.0, 0, HUB_H) + tube(HUB_OD / 2, SPIGOT_ID / 2, HUB_H - 4.0, HUB_H)  # hollow, with a top deck
    spig = tube(SPIGOT_OD / 2, SPIGOT_ID / 2, HUB_H - 0.5, HUB_H + SPIGOT_LEN)
    part = hub + spig
    rings = Manifold()
    for cx, cy in RING_CENTRES:
        c = np.array([cx, cy, 0.0])
        ring = tube(CAN_D / 2 + RING_WALL, CAN_D / 2, 0, RING_H)
        floor = tube(CAN_D / 2 + 0.01, CAN_D / 2 - RING_FLOOR_W, 0, RING_FLOOR)
        rings = rings + (ring + floor).translate(c.tolist())
        L = float(np.hypot(c[0], c[1]))
        spoke = box(0, -SPOKE_W / 2, 0, L, SPOKE_W / 2, SPOKE_H).rotate([0, 0, float(np.degrees(np.arctan2(cy, cx)))])
        part = part + spoke
    part = part + rings
    # Hollow hub so a cable can come down the leg and out the side; pin hole through the spigot.
    part = part - cyl(SPIGOT_ID / 2, 6, HUB_H + SPIGOT_LEN + 1)
    w, h = CABLE_SLOT
    part = part - box(-HUB_OD, -w / 2, 2, 0, w / 2, 2 + h)  # exits toward -X (away from the arm), between rings
    return part - pin_hole(HUB_H + PIN_Z)


def elbow() -> Manifold:
    """Female socket at the bottom (onto the leg), male spigot along +X (into the arm)."""
    zc = SPIGOT_LEN + TUBE_OD / 2 + 5.0  # arm axis height above the socket mouth
    r = TUBE_OD / 2
    vert = cyl(r, 0, zc)
    corner = Manifold.sphere(r, 96).translate([0, 0, zc])
    hx = TUBE_OD / 2 + 5.0  # horizontal body ends here; spigot beyond
    horiz = Manifold.cylinder(hx, r, r, 96).rotate([0, 90, 0]).translate([0, 0, zc])
    spig = (cyl(SPIGOT_OD / 2, -0.5, SPIGOT_LEN) - cyl(SPIGOT_ID / 2, -1, SPIGOT_LEN + 1)).rotate([0, 90, 0]).translate([hx, 0, zc])
    gusset = box(0, -r * 0.55, 0, 0.01, r * 0.55, 0.01)  # 45 degree support under the horizontal arm
    gusset = (gusset.translate([0, 0, zc - hx - 2]) + box(hx - 0.01, -r * 0.55, zc - 2, hx, r * 0.55, zc)).hull()
    part = vert + corner + horiz + spig + gusset
    part = part - cyl(BORE / 2, -1, SPIGOT_LEN)  # socket for the leg
    part = part - cyl(SPIGOT_ID / 2, SPIGOT_LEN - 1, zc)  # cable / weight-saving channel
    part = part - Manifold.cylinder(hx + SPIGOT_LEN + 2, SPIGOT_ID / 2, SPIGOT_ID / 2, 64).rotate([0, 90, 0]).translate([0, 0, zc])
    part = part - pin_hole(PIN_Z, "x")  # matches the leg's pin axis (world X)
    spin = pin_hole(0, "y").translate([hx + PIN_Z, 0, zc])  # arm pin axis = world Y (horizontal)
    return part - spin


def head() -> Manifold:
    """Arm-end cap with the C270 looking straight down. Built in world axes, arm axis = +X at z = 0."""
    r = TUBE_OD / 2
    cap = Manifold.cylinder(HEAD_LEN, r, r, 96).rotate([0, 90, 0])
    cap = cap - Manifold.cylinder(HEAD_LEN - 3.0, BORE / 2, BORE / 2, 96).rotate([0, 90, 0]).translate([-0.01, 0, 0])  # hollow, closed far end
    cap = cap - pin_hole(0, "y").translate([PIN_Z, 0, 0])

    body = _body()
    s_cam, keep_cam = sleeve(body)
    # Camera axes in world: image x = +Y (across the arm), image y = +X (along the arm), optical axis -Z.
    R_cam_to_world = np.column_stack([[0, 1, 0], [1, 0, 0], [0, 0, -1.0]])
    lens = np.array([HEAD_CAM_X, 0.0, -(r + CAM_DROP + body["depth"] + 25.0)])
    s = transform(s_cam, R_cam_to_world, lens)
    keep = transform(keep_cam, R_cam_to_world, lens)

    # Two legs from the cap down to the sleeve walls that face along the arm (camera +/-y),
    # straddling the camera body so nothing sits behind it.
    hy = body["height"] / 2 + CAM_CLEARANCE
    hx = body["width"] / 2 + CAM_CLEARANCE
    legs = Manifold()
    for sgn in (-1, 1):
        wx = HEAD_CAM_X + sgn * (hy + SLEEVE_WALL / 2)
        # the top flares 45 degrees along the cap so the cap needs no support when printed camera-down
        z_top = -(BORE / 2 + 0.8)  # inside the cap's wall, never inside its bore (the arm spigot goes there)
        flare = z_top - (lens[2] + SLEEVE_DEPTH)
        top = box(max(wx - flare, 3.0), -12, z_top, min(wx + flare, HEAD_LEN - 3.0), 12, z_top + 0.01)
        bottom = box(wx - SLEEVE_WALL / 2, -14, lens[2] - LIP_T_SAFE, wx + SLEEVE_WALL / 2, 14, lens[2] + SLEEVE_DEPTH)
        legs = legs + (top + bottom).hull()
    part = cap + legs + s - keep
    part = part - Manifold.cylinder(HEAD_LEN - 3.0, BORE / 2, BORE / 2, 96).rotate([0, 90, 0]).translate([-0.01, 0, 0])
    # Cable path from the sleeve's closed end (camera -x = world -Y) is left open: zip-tie the cable along the arm.
    return part


LIP_T_SAFE = 1.6


# ---- assembly, printing, export ------------------------------------------------------------

def assembled() -> dict[str, Manifold]:
    a = Assembly()
    parts = {"base": base()}
    for i in range(N_LEG):
        parts[f"leg_{i + 1}"] = segment().translate([0, 0, a.base_top + i * SEG_LEN])
    parts["elbow"] = elbow().translate([0, 0, a.leg_top])
    R_arm = np.column_stack([[0, 1.0, 0], [0, 0, 1.0], [1.0, 0, 0]])  # local z (axis) -> world +X, local x (pins) -> world Y
    for i in range(N_ARM):
        parts[f"arm_{i + 1}"] = transform(segment(), R_arm, [a.arm_start_x + i * SEG_LEN, 0, a.arm_axis_z])
    parts["head"] = head().translate([a.head_start_x, 0, a.arm_axis_z])
    return parts


def lay_flat(m: Manifold, candidates: list[np.ndarray] | None = None) -> Manifold:
    """Pick the axis-aligned orientation with the least overhang, resting on z = 0."""
    rots = candidates or [np.array(r) for r in _cube_rotations()]
    best, score = None, None
    for R in rots:
        c = transform(m, R, [0, 0, 0])
        x0, y0, z0, x1, y1, _ = c.bounding_box()
        c = c.translate([-(x0 + x1) / 2, -(y0 + y1) / 2, -z0])
        s = _overhang(c)
        if score is None or s < score:
            best, score = c, s
    return best


def _cube_rotations() -> list[list[list[float]]]:
    out = []
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((-1, 1), repeat=3):
            R = np.zeros((3, 3))
            for i, (p, s) in enumerate(zip(perm, signs)):
                R[i, p] = s
            if np.isclose(np.linalg.det(R), 1):
                out.append(R.tolist())
    return out


def _overhang(m: Manifold) -> float:
    t = to_trimesh(m)
    n, c = t.face_normals, t.triangles_center
    bad = (n[:, 2] < -0.71) & (c[:, 2] > 0.3)
    return float(t.area_faces[bad].sum())


def to_trimesh(m: Manifold) -> trimesh.Trimesh:
    mesh = m.to_mesh()
    return trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts), process=True)


def print_parts() -> dict[str, tuple[Manifold, int]]:
    """Print-oriented parts and how many of each to print."""
    return {
        "segment": (segment(), N_LEG + N_ARM),  # already upright: socket down, spigot up
        "base": (base(), 1),
        "elbow": (elbow(), 1),  # socket down; small support under the spigot
        "head": (lay_flat(head()), 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=HERE / "stl")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for name, (part, qty) in print_parts().items():
        t = to_trimesh(part)
        t.export(args.out / f"print_{name}.stl")
        e = t.bounding_box.extents
        print(f"print_{name}.stl  x{qty}  {e[0]:.0f} x {e[1]:.0f} x {e[2]:.0f} mm  {t.volume / 1000:.1f} cm^3  "
              f"watertight={t.is_watertight}")
    whole = Manifold()
    for p in assembled().values():
        whole = whole + p
    to_trimesh(whole).export(args.out / "assembled_preview.stl")
    a = Assembly()
    print(f"arm axis {a.arm_axis_z / 1000:.3f} m above the table, lens at {np.round(a.lens / 1000, 3).tolist()} m")


if __name__ == "__main__":
    main()
