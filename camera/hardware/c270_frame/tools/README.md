# Rig preview renders

```bash
python camera/hardware/c270_frame/tools/export_scene.py > /tmp/rig/scene.json
cp camera/hardware/c270_frame/stl/mount_*.stl camera/hardware/c270_frame/tools/rig_scene.html /tmp/rig/
cd /tmp/rig && npm i three@0.169.0 && python3 -m http.server 8765 &
node camera/hardware/c270_frame/tools/shoot_rig_scene.js camera/hardware/c270_frame/renders   # needs playwright + chromium
```
