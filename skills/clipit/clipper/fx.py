"""Per-frame visual effects for edits. All functions take/return uint8 BGR frames.

Envelope convention: an effect is driven by a scalar 0..1 (or px) computed per output
frame from timed "hits" (see render.env). Effects are cheap enough for 1080x1920@30fps.
"""
import math
import cv2
import numpy as np

OUT_W, OUT_H = 1080, 1920


# ---------------------------------------------------------------- camera / framing
def camera(frame, cx, cy, zoom=1.0, rot=0.0, dx=0.0, dy=0.0, out_w=OUT_W, out_h=OUT_H, fill="blur", sy=1.0):
    """Crop a 9:16 window centred on (cx, cy) (normalised source coords), apply zoom (>1 = closer, <1 = the
    picture smaller than the frame), rotation (deg), pixel shake offsets and a vertical stretch `sy` (about the
    frame centre), in ONE affine warp. Where the window runs past the picture, `fill` decides what shows:
    "reflect" mirrored copies (motion tile), "blur" a blurred, darkened copy, else the edge pixels repeated."""
    h, w = frame.shape[:2]
    target_ar = out_w / out_h
    # base crop that fills the output at zoom 1
    if w / h > target_ar:
        crop_h = h
        crop_w = h * target_ar
    else:
        crop_w = w
        crop_h = w / target_ar
    crop_w /= zoom
    crop_h /= zoom
    s = out_w / crop_w
    px = np.clip(cx * w, crop_w / 2, w - crop_w / 2) if crop_w <= w else w / 2
    py = np.clip(cy * h, crop_h / 2, h - crop_h / 2) if crop_h <= h else h / 2
    M = cv2.getRotationMatrix2D((float(px), float(py)), rot, s)
    M[0, 2] += out_w / 2 - px + dx
    M[1, 2] += out_h / 2 - py + dy
    if abs(sy - 1) > 1e-3:
        M[1] *= sy
        M[1, 2] += out_h / 2 * (1 - sy)
    if fill == "blur" and (crop_h > h + 1 or crop_w > w + 1):   # picture smaller than the frame: blurred surround
        bg = cv2.GaussianBlur(camera(frame, cx, cy, 1.0, out_w=out_w // 4, out_h=out_h // 4, fill="replicate"), (0, 0), 6)
        bg = (cv2.resize(bg, (out_w, out_h)) * 0.55).astype(np.uint8)
        fg = cv2.warpAffine(frame, M, (out_w, out_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        m = cv2.warpAffine(np.full((h, w), 255, np.uint8), M, (out_w, out_h), flags=cv2.INTER_LINEAR)[..., None] / 255.0
        return (fg * m + bg * (1 - m)).astype(np.uint8)
    border = cv2.BORDER_REFLECT101 if fill == "reflect" else cv2.BORDER_REPLICATE
    return cv2.warpAffine(frame, M, (out_w, out_h), flags=cv2.INTER_LINEAR, borderMode=border)


def fit_with_blur_bg(frame, out_w=OUT_W, out_h=OUT_H):
    """Classic clip-page layout: full 16:9 frame centred over a blurred, zoomed copy of itself."""
    h, w = frame.shape[:2]
    bg = camera(frame, 0.5, 0.5, 1.0, out_w=out_w // 4, out_h=out_h // 4)
    bg = cv2.GaussianBlur(bg, (0, 0), 6)
    bg = cv2.resize(bg, (out_w, out_h))
    bg = (bg * 0.55).astype(np.uint8)
    s = out_w / w
    fw, fh = int(w * s), int(h * s)
    fg = cv2.resize(frame, (fw, fh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    y0, x0 = (out_h - fh) // 2, (out_w - fw) // 2
    ys, xs = max(0, y0), max(0, x0)
    bg[ys:ys + min(fh, out_h), xs:xs + min(fw, out_w)] = fg[ys - y0:ys - y0 + min(fh, out_h),
                                                           xs - x0:xs - x0 + min(fw, out_w)]
    return bg


# ---------------------------------------------------------------- hit effects
def eye_glow(frame, pts, amt, color="red"):
    """Glowing eyes: a hot core and a horizontal flare on each eye point (output px), bloomed and screened on."""
    if amt <= 0.01 or not pts:
        return frame
    h, w = frame.shape[:2]
    layer = np.zeros((h, w), np.float32)
    r = max(3.0, (math.dist(pts[0], pts[1]) if len(pts) == 2 else 60) * 0.16)
    for x, y in pts:
        cv2.circle(layer, (int(x), int(y)), int(r), 1.0, -1, cv2.LINE_AA)
        cv2.ellipse(layer, (int(x), int(y)), (int(r * 5), max(1, int(r * 0.35))), 0, 0, 360, 0.7, -1, cv2.LINE_AA)
    glow = cv2.GaussianBlur(layer, (0, 0), r * 0.8) * 1.4 + cv2.GaussianBlur(layer, (0, 0), r * 3) * 1.6 \
        + cv2.GaussianBlur(layer, (0, 0), r * 9) * 0.9
    tint = np.array({"red": (0.1, 0.05, 1.0), "blue": (1.0, 0.45, 0.1), "purple": (1.0, 0.2, 0.8),
                     "white": (1.0, 1.0, 1.0)}.get(color, (0.1, 0.05, 1.0)), np.float32)   # BGR
    core = cv2.GaussianBlur(layer, (0, 0), r * 0.35)[..., None] * 0.6
    return _screen(frame, glow[..., None] * tint * amt + core * amt)


def lens_blur(frame, radius):
    """Out-of-focus lens: a disc-shaped blur (round bokeh, like a real defocus), radius in output px."""
    if radius < 0.6:
        return frame
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    r = max(1.0, radius / 2)
    n = int(np.ceil(r)) * 2 + 1
    yy, xx = np.mgrid[:n, :n] - n // 2
    k = np.clip(r + 0.5 - np.hypot(xx, yy), 0, 1).astype(np.float32)   # anti-aliased disc
    out = cv2.filter2D(small, -1, k / k.sum(), borderType=cv2.BORDER_REFLECT101)
    return cv2.resize(out, (w, h), interpolation=cv2.INTER_LINEAR)


def flash(frame, amt, color=(255, 255, 255)):
    if amt <= 0.01:
        return frame
    amt = min(1.0, amt)
    c = np.array(color, np.float32)
    return (frame.astype(np.float32) * (1 - amt) + c * amt).astype(np.uint8)


def exposure(frame, gain):
    """gain > 1 brightens (exposure flicker / pulse)."""
    if abs(gain - 1) < 0.01:
        return frame
    return cv2.convertScaleAbs(frame, alpha=gain, beta=0)


def rgb_split(frame, px):
    """Chromatic aberration: red shifted one way, blue the other."""
    px = int(round(px))
    if px == 0:
        return frame
    b, g, r = cv2.split(frame)
    return cv2.merge([np.roll(b, -px, axis=1), g, np.roll(r, px, axis=1)])


def motion_blur(frame, length, angle=0.0):
    """Directional blur (whip / speed feel). length in px."""
    L = int(length)
    if L < 3:
        return frame
    small = cv2.resize(frame, (frame.shape[1] // 2, frame.shape[0] // 2))
    L2 = max(3, L // 2) | 1
    k = np.zeros((L2, L2), np.float32)
    k[L2 // 2, :] = 1.0
    k = cv2.warpAffine(k, cv2.getRotationMatrix2D((L2 / 2 - .5, L2 / 2 - .5), angle, 1.0), (L2, L2))
    k /= max(k.sum(), 1e-6)
    out = cv2.filter2D(small, -1, k)
    return cv2.resize(out, (frame.shape[1], frame.shape[0]))


def zoom_blur(frame, amt, steps=5):
    """Radial / zoom blur: average of progressively scaled copies (zoom transition look)."""
    if amt <= 0.005:
        return frame
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (w // 2, h // 2)).astype(np.float32)
    acc = small.copy()
    for i in range(1, steps):
        s = 1 + amt * i / steps
        M = cv2.getRotationMatrix2D((w / 4, h / 4), 0, s)
        acc += cv2.warpAffine(small, M, (w // 2, h // 2), borderMode=cv2.BORDER_REPLICATE)
    acc /= steps
    return cv2.resize(acc.astype(np.uint8), (w, h))


def glitch(frame, amt, rng):
    """Horizontal slice displacement + channel offset (digital glitch)."""
    if amt <= 0.02:
        return frame
    out = frame.copy()
    h, w = frame.shape[:2]
    n = int(4 + 14 * amt)
    for _ in range(n):
        y = rng.integers(0, h - 10)
        bh = int(rng.integers(6, max(8, int(120 * amt))))
        shift = int(rng.normal(0, 90 * amt))
        out[y:y + bh] = np.roll(out[y:y + bh], shift, axis=1)
    return rgb_split(out, 14 * amt)


def letterbox(frame, frac):
    if frac <= 0:
        return frame
    h = frame.shape[0]
    bar = int(h * frac)
    out = frame.copy()
    out[:bar] = 0
    out[h - bar:] = 0
    return out


# ---------------------------------------------------------------- look / grade
def load_cube(path):
    """A 3D .cube LUT as an array indexed [b][g][r] -> rgb (0..1)."""
    n, rows = None, []
    for line in open(path):
        s = line.strip()
        if s.upper().startswith("LUT_3D_SIZE"):
            n = int(s.split()[1])
        elif s and (s[0].isdigit() or s[0] in "-."):
            rows.append([float(v) for v in s.split()[:3]])
    if n is None or len(rows) != n ** 3:
        raise ValueError(f"{path}: not a 3D .cube LUT")
    return np.asarray(rows, np.float32).reshape(n, n, n, 3)


def apply_lut(frame, lut):
    """Grade a BGR uint8 frame through a 3D LUT (trilinear)."""
    n = lut.shape[0]
    p = frame.astype(np.float32) * ((n - 1) / 255)
    i0 = np.minimum(p.astype(np.int32), n - 2)
    f = p - i0
    out = 0
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                w = ((f[..., 0:1] if db else 1 - f[..., 0:1]) * (f[..., 1:2] if dg else 1 - f[..., 1:2])
                     * (f[..., 2:3] if dr else 1 - f[..., 2:3]))
                out = out + lut[i0[..., 0] + db, i0[..., 1] + dg, i0[..., 2] + dr] * w
    return (np.clip(out[..., ::-1], 0, 1) * 255).astype(np.uint8)


class Look:
    """Precomputed colour grade + grain + vignette. Presets tuned for edit pages; a path to a .cube file uses that
    LUT (e.g. one fitted to a reference with `clip.py match-look`) with a light sharpen and vignette."""
    PRESETS = {
        # contrast, saturation, (b,g,r) shadow tint, (b,g,r) highlight tint, grain, vignette, sharpen
        "clean":   dict(contrast=1.05, sat=1.05, shadow=(0, 0, 0), high=(0, 0, 0), grain=0.0, vig=0.15, sharp=0.3),
        "punchy":  dict(contrast=1.18, sat=1.18, shadow=(4, 0, -2), high=(-4, 0, 4), grain=0.03, vig=0.3, sharp=0.5),
        "teal_orange": dict(contrast=1.2, sat=1.1, shadow=(14, 4, -6), high=(-12, 0, 12), grain=0.04, vig=0.35, sharp=0.5),
        "dark":    dict(contrast=1.3, sat=0.75, shadow=(8, 2, 0), high=(0, 0, 0), grain=0.06, vig=0.5, sharp=0.6),
        "mono":    dict(contrast=1.35, sat=0.0, shadow=(0, 0, 0), high=(0, 0, 0), grain=0.07, vig=0.45, sharp=0.6),
        "warm_film": dict(contrast=1.1, sat=0.95, shadow=(-4, 2, 8), high=(-10, 2, 10), grain=0.06, vig=0.35, sharp=0.2),
        # poster frames: rich colour, soft (unsharpened) image, heavy print grain
        "poster": dict(contrast=1.12, sat=1.15, shadow=(6, 2, -2), high=(-4, 0, 6), grain=0.1, vig=0.15, sharp=0.0),
        # "4K" edit look: sharpen + big-radius unsharp (clarity), brightness lift, contrast, saturation
        # ~1.26 + vibrance, teal/orange split tone, soft highlight glow, vignette
        "crisp4k": dict(contrast=1.14, sat=1.18, shadow=(10, 3, -4), high=(-8, 0, 8), grain=0.0, vig=0.3,
                        sharp=0.9, clarity=0.35, clarity_r=10, vib=0.25, bright=6, glow=0.18, glow_thr=0.6),
        # HDR look: exposure/gamma lift, strong local contrast (inverted-blur difference trick),
        # vibrance 1.16, mild contrast, threshold glow screened at ~20%
        "hdr": dict(contrast=1.07, sat=1.05, shadow=(4, 2, 0), high=(-4, 0, 4), grain=0.0, vig=0.2,
                    sharp=0.5, clarity=0.7, clarity_r=24, vib=0.16, bright=4, gamma=0.92, glow=0.2, glow_thr=0.83,
                    shadow_lift=0.12),
        # wholesome / feel-good: bright and airy, rich but soft colour, glowing highlights (tears and eyes catch
        # the light), lifted shadows, warm-pink highlights
        "bright": dict(contrast=1.04, sat=1.2, shadow=(6, 2, 0), high=(-6, 2, 10), grain=0.0, vig=0.08,
                       sharp=0.45, clarity=0.35, clarity_r=16, vib=0.3, bright=12, gamma=0.9, glow=0.3, glow_thr=0.7,
                       shadow_lift=0.15),
    }

    def __init__(self, name="punchy", w=OUT_W, h=OUT_H, seed=7):
        self.cube = load_cube(name) if str(name).lower().endswith(".cube") else None
        p = dict(self.PRESETS["clean"], contrast=1.0, sat=1.0) if self.cube is not None else self.PRESETS[name]
        self.p = p
        x = np.arange(256, dtype=np.float32) / 255.0
        x = np.clip(x + p.get("bright", 0) / 255.0, 0, 1) ** p.get("gamma", 1.0)
        if p.get("shadow_lift"):   # tone-map: lift shadows, keep highlights (HDR feel)
            x = x + p["shadow_lift"] * (1 - x) ** 3 * x * 4
        # S-curve contrast around mid grey
        c = p["contrast"]
        curve = 0.5 + (x - 0.5) * c
        curve = curve + 0.08 * (c - 1) * np.sin((x - 0.5) * math.pi)  # soft shoulder
        luts = [np.clip((curve + (p["shadow"][i] / 255.0) * (1 - x) ** 2 + (p["high"][i] / 255.0) * x ** 2) * 255,
                        0, 255).astype(np.uint8) for i in range(3)]
        self.lut = np.stack(luts, axis=1).reshape(256, 1, 3)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
        self.vig = (1 - p["vig"] * np.clip(d - 0.35, 0, 1) ** 1.6)[..., None].astype(np.float32)
        rng = np.random.default_rng(seed)
        self.grain = [rng.normal(0, 255 * p["grain"], (h // 2, w // 2)).astype(np.float32) for _ in range(6)] \
            if p["grain"] > 0 else None
        self.i = 0

    def __call__(self, frame):
        p = self.p
        out = cv2.LUT(apply_lut(frame, self.cube) if self.cube is not None else frame, self.lut)
        if p.get("clarity"):       # local contrast: add back detail relative to a big blur
            h, w = out.shape[:2]
            r = p.get("clarity_r", 16)
            small = cv2.resize(out, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
            bl = cv2.resize(cv2.GaussianBlur(small, (0, 0), r / 4), (w, h))
            out = cv2.addWeighted(out, 1 + p["clarity"], bl, -p["clarity"], 0)
        if abs(p["sat"] - 1) > 0.01 or p.get("vib"):
            hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
            sat = hsv[..., 1] / 255.0 * p["sat"]
            if p.get("vib"):        # vibrance: boost muted colours more than saturated ones
                sat = sat * (1 + p["vib"] * (1 - sat))
            hsv[..., 1] = np.clip(sat * 255, 0, 255)
            out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
        if p.get("glow"):          # threshold glow, screen-blended
            out = bloom(out, p["glow"], p.get("glow_thr", 0.7), 24)
        if p["sharp"] > 0:
            bl = cv2.GaussianBlur(out, (0, 0), 1.2)
            out = cv2.addWeighted(out, 1 + p["sharp"], bl, -p["sharp"], 0)
        f = out.astype(np.float32) * self.vig
        if self.grain is not None:
            g = cv2.resize(self.grain[self.i % len(self.grain)], (frame.shape[1], frame.shape[0]))
            f += g[..., None]
            self.i += 1
        return np.clip(f, 0, 255).astype(np.uint8)


def _screen(frame, light):
    """Screen-blend `light` (float 0..1, per pixel or broadcastable) onto a uint8 frame."""
    f = frame.astype(np.float32) / 255
    return (np.clip(1 - (1 - f) * (1 - np.clip(light, 0, 1)), 0, 1) * 255).astype(np.uint8)


# ================================================================= pro effects
# Bloom, lens bulge, radial aberration, echo trails, VHS, light leaks, handheld drift, jolts.

def bloom(frame, strength=0.8, threshold=0.7, radius=30):
    """Highlight bloom: extract highlights, blur at several radii, add (screen) back."""
    if strength <= 0.01:
        return frame
    f = frame.astype(np.float32) / 255
    lum = f.max(axis=2, keepdims=True)
    hi = f * np.clip((lum - threshold) / max(1e-3, 1 - threshold), 0, 1)
    small = cv2.resize(hi, (f.shape[1] // 4, f.shape[0] // 4), interpolation=cv2.INTER_AREA)
    g = sum(cv2.GaussianBlur(small, (0, 0), r) * w for r, w in ((radius / 8, .5), (radius / 4, .35), (radius / 2, .25)))
    return _screen(frame, cv2.resize(g, (f.shape[1], f.shape[0])) * strength * 1.6)


_bulge_cache = {}


def bulge(frame, k):
    """Lens distortion / fisheye. k > 0 bulges out (zoom-transition 'suck'), k < 0 pinches."""
    if abs(k) < 0.01:
        return frame
    h, w = frame.shape[:2]
    key = (h, w, round(k, 2))
    if key not in _bulge_cache:
        if len(_bulge_cache) > 40:
            _bulge_cache.clear()
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        nx, ny = (xs - w / 2) / (w / 2), (ys - h / 2) / (w / 2)
        r2 = nx * nx + ny * ny
        f = 1 / np.maximum(0.2, 1 + k * r2)   # clamped so a strong pinch (k < 0) never flips the image
        _bulge_cache[key] = ((nx * f) * (w / 2) + w / 2, (ny * f) * (w / 2) + h / 2)
    mx, my = _bulge_cache[key]
    return cv2.remap(frame, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT101)


def rgb_radial(frame, amt):
    """Radial chromatic aberration: R scaled up, B scaled down around the centre (lens fringing)."""
    if amt <= 0.001:
        return frame
    h, w = frame.shape[:2]
    b, g, r = cv2.split(frame)
    sc = lambda ch, s: cv2.warpAffine(ch, cv2.getRotationMatrix2D((w / 2, h / 2), 0, s), (w, h),
                                      borderMode=cv2.BORDER_REPLICATE)
    return cv2.merge([sc(b, 1 - amt), g, sc(r, 1 + amt)])


def echo(frame, history, amt=0.6, n=4):
    """Frame trails: blend decaying copies of previous output frames (lighten)."""
    if amt <= 0.01 or not history:
        return frame
    out = frame.astype(np.float32)
    for i, prev in enumerate(reversed(history[-n:])):
        w = amt * (0.65 ** i)
        out = np.maximum(out, prev.astype(np.float32) * w + out * (1 - w))
    return out.astype(np.uint8)


def vhs(frame, amt, k, rng):
    """VHS / CRT: scanlines, chroma bleed, noise, a rolling tracking band."""
    if amt <= 0.01:
        return frame
    h, w = frame.shape[:2]
    out = frame.astype(np.float32)
    out[::3] *= 1 - 0.35 * amt                                      # scanlines
    ycc = cv2.cvtColor(out.astype(np.uint8), cv2.COLOR_BGR2YCrCb).astype(np.float32)
    for c in (1, 2):                                                # chroma bleed (smear right)
        ycc[..., c] = cv2.blur(np.roll(ycc[..., c], int(6 * amt), axis=1), (int(1 + 14 * amt), 1))
    out = cv2.cvtColor(np.clip(ycc, 0, 255).astype(np.uint8), cv2.COLOR_YCrCb2BGR).astype(np.float32)
    out += rng.normal(0, 14 * amt, (h // 4, w // 4, 1)).repeat(4, 0).repeat(4, 1)[:h, :w]
    y = int((k * 23) % h)                                           # tracking band
    bh = int(30 + 60 * amt)
    out[y:y + bh] = np.roll(out[y:y + bh], int(rng.integers(-40, 40) * amt), axis=1) * 1.08
    return np.clip(out, 0, 255).astype(np.uint8)


def light_leak(frame, amt, t):
    """Procedural warm light leak drifting across the frame (screen blend)."""
    if amt <= 0.01:
        return frame
    h, w = frame.shape[:2]
    sw, sh = w // 8, h // 8
    ys, xs = np.mgrid[0:sh, 0:sw].astype(np.float32)
    acc = np.zeros((sh, sw, 3), np.float32)
    for i, ph in enumerate((0.8, 3.0, 5.1)):  # fixed phases
        cx = sw * (0.5 + 0.6 * np.sin(t * 0.7 + ph))
        cy = sh * (0.5 + 0.5 * np.cos(t * 0.5 + ph * 1.3))
        d = ((xs - cx) ** 2 + (ys - cy) ** 2) / (sw * 0.45) ** 2
        col = np.array([[40, 120, 255], [60, 60, 255], [120, 200, 255]][i], np.float32) / 255
        acc += np.exp(-d)[..., None] * col
    return _screen(frame, cv2.resize(acc, (w, h)) * amt)


def handheld(t, amp=12.0, speed=1.0):
    """Smooth pseudo-Perlin camera drift (sum of incommensurate sines). Returns dx, dy, rot."""
    r = (0.4, 2.2, 4.0, 1.3, 5.5, 3.1)  # fixed phases
    s = speed
    dx = amp * (0.6 * np.sin(1.3 * s * t + r[0]) + 0.4 * np.sin(2.9 * s * t + r[1]))
    dy = amp * (0.6 * np.sin(1.1 * s * t + r[2]) + 0.4 * np.sin(3.7 * s * t + r[3]))
    rot = amp / 25 * (0.7 * np.sin(0.9 * s * t + r[4]) + 0.3 * np.sin(2.3 * s * t + r[5]))
    return float(dx), float(dy), float(rot)


def jolt_ops(k, amt, speed, seed=0):
    """Jolts: every 2 frames, roll (probability ~ speed) for six channels: blur, color, light,
    scale, slide, time. Seeded by (seed, frame), so every render is identical. Returns per-frame offsets."""
    if amt <= 0.01:
        return {}
    r = np.random.default_rng([int(seed) & 0xFFFFFFFF, k // 2])
    p = min(0.95, 0.25 + 0.6 * speed)
    o = {}
    if r.random() < p:
        o["blur"] = float(r.uniform(20, 90) * amt)
    if r.random() < p * 0.6:
        o["color"] = int(r.integers(0, 3))
        o["color_amt"] = float(r.uniform(0.3, 0.8) * amt)
    if r.random() < p * 0.7:
        o["light"] = float(r.uniform(-0.35, 0.8) * amt)
    if r.random() < p:
        o["scale"] = float(r.uniform(0.02, 0.22) * amt)
    if r.random() < p * 0.8:
        o["slide"] = float(r.uniform(-1, 1) * 120 * amt)
    if r.random() < p * 0.5:
        o["time"] = -int(r.integers(1, 4))  # repeat an earlier frame (stutter)
    return o


def tint(frame, ch, amt):
    out = frame.astype(np.float32)
    out[..., ch] = out[..., ch] * (1 + amt) + 40 * amt
    return np.clip(out, 0, 255).astype(np.uint8)


def edge_glow(frame, amt, color=(255, 230, 0), grow=1.0):
    """Neon outline: the frame's edges, tinted (RGB `color`) and bloomed, screened back on. `grow` > 1
    scales the outline up from the centre, so a decaying hit reads as a ghost bursting outwards."""
    if amt <= 0.01:
        return frame
    h, w = frame.shape[:2]
    e = cv2.Canny(cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (0, 0), 1.5), 50, 130)
    e = cv2.dilate(e, None)
    if grow > 1.001:
        e = cv2.warpAffine(e, cv2.getRotationMatrix2D((w / 2, h / 2), 0, grow), (w, h))
    line = (e.astype(np.float32) / 255)[..., None] * (np.array(color[::-1], np.float32) / 255)
    return _screen(frame, np.clip(line + 1.6 * cv2.GaussianBlur(line, (0, 0), 7), 0, 1) * min(1.0, amt))


def jaws(frame, amt, teeth=9, tilt=0.0, opacity=0.8):
    """Jagged bars biting in from the top and bottom; `amt` = how far each bar reaches (0..0.5 of
    the height), `tilt` slants them (deg)."""
    if amt <= 0.005:
        return frame
    h, w = frame.shape[:2]
    xs = np.linspace(0, w, teeth * 2 + 1)
    depth = np.where(np.arange(len(xs)) % 2 == 0, amt * h, amt * h * 0.55) + math.tan(math.radians(tilt)) * (xs - w / 2)
    top = np.array([(0, 0)] + list(zip(xs, depth)) + [(w, 0)], np.int32)
    bot = np.array([(0, h)] + list(zip(xs, h - depth)) + [(w, h)], np.int32)
    ov = frame.copy()
    cv2.fillPoly(ov, [top, bot], (0, 0, 0))
    return cv2.addWeighted(ov, opacity, frame, 1 - opacity, 0)


def edge_rays(frame, amt, color=(255, 160, 40), length=0.35, steps=8):
    """Light rays: the frame's bright edges streaked outward from the centre (a radial light burst)."""
    if amt <= 0.01:
        return frame
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    e = cv2.Canny(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), 60, 140).astype(np.float32) / 255
    e = e[..., None] * (np.array(color[::-1], np.float32) / 255)
    acc = np.zeros_like(e)
    for i in range(steps):
        M = cv2.getRotationMatrix2D((w / 4, h / 4), 0, 1 + length * i / steps)
        acc += cv2.warpAffine(e, M, (w // 2, h // 2)) * (1 - i / steps)
    return _screen(frame, cv2.resize(cv2.GaussianBlur(acc, (0, 0), 2) * (3.0 / steps), (w, h)) * amt)


_grid_cache = {}


def _grid(h, w):
    if (h, w) not in _grid_cache:
        _grid_cache.clear()
        _grid_cache[(h, w)] = np.mgrid[0:h, 0:w].astype(np.float32)
    return _grid_cache[(h, w)]


def halftone(frame, amt, cell=12, mono=False):
    """Print halftone: the picture as a grid of dots sized by brightness, mixed in by `amt`."""
    if amt <= 0.01:
        return frame
    h, w = frame.shape[:2]
    cs = cv2.resize(frame, (max(1, w // cell), max(1, h // cell)), interpolation=cv2.INTER_AREA)
    up = cv2.resize(cs, (w, h), interpolation=cv2.INTER_NEAREST)
    lum = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    yy, xx = _grid(h, w)
    d = np.hypot((xx % cell) - cell / 2, (yy % cell) - cell / 2)
    dots = (d <= cell * 0.72 * np.sqrt(lum)).astype(np.float32)[..., None]
    ink = (np.full_like(up, 235) if mono else up).astype(np.float32) * dots
    return cv2.addWeighted(frame, 1 - min(1.0, amt), ink.astype(np.uint8), min(1.0, amt), 0)


def ripple(frame, amp, age, cx=0.5, cy=0.5, wavelength=90.0, speed=600.0, light=0.25):
    """Water ripple: rings travelling out from (cx, cy), displacing the picture radially, with a
    slight shine on the crests. `amp` in px, `age` = seconds since the ripple started."""
    if amp <= 0.5:
        return frame
    h, w = frame.shape[:2]
    yy, xx = _grid(h, w)
    dx, dy = xx - cx * w, yy - cy * h
    r = np.sqrt(dx * dx + dy * dy) + 1e-3
    front = speed * age   # rings only exist inside the expanding front, fading behind it
    env = np.clip(1 - (r - front) / wavelength, 0, 1) * np.exp(-np.maximum(0, front - r) / (3 * wavelength))
    wave = np.sin(2 * np.pi * (r - front) / wavelength) * env
    off = amp * wave
    out = cv2.remap(frame, xx + dx / r * off, yy + dy / r * off, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT101)
    if light:
        out = np.clip(out.astype(np.float32) * (1 + light * np.maximum(0, wave)[..., None]), 0, 255).astype(np.uint8)
    return out


def light_sweep(frame, progress, angle=30.0, width=0.12, color=(255, 255, 255), strength=0.6):
    """A soft band of light sweeping across the frame; `progress` 0..1 moves it from edge to edge."""
    if not 0 <= progress <= 1:
        return frame
    h, w = frame.shape[:2]
    yy, xx = _grid(h, w)
    a = math.radians(angle)
    proj = (xx / w - 0.5) * math.cos(a) + (yy / h - 0.5) * math.sin(a) * h / w
    pos = -0.9 + 1.8 * progress
    band = np.exp(-((proj - pos) / width) ** 2)[..., None]
    return _screen(frame, band * (np.array(color[::-1], np.float32) / 255) * strength)


def film_damage(frame, amt, k):
    """Old-film dust, specks and the odd scratch, re-rolled every frame (seeded by the frame number)."""
    if amt <= 0.01:
        return frame
    h, w = frame.shape[:2]
    r = np.random.default_rng(k)
    out = frame.copy()
    for _ in range(int(6 + 40 * amt)):
        c = (20, 20, 20) if r.random() < 0.6 else (235, 235, 225)
        cv2.circle(out, (int(r.integers(0, w)), int(r.integers(0, h))), int(r.integers(1, 4)), c, -1, cv2.LINE_AA)
    if r.random() < 0.35 * amt:   # a vertical scratch
        x = int(r.integers(0, w))
        cv2.line(out, (x, 0), (x + int(r.integers(-30, 30)), h), (210, 210, 200), 1, cv2.LINE_AA)
    return cv2.addWeighted(out, min(1.0, amt), frame, 1 - min(1.0, amt), 0)


def desaturate(frame, amt):
    """Pull the colour out (amt 1 = black and white)."""
    if amt <= 0.01:
        return frame
    g = cv2.cvtColor(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    return cv2.addWeighted(frame, 1 - min(1.0, amt), g, min(1.0, amt), 0)


def round_mask(h, w, r):
    """Rounded-rectangle mask (0/255), h x w, corner radius r."""
    m = np.zeros((h, w), np.uint8)
    cv2.rectangle(m, (r, 0), (w - r, h), 255, -1)
    cv2.rectangle(m, (0, r), (w, h - r), 255, -1)
    for cx, cy in ((r, r), (w - r, r), (r, h - r), (w - r, h - r)):
        cv2.circle(m, (cx, cy), r, 255, -1, cv2.LINE_AA)
    return m


def card(frame, cx, cy, scale=0.78, out_w=OUT_W, out_h=OUT_H, bg="halftone", radius=28):
    """Picture-in-picture card: the shot shrunk to `scale` with rounded corners and a soft shadow,
    over a zoomed copy of itself treated as a background plate (halftone | blur | mono)."""
    plate = camera(frame, cx, cy, 1.45, out_w=out_w, out_h=out_h, fill="reflect")
    if bg == "halftone":
        plate = halftone(desaturate(plate, 1.0), 1.0, 14, mono=True)
    elif bg == "mono":
        plate = desaturate(plate, 1.0)
    else:
        plate = cv2.GaussianBlur(plate, (0, 0), 18)
    plate = (plate * 0.55).astype(np.uint8)
    fg = cv2.resize(camera(frame, cx, cy, 1.0, out_w=out_w, out_h=out_h), (int(out_w * scale), int(out_h * scale)))
    fh, fw = fg.shape[:2]
    m = round_mask(fh, fw, radius)
    x0, y0 = (out_w - fw) // 2, (out_h - fh) // 2
    sh = np.zeros((out_h, out_w), np.float32)
    sh[y0 + 24:y0 + 24 + fh, x0 + 12:x0 + 12 + fw] = m[: out_h - y0 - 24, : out_w - x0 - 12] / 255
    sh = cv2.GaussianBlur(sh, (0, 0), 28)[..., None] * 0.75
    out = plate.astype(np.float32) * (1 - sh)
    a = (m.astype(np.float32) / 255)[..., None]
    out[y0:y0 + fh, x0:x0 + fw] = fg * a + out[y0:y0 + fh, x0:x0 + fw] * (1 - a)
    return np.clip(out, 0, 255).astype(np.uint8)


def rim_light(frame, mask, amt, color=(120, 200, 255), width=6):
    """Glowing rim around the subject (needs a subject mask 0..1, same size as the frame)."""
    if amt <= 0.01 or mask is None:
        return frame
    m = (mask > 0.5).astype(np.uint8) * 255
    edge = cv2.subtract(cv2.dilate(m, None, iterations=width), cv2.erode(m, None, iterations=1)).astype(np.float32) / 255
    line = edge[..., None] * (np.array(color[::-1], np.float32) / 255)
    return _screen(frame, np.clip(line + 1.5 * cv2.GaussianBlur(line, (0, 0), 9), 0, 1) * min(1.0, amt))


class SubjectMask:
    """Person/subject cut-out masks for text-behind-subject and rim light. Uses the optional `rembg`
    package (install.sh offers it); without it, these effects are skipped with one warning."""

    def __init__(self):
        self.session, self.ok, self.cache = None, None, {}

    def __call__(self, frame, key):
        if self.ok is None:
            try:
                from rembg import new_session
                self.session, self.ok = new_session("u2net_human_seg"), True
            except Exception as e:
                self.ok = False
                print(f"  ! subject cut-out unavailable ({e}); text-behind and rim effects are skipped. "
                      f"Install it with: .venv/bin/pip install rembg onnxruntime")
        if not self.ok:
            return None
        if key not in self.cache:
            from rembg import remove
            if len(self.cache) > 8:
                self.cache.clear()
            h, w = frame.shape[:2]
            small = cv2.resize(frame, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
            m = remove(cv2.cvtColor(small, cv2.COLOR_BGR2RGB), session=self.session, only_mask=True)
            self.cache[key] = cv2.resize(np.asarray(m, np.float32) / 255, (w, h))
        return self.cache[key]


def blend(frame, layer, mode="screen", opacity=1.0):
    """Composite an overlay frame (uint8 BGR, same size) with a blend mode: screen | add | lighten |
    multiply | overlay. Light leaks, particles and dust plates usually go on with screen or add."""
    f, o = frame.astype(np.float32) / 255, layer.astype(np.float32) / 255
    if mode == "add":
        r = f + o
    elif mode == "lighten":
        r = np.maximum(f, o)
    elif mode == "multiply":
        r = f * o
    elif mode == "overlay":
        r = np.where(f < 0.5, 2 * f * o, 1 - 2 * (1 - f) * (1 - o))
    else:
        r = 1 - (1 - f) * (1 - o)
    r = f + (np.clip(r, 0, 1) - f) * opacity
    return (np.clip(r, 0, 1) * 255).astype(np.uint8)
