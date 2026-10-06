"""Word-by-word captions rendered in-frame (no libass needed). Two styles:
  "clip"  clip-page captions: ALL CAPS, heavy font, white + thick black stroke, active/keyword word in yellow,
          1-3 words per card, pop-in scale 80->110->100% over ~5 frames, at ~65% screen height.
  "edit"  subtitles for edits: one small line (up to ~6 words), each word fading up as it is spoken,
          key words in red, a soft shadow, fading out at the end of the line."""
import os
import re
import unicodedata
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import shaping
from .moments import POLAR

_HERE = os.path.dirname(os.path.abspath(__file__))
_FONT_DIRS = [os.path.join(os.environ.get("CLIPIT_HOME", os.path.expanduser("~/.clipit")), "fonts"),
              os.path.join(_HERE, "..", "fonts"), os.path.expanduser("~/Library/Fonts"), "/Library/Fonts",
              "/System/Library/Fonts/Supplemental", "/System/Library/Fonts", "/usr/share/fonts/truetype/dejavu",
              os.path.expanduser("~/.local/share/fonts"), "/usr/share/fonts/TTF", "C:/Windows/Fonts"]
FONTS = {
    # heavy geometric sans for captions
    "heavy": ["Montserrat-Black.ttf", "TheBoldFont.ttf", "Arial Black.ttf", "ariblk.ttf", "DejaVuSans-Bold.ttf"],
    # tall condensed display face for slam titles
    "condensed": ["Anton-Regular.ttf", "BebasNeue-Regular.ttf", "Impact.ttf", "impact.ttf",
                  "DejaVuSansCondensed-Bold.ttf", "DejaVuSans-Bold.ttf"],
    "bold": ["Montserrat-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"],
    "regular": ["Montserrat-Regular.ttf", "Arial.ttf", "arial.ttf", "DejaVuSans.ttf"],
    # poster frames: heavy condensed headline, heavy wide wordmark, mono labels
    "poster": ["Anton-Regular.ttf", "BebasNeue-Regular.ttf", "Impact.ttf", "impact.ttf",
               "DejaVuSansCondensed-Bold.ttf", "DejaVuSans-Bold.ttf"],
    "wide": ["ArchivoBlack-Regular.ttf", "Arial Black.ttf", "ariblk.ttf", "Montserrat-Black.ttf", "DejaVuSans-Bold.ttf"],
    "mono": ["SpaceMono-Bold.ttf", "Courier New Bold.ttf", "courbd.ttf", "DejaVuSansMono-Bold.ttf"],
    # thin handwritten caption face for quiet "pov:" style intros
    "hand": ["AmaticSC-Bold.ttf", "Chalkboard.ttc", "Bradley Hand Bold.ttf", "DejaVuSans.ttf"],
    # non-Latin scripts (Hindi, Arabic, ...): fonts that actually contain them, instead of empty boxes
    "unicode": ["NotoSansDevanagari-Bold.ttf", "Kohinoor.ttc", "Arial Unicode.ttf", "NotoSans-Bold.ttf",
                "DejaVuSans-Bold.ttf"],
}


def font_path(name="heavy"):
    """Resolve a font alias (heavy | condensed | bold | regular | poster | wide | mono | hand) or a .ttf/.otf path.
    Drop your own fonts (e.g. Montserrat Black, Anton) into the repo's fonts/ folder."""
    if name and os.path.exists(name):
        return name
    for fn in FONTS.get(name, FONTS["heavy"]):
        for d in _FONT_DIRS:
            p = os.path.join(d, fn)
            if os.path.exists(p):
                return p
    raise FileNotFoundError(f"no font found for '{name}'; put a .ttf in fonts/")


YELLOW = (255, 229, 0)
GREEN = (60, 255, 90)
WHITE = (255, 255, 255)


def _clean(w):
    """Upper-case word without stray punctuation; vowel signs and other combining marks (Hindi matras) stay."""
    return "".join(ch for ch in w if ch.isalnum() or ch in "'%$!?&-" or unicodedata.category(ch)[0] == "M").upper()


