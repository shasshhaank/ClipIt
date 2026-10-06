"""Render an edit plan (JSON-able dict) to MP4.

plan = {
  fps, width, height, look, letterbox (0..0.15), duration,
  shots: [{src, out:[t0,t1], src_in, src_span, profile:{type, ...}, zoom:[z0,z1], layout:"fill"|"fit",
           track:{t:[], x:[], y:[]}, interp_fps (optional, smooth slow-mo)}],
  hits:  [{t, type, amt, dur, ...}]     # see docs/EFFECTS.md: flash, shake, punch, zoom_in, whip, jolt, bloom, ...
  texts / images / overlays: [{t0, t1, ...}]  # text cards, poster frames, pictures, overlay clips
  captions: {words:[...], source_time, y}     # word timestamps in source time (or output time)
  title: {text, t0, t1}
  audio: "mix.wav"
}
"""
import math
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import fx
from .media import SegmentReader, CachedReader, Encoder, probe
from .captions import CaptionRenderer, title_card, _paste, font_path


# ---------------------------------------------------------------- speed curves
def speed_profile(p, u):
    typ = p.get("type", "const")
    if typ == "const":
        return np.full_like(u, p.get("speed", 1.0))
    if typ == "ramp":      # velocity: fast -> slow (middle) -> fast. U-shaped
        hi, lo, k = p.get("hi", 4.0), p.get("lo", 0.3), p.get("k", 2.5)
        c = p.get("center", 0.5)
        d = np.where(u < c, (c - u) / max(c, 1e-6), (u - c) / max(1 - c, 1e-6))
        return lo + (hi - lo) * d ** k
    if typ == "ease_out":  # slow -> fast (speeds into the next cut)
        return p.get("lo", 0.4) + (p.get("hi", 3.0) - p.get("lo", 0.4)) * u ** p.get("k", 2.5)
    if typ == "ease_in":   # fast -> slow (lands into slow-mo)
        return p.get("lo", 0.3) + (p.get("hi", 3.0) - p.get("lo", 0.3)) * (1 - u) ** p.get("k", 2.5)
    if typ == "pulses":    # speed peaks at given points (u in 0..1), e.g. synced to zoom-chain beats
        lo, hi, w = p.get("lo", 0.35), p.get("hi", 4.0), p.get("w", 0.05)
        acc = np.zeros_like(u)
        for a in p.get("at", [0.5]):
            acc += np.exp(-((u - a) / w) ** 2)
        return lo + (hi - lo) * np.clip(acc, 0, 1)
    if typ in ("decel", "boomerang", "reverse"):  # fast -> slow (10x -> 1x style, cubic out)
        return p.get("lo", 0.6) + (p.get("hi", 8.0) - p.get("lo", 0.6)) * (1 - u) ** p.get("k", 3.0)
    raise ValueError(typ)


def _cum(s):
    v = np.concatenate([[0], np.cumsum((s[1:] + s[:-1]) / 2)])
    return v / v[-1], v[-1] / (len(s) - 1)


def remap_table(p, n=400):
    """(u, normalised source progress v(u), mean speed, |speed|(u)).
    'boomerang' plays forward decelerating, then the same frames in reverse (back-and-forth
    reverse trend); 'reverse' plays backwards. Both need random-access (cached) readers."""
    u = np.linspace(0, 1, n)
    typ = p.get("type", "const")
    if typ == "boomerang":
        split = p.get("split", 0.5)
        f = speed_profile(p, u)
        vf, mean_f = _cum(f)
        fwd = u <= split
        uf = np.where(fwd, u / split, 1 - (u - split) / (1 - split))
        v = np.interp(uf, u, vf)
        s = np.interp(uf, u, f) * np.where(fwd, 1.0, split / (1 - split))
        return u, v, split * mean_f, s
    s = speed_profile(p, u)
    v, mean = _cum(s)
    if typ == "reverse":
        v = 1 - v
    return u, v, mean, s


# ---------------------------------------------------------------- hit envelopes
def env(t, h):
    """0..1 envelope of hit h at output time t. Attack 'att' (s) then decay over 'dur' (s)."""
    t0, dur, att = h["t"], h.get("dur", 0.15), h.get("att", 0.0)
    if t < t0 - att or t > t0 + dur:
        return 0.0
    if t < t0:
        return ((t - (t0 - att)) / att) ** 2 if att > 0 else 1.0
    x = (t - t0) / dur
    shape = h.get("shape", "exp")
    if shape == "hold":
        return 1.0
    if shape == "lin":
        return 1 - x
    return math.exp(-4.5 * x) * (1 - x)


def _fade(rgba, alpha):
    """Copy of an RGBA layer with its opacity scaled by `alpha`."""
    out = rgba.copy()
    out[..., 3] = (out[..., 3] * max(0.0, alpha)).astype(np.uint8)
    return out


def _rotate(rgba, deg, scale=1.0):
    """Rotate (and scale) an RGBA layer about its centre onto a canvas big enough to hold all of it."""
    h, w = rgba.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), deg, scale)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw, nh = int(h * sin + w * cos) + 2, int(h * cos + w * sin) + 2
    M[0, 2] += nw / 2 - w / 2
    M[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(rgba, M, (nw, nh), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))


