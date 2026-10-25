"""Cross-view local-feature candidates; never triangulate box centers.

Inputs must already be undistorted using the calibration's intrinsics.
F maps homogeneous pixels in camera A to epipolar lines in camera B.
"""
import cv2
import numpy as np


def associate(frame_a, mask_a, frame_b, fundamental, *, timestamp_a_ms,
              timestamp_b_ms, calibration_version, max_skew_ms=40):
    F = np.asarray(fundamental, dtype=float)
    if F.shape != (3,3) or not np.isfinite(F).all() or np.linalg.matrix_rank(F) != 2:
        raise ValueError('fundamental matrix must be finite and rank 2')
    if abs(timestamp_a_ms-timestamp_b_ms) > max_skew_ms:
        return {'state':'unresolved', 'reason':'timestamp_skew', 'matches':[]}
    detector = cv2.SIFT_create(nfeatures=1200)
    ka, da = detector.detectAndCompute(frame_a, mask_a)
    kb, db = detector.detectAndCompute(frame_b, None)
    result = dict(state='unresolved', matches=[], calibration_version=calibration_version)
    if da is None or db is None or len(db) < 2:
        return result
    matcher = cv2.BFMatcher()
    forward = matcher.knnMatch(da, db, k=2)
    reverse = matcher.match(db, da)
    reverse_ids = {m.queryIdx:m.trainIdx for m in reverse}
    candidates = []
    for pair in forward:
        if len(pair) != 2:
            continue
        m,n = pair
        if m.distance >= .7*n.distance or reverse_ids.get(m.trainIdx) != m.queryIdx:
            continue
        a = np.array([*ka[m.queryIdx].pt,1.])
        b = np.array([*kb[m.trainIdx].pt,1.])
        fa, fb = F@a, F.T@b
        denom = fa[0]**2+fa[1]**2+fb[0]**2+fb[1]**2
        error = float((b@F@a)**2/max(denom,1e-12))
        if error <= 2.25:
            candidates.append(dict(pixel_a=a[:2].tolist(), pixel_b=b[:2].tolist(),
                                   sampson_error_px2=error))
    # Calibrated epipolar filtering is necessary, but repeated textures can remain
    # ambiguous. These are candidates requiring confirmation, never identity proof.
    result['matches'] = candidates
    result['state'] = 'needs_confirmation' if len(candidates) >= 6 else 'unresolved'
    return result
