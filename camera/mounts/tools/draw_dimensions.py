import sys, math
sys.path.insert(0, "camera/mounts")
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from matplotlib.patches import Rectangle, FancyArrowPatch, Circle, Wedge
import generate_mounts as g  # run from repo root: python camera/mounts/tools/draw_dimensions.py camera/mounts/dimensions.png

phones = g.load_phones()
fig = plt.figure(figsize=(17, 7.6))
gs = fig.add_gridspec(2, 5, width_ratios=[1.25, 0.45, 1.25, 0.45, 2.0], height_ratios=[1, 0.06], wspace=0.25)
BLUE, PHONE, DIM = "#3b7dd8", "#d9d9d9", "#c0392b"

def dim(ax, p0, p1, text, off, horiz):
    (x0, y0), (x1, y1) = p0, p1
    if horiz:
        y = off
        ax.plot([x0, x0], [y0, y], color=DIM, lw=.6); ax.plot([x1, x1], [y1, y], color=DIM, lw=.6)
        ax.annotate("", (x0, y), (x1, y), arrowprops=dict(arrowstyle="<->", color=DIM, lw=1))
        ax.text((x0+x1)/2, y + 2, text, ha="center", va="bottom", color=DIM, fontsize=9, fontweight="bold")
    else:
        x = off
        ax.plot([x0, x], [y0, y0], color=DIM, lw=.6); ax.plot([x1, x], [y1, y1], color=DIM, lw=.6)
        ax.annotate("", (x, y0), (x, y1), arrowprops=dict(arrowstyle="<->", color=DIM, lw=1))
        ax.text(x - 2, (y0+y1)/2, text, ha="right", va="center", color=DIM, fontsize=9, fontweight="bold", rotation=90)

def project(mesh, axes):
    tri = mesh.vertices[mesh.faces][:, :, axes]
    return PolyCollection(tri, facecolor=BLUE, edgecolor=BLUE, lw=.1)

col = 0
for name, p in phones.items():
    m = g.to_trimesh(g.build_cradle(p))
    w = p.width + 2*g.CLEARANCE; h = p.height + 2*g.CLEARANCE; d = p.depth + g.CLEARANCE
    (x0, y0, z0), (x1, y1, z1) = m.bounds
    # Front view (looking at the screen side)
    ax = fig.add_subplot(gs[0, col])
    ax.add_collection(project(m, [0, 1]))
    ax.add_patch(Rectangle((g.CLEARANCE, g.CLEARANCE), p.width, p.height, fc=PHONE, ec="#888", alpha=.55, lw=1, ls="--"))
    ax.add_patch(Rectangle((w - p.notch_w, h - p.notch_h), p.notch_w, p.notch_h, fc="none", ec="#e67e22", lw=1.5, ls=":"))
    ax.text(w - p.notch_w/2, h - p.notch_h/2, f"open camera\nwindow\n{p.notch_w:.0f} × {p.notch_h:.0f}", ha="center", va="center", fontsize=8, color="#e67e22")
    ax.text(w*0.35, h - p.notch_h - 22, f"phone\n{p.height} × {p.width}", ha="center", fontsize=8, color="#555")
    if p.edge_mount:
        ax.text(x0 - 2, h*0.30 + 14, "edge\n1/4\"-20\n(boom)", ha="right", va="center", fontsize=7, color="#555")
    pw = w + 2*g.WALL_T
    dim(ax, (-g.WALL_T, y1), (w + g.WALL_T, y1), f"{pw:.1f} plate", y1 + 8, True)
    dim(ax, (x0, y0), (x1, y0), f"{x1-x0:.1f} with band posts", y0 - 14, True)
    dim(ax, (x0, y0), (x0, y1), f"{y1-y0:.1f}", x0 - 8, False)
    dim(ax, (x1, y0), (x1, g.CUP_H), f"cup {g.CUP_H+g.WALL_T:.0f}", x1 + 22, False)
    ax.set_xlim(x0 - 28, x1 + 28); ax.set_ylim(y0 - 26, y1 + 22); ax.set_aspect("equal"); ax.axis("off")
    ax.set_title(f"{name.replace('_', ' ').replace('iphone', 'iPhone').replace('pro max','Pro Max').replace('pro','Pro')}\nfront view", fontsize=11)
    # Side view (Z horizontal, Y vertical)
    ax2 = fig.add_subplot(gs[0, col + 1])
    ax2.add_collection(project(m, [2, 1]))
    ax2.add_patch(Rectangle((0, g.CLEARANCE), p.depth, p.height, fc=PHONE, ec="#888", alpha=.55, lw=1, ls="--"))
    dim(ax2, (z0, y1), (z1, y1), f"{z1-z0:.1f}", y1 + 8, True)
    dim(ax2, (-g.PLATE_T, y0), (d + g.LIP_T, y0), f"{d + g.LIP_T + g.PLATE_T:.1f}", y0 - 14, True)
    ax2.text(z0 - 1, (h - p.notch_h)*0.55, "1/4\"-20\nboss", ha="right", va="center", fontsize=7, color="#555")
    ax2.set_xlim(z0 - 18, z1 + 8); ax2.set_ylim(y0 - 26, y1 + 22); ax2.set_aspect("equal"); ax2.axis("off")
    ax2.set_title("side view", fontsize=11)
    col += 2