class TextLayer:
    """Animated text: anim = pop | slam (3x -> 1x hit) | type (typewriter) | words (word by word, in
    place) | fade. Drawn after grading so it stays crisp. Per-word colour via [brackets] = accent;
    `gradient` [[r,g,b], [r,g,b]] fills top to bottom; `rot` turns the card (deg, e.g. 90 = sideways)."""

    def __init__(self, spec, W):
        self.s = spec
        self.W = W
        self.font = ImageFont.truetype(font_path(spec.get("font", "heavy")), spec.get("size", 110))
        self.cache = {}

    def _wrap(self, text):
        lines, cur = [], []
        for w in text.split():
            if cur and self.font.getlength(" ".join(x.strip("[]") for x in cur + [w])) > self.W - 80:
                lines.append(cur)
                cur = []
            cur.append(w)
        lines.append(cur)
        return lines

    def _img(self, text, upto=None):
        """Rendered card; with `upto`, only the first `upto` words are drawn (layout stays put)."""
        if (text, upto) in self.cache:
            return self.cache[(text, upto)]
        sp = self.s
        f = self.font
        lines = self._wrap(text)
        lh = int(f.size * sp.get("leading", 1.12))
        stroke = sp.get("stroke", 0)
        size = (self.W, lh * len(lines) + 60)
        img = Image.new("RGBA", size, (0, 0, 0, 0))
        top = Image.new("RGBA", size, (0, 0, 0, 0)) if sp.get("gradient") else img   # fills, recoloured below
        d, dt = ImageDraw.Draw(img), ImageDraw.Draw(top)
        col = tuple(sp.get("color", (255, 255, 255)))
        acc = tuple(sp.get("accent", (230, 30, 40)))
        n = 0
        for i, ln in enumerate(lines):
            clean = [w.strip("[]") for w in ln]
            x = (self.W - f.getlength(" ".join(clean))) / 2
            if sp.get("bar"):   # a solid bar behind the line, e.g. a meme label across the eyes
                b = f.getbbox(" ".join(clean))
                p = sp.get("bar_pad", 0.35) * f.size
                d.rectangle((x + b[0] - p, 30 + i * lh + b[1] - p / 2, x + b[2] + p, 30 + i * lh + b[3] + p / 2),
                            fill=tuple(sp["bar"]))
            for w, c in zip(ln, clean):
                if upto is None or n < upto:
                    fill = acc if w.startswith("[") else col
                    if sp.get("shadow", True):
                        d.text((x + 6, 30 + i * lh + 8), c, font=f, fill=(0, 0, 0, 170), stroke_width=stroke,
                               stroke_fill=(0, 0, 0, 170))
                    dt.text((x, 30 + i * lh), c, font=f, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0))
                x += f.getlength(c + " ")
                n += 1
        if sp.get("gradient"):
            g = np.array(top)
            c0, c1 = (np.array(c, np.float32) for c in sp["gradient"])
            ramp = np.linspace(0, 1, g.shape[0], dtype=np.float32)[:, None, None]
            g[..., :3] = (c0 + (c1 - c0) * ramp).astype(np.uint8)
            img = Image.alpha_composite(img, Image.fromarray(g))
        arr = np.array(img)
        if sp.get("glow", 0):
            arr = add_glow(arr, sp["glow"], sp.get("glow_radius", 22), sp.get("glow_color"))
        if sp.get("rot"):
            arr = _rotate(arr, sp["rot"])
        self.cache[(text, upto)] = arr
        return arr

    def draw(self, frame, t, k, aenv=0.0):
        sp = self.s
        t0, t1 = sp["t0"], sp["t1"]
        if not (t0 <= t < t1):
            return frame
        age = t - t0
        text = sp["text"]
        anim = sp.get("anim", "pop")
        sc, alpha, dx, upto = 1.0, 1.0, 0, None
        if anim == "words":
            nw = len(text.split())
            upto = math.ceil(nw * min(1, age / max(sp.get("type_dur", 0.6), 1e-3)))
            if not upto:
                return frame
        elif anim == "type":
            n = int(len(text) * min(1, age / max(sp.get("type_dur", 0.5), 1e-3)))
            text = text[:n]
            if not text.strip():
                return frame
        elif anim == "slam":
            d = sp.get("slam_dur", 0.12)
            if age < d:
                x = age / d
                sc = 2.6 - 1.6 * (1 - (1 - x) ** 3)
            # small decaying shake after impact
            if age < 0.35:
                dx = int(14 * math.sin(age * 90) * (1 - age / 0.35))
        elif anim == "pop":
            if age < 0.066:
                sc = 0.75 + 0.4 * age / 0.066
            elif age < 0.2:
                sc = 1.15 - 0.15 * (age - 0.066) / 0.134
        out_fade = sp.get("fade_out", 0.0)
        if out_fade and t > t1 - out_fade:
            alpha = (t1 - t) / out_fade
        if sp.get("flicker") and age < 0.25 and k % 2:
            alpha *= 0.35
        alpha *= hum_flicker(sp.get("hum", 0), t, k, aenv)
        if anim == "assemble" or sp.get("exit") == "scatter":
            return self._letters(frame, age, t1 - t, alpha)
        img = self._img(text, upto)
        if alpha < 0.999:
            img = _fade(img, alpha)
        return _paste(frame, img, int(sp.get("x", self.W // 2)) + dx, int(sp.get("y", 960)), sc)

    def _sprites(self):
        """One small RGBA sprite per letter, with its centre on the card (built once)."""
        if hasattr(self, "_sp"):
            return self._sp
        sp, f = self.s, self.font
        lines = self._wrap(sp["text"])
        lh = int(f.size * sp.get("leading", 1.12))
        col, acc = tuple(sp.get("color", (255, 255, 255))), tuple(sp.get("accent", (230, 30, 40)))
        card_h = lh * len(lines) + 60
        out = []
        for i, ln in enumerate(lines):
            x = (self.W - f.getlength(" ".join(w.strip("[]") for w in ln))) / 2
            for w in ln:
                for ch in w.strip("[]"):
                    cw = f.getlength(ch)
                    im = Image.new("RGBA", (int(cw) + 40, lh + 40), (0, 0, 0, 0))
                    d = ImageDraw.Draw(im)
                    if sp.get("shadow", True):
                        d.text((26, 28), ch, font=f, fill=(0, 0, 0, 170))
                    d.text((20, 20), ch, font=f, fill=acc if w.startswith("[") else col,
                           stroke_width=sp.get("stroke", 0), stroke_fill=(0, 0, 0))
                    a = np.array(im)
                    if sp.get("glow", 0):
                        a = add_glow(a, sp["glow"], sp.get("glow_radius", 22), sp.get("glow_color"))
                    out.append((a, x + cw / 2, 30 + i * lh + lh / 2 - card_h / 2))
                    x += cw
                x += f.getlength(" ")
        r = np.random.default_rng(len(out))   # fixed per text, so every render matches
        self._sp = [(a, cx, cy, r.uniform(-1, 1, 2), r.uniform(-1, 1), r.random()) for a, cx, cy in out]
        return self._sp

    def _letters(self, frame, age, left, alpha):
        """assemble: letters fly in from scattered spots, spinning and growing, in random order.
        exit "scatter": in the last `exit_dur` s they fly apart, spin and shrink away."""
        sp = self.s
        d_in, d_out = max(sp.get("type_dur", 0.8), 1e-3), max(sp.get("exit_dur", 0.6), 1e-3)
        dist, spin = sp.get("scatter_px", 520), sp.get("scatter_rot", 360)
        x0, y0 = int(sp.get("x", self.W // 2)), int(sp.get("y", 960))
        for a, cx, cy, vec, rot, order in self._sprites():
            p_in = 1.0 if sp.get("anim") != "assemble" else min(1.0, max(0.0, (age - order * d_in * 0.6) / (d_in * 0.4)))
            e_in = 1 - (1 - p_in) ** 3
            p_out = 0.0 if sp.get("exit") != "scatter" else min(1.0, max(0.0, (d_out - left - order * d_out * 0.4) / (d_out * 0.6)))
            e_out = p_out * p_out
            move = (1 - e_in) + e_out
            sc = max(0.01, e_in * (1 - e_out))
            if sc <= 0.02:
                continue
            im = a
            r = rot * spin * move
            if abs(r) > 0.5:
                h, w = a.shape[:2]
                im = cv2.warpAffine(a, cv2.getRotationMatrix2D((w / 2, h / 2), r, 1.0), (w, h), borderValue=(0, 0, 0, 0))
            if alpha * (1 - e_out) < 0.999:
                im = _fade(im, alpha * (1 - e_out))
            frame = _paste(frame, im, int(x0 - self.W / 2 + cx + vec[0] * dist * move),
                           int(y0 + cy + vec[1] * dist * move), sc)
        return frame


def add_glow(rgba, strength=1.0, radius=22, color=None):
    """Bloom: blurred copy of the text (in its own colours or a fixed glow colour) under the text."""
    pad = radius * 2
    a = np.pad(rgba, ((pad, pad), (pad, pad), (0, 0)))
    alpha = a[..., 3:4].astype(np.float32) / 255
    col = a[..., :3].astype(np.float32) if color is None else np.full_like(a[..., :3], color, dtype=np.float32)
    g = cv2.GaussianBlur(np.concatenate([col * alpha, alpha], 2), (0, 0), radius)
    g2 = cv2.GaussianBlur(np.concatenate([col * alpha, alpha], 2), (0, 0), radius / 3)
    g = g * 0.65 + g2 * 0.6
    ga = np.clip(g[..., 3:4] * strength, 0, 1)
    gc = g[..., :3] / np.maximum(g[..., 3:4], 1e-4)
    ta = alpha
    out_a = ta + ga * (1 - ta)
    out_c = (a[..., :3] * ta + gc * ga * (1 - ta)) / np.maximum(out_a, 1e-4)
    return np.concatenate([np.clip(out_c, 0, 255), out_a * 255], 2).astype(np.uint8)


def hum_flicker(depth, t, k, aenv, drop=True):
    """'50 Hz' mains/CRT flicker: a 50 Hz sine sampled at 30 fps aliases to a slow 10 Hz 3-frame
    shimmer. Depth swells with the music's onset envelope; strong hits drop the layer for a frame."""
    if not depth:
        return 1.0
    hum = 0.5 + 0.5 * math.sin(2 * math.pi * 50 * t)
    d = min(0.9, depth * (0.25 + 0.9 * aenv))
    v = 1 - d * hum
    if drop and aenv > 0.82 and k % 3 == 0:
        v *= 0.15
    return v


class PosterLayer:
    """Poster frame: display type composed like a printed poster. Use rarely (title, after the drop, end).
    layout "stack": one line per word (or split lines with "/"), each line filling `w` of the width with
      tight leading; "|" in a line steps the rest of that line down (GIN|GER).
    layout "mark": one wordmark `w` wide, optional superscript `sup` (e.g. "®") and a small stacked `tag`
      lockup to its right ("\\n" between tag lines).
    `align` l|c|r; `w` > 1 lets oversized type bleed off the frame; `rot` tilts and `skew` obliques the
      headline (degrees). `bg` turns it into a solid colour type card; `panel` {y, color} lays a paper panel
      from y (0-1) to the bottom. `extras` are small labels {text, x, y (0-1), size, font, align, box, color}.
    anim "cut" shows everything at once, "stack" reveals one line at a time over `reveal` s, "zoom" flies in
      through the letters (starts `zoom_from` x big, settles over `zoom_dur` s). `texture` and `soft` give
      the ink a printed feel."""

    def __init__(self, spec, W, H):
        self.s, self.W, self.H = spec, W, H
        t = spec["text"]
        self.lines = ([x.strip() for x in t.replace("/", "\n").split("\n") if x.strip()] if ("/" in t or "\n" in t)
                      else t.split()) if spec.get("layout", "stack") == "stack" else [t]
        self.cache = {}

    def _font(self, name, size):
        return ImageFont.truetype(font_path(name), max(8, int(size)))

    def _fit(self, name, text, width):
        """Font sized so `text` is `width` px wide, plus its ink bbox at that size."""
        x0, _, x1, _ = self._font(name, 200).getbbox(text)
        f = self._font(name, 200 * width / max(1, x1 - x0))
        return f, f.getbbox(text)

    def _headline(self, n):
        sp, W, H = self.s, self.W, self.H
        col, name, cy = tuple(sp.get("color", (240, 236, 224))), sp.get("font", "poster"), sp.get("y", H / 2)
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        if sp.get("layout", "stack") == "stack":
            cw = W * sp.get("w", 0.86)
            plain = [ln.replace("|", "") for ln in self.lines]

            def fit(width):   # "block": one size, set by the widest line; "lines": every line fills the width
                if sp.get("fit", "block") == "lines":
                    return [self._fit(name, ln, width) for ln in plain]
                f = self._fit(name, max(plain, key=lambda x: self._font(name, 200).getlength(x)), width)[0]
                return [(f, f.getbbox(ln)) for ln in plain]
            fits = fit(cw)
            hs = [b[3] - b[1] for _, b in fits]
            gap = sp.get("leading", 0.07) * float(np.mean(hs))
            k = min(1.0, H * sp.get("h", 0.62) / (sum(hs) + gap * (len(hs) - 1)))   # too tall: shrink every line
            if k < 1:
                fits = fit(cw * k)
                hs, gap = [b[3] - b[1] for _, b in fits], gap * k
            y = cy - (sum(hs) + gap * (len(hs) - 1)) / 2
            for ln, (f, b), h in list(zip(self.lines, fits, hs))[:n]:
                lw = b[2] - b[0]
                x = {"l": (W - cw) / 2, "c": (W - lw) / 2, "r": (W + cw) / 2 - lw}[sp.get("align", "c")]
                for j, seg in enumerate(ln.split("|")):
                    d.text((x - b[0], y - b[1] + j * sp.get("step", 0.45) * h), seg, font=f, fill=col)
                    x += f.getlength(seg)
                y += h + gap
        else:
            f, b = self._fit(name, self.lines[0], W * sp.get("w", 0.6))
            tw, th = b[2] - b[0], b[3] - b[1]
            tag = sp.get("tag", "").split("\n") if sp.get("tag") else []
            ft = self._font(sp.get("tag_font", "wide"), th / max(1, len(tag)) * 0.82) if tag else None
            tagw = max((ft.getlength(x) for x in tag), default=0) + th * 0.12 if tag else 0
            x, y = (W - tw - tagw) / 2, cy - th / 2
            d.text((x - b[0], y - b[1]), self.lines[0], font=f, fill=col)
            if sp.get("sup"):
                d.text((x + tw + th * 0.05, y - th * 0.04), sp["sup"], font=self._font("bold", th * 0.26), fill=col)
            for i, ln in enumerate(tag):
                d.text((x + tw + th * 0.12, y + i * th / len(tag)), ln, font=ft, fill=col)
        a = np.array(img)
        if sp.get("skew"):    # oblique: top leans right
            s = math.tan(math.radians(sp["skew"]))
            a = cv2.warpAffine(a, np.float32([[1, -s, s * cy], [0, 1, 0]]), (W, H))
        if sp.get("rot"):
            a = cv2.warpAffine(a, cv2.getRotationMatrix2D((W / 2, cy), sp["rot"], 1.0), (W, H))
        al = a[..., 3].astype(np.float32)
        if sp.get("soft", 0.6):
            al = cv2.GaussianBlur(al, (0, 0), sp.get("soft", 0.6))
        if sp.get("texture", 0.15):   # speckled ink, fixed seed so every render matches
            nz = cv2.resize(np.random.default_rng(11).random((H // 3, W // 3)).astype(np.float32), (W, H))
            al *= 1 - sp.get("texture", 0.15) * np.clip((nz - 0.55) / 0.45, 0, 1)
        a[..., 3] = np.clip(al, 0, 255).astype(np.uint8)
        return a

    def _compose(self, n):
        """Background (solid card and/or paper panel), headline over it, then the small labels."""
        sp, W, H = self.s, self.W, self.H
        base = np.zeros((H, W, 4), np.float32)
        if sp.get("bg"):
            base[:] = (*sp["bg"], 255)
        if sp.get("panel"):
            base[int(sp["panel"].get("y", 0.75) * H):] = (*sp["panel"].get("color", (245, 245, 242)), 255)
        head = self._headline(n).astype(np.float32)
        a, b = head[..., 3:] / 255, base[..., 3:] / 255
        out_a = a + b * (1 - a)   # "over" in straight alpha, so soft edges don't get dark fringes
        rgb = (head[..., :3] * a + base[..., :3] * b * (1 - a)) / np.maximum(out_a, 1e-6)
        return self._extras(np.concatenate([rgb, out_a * 255], 2).astype(np.uint8))

    def _extras(self, a):
        sp = self.s
        im = Image.fromarray(a)
        d = ImageDraw.Draw(im)
        col = tuple(sp.get("extras_color", sp.get("color", (240, 236, 224))))
        for e in sp.get("extras", []):
            f = self._font(e.get("font", "mono"), e.get("size", 28))
            al = {"l": "left", "c": "center", "r": "right"}[e.get("align", "c")]
            b = d.multiline_textbbox((0, 0), e["text"], font=f, spacing=6, align=al)
            w, h = b[2] - b[0], b[3] - b[1]
            x = e["x"] * self.W - {"l": 0, "c": 0.5, "r": 1}[e.get("align", "c")] * w
            y = e["y"] * self.H - h / 2
            c = tuple(e.get("color", col))
            d.multiline_text((x - b[0], y - b[1]), e["text"], font=f, fill=c, spacing=6, align=al)
            if e.get("box"):
                p = e.get("pad", 12)
                d.rectangle((x - p, y - p, x + w + p, y + h + p), outline=c, width=e.get("line", 3))
        return np.array(im)

    def draw(self, frame, t, k, aenv=0.0):
        sp = self.s
        if not (sp["t0"] <= t < sp["t1"]):
            return frame
        age = t - sp["t0"]
        n = len(self.lines)
        if sp.get("anim", "cut") == "stack":
            n = min(n, 1 + int(age / (sp.get("reveal", 0.6) / n)))
        if n not in self.cache:
            self.cache[n] = self._compose(n)
        img = self.cache[n]
        sc = 1 + sp.get("grow", 0.008) * age
        if sp.get("anim") == "zoom" and age < sp.get("zoom_dur", 0.35):   # ease-out from huge
            sc *= 1 + (sp.get("zoom_from", 6.0) - 1) * (1 - age / sp.get("zoom_dur", 0.35)) ** 3
        if sc > 1.001:   # scale up by cropping the centre (never builds a giant canvas)
            cw, ch = int(self.W / sc), int(self.H / sc)
            x0, y0 = (self.W - cw) // 2, (self.H - ch) // 2
            img = cv2.resize(img[y0:y0 + ch, x0:x0 + cw], (self.W, self.H))
        fo = sp.get("fade_out", 0.0)
        if fo and t > sp["t1"] - fo:
            img = _fade(img, (sp["t1"] - t) / fo)
        return _paste(frame, img, self.W // 2, self.H // 2)


class ImageLayer:
    """Picture overlay (thumbnails, logos): anim pop|slam|fade|drop, rotation, rounded corners,
    white border + shadow (cards), circle mask, glow, hum flicker."""

    def __init__(self, spec):
        self.s = spec
        im = cv2.imread(spec["path"], cv2.IMREAD_UNCHANGED)
        if im.shape[2] == 3:
            im = np.dstack([im, np.full(im.shape[:2], 255, np.uint8)])
        im = cv2.cvtColor(im, cv2.COLOR_BGRA2RGBA)  # layers are RGBA (like PIL output)
        w = int(spec.get("w", 800))
        h = int(im.shape[0] * w / im.shape[1])
        im = cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA)
        if spec.get("circle"):
            m = np.zeros((h, w), np.uint8)
            cv2.circle(m, (w // 2, h // 2), min(w, h) // 2 - 1, 255, -1, cv2.LINE_AA)
            im[..., 3] = np.minimum(im[..., 3], m)
        elif spec.get("radius", 0):
            im[..., 3] = np.minimum(im[..., 3], fx.round_mask(h, w, spec["radius"]))
        if spec.get("border", 0):
            b = spec["border"]
            big = np.zeros((h + 2 * b, w + 2 * b, 4), np.uint8)
            big[..., :3] = 255
            big[..., 3] = fx.round_mask(h + 2 * b, w + 2 * b, spec.get("radius", 0) + b)
            a = im[..., 3:4].astype(np.float32) / 255
            reg = big[b:b + h, b:b + w]
            reg[..., :3] = (im[..., :3] * a + reg[..., :3] * (1 - a)).astype(np.uint8)
            im = big
        if spec.get("shadow", False):
            pad = 40
            im = np.pad(im, ((pad, pad), (pad, pad), (0, 0)))
            sh = cv2.GaussianBlur(im[..., 3].astype(np.float32), (0, 0), 16)
            sh = np.roll(np.roll(sh, 14, 0), 8, 1) * 0.75
            a = im[..., 3].astype(np.float32)
            out_a = a + sh * (1 - a / 255)
            im[..., :3] = (im[..., :3].astype(np.float32) * (a / np.maximum(out_a, 1))[..., None]).astype(np.uint8)
            im[..., 3] = np.clip(out_a, 0, 255).astype(np.uint8)
        if spec.get("glow", 0):
            im = add_glow(im, spec["glow"], spec.get("glow_radius", 40), spec.get("glow_color"))
        self.img = im

    def draw(self, frame, t, k, aenv=0.0):
        sp = self.s
        if not (sp["t0"] <= t < sp["t1"]):
            return frame
        age = t - sp["t0"]
        sc, rot, alpha, dy = 1.0, sp.get("rot", 0.0), 1.0, 0
        anim = sp.get("anim", "pop")
        if anim == "pop":
            if age < 0.07:
                sc = 0.6 + 0.55 * age / 0.07
            elif age < 0.2:
                sc = 1.15 - 0.15 * (age - 0.07) / 0.13
        elif anim == "slam":
            d = sp.get("slam_dur", 0.13)
            if age < d:
                sc = 2.4 - 1.4 * (1 - (1 - age / d) ** 3)
        elif anim == "drop":
            if age < 0.18:
                x = age / 0.18
                dy = int(-500 * (1 - x) ** 3)
                rot += 12 * (1 - x) ** 2
        elif anim == "fade":
            alpha = min(1.0, age / sp.get("fade_in", 0.3))
        sc *= 1 + sp.get("grow", 0.0) * age
        x0, y0 = sp.get("x", 540), sp.get("y", 960)
        if sp.get("kf"):  # keyframes [[t, x, y, scale], ...] with smoothstep easing between them
            kf = sp["kf"]
            if t <= kf[0][0]:
                x0, y0, ks = kf[0][1:4]
            elif t >= kf[-1][0]:
                x0, y0, ks = kf[-1][1:4]
            else:
                for a, b in zip(kf[:-1], kf[1:]):
                    if a[0] <= t < b[0]:
                        u = (t - a[0]) / (b[0] - a[0])
                        u = u * u * (3 - 2 * u)
                        x0, y0, ks = [a[i] + (b[i] - a[i]) * u for i in (1, 2, 3)]
                        break
            sc *= ks
        fo = sp.get("fade_out", 0.0)
        if fo and t > sp["t1"] - fo:
            alpha *= (sp["t1"] - t) / fo
        alpha *= hum_flicker(sp.get("hum", 0), t, k, aenv, sp.get("hum_drop", True))
        im = self.img
        if abs(sc - 1) > 0.005 or abs(rot) > 0.05:
            im = _rotate(im, rot, sc)
        if alpha < 0.999:
            im = _fade(im, alpha)
        return _paste(frame, im, int(x0), int(y0) + dy, 1.0)


def flow_ease(u, p=4.0):
    """Aggressive S-curve: slow-fast-slow with the
    velocity peak exactly at u = 0.5. p=2 is a soft ease, 4-6 is snappy."""
    u = min(1.0, max(0.0, u))
    return 0.5 * (2 * u) ** p if u < 0.5 else 1 - 0.5 * (2 - 2 * u) ** p


class Renderer:
    def __init__(self, plan):
        self.p = plan
        self.fps = plan.get("fps", 30)
        self.W, self.H = plan.get("width", 1080), plan.get("height", 1920)
        self.look = fx.Look(plan.get("look", "punchy"), self.W, self.H)
        self.rng = np.random.default_rng(3)
        self.infos = {}
        self.looks = {plan.get("look", "punchy"): self.look}
        for s in plan["shots"]:
            if s["src"] not in self.infos:
                self.infos[s["src"]] = probe(s["src"])
            if s.get("look") and s["look"] not in self.looks:
                self.looks[s["look"]] = fx.Look(s["look"], self.W, self.H)
            s["_tab"] = remap_table(s.get("profile", {"type": "const"}))
            s["_zk"] = sorted(s.get("zooms", []), key=lambda z: z["t"])
        self.caps = None
        c = plan.get("captions")
        if c and c.get("words"):
            self.caps = CaptionRenderer(c["words"], self.W, self.H, size=c.get("size", 86), y_frac=c.get("y", 0.66),
                                        style=c.get("style", "clip"))
        self.title = None
        if plan.get("title"):
            self.title = title_card(plan["title"]["text"], self.W, plan["title"].get("size", 84))
        self.readers = {}
        self.hist = []
        layers = [(tx.get("z", 10), PosterLayer(tx, self.W, self.H) if tx.get("kind") == "poster" else TextLayer(tx, self.W))
                  for tx in plan.get("texts", [])]
        layers += [(im.get("z", 5), ImageLayer(im)) for im in plan.get("images", [])]
        self.texts = [l for _, l in sorted(layers, key=lambda x: x[0])]
        self.aenv = np.array(plan.get("audio_env", []), np.float32)
        self.mask = fx.SubjectMask()
        self.overlays = plan.get("overlays", [])
        self.ov_readers = {}

    # ------------------------------------------------------------ source access
    def _reader(self, i):
        shots = self.p["shots"]
        s = shots[i]
        if i not in self.readers:
            for k in list(self.readers):  # close finished shots
                if k < i - 1:
                    self.readers.pop(k).close()
            info = self.infos[s["src"]]
            w, h = info["width"], info["height"]
            sc = min(1.0, 2160 / max(w, h))
            w, h = int(w * sc) // 2 * 2, int(h * sc) // 2 * 2
            # extra source after the shot so the next shot can dissolve over it
            tail = 0.0
            if i + 1 < len(shots) and shots[i + 1].get("mix"):
                _, _, _, end_speed = self._timing(s, s["out"][1] - 1e-4)
                tail = shots[i + 1]["mix"] * max(1.0, abs(end_speed)) + 0.1
            interp = s.get("interp", self.p.get("interp", "blend"))
            ptype = s.get("profile", {}).get("type", "const")
            if ptype in ("boomerang", "reverse"):   # non-monotonic time needs random access
                rd = CachedReader(s["src"], s["src_in"] - 0.05, s["src_span"] + 0.2 + tail, w, h,
                                  info["fps"], interp=interp)
            else:
                rd = SegmentReader(s["src"], s["src_in"] - 0.05, s["src_span"] + 0.2 + tail, w, h,
                                   info["fps"], s.get("interp_fps"), interp=interp)
            self.readers[i] = rd
        return self.readers[i]

    def _shot_at(self, t):
        shots = self.p["shots"]
        for i, s in enumerate(shots):
            if s["out"][0] <= t < s["out"][1]:
                return i
        return len(shots) - 1

    def _timing(self, s, t):
        """(u, source time, normalised progress v, playback speed) at output time t.
        Past the end of the shot (dissolve tails) time keeps moving at the end speed."""
        o0, o1 = s["out"]
        d = max(o1 - o0, 1e-6)
        ur = (t - o0) / d
        u = min(1.0, max(0.0, ur))
        tu, tv, mean, sp = s["_tab"]
        v = float(np.interp(u, tu, tv))
        if ur > 1:
            v += (ur - 1) * (tv[-1] - tv[-2]) / (tu[-1] - tu[-2])
        speed = float(np.interp(u, tu, sp)) / mean * s["src_span"] / d
        return u, s["src_in"] + s["src_span"] * v, v, speed

    # ------------------------------------------------------------ camera
    def _zoom_chain(self, s, t):
        """Velocity zoom chain: keyframes {t, scale, x, y, rot, dur}. Each move eases with an
        aggressive S-curve centred on its beat, and scales compound (zoom keeps zooming)."""
        zk = s["_zk"]
        if not zk:
            return 1.0, None, None, 0.0
        sc, x, y, rot = 1.0, None, None, 0.0
        for z in zk:
            dur = z.get("dur", 0.3)
            if z.get("curve") == "out":   # bursts out on the beat, then glides to rest
                u = (t - z["t"]) / dur
                e = 0.0 if u <= 0 else 1 - (1 - min(1.0, u)) ** z.get("ease", 4.0)
            else:                         # S-curve with its velocity peak on the beat
                e = flow_ease((t - (z["t"] - dur / 2)) / dur, z.get("ease", 4.0))
            if e <= 0:
                break
            ts = z.get("scale", sc)
            sc = math.exp(math.log(sc) + (math.log(ts) - math.log(sc)) * e)
            if "x" in z:
                x = z["x"] if x is None or e >= 1 else x + (z["x"] - x) * e
            if "y" in z:
                y = z["y"] if y is None or e >= 1 else y + (z["y"] - y) * e
            rot = rot + (z.get("rot", rot) - rot) * e
        return sc, x, y, rot

    def _camera(self, s, t, k, src_t, u, jolt):
        """Camera transform + hit-driven effect amounts at time t."""
        z0, z1 = s.get("zoom", [1.0, 1.0])
        if s.get("zoom_follow"):   # zoom tracks source progress (in on the way forward, out on the way back)
            _, _, v, _ = self._timing(s, t)
            e = v * v * (3 - 2 * v)
        else:
            e = u * u * (3 - 2 * u)
        zoom = z0 + (z1 - z0) * e
        tr = s.get("track")
        if s.get("fit_z") and tr and tr.get("z"):   # the head only fits smaller: shrink the picture, fill around it
            k = max(0, int(np.searchsorted(tr["t"], src_t, "right")) - 1)   # a step per scene, not a morph
            zoom *= min(1.0, tr["z"][min(k, len(tr["z"]) - 1)] / s["fit_z"])
        cx, cy = (0.5, 0.45)
        if tr and len(tr["t"]):
            cx = float(np.interp(src_t, tr["t"], tr["x"]))
            cy = float(np.interp(src_t, tr["t"], tr["y"]))
        cx, cy = s.get("cx", cx), s.get("cy", cy)
        zc, zx, zy, zr = self._zoom_chain(s, t)
        zoom *= zc
        if zx is not None:
            cx = zx
        if zy is not None:
            cy = zy
        c = dict(zoom=zoom, cx=cx, cy=cy, rot=zr, dx=0.0, dy=0.0, sy=1.0, zoom_blur=0.0, blur_len=0.0, rgb=0.0,
                 glitch=0.0, flash_w=0.0, flash_b=0.0, expo=1.0, inv=False, defocus=0.0, edges=0.0, jaws=0.0,
                 rays=0.0, desat=0.0, ripple=0.0, sweep=-1.0, rim=0.0)
        base = dict(self.p.get("fx", {}), **s.get("fx", {}))
        for key in ("bloom", "leak", "vhs", "echo", "rgb_radial", "bulge", "halftone", "dust"):
            c[key] = base.get(key, 0.0)
        c["bloom_threshold"] = base.get("bloom_threshold", 0.7)
        if base.get("film_flicker"):   # constant irregular exposure flicker, the same on every render
            c["expo"] *= 1 + base["film_flicker"] * (((math.sin(k * 12.9898) * 43758.5453) % 1) * 2 - 1)
        if base.get("handheld"):
            hx, hy, hr = fx.handheld(t, base["handheld"], base.get("handheld_speed", 1.0))
            c["dx"] += hx
            c["dy"] += hy
            c["rot"] += hr
        if jolt:
            c["zoom"] *= 1 + jolt.get("scale", 0)
            c["dx"] += jolt.get("slide", 0)
            c["blur_len"] = max(c["blur_len"], jolt.get("blur", 0), abs(jolt.get("slide", 0)) * 0.8)
            c["expo"] *= 1 + jolt.get("light", 0)
        for h in self.p["hits"]:
            e = env(t, h)
            if e <= 0:
                continue
            typ, a = h["type"], h.get("amt", 1.0)
            if typ == "punch":
                c["zoom"] *= 1 + a * e
            elif typ == "shake":
                f = h.get("freq", 15)
                ph = (t - h["t"]) * f * 2 * math.pi
                A = h.get("px", 45) * a * e
                c["dx"] += A * math.sin(ph * 1.0 + 0.3)
                c["dy"] += A * 0.8 * math.sin(ph * 1.37 + 1.1)
                c["rot"] += h.get("rot", 1.5) * a * e * math.sin(ph * 0.9)
                if not self.p.get("camera_blur", True):
                    c["blur_len"] = max(c["blur_len"], 18 * a * e)
            elif typ == "flash":
                c["flash_w"] = max(c["flash_w"], a * e)
            elif typ == "black":
                c["flash_b"] = max(c["flash_b"], a * e)
            elif typ == "rgb":
                c["rgb"] = max(c["rgb"], h.get("px", 18) * a * e)
            elif typ == "glitch":
                c["glitch"] = max(c["glitch"], a * e)
            elif typ == "invert":
                c["inv"] = True
            elif typ == "exposure":
                c["expo"] *= 1 + a * e
            elif typ == "flicker":
                c["expo"] *= (1 + 0.9 * a * e) if k % 2 == 0 else (1 - 0.55 * a * e)
            elif typ == "zoom_in":
                c["zoom"] *= 1 + h.get("scale", 0.8) * a * e
                c["zoom_blur"] = max(c["zoom_blur"], 0.35 * a * e)
            elif typ == "zoom_out":
                c["zoom"] *= max(0.55, 1 - 0.45 * a * e)
                c["zoom_blur"] = max(c["zoom_blur"], 0.25 * a * e)
            elif typ == "whip":
                d = 1 if h.get("dir", 1) > 0 else -1
                ax = "dy" if h.get("axis") == "y" else "dx"   # axis "y": vertical swipe
                c[ax] += d * (-1 if t < h["t"] else 1) * (self.H if ax == "dy" else self.W) * h.get("dist", 1.0) * e * a
                c["blur_len"] = max(c["blur_len"], 160 * a * e)
            elif typ == "bounce":    # damped-spring drop-in: starts displaced, overshoots, settles
                x = max(0.0, t - h["t"])
                off = h.get("px", 0.25 * self.H) * a * math.exp(-h.get("damp", 7.0) * x) * math.cos(2 * math.pi * h.get("freq", 3.0) * x)
                c["dx" if h.get("axis") == "x" else "dy"] += off * (1 if h.get("dir", 1) > 0 else -1)
                c["blur_len"] = max(c["blur_len"], abs(off) * 0.3)
            elif typ == "stretch":   # vertical stretch (amt > 0) or squash (amt -1 collapses to a line)
                c["sy"] *= max(0.02, 1 + a * e)
            elif typ == "defocus":   # lens defocus, e.g. a focus pull into a new shot
                c["defocus"] = max(c["defocus"], h.get("px", 14) * a * e)
            elif typ == "focus":     # focus-hunting cut: rack soft into the cut, then hunt (sharp, soft, sharp)
                x = t - h["t"]
                if x < 0:
                    v = (1 + x / max(h.get("att", 0.2), 1e-3)) ** 2
                else:
                    u = min(1.0, x / max(h.get("dur", 0.45), 1e-3))
                    v = (1 - u) * abs(math.cos(1.5 * math.pi * u))
                c["defocus"] = max(c["defocus"], h.get("px", 16) * a * v)
                c["zoom"] *= 1 + 0.025 * a * v   # focus breathing: the frame grows a touch as it goes soft
            elif typ == "zoomcut":   # zoom cut: push into the cut, the next shot lands close and eases back
                c["zoom"] *= 1 + h.get("scale", 0.12) * a * e
                c["zoom_blur"] = max(c["zoom_blur"], 0.12 * a * e)
            elif typ == "edges":     # neon outline flash; the outline grows as it fades
                c["edges"] = max(c["edges"], a * e)
                c["edges_color"], c["edges_grow"] = h.get("color", (255, 230, 0)), 1 + h.get("grow", 0.45) * (1 - e)
            elif typ == "rays":      # light rays streaking out from the bright edges
                c["rays"] = max(c["rays"], a * e)
                c["rays_h"] = h
            elif typ == "halftone":  # print-dot flash
                c["halftone"] = max(c["halftone"], a * e)
            elif typ == "desat":     # colour drains out (1 = black and white)
                c["desat"] = max(c["desat"], a * e)
            elif typ == "ripple":    # water ripple spreading from a point
                c["ripple"] = max(c["ripple"], h.get("px", 22) * a * e)
                c["ripple_h"] = h
            elif typ == "sweep":     # a band of light crossing the frame over the hit's duration
                c["sweep"] = (t - h["t"]) / max(h.get("dur", 0.6), 1e-3)
                c["sweep_h"] = h
            elif typ == "rim":       # glowing outline around the subject (needs the cut-out model)
                c["rim"] = max(c["rim"], a * e)
                c["rim_h"] = h
            elif typ == "jaws":      # jagged bars biting in from top and bottom
                c["jaws"] = max(c["jaws"], h.get("depth", 0.2) * a * e)
                c["jaws_h"] = h
            elif typ == "spin":
                c["rot"] += h.get("deg", 25) * a * e * (1 if t < h["t"] else -1)
                c["zoom"] *= 1 + 0.25 * e
                c["zoom_blur"] = max(c["zoom_blur"], 0.2 * a * e)
            elif typ == "blur":
                c["blur_len"] = max(c["blur_len"], h.get("px", 60) * a * e)
            elif typ == "bloom":
                c["bloom"] = max(c["bloom"], a * e)
            elif typ == "bulge":
                c["bulge"] += h.get("k", 0.6) * a * e
            elif typ == "rgb_radial":
                c["rgb_radial"] = max(c["rgb_radial"], h.get("px", 0.02) * a * e)
            elif typ == "echo":
                c["echo"] = max(c["echo"], a * e)
            elif typ == "vhs":
                c["vhs"] = max(c["vhs"], a * e)
            elif typ == "leak":
                c["leak"] = max(c["leak"], a * e)
            elif typ == "handheld":
                hx, hy, hr = fx.handheld(t, h.get("px", 14) * a * e, h.get("speed", 1.0))
                c["dx"] += hx
                c["dy"] += hy
                c["rot"] += hr
        return c

    def _warp(self, s, src, c):
        edge = s.get("edge", self.p.get("edge", "mirror"))   # mirror (motion tile) | blur | stretch
        fill = {"mirror": "reflect", "blur": "blur"}.get(edge, "replicate")
        layout = s.get("layout", "fill")
        if layout not in ("card", "fit"):
            return fx.camera(src, c["cx"], c["cy"], c["zoom"], c["rot"], c["dx"], c["dy"], self.W, self.H, fill=fill,
                             sy=c["sy"])
        # card: picture-in-picture over a treated copy of itself; fit: the whole frame over a blurred copy
        img = (fx.card(src, c["cx"], c["cy"], s.get("card_scale", 0.78), self.W, self.H, s.get("card_bg", "halftone"))
               if layout == "card" else fx.fit_with_blur_bg(src, self.W, self.H))
        if abs(c["zoom"] - 1) > 0.005 or c["dx"] or c["dy"] or c["rot"] or abs(c["sy"] - 1) > 0.005:
            img = fx.camera(img, 0.5, 0.5, c["zoom"], c["rot"], c["dx"], c["dy"], self.W, self.H, fill=fill, sy=c["sy"])
        return img

    # ------------------------------------------------------------ one shot's picture
    def _shot_image(self, i, t, k):
        s = self.p["shots"][i]
        u, src_t, _, speed = self._timing(s, t)
        rd = self._reader(i)
        P = float(s.get("stepped_fps") or s.get("posterize") or 0)   # choppy, stepped frame rate
        if P:
            src_t = s["src_in"] + math.floor((src_t - s["src_in"]) * P) / P
        jolt = {}
        for h in self.p["hits"] if not s.get("voice") else []:   # speech never stutters
            if h["type"] == "jolt":
                e = env(t, h)
                if e > 0:
                    jolt = fx.jolt_ops(k, h.get("amt", 1.0) * e, h.get("speed", 0.6), h.get("seed", 0))
        if jolt.get("time"):
            src_t = max(s["src_in"], src_t + jolt["time"] / rd.fps)

        # source motion blur proportional to playback speed
        mb = self.p.get("motion_blur", True)
        aspeed = abs(speed)
        if mb == "flow" and aspeed > 1.3:
            fr, fl = rd.motion(src_t)
            src = rd.flow.vector_blur(fr, fl * speed * rd.fps / self.fps, 0.5) if fl is not None else rd.get(src_t)
        elif mb and aspeed > 1.6:
            span = 0.5 / self.fps * speed
            n = int(min(6, 2 + aspeed))
            acc = None
            for j in range(n):
                f = rd.get(src_t - span + span * j / (n - 1)).astype(np.float32)
                acc = f if acc is None else acc + f
            src = (acc / n).astype(np.uint8)
        else:
            src = rd.get(src_t, blend=aspeed < 0.95)   # in-between frames only for slow motion

        c = self._camera(s, t, k, src_t, u, jolt)
        img = self._warp(s, src, c)
        # camera motion blur: average the warp over the shutter
        # interval whenever the camera itself moves fast (zoom chains, punches, shakes, spins)
        if self.p.get("camera_blur", True):
            dt = 0.5 / self.fps
            cp = self._camera(s, t - dt, k, src_t, u, jolt)
            move = (abs(math.log(c["zoom"] / cp["zoom"])) * self.W + abs(c["dx"] - cp["dx"]) +
                    abs(c["dy"] - cp["dy"]) + abs(c["rot"] - cp["rot"]) * self.W / 60 +
                    abs(math.log(c["sy"] / cp["sy"])) * self.H +
                    (abs(c["cx"] - cp["cx"]) + abs(c["cy"] - cp["cy"])) * self.W * c["zoom"])
            if move > 3:
                n = int(min(10, 3 + move / 6))
                acc = img.astype(np.float32)
                for j in range(1, n):
                    tj = t - dt * j / (n - 1)
                    acc += self._warp(s, src, self._camera(s, tj, k, src_t, u, jolt)).astype(np.float32)
                img = (acc / n).astype(np.uint8)

        if s.get("blur"):
            img = cv2.GaussianBlur(img, (0, 0), s["blur"])
            img = (img * s.get("dim", 1.0)).astype(np.uint8)
        if c["ripple"] > 0.5:
            rh = c["ripple_h"]
            img = fx.ripple(img, c["ripple"], t - rh["t"], rh.get("x", 0.5), rh.get("y", 0.5), rh.get("wavelength", 90))
        mask = self.mask(img, ("shot", i, k)) if c["rim"] > 0.01 else None
        if c["defocus"] > 0.5:
            img = fx.lens_blur(img, c["defocus"])
        if c["zoom_blur"] > 0.01:
            img = fx.zoom_blur(img, c["zoom_blur"])
        if c["blur_len"] > 3:
            img = fx.motion_blur(img, c["blur_len"], 0 if abs(c["dx"]) >= abs(c["dy"]) else 90)
        if abs(c["bulge"]) > 0.01:
            img = fx.bulge(img, c["bulge"])
        if c["glitch"] > 0.02:
            img = fx.glitch(img, c["glitch"], self.rng)
        if c["rgb"] > 0.5:
            img = fx.rgb_split(img, c["rgb"])
        if c["rgb_radial"] > 0.001:
            img = fx.rgb_radial(img, c["rgb_radial"])
        img = self.looks[s.get("look", self.p.get("look", "punchy"))](img)
        if c["edges"] > 0.01:
            img = fx.edge_glow(img, c["edges"], c["edges_color"], c["edges_grow"])
        if c["desat"] > 0.01:
            img = fx.desaturate(img, c["desat"])
        if c["halftone"] > 0.01:
            img = fx.halftone(img, c["halftone"])
        if c["rays"] > 0.01:
            img = fx.edge_rays(img, c["rays"], c["rays_h"].get("color", (255, 160, 40)), c["rays_h"].get("length", 0.35))
        if 0 <= c["sweep"] <= 1:
            sh = c["sweep_h"]
            img = fx.light_sweep(img, c["sweep"], sh.get("angle", 30), sh.get("width", 0.12),
                                 sh.get("color", (255, 255, 255)), sh.get("amt", 0.6))
        if c["dust"] > 0.01:
            img = fx.film_damage(img, c["dust"], k)
        if mask is not None:
            img = fx.rim_light(img, mask, c["rim"], c["rim_h"].get("color", (120, 200, 255)))
        if self.p.get("base_rgb", 0):
            img = fx.rgb_split(img, self.p["base_rgb"])
        if c["bloom"] > 0.01:
            img = fx.bloom(img, c["bloom"], c["bloom_threshold"])
        if c["leak"] > 0.01:
            img = fx.light_leak(img, c["leak"], t)
        if c["vhs"] > 0.01:
            img = fx.vhs(img, c["vhs"], k, self.rng)
        img = fx.exposure(img, c["expo"])
        if "color" in jolt:
            img = fx.tint(img, jolt["color"], jolt["color_amt"])
        if c["inv"]:
            img = 255 - img
        if c["jaws"] > 0.005:
            jh = c["jaws_h"]
            img = fx.jaws(img, c["jaws"], jh.get("teeth", 9), jh.get("tilt", 0.0), jh.get("opacity", 0.8))
        return img, c, src_t

    # ------------------------------------------------------------ full frame
    def frame(self, k):
        t = k / self.fps
        i = self._shot_at(t)
        s = self.p["shots"][i]
        img, c, src_t = self._shot_image(i, t, k)
        mix = s.get("mix", 0)
        if mix and i > 0 and t < s["out"][0] + mix:
            # cross-dissolve ("Mix" transition) from the previous shot, which keeps playing
            a = (t - s["out"][0]) / mix
            a = a * a * (3 - 2 * a)
            prev, _, _ = self._shot_image(i - 1, t, k)
            img = cv2.addWeighted(prev, 1 - a, img, a, 0)
        img = fx.flash(img, c["flash_w"])
        img = fx.flash(img, c["flash_b"], (0, 0, 0))
        if c["echo"] > 0.01:
            img = fx.echo(img, self.hist, c["echo"])
        self.hist = (self.hist + [img])[-6:]
        img = fx.letterbox(img, self.p.get("letterbox", 0))

        # a poster frame owns the screen: while one is up, no other text, image, caption or title is drawn
        poster = [tl for tl in self.texts if isinstance(tl, PosterLayer) and tl.s["t0"] <= t < tl.s["t1"]]
        for j, o in enumerate(self.overlays if not poster else []):
            if o["t0"] <= t < o["t1"]:
                img = fx.blend(img, self._overlay(j, o, t), o.get("blend", "screen"), o.get("opacity", 1.0))
        if self.caps is not None and s.get("captions", True) and not poster:
            cp = self.p["captions"]
            img = self.caps.overlay(img, src_t if cp.get("source_time", True) else t)
        ae = float(self.aenv[min(k, len(self.aenv) - 1)]) if len(self.aenv) else 0.0
        plate = img
        for tl in poster or self.texts:
            ft = tl.s.get("follow_track")
            if ft and ft["src"] == s["src"] and tl.s["t0"] <= t < tl.s["t1"]:   # text rides along with the subject
                x, y = self._to_out(s, c, float(np.interp(src_t, ft["t"], ft["x"])), float(np.interp(src_t, ft["t"], ft["y"])))
                tl.s["x"], tl.s["y"] = x + ft.get("dx", 0), y + ft.get("dy", -260)
            img = tl.draw(img, t, k, ae)
            if tl.s.get("behind") and tl.s["t0"] <= t < tl.s["t1"]:   # put the subject back in front of the text
                m = self.mask(plate, ("frame", k))
                if m is not None:
                    img = (img * (1 - m[..., None]) + plate * m[..., None]).astype(np.uint8)
        if self.title is not None and not poster:
            tt = self.p["title"]
            if tt.get("t0", 0) <= t < tt.get("t1", 3):
                img = _paste(img, self.title, self.W // 2, tt.get("y", 300))
        return img

    def _to_out(self, s, c, nx, ny):
        """Output pixel position of a normalised source point under the shot's current camera
        (zoom, framing, offsets; rotation ignored)."""
        info = self.infos[s["src"]]
        w, h = info["width"], info["height"]
        ar = self.W / self.H
        cw, ch = (h * ar, h) if w / h > ar else (w, w / ar)
        cw, ch = cw / c["zoom"], ch / c["zoom"]
        k = self.W / cw
        px = float(np.clip(c["cx"] * w, cw / 2, w - cw / 2)) if cw <= w else w / 2
        py = float(np.clip(c["cy"] * h, ch / 2, h - ch / 2)) if ch <= h else h / 2
        return self.W / 2 + (nx * w - px) * k + c["dx"], self.H / 2 + ((ny * h - py) * k + c["dy"]) * c["sy"]

    def _overlay(self, j, o, t):
        """Frame of a user-supplied overlay clip (light leak, particles, dust...) at output time t,
        covering the frame (optionally rotated and scaled), tinted if `tint` [r,g,b] is set."""
        if j not in self.ov_readers:
            info = probe(o["path"])
            sc = min(1.0, 1080 / max(info["width"], info["height"]))
            w, h = int(info["width"] * sc) // 2 * 2, int(info["height"] * sc) // 2 * 2
            self.ov_readers[j] = SegmentReader(o["path"], o.get("src_in", 0.0),
                                               (o["t1"] - o["t0"]) * o.get("speed", 1.0) + 0.5, w, h, info["fps"])
        rd = self.ov_readers[j]
        f = rd.get(o.get("src_in", 0.0) + (t - o["t0"]) * o.get("speed", 1.0))
        f = fx.camera(f, 0.5, 0.5, o.get("scale", 1.0), o.get("rot", 0.0), out_w=self.W, out_h=self.H, fill="replicate")
        if o.get("key"):    # chroma key: the key colour becomes the frame underneath (black, for screen blends)
            kc = np.array(o["key"][::-1], np.float32)
            far = np.linalg.norm(f.astype(np.float32) - kc, axis=2) > o.get("key_tol", 90)
            f = f * far[..., None].astype(np.uint8)
        if o.get("tint"):   # map brightness onto one colour
            lum = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)[..., None] / 255
            f = (lum * np.array(o["tint"][::-1], np.float32)).astype(np.uint8)
        return f

    def run(self, out_path):
        n = int(round(self.p["duration"] * self.fps))
        enc = Encoder(out_path, self.W, self.H, self.fps, audio=self.p.get("audio"), crf=self.p.get("crf", 17))
        try:
            for k in range(n):
                enc.write(self.frame(k))
                if k % 60 == 0:
                    print(f"  frame {k}/{n}", flush=True)
        except BaseException:
            enc.proc.kill()   # don't leave ffmpeg waiting on a half-written file
            raise
        finally:
            for r in list(self.readers.values()) + list(self.ov_readers.values()):
                r.close()
        enc.close()
        return out_path