def group_words(words, max_words=3, max_chars=16, max_gap=0.35):
    groups, cur = [], []
    for w in words:
        t = _clean(w["w"])
        if not t:
            continue
        item = dict(w, t=t)
        if cur and (len(cur) >= max_words or sum(len(x["t"]) + 1 for x in cur) + len(t) > max_chars
                    or w["s"] - cur[-1]["e"] > max_gap or cur[-1]["w"].endswith((".", "?", "!", ","))):
            groups.append(cur)
            cur = []
        cur.append(item)
    if cur:
        groups.append(cur)
    for g in groups:
        for x in g:
            x["key"] = POLAR.get(x["t"].lower().strip("!?."), 0) >= 2 or bool(re.search(r"\d", x["t"]))
    return groups


class CaptionRenderer:
    def __init__(self, words, width=1080, height=1920, size=86, y_frac=0.66, stroke=9, style="clip"):
        self.style = style
        self.face = "unicode" if any(ord(ch) > 0x24F for w in words for ch in w["w"]) else None
        if style == "edit":
            self.groups = group_words(words, max_words=6, max_chars=32, max_gap=0.6)
            size = min(size, 46)
        else:
            self.groups = group_words(words)
        self.W, self.H = width, height
        self.face = self.face or ("bold" if style == "edit" else "heavy")
        # joined scripts (Hindi...) are shaped with HarfBuzz when installed (install.sh --with-hindi)
        self.shape = shaping.available() and any(shaping.needs(w["w"]) for w in words)
        self.font = ImageFont.truetype(font_path(self.face), size)
        self.size = size
        self.y = int(height * y_frac)
        self.stroke = stroke
        self.cache = {}
        # each card holds until the next starts (max +0.5s)
        self.cards = []
        for i, g in enumerate(self.groups):
            s, e = g[0]["s"], g[-1]["e"]
            nxt = self.groups[i + 1][0]["s"] if i + 1 < len(self.groups) else e + 0.5
            self.cards.append((s, min(nxt, e + 0.5), g))

    def _width(self, text, font):
        return shaping.text_rgba(text, font.path, font.size, (255, 255, 255))[1] if self.shape else font.getlength(text)

    def _text(self, img, d, xy, text, font, fill, stroke=0, stroke_fill=(0, 0, 0)):
        """Draw a word: Pillow's own layout, or shaped glyphs for joined scripts."""
        if not self.shape:
            d.text(xy, text, font=font, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
            return
        arr, _ = shaping.text_rgba(text, font.path, font.size, fill[:3], stroke, stroke_fill[:3])
        if len(fill) > 3:
            arr[..., 3] = (arr[..., 3].astype(np.float32) * fill[3] / 255).astype(np.uint8)
        pad = stroke + 4
        x, y = int(xy[0]) - pad, int(xy[1] + font.getmetrics()[0] - int(font.size * 1.15) - pad)
        x0, y0 = max(0, x), max(0, y)
        crop = arr[y0 - y:y0 - y + img.height - y0, x0 - x:x0 - x + img.width - x0]
        if crop.size:
            img.alpha_composite(Image.fromarray(crop), (x0, y0))

    def _render(self, gi, active):
        key = (gi, active)
        if key in self.cache:
            return self.cache[key]
        g = self.cards[gi][2]
        space = self.size * 0.28
        widths = [self._width(x["t"], self.font) for x in g]
        total = sum(widths) + space * (len(g) - 1)
        scale = min(1.0, (self.W - 120) / total)
        font = self.font if scale >= 1 else ImageFont.truetype(font_path(self.face), int(self.size * scale))
        widths = [self._width(x["t"], font) for x in g]
        total = sum(widths) + space * scale * (len(g) - 1)
        pad = self.stroke * 2 + 10
        h = int(font.size * 1.35) + pad * 2
        img = Image.new("RGBA", (int(total) + pad * 2, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        x = pad
        for i, it in enumerate(g):
            col = YELLOW if i == active else GREEN if it["key"] else WHITE
            # drop shadow then stroked text
            self._text(img, d, (x + 5, pad + 7), it["t"], font, (0, 0, 0, 150), self.stroke, (0, 0, 0, 150))
            self._text(img, d, (x, pad), it["t"], font, col, self.stroke, (0, 0, 0))
            x += widths[i] + space * scale
        arr = np.array(img)
        self.cache[key] = arr
        return arr

    def _render_edit(self, gi, t):
        """The line with each word faded up as it is spoken (alphas rounded so frames can be cached)."""
        s, e, g = self.cards[gi]
        out_a = min(1.0, (e - t) / 0.15)
        alphas = tuple(round(min(1.0, max(0.0, (t - it["s"]) / 0.15)) * out_a, 1) for it in g)
        key = (gi, alphas)
        if key in self.cache:
            return self.cache[key]
        f, space = self.font, self.size * 0.3
        words = [it["w"].strip() for it in g]
        widths = [self._width(w, f) for w in words]
        total = sum(widths) + space * (len(g) - 1)
        if total > self.W - 120:
            f = ImageFont.truetype(font_path(self.face), int(self.size * (self.W - 120) / total))
            widths = [self._width(w, f) for w in words]
            total = sum(widths) + space * (len(g) - 1)
        pad = 24
        img = Image.new("RGBA", (int(total) + 2 * pad, int(f.size * 1.4) + 2 * pad), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        x = pad
        for w, wd, it, a in zip(words, widths, g, alphas):
            if a > 0:
                col = (235, 40, 40) if it["key"] else (245, 245, 245)
                self._text(img, d, (x + 2, pad + 3), w, f, (0, 0, 0, int(150 * a)))
                self._text(img, d, (x, pad), w, f, col + (int(255 * a),))
            x += wd + space
        arr = np.array(img)
        self.cache[key] = arr
        return arr

    def overlay(self, frame, t):
        """t = time on the words' clock (source speech time, or output time; see plan "source_time")."""
        for gi, (s, e, g) in enumerate(self.cards):
            if s <= t < e and self.style == "edit":
                return _paste(frame, self._render_edit(gi, t), self.W // 2, self.y)
            if s <= t < e:
                active = 0
                for k, it in enumerate(g):
                    if it["s"] <= t:
                        active = k
                img = self._render(gi, active)
                age = t - s
                # pop: 0.8 -> 1.1 (2f) -> 1.0 (4f)
                if age < 0.066:
                    sc = 0.8 + 0.3 * age / 0.066
                elif age < 0.2:
                    sc = 1.1 - 0.1 * (age - 0.066) / 0.134
                else:
                    sc = 1.0
                return _paste(frame, img, self.W // 2, self.y, sc)
        return frame


def _paste(frame, rgba, cx, cy, scale=1.0):
    if abs(scale - 1) > 0.01:
        rgba = cv2.resize(rgba, (max(1, int(rgba.shape[1] * scale)), max(1, int(rgba.shape[0] * scale))))
    h, w = rgba.shape[:2]
    x0, y0 = cx - w // 2, cy - h // 2
    fx0, fy0 = max(0, x0), max(0, y0)
    fx1, fy1 = min(frame.shape[1], x0 + w), min(frame.shape[0], y0 + h)
    if fx1 <= fx0 or fy1 <= fy0:
        return frame
    sub = rgba[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0]
    a = sub[..., 3:4].astype(np.float32) / 255
    rgb = sub[..., 2::-1].astype(np.float32)  # RGBA -> BGR
    roi = frame[fy0:fy1, fx0:fx1].astype(np.float32)
    frame = frame.copy()
    frame[fy0:fy1, fx0:fx1] = (roi * (1 - a) + rgb * a).astype(np.uint8)
    return frame


def title_card(text, width=1080, size=64):
    """Static hook/title text (top of frame) as an RGBA array."""
    font = ImageFont.truetype(font_path(), size)
    lines, cur = [], ""
    for w in text.upper().split():
        if font.getlength(cur + " " + w) > width - 140 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    lh = int(size * 1.25)
    img = Image.new("RGBA", (width, lh * len(lines) + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        x = (width - font.getlength(ln)) / 2
        d.text((x, 20 + i * lh), ln, font=font, fill=WHITE, stroke_width=7, stroke_fill=(0, 0, 0))
    return np.array(img)
