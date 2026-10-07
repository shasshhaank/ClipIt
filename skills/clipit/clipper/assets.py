"""Generated overlay assets: subscribe buttons, cursor, comment cards, circular logo cut-outs.
Everything is drawn locally (PIL/OpenCV); no stock packs needed."""
import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .captions import font_path


def subscribe_buttons(folder, label="SUBSCRIBE", done="SUBSCRIBED", color=(230, 15, 25)):
    os.makedirs(folder, exist_ok=True)
    f = ImageFont.truetype(font_path("bold"), 62)

    def pill(text, bg, fg, path, w, bell=False):
        h = 140
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=bg)
        x = (w - f.getlength(text)) / 2 + (30 if bell else 0)
        d.text((x, h / 2), text, font=f, fill=fg, anchor="lm")
        if bell:  # simple bell glyph
            bx, by = x - 70, h / 2
            d.pieslice((bx - 26, by - 34, bx + 26, by + 18), 180, 360, fill=fg)
            d.rectangle((bx - 26, by - 8, bx + 26, by + 16), fill=fg)
            d.polygon([(bx - 34, by + 16), (bx + 34, by + 16), (bx + 26, by + 6), (bx - 26, by + 6)], fill=fg)
            d.ellipse((bx - 9, by + 16, bx + 9, by + 32), fill=fg)
        im.save(path)
        return path

    a = pill(label, tuple(color) + (255,), (255, 255, 255, 255), os.path.join(folder, "subscribe.png"),
             max(560, int(f.getlength(label)) + 140))
    b = pill(done, (60, 60, 60, 255), (235, 235, 235, 255), os.path.join(folder, "subscribed.png"),
             max(640, int(f.getlength(done)) + 220), bell=True)
    return a, b


def cursor(folder):
    os.makedirs(folder, exist_ok=True)
    im = Image.new("RGBA", (140, 200), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(10, 10), (10, 160), (48, 124), (76, 186), (104, 174), (76, 114), (126, 114)], fill=(0, 0, 0, 255))
    d.polygon([(22, 36), (22, 132), (50, 106), (80, 168), (90, 163), (62, 102), (98, 102)], fill=(255, 255, 255, 255))
    p = os.path.join(folder, "cursor.png")
    im.save(p)
    return p


def circle_logo(src, dst, size=900):
    """Crop an image to a circle with an alpha channel (channel avatars, round logos)."""
    a = cv2.imread(src, cv2.IMREAD_UNCHANGED)
    h, w = a.shape[:2]
    s = min(h, w)
    a = a[(h - s) // 2:(h - s) // 2 + s, (w - s) // 2:(w - s) // 2 + s]
    a = cv2.resize(a, (size, size), interpolation=cv2.INTER_AREA)
    if a.shape[2] == 3:
        a = np.dstack([a, np.full((size, size), 255, np.uint8)])
    m = np.zeros((size, size), np.uint8)
    cv2.circle(m, (size // 2, size // 2), size // 2 - 1, 255, -1, cv2.LINE_AA)
    a[..., 3] = np.minimum(a[..., 3], m)
    cv2.imwrite(dst, a)
    return dst


def emoji_png(ch, size, dst):
    """A colour emoji as a PNG (Apple Color Emoji on macOS, Noto Color Emoji on Linux); None without such a font."""
    for path in ("/System/Library/Fonts/Apple Color Emoji.ttc", "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
                 "/usr/share/fonts/noto/NotoColorEmoji.ttf"):
        for fs in (160, 109):   # colour emoji fonts only render at their built-in sizes
            try:
                f = ImageFont.truetype(path, fs)
            except OSError:
                continue
            im = Image.new("RGBA", (fs * 2, fs * 2))
            ImageDraw.Draw(im).text((fs // 4, fs // 4), ch, font=f, embedded_color=True)
            if im.getbbox():
                im = im.crop(im.getbbox())
                k = size / max(im.size)
                im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS).save(dst)
                return dst
    print(f"  ! no colour emoji font: skipping {ch!r} (use an image instead)")
    return None


def mask_handle(h):
    """Privacy: '@someone123' -> '@so•••••' (show only the first two characters)."""
    h = h.lstrip("@")
    return "@" + h[:2] + "•" * max(3, min(6, len(h) - 2))


AVATAR_COLORS = [(214, 92, 92), (92, 150, 214), (110, 190, 120), (200, 160, 70), (160, 110, 200)]


def _heart(d, x, y, s, fill):
    """Heart drawn as shapes (a font glyph can render as an empty box)."""
    r = s / 4
    d.ellipse((x, y, x + 2 * r, y + 2 * r), fill=fill)
    d.ellipse((x + 2 * r, y, x + 4 * r, y + 2 * r), fill=fill)
    d.polygon([(x + 0.3, y + 1.4 * r), (x + 4 * r - 0.3, y + 1.4 * r), (x + 2 * r, y + 4 * r)], fill=fill)


def comment_card(text, handle, dst, likes=None, width=920, idx=0):
    """Dark comment card. Use ONLY real comments supplied by the user.
    Handles are always masked: commenters are private people."""
    fb = ImageFont.truetype(font_path("bold"), 34)
    fr = ImageFont.truetype(font_path("regular"), 40)
    words, lines, cur = text.split(), [], ""
    for w in words:
        if fr.getlength(cur + " " + w) > width - 160 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    h = 120 + 50 * len(lines) + (40 if likes else 0)
    im = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, width - 1, h - 1), 28, fill=(24, 24, 24, 240))
    d.ellipse((30, 30, 100, 100), fill=AVATAR_COLORS[idx % len(AVATAR_COLORS)])
    d.text((65, 65), (handle.lstrip("@")[:1] or "?").upper(), font=fb, fill="white", anchor="mm")
    d.text((125, 34), mask_handle(handle), font=fb, fill=(170, 170, 170))
    for j, ln in enumerate(lines):
        d.text((125, 84 + j * 50), ln, font=fr, fill="white")
    if likes:
        y = 84 + len(lines) * 50 + 4
        _heart(d, 125, y + 7, 28, (170, 170, 170))
        d.text((164, y), str(likes), font=fb, fill=(170, 170, 170))
    im.save(dst)
    return dst