# Rig layout (top view), meters
ax = fig.add_subplot(gs[0, 4])
ax.add_patch(Rectangle((-0.55, -0.45), 1.1, 0.9, fc="#f3efe6", ec="#999"))
ax.add_patch(Circle((0, 0), 0.25, fc="#fde9d9", ec="#e67e22", ls="--"))
ax.text(0, 0, "work area\n~0.5 m", ha="center", va="center", fontsize=9, color="#e67e22")
ax.text(-0.52, 0.42, "table", fontsize=8, color="#777", va="top")
R = 0.8
for cid, ang, model in [("cam_2", -90, "14 Pro Max"), ("cam_3", 20, "14 Pro Max")]:
    a = math.radians(ang); x, y = R*math.cos(a), R*math.sin(a)
    ax.add_patch(Wedge((x, y), 0.55, ang + 180 - 28, ang + 180 + 28, fc=BLUE, alpha=.22, ec="none"))
    ax.plot([x, 0], [y, 0], color=BLUE, lw=.8, ls=":")
    ax.add_patch(Rectangle((x - 0.05, y - 0.05), 0.1, 0.1, fc=BLUE, ec="k"))
    ax.text(x, y + (0.1 if y >= 0 else -0.1), f"{cid}\n{model}\ntripod, 30–45° up", ha="center", va="bottom" if y >= 0 else "top", fontsize=9, fontweight="bold")
ax.add_patch(Rectangle((-0.075, -0.04), 0.15, 0.08, fc="#e67e22", ec="k", zorder=5))
ax.plot([-0.0, 0.0], [0.04, 0.85], color="#555", lw=3, zorder=4)
ax.text(0.03, 0.62, "boom arm\n(from C-stand)", fontsize=8, color="#555")
ax.text(-0.3, -0.05, "cam_1  16 Pro\noverhead ~1.0 m\nlooking down", ha="right", va="center", fontsize=9, fontweight="bold", color="#b35900")
ax.annotate("", (0, 0), (R*math.cos(math.radians(20)), R*math.sin(math.radians(20))), arrowprops=dict(arrowstyle="<->", color=DIM))
ax.text(0.35, 0.02, "0.6–1.0 m", color=DIM, fontsize=9, fontweight="bold", rotation=20)
ax.text(0.22, -0.3, "~110°", color=DIM, fontsize=10, fontweight="bold")
ax.set_xlim(-1.15, 1.15); ax.set_ylim(-1.1, 1.05); ax.set_aspect("equal"); ax.axis("off")
ax.set_title("rig layout (top view)\n1 overhead + 2 angled, all landscape, aimed at centre", fontsize=11)

fig.text(0.5, 0.02, "All cradle dimensions in mm (bare phones, 0.4 mm clearance per side).   Grey dashed = phone.   Blue = printed cradle.   Orange dotted = camera keep-out.   Bottom wall has a 16 mm USB-C cable slot.",
         ha="center", fontsize=10, color="#444")
plt.savefig(sys.argv[1], dpi=120, bbox_inches="tight")
