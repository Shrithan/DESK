# Recording diagnosis and fixes — 2026-10-24 16:40

Reviewed the user's 16.4-second screen recording. Visible symptoms: an overhead box sometimes moves into empty background, the side track intermittently disappears despite the visible can, and object class labels vary by viewpoint. YOLOE-X replay on sampled, cropped preview regions found the side can mostly as cup/can, once book while tilted; the overhead lid varied between bottle, disk and cup, and an occluded region once appeared as phone. These are diagnostic crops containing UI overlays, not raw-camera ground truth or an accuracy benchmark.

Changes:

- Align asynchronous detection masks from the submitted image to the current image using forward/backward optical flow and robust affine fitting. Reject masks that cannot be aligned after occlusion. Do not use drifting/predicted track centres to relocate current production detections.
- Preserve the last measured flow image/points/mask during an unreliable interval. Previously constant-velocity coasting overwrote these anchors, allowing background points to become a tracked object on the next update. Recovery uses elapsed time since the last measured frame.
- Normalize grayscale consistently when semantic corrections reseed optical flow; discard old coast velocity after a correction.
- Match overhead disk/container label flicker only for a unique local object with overlapping geometry and matching appearance. Preserve its enrolled ID/name. Distant disks do not become the can.
- Cap overlay latency lead to 20% of the object's smaller dimension, at most 16 pixels, with at most 60 ms extrapolation; expire lead after 160 ms. Hide stale tracking overlays after 220 ms.

Validation: 226 Python tests passed, 2 skipped; all 16 JavaScript test scripts passed. New regression cases cover direction reversals during model latency, full cover rejecting old masks, immutable flow anchors during dropouts, lid label changes retaining one ID, and a distant disk not stealing a can ID. On two sampled recording crop pairs, median mask-alignment cost over ten measured calls was about 4.1 ms side / 2.9 ms overhead using box-shaped diagnostic masks. These timings do not establish end-to-end latency or physical tracking accuracy.

YOLOE Extra Large remains active; EdgeTAM is disabled. Live physical movement still needs validation. For this reflective silver can a flat matte black background should improve contrast versus the bright wrinkled cloth; a dark object may require a lighter background instead. Background changes cannot correct software prediction or identity errors.
