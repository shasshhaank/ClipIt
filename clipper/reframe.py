"""16:9 -> 9:16 subject tracking. Samples faces at a few fps, falls back to motion saliency,
then smooths into a camera path (no jitter, holds steady, snaps at shot cuts)."""
import cv2
import numpy as np

_face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
_prof = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")


def _detect(gray):
    h, w = gray.shape
    best = None
    for casc, flip in ((_face, False), (_prof, False), (_prof, True)):
        g = cv2.flip(gray, 1) if flip else gray
        rs = casc.detectMultiScale(g, 1.15, 5, minSize=(w // 20, w // 20))
        for (x, y, fw, fh) in rs:
            if flip:
                x = w - x - fw
            if best is None or fw * fh > best[2] * best[3]:
                best = (x, y, fw, fh)
        if best is not None:
            break
    if best is None:
        return None
    x, y, fw, fh = best
    return ((x + fw / 2) / w, (y + fh / 2) / h, fw * fh / (w * h))


def track(src, start, end, cuts=(), sample_fps=5):
    """Returns (times, cx, cy) arrays: smoothed normalised centre of interest."""
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    step = max(1, int(round(fps / sample_fps)))
    ts, xs, ys, prev = [], [], [], None
    i = 0
    while True:
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if t > end:
            break
        ok = cap.grab()
        if not ok:
            break
        if i % step == 0:
            _, f = cap.retrieve()
            small = cv2.resize(f, (480, int(480 * f.shape[0] / f.shape[1])))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            d = _detect(gray)
            if d is None and prev is not None:  # motion saliency fallback
                diff = cv2.GaussianBlur(cv2.absdiff(gray, prev), (21, 21), 0)
                if diff.max() > 12:
                    m = cv2.moments(diff)
                    if m["m00"] > 0:
                        d = (m["m10"] / m["m00"] / gray.shape[1], m["m01"] / m["m00"] / gray.shape[0], 0)
            prev = gray
            ts.append(t)
            xs.append(np.nan if d is None else d[0])
            ys.append(np.nan if d is None else d[1] - 0.05)  # keep a bit of headroom
        i += 1
    cap.release()
    ts, xs, ys = np.array(ts), np.array(xs), np.array(ys)
    if len(ts) == 0:
        return np.array([start, end]), np.array([.5, .5]), np.array([.45, .45])
    return ts, _smooth(ts, xs, cuts, 0.5), _smooth(ts, ys, cuts, 0.42)


def _smooth(ts, v, cuts, default):
    """Fill gaps, then smooth per shot with dead-zone so the camera holds still on small moves."""
    v = v.copy()
    if np.all(np.isnan(v)):
        return np.full_like(ts, default)
    idx = np.arange(len(v))
    good = ~np.isnan(v)
    v = np.interp(idx, idx[good], v[good])
    out = np.empty_like(v)
    bounds = [0] + [int(np.searchsorted(ts, c)) for c in sorted(cuts)] + [len(v)]
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b <= a:
            continue
        seg = v[a:b]
        med = np.convolve(np.pad(seg, 3, mode="edge"), np.ones(7) / 7, mode="valid")
        cam = med[0]
        for k in range(len(med)):
            if abs(med[k] - cam) > 0.06:      # dead-zone: only follow meaningful moves
                cam += (med[k] - cam) * 0.25  # ease toward target
            out[a + k] = cam
    return out
