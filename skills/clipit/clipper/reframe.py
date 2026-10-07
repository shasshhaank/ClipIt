"""16:9 -> 9:16 framing. Finds faces a few times a second (OpenCV's YuNet model, or its Haar cascades when
the model is missing), follows the person who is talking, and turns that into a steady camera path with the
eyes on the upper third.

It also works out `zmax`: how far the shot may zoom before a head stops fitting the 9:16 frame. A close-up
from a 16:9 source usually doesn't fit even at zoom 1 (the head is wider than the vertical crop), so the
planners zoom *out* below 1 and the renderer fills above and below with mirrored copies (motion tile) or a
blurred copy, instead of cutting the face off."""
import os
import cv2
import numpy as np

MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "face_detection_yunet_2023mar.onnx")
OUT_AR = 9 / 16
HEAD_W, HEAD_H = 1.6, 1.7   # a whole head (hair, ears, chin) is about this much bigger than the face box
MAX_W, MAX_H = 0.86, 0.45   # the biggest a head may get: share of the output width / height
EYE_LINE = 0.38             # eyes this far down the frame: upper third, with a little headroom
Z_REF = 1.12                # typical zoom while a shot plays, used to place the eye line

_det = {}


def detect(img):
    """Faces in a BGR frame: [(cx, cy, w, h, eye_y, mouth_y, (lx, ly, rx, ry))], normalised to the frame (0..1)."""
    h, w = img.shape[:2]
    if "yunet" not in _det:
        try:
            _det["yunet"] = cv2.FaceDetectorYN.create(MODEL, "", (w, h), 0.7, 0.3, 50) if os.path.exists(MODEL) else None
        except Exception:
            _det["yunet"] = None
        _det["haar"] = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    yn = _det["yunet"]
    out = []
    if yn is not None:
        yn.setInputSize((w, h))
        _, faces = yn.detect(img)
        for f in faces if faces is not None else []:
            x, y, fw, fh = f[:4]
            eye_y = (f[5] + f[7]) / 2
            mouth_y = (f[11] + f[13]) / 2
            out.append(((x + fw / 2) / w, (y + fh / 2) / h, fw / w, fh / h, eye_y / h, mouth_y / h,
                        (f[4] / w, f[5] / h, f[6] / w, f[7] / h)))
        return out
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    for x, y, fw, fh in _det["haar"].detectMultiScale(gray, 1.15, 5, minSize=(w // 24, w // 24)):
        ey = (y + 0.4 * fh) / h
        out.append(((x + fw / 2) / w, (y + fh / 2) / h, fw / w, fh / h, ey, (y + 0.78 * fh) / h,
                    ((x + 0.3 * fw) / w, ey, (x + 0.7 * fw) / w, ey)))
    return out


def zoom_cap(fw, fh, src_ar):
    """Largest zoom (1 = 9:16 crop at full height) at which a head with this face box still fits the frame."""
    return min(MAX_W * OUT_AR / (HEAD_W * fw * src_ar), MAX_H / (HEAD_H * fh))


def track(src, start, end, sample_fps=5):
    """Camera path for a source window: {t, x, y (crop centre), ex, ey (subject's eyes), z (zoom limit per sample,
    one value per scene), zmax (the tightest of those, or None without faces)}."""
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, start) * 1000)
    step = max(1, int(round(fps / sample_fps)))
    samples, prev, i, src_ar, scene = [], None, 0, 16 / 9, []
    while True:
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if t > end or not cap.grab():
            break
        if i % step == 0:
            _, f = cap.retrieve()
            src_ar = f.shape[1] / f.shape[0]
            small = cv2.resize(f, (640, int(640 * f.shape[0] / f.shape[1])))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            faces = [fc for fc in detect(small) if fc[2] > 0.025]
            motion = None
            if prev is not None and cv2.absdiff(cv2.resize(gray, (64, 36)), cv2.resize(prev, (64, 36))).mean() > 28:
                scene.append(t)   # a hard scene change inside the window: framing restarts there
            if not faces and prev is not None:   # no face: follow what moves
                diff = cv2.GaussianBlur(cv2.absdiff(gray, prev), (21, 21), 0)
                m = cv2.moments(diff)
                if diff.max() > 12 and m["m00"] > 0:
                    motion = (m["m10"] / m["m00"] / gray.shape[1], m["m01"] / m["m00"] / gray.shape[0])
            samples.append((t, faces, motion, _mouths(gray, faces)))
            prev = gray
        i += 1
    cap.release()
    if not samples:
        return {"t": [start, end], "x": [0.5, 0.5], "y": [0.45, 0.45], "ex": [0.5, 0.5], "ey": [0.4, 0.4], "zmax": None,
                "eyes": None}
    subject, switches = _speaker(samples)
    ts = np.array([s[0] for s in samples])
    xs, ys, ex, ey, caps, room = (np.full(len(samples), np.nan) for _ in range(6))
    eyes = np.full((len(samples), 4), np.nan)
    for k, (t, faces, motion, _) in enumerate(samples):
        f = faces[subject[k]] if subject[k] is not None else None
        if f is not None:
            ex[k], ey[k] = f[0], f[4]
            eyes[k] = f[6]
            xs[k], ys[k] = f[0], f[4] + (0.5 - EYE_LINE) / Z_REF
            caps[k] = zoom_cap(f[2], f[3], src_ar)
            # how far the camera may lag behind the face before the head starts leaving the frame
            room[k] = max(0.0, OUT_AR / src_ar / Z_REF / 2 - HEAD_W * f[2] / 2) * 0.9
        elif motion is not None:
            xs[k], ys[k] = motion[0], motion[1] - 0.05
    # zoom limit per scene: the tighter end of what that scene's faces allow (a scene without faces has none)
    z = np.full(len(samples), 3.0)
    bounds = [0] + [int(np.searchsorted(ts, c)) for c in scene] + [len(samples)]
    for a, b in zip(bounds[:-1], bounds[1:]):
        good = caps[a:b][~np.isnan(caps[a:b])]
        if b > a and len(good) >= max(1, (b - a) // 4):
            z[a:b] = np.clip(np.percentile(good, 25), 0.45, 2.5)
    cuts = sorted(scene + switches)
    return {"t": ts.tolist(), "x": _smooth(ts, xs, cuts, 0.5, room).tolist(),
            "y": np.clip(_smooth(ts, ys, cuts, 0.42), 0, 1).tolist(),
            "ex": _fill(ex, 0.5).tolist(), "ey": _fill(ey, 0.4).tolist(), "z": z.tolist(),
            "eyes": [_fill(eyes[:, j], np.nan).tolist() for j in range(4)] if not np.isnan(eyes).all() else None,
            "zmax": float(z.min()) if z.min() < 3.0 else None}


def _mouths(gray, faces):
    """A small patch around each mouth, to tell who is talking."""
    h, w = gray.shape
    out = []
    for cx, _, fw, fh, _, my, _ in faces:
        x0, x1 = int((cx - fw * 0.3) * w), int((cx + fw * 0.3) * w)
        y0, y1 = int((my - fh * 0.15) * h), int((my + fh * 0.15) * h)
        p = gray[max(0, y0):max(1, y1), max(0, x0):max(1, x1)]
        out.append(cv2.resize(p, (24, 12)).astype(np.float32) if p.size else None)
    return out


def _speaker(samples, hold=1.0):
    """Index of the face to frame in each sample: the only face, or (with several) whoever's mouth moves most.
    Holds a choice for at least `hold` s so the frame doesn't flick between people; each switch is a cut."""
    tracks, last, act = [], {}, []   # face -> track id by position; mouth activity per (sample, face)
    for k, (t, faces, _, mouths) in enumerate(samples):
        ids, a = [], []
        for j, f in enumerate(faces):
            tid = min(last, key=lambda q: abs(last[q][0] - f[0]), default=None)
            if tid is None or abs(last[tid][0] - f[0]) > 0.12:
                tid = len(tracks)
                tracks.append(tid)
            prev_m = last.get(tid, (None, None))[1]
            a.append(float(np.abs(mouths[j] - prev_m).mean()) if mouths[j] is not None and prev_m is not None else 0.0)
            last[tid] = (f[0], mouths[j])
            ids.append(tid)
        act.append((ids, a))
    subject, switches, cur, since = [], [], None, -1e9
    for k, (t, faces, _, _) in enumerate(samples):
        ids, _ = act[k]
        if not faces:
            subject.append(None)
            continue
        big = max(f[2] for f in faces)
        score = {}
        for kk in range(max(0, k - 3), min(len(samples), k + 4)):   # mouth movement over about a second
            for tid, v in zip(*act[kk]):
                score[tid] = score.get(tid, 0.0) + v
        cand = [j for j, f in enumerate(faces) if f[2] >= 0.6 * big]
        best = max(cand, key=lambda j: (score.get(ids[j], 0.0), faces[j][2]))
        here = [j for j in cand if ids[j] == cur]
        if here and (t - since < hold or score.get(ids[best], 0) < 1.3 * score.get(cur, 0) + 1e-6):
            best = here[0]
        if ids[best] != cur:
            if cur is not None:
                switches.append(t)
            cur, since = ids[best], t
        subject.append(best)
    return subject, switches


def _fill(v, default):
    v = v.copy()
    good = ~np.isnan(v)
    if not good.any():
        return np.full_like(v, default)
    idx = np.arange(len(v))
    return np.interp(idx, idx[good], v[good])


def _smooth(ts, v, cuts, default, room=None):
    """Fill gaps, then smooth per shot with a dead zone so the camera holds still on small moves. With `room`,
    the camera never lags further than that behind the target (the head stays in frame)."""
    if np.all(np.isnan(v)):
        return np.full_like(ts, default)
    v = _fill(v, default)
    room = None if room is None else _fill(room, 1.0)
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
                cam += (med[k] - cam) * 0.3   # ease toward target
            if room is not None and abs(seg[k] - cam) > room[a + k]:
                cam = seg[k] - np.sign(seg[k] - cam) * room[a + k]
            out[a + k] = cam
    return out
