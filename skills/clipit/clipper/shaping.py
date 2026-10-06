"""Correct rendering for joined scripts (Hindi and other Indic scripts, Arabic): Pillow alone can't form their
conjuncts and vowel signs without the libraqm system library, so text is shaped with HarfBuzz and drawn glyph by
glyph with FreeType. Both come from small pip packages that `install.sh --with-hindi` adds; without them,
captions fall back to Pillow's basic layout."""
import importlib.util
import re
import numpy as np

COMPLEX = re.compile("[\u0590-\u08FF\u0900-\u0DFF\u0F00-\u109F\u1780-\u17FF]")   # Hebrew/Arabic, Indic, Tibetan, Khmer


def available():
    return all(importlib.util.find_spec(m) for m in ("uharfbuzz", "freetype"))


def needs(text):
    return bool(COMPLEX.search(text))


def text_rgba(text, font_path, size, color, stroke=0, stroke_color=(0, 0, 0)):
    """RGBA image of `text`, shaped. Returns (array, advance width in px). The baseline sits at 0.8 of the height."""
    import cv2
    import freetype
    import uharfbuzz as hb
    index = 0
    blob = hb.Blob.from_file_path(font_path)
    font = hb.Font(hb.Face(blob, index))
    font.scale = (size * 64, size * 64)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {})
    ft = freetype.Face(font_path, index)
    ft.set_char_size(size * 64)
    pad = stroke + 4
    h = int(size * 1.5) + 2 * pad
    base = int(size * 1.15) + pad
    width = int(sum(p.x_advance for p in buf.glyph_positions) / 64) + 2 * pad + size
    alpha = np.zeros((h, width), np.float32)
    x = pad
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        ft.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER)
        bm = ft.glyph.bitmap
        if bm.width and bm.rows:
            g = np.array(bm.buffer, np.uint8).reshape(bm.rows, bm.pitch)[:, :bm.width].astype(np.float32) / 255
            gx = int(round(x + pos.x_offset / 64 + ft.glyph.bitmap_left))
            gy = int(round(base - pos.y_offset / 64 - ft.glyph.bitmap_top))
            y0, x0 = max(0, gy), max(0, gx)
            y1, x1 = min(h, gy + g.shape[0]), min(width, gx + g.shape[1])
            if y1 > y0 and x1 > x0:
                alpha[y0:y1, x0:x1] = np.maximum(alpha[y0:y1, x0:x1], g[y0 - gy:y1 - gy, x0 - gx:x1 - gx])
        x += pos.x_advance / 64
    out = np.zeros((h, width, 4), np.uint8)
    if stroke:   # outline: the dilated shape in the stroke colour under the fill
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * stroke + 1, 2 * stroke + 1))
        outline = cv2.dilate(alpha, k)
        out[..., :3] = stroke_color
        out[..., 3] = (outline * 255).astype(np.uint8)
    a = alpha[..., None]
    out[..., :3] = (np.array(color[:3], np.float32) * a + out[..., :3] * (1 - a)).astype(np.uint8)
    out[..., 3] = np.maximum(out[..., 3], (alpha * 255).astype(np.uint8))
    return out, int(x - pad)
