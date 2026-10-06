"""Story edits from a JSON spec, timed in BEATS relative to the music drop.

A story edit is a narrative fan edit: setup text over slow mono footage -> blackout -> drop ->
beat-cut hype -> end card. Every time field ("from", "to", "at") is a beat index relative to the
drop (0 = drop, -4 = one bar before, 8 = two bars after). Fractions are allowed (e.g. -19.5).
See docs/STORY_SPEC.md for every field.
"""
import json
import os
import re

import numpy as np

from . import assets
from . import audio as A
from .beats import analyze
from .media import load_audio, probe, save_audio
from .moments import looks_like_slideshow
from .planner import _track, lv
from .render import remap_table

SPEEDS = {
    "normal": {"type": "const", "speed": 1.0},
    "slow": {"type": "const", "speed": 0.5},
    "slower": {"type": "const", "speed": 0.3},
    # pro velocity edits rarely go past 2x: real time, a short kick, then deep slow-mo
    "ramp": {"type": "ramp", "hi": 1.8, "lo": 0.22, "k": 2.2},     # velocity: fast-slow-fast
    "quick": {"type": "ease_in", "hi": 1.6, "lo": 0.35},            # a kick that slides into slow-mo
    "push": {"type": "ease_out", "lo": 0.5, "hi": 1.8},             # slow into fast (into a cut)
    "settle": {"type": "ease_in", "hi": 1.0, "lo": 0.3, "k": 2.0},  # real time decelerating to 30%: the workhorse
    "smooth": {"type": "ramp", "hi": 6.0, "lo": 0.15, "k": 1.6},    # V curve: 10x-0.1x-10x feel
    "decel": {"type": "decel", "hi": 8.0, "lo": 1.0, "k": 3.0},     # 10x -> 1x, cubic out
    "boomerang": {"type": "boomerang", "hi": 4.0, "lo": 0.4, "k": 3.0},  # forward (decelerating) then back
    "reverse": {"type": "reverse", "hi": 3.0, "lo": 0.6, "k": 2.0},      # plays backwards, landing slow
    "hold": {"type": "const", "speed": 0.08},                       # near-freeze, for poster frames
    "freeze": {"type": "const", "speed": 0.001},                    # a freeze frame
}
TEXT_STYLES = {
    "title": dict(font="condensed", size=100, stroke=0, color=(245, 245, 245), accent=(235, 30, 40),
                  glow=0.9, glow_radius=20, hum=0.35, anim="pop", y=1420),
    "slam": dict(font="condensed", size=150, stroke=6, color=(255, 255, 255), accent=(235, 25, 35),
                 glow=1.1, glow_radius=26, hum=0.45, anim="slam", y=900),
    "type": dict(font="condensed", size=90, stroke=0, color=(240, 240, 240), accent=(235, 30, 40),
                 glow=0.7, glow_radius=18, hum=0.3, anim="type", type_dur=0.45, y=1420),
    # full-frame poster typography (render.PosterLayer); rare by design, see docs/PLAYBOOK.md
    "poster": dict(kind="poster", font="poster", color=(240, 236, 224), layout="stack", anim="cut", y=960),
}


class Beats:
    def __init__(self, music, drop_hint=None, bars_before=5, bars_after=7):
        ma = analyze(music)
        self.ma = ma
        if drop_hint in (None, "auto"):
            drop = ma["drop"]
        else:  # user-given drop time: snap to the nearest detected beat if close, else trust the hint
            near = min(ma["beats"] or [drop_hint], key=lambda b: abs(b - drop_hint))
            drop = near if abs(near - drop_hint) < 0.15 else float(drop_hint)
        self.B = 60.0 / ma["tempo"]
        # constant-tempo grid anchored on the drop, snapped to detected beats where they agree
        # (robust to sparse intros / breakdowns where the tracker drops beats)
        det = np.array(ma["beats"]) if ma["beats"] else np.array([drop])
        n0 = bars_before * 4 + 8
        grid = []
        for n in range(-n0, bars_after * 4 + 12):
            g = drop + n * self.B
            j = int(np.argmin(np.abs(det - g)))
            grid.append(float(det[j]) if abs(det[j] - g) < 0.07 else g)
        self.di = n0
        self.start_idx = self.di - bars_before * 4
        self.M0 = max(0.0, grid[self.start_idx])
        self.beats = [b - self.M0 for b in grid]
        self.end_beat = bars_after * 4

    def __call__(self, n):
        """Output time (s) of beat n relative to the drop; fractional beats interpolate."""
        lo = int(np.floor(n))
        f = n - lo
        i = self.di + lo
        a = self.beats[max(0, min(i, len(self.beats) - 1))]
        b = self.beats[max(0, min(i + 1, len(self.beats) - 1))]
        return max(0.0, a + (b - a) * f)


_SCENES = {}


def scene_cuts(src, workdir):
    """Scene-cut times for a source (PySceneDetect), cached in the work dir."""
    if src in _SCENES:
        return _SCENES[src]
    cache = os.path.join(workdir, "scenes_" + os.path.basename(src) + ".json")
    if os.path.exists(cache):
        cuts = json.load(open(cache))
    else:
        from scenedetect import detect, ContentDetector
        print(f"  detecting scene cuts in {os.path.basename(src)} (cached afterwards)...")
        cuts = [b.get_seconds() for _, b in detect(src, ContentDetector(threshold=27.0), show_progress=False)][:-1]
        json.dump(cuts, open(cache, "w"))
    _SCENES[src] = cuts
    return cuts


def _fit(src, peak, span, dur, workdir, guard=True):
    """Centre the source window on `peak`, but keep it inside the scene that contains the peak,
    so speed-ups never spill across a cut into unrelated footage."""
    lo, hi = 0.0, dur
    if guard:
        for c in scene_cuts(src, workdir):
            if c <= peak:
                lo = c + 0.04
            else:
                hi = c - 0.04
                break
    if hi - lo < span:
        print(f"  ! {os.path.basename(src)} @ {peak:.2f}s: scene is {hi - lo:.2f}s but the shot needs "
              f"{span:.2f}s of source - it will cross a cut. Use a slower speed, a shorter shot or another peak.")
        return float(np.clip(peak - span / 2, 0, max(0, dur - span - 0.1)))
    return float(np.clip(peak - span / 2, lo, hi - span))


def reading_time(text, anim=None, type_dur=0.0, wps=3.0, lead=0.4, min_on=1.2):
    """Seconds an average viewer needs to read a short bold caption: a 0.4 s glance-in plus
    ~3 words/s, never less than 1.2 s; typewriter text also needs its typing time."""
    words = len(re.findall(r"[A-Za-z0-9'%$]+", text))
    need = max(min_on, lead + words / wps)
    return need + (type_dur if anim == "type" else 0.0)


def readable(texts, end, opts=None):
    """Make every text card stay up long enough to read. Cards that are too short are extended
    (up to the next card in the same screen area); anything that still can't be read is reported.
    Also warns when there is simply too much text for the runtime."""
    opts = opts or {}
    if opts.get("off"):
        return
    wps, min_on = opts.get("wps", 3.0), opts.get("min_on", 1.2)
    for tx in texts:
        need = reading_time(tx["text"], tx.get("anim"), tx.get("type_dur", 0.0), wps, min_on=min_on)
        shown = tx["t1"] - tx["t0"]
        if shown >= need - 1e-3:
            continue
        cap = end
        for o in texts:   # don't run into the next card in the same spot, or any poster (it owns the frame)
            if o is not tx and o["t0"] > tx["t0"] + 1e-3 and (o.get("kind") == "poster"
                                                               or abs(o.get("y", 960) - tx.get("y", 960)) < 140):
                cap = min(cap, o["t0"])
        new_t1 = min(tx["t0"] + need, cap)
        if new_t1 > tx["t1"]:
            tx["t1"] = new_t1
        if tx["t1"] - tx["t0"] < need - 0.05:
            print(f"  ! text '{tx['text']}' is on screen {tx['t1'] - tx['t0']:.2f}s but needs ~{need:.1f}s to read. "
                  f"Cut words, merge it with the next card, or give it a calmer moment.")
        else:
            print(f"  text '{tx['text']}' held to {tx['t1'] - tx['t0']:.2f}s so it can be read")
    words = sum(len(tx["text"].split()) for tx in texts)
    if end > 0 and words / end > 1.6:
        print(f"  ! {words} words of on-screen text in {end:.0f}s - that's a lot. Aim for under ~1.5 words/s; "
              f"let the footage and the music carry the rest.")


def build(spec, workdir, base_dir="."):
    P = lambda p: p if os.path.isabs(p) else os.path.join(base_dir, p)
    os.makedirs(workdir, exist_ok=True)
    m = spec["music"]
    bt = Beats(P(m["path"]), m.get("drop", "auto"), m.get("bars_before", 5), m.get("bars_after", 7))
    B = bt.B
    first = min(s["from"] for s in spec["shots"])
    last = spec.get("end", bt.end_beat)
    END = bt(last)
    DROP = bt(0)
    until = lambda b: END if b >= last else bt(b)   # end time of anything that runs to `b` (or to the end)
    shots, hits, texts, images = [], [], [], []
    voices, cap_words = [], []   # soundbites that play their own speech, and their captions (output time)

    # ------------------------------------------------------------ shots
    for s in sorted(spec["shots"], key=lambda x: x["from"]):
        o0 = 0.0 if s["from"] == first else bt(s["from"])
        o1 = until(s["to"])
        sp = s.get("speed", "normal")
        prof = dict(SPEEDS[sp]) if isinstance(sp, str) else ({"type": "const", "speed": sp}
                                                             if isinstance(sp, (int, float)) else sp)
        _, _, mean, _ = remap_table(prof)
        span = (o1 - o0) * mean
        src = P(s["src"])
        dur = probe(src)["duration"]
        peak = s.get("peak", dur / 2)
        src_in = _fit(src, peak, span, dur, workdir, spec.get("guard_cuts", True))
        if "start" in s:   # exact source second, e.g. where a soundbite begins
            src_in = float(np.clip(s["start"], 0, max(0, dur - span)))
        shot = {"src": src, "out": [o0, o1], "src_in": src_in, "src_span": span, "profile": prof,
                "zoom": s.get("zoom", [1.0, 1.12]), "layout": s.get("layout", "fill"), "captions": False}
        for key in ("look", "blur", "dim", "fx", "stepped_fps", "posterize", "interp", "mix", "zoom_follow"):
            if key in s:
                shot[key] = s[key]
        if prof["type"] == "boomerang" and "zoom_follow" not in s:
            shot["zoom_follow"] = True   # zoom in going forward, back out on the reverse
        if s.get("pulse"):   # beat pulse: an exposure kick and a focus snap on every N beats of the shot
            for at in np.arange(s["from"], s["to"], s["pulse"]):
                hits += [{"t": bt(float(at)), "type": "exposure", "amt": 0.7, "dur": 0.85 * B},
                         {"t": bt(float(at)), "type": "defocus", "amt": 1.0, "dur": 0.85 * B, "px": 12}]
        zl = list(s.get("zooms", []))
        cf = s.get("camera_flow")
        if cf:   # a new compounding camera move on every beat: dolly in or out, roll, optional drift
            cf = cf if isinstance(cf, dict) else {}
            sc, every = 1.0, cf.get("every", 1)
            for j, at in enumerate(np.arange(s["from"] + every, s["to"], every)):
                zin, side = (1, 1, -1, 1)[j % 4], (1, -1, -1, 1)[j % 4]
                sc = max(1.0, sc * (1 + cf.get("zoom", 0.12)) ** zin)
                z = {"at": float(at), "scale": sc, "rot": side * cf.get("roll", 10) * (1 + j % 3) / 2,
                     "dur": cf.get("dur", 1.6), "ease": cf.get("ease", 2.5)}
                if cf.get("pan"):
                    z["x"] = s.get("cx", 0.5) + side * cf["pan"]
                zl.append(z)
        if zl:
            # velocity zoom chain: each keyframe lands on a beat; times in beats -> output seconds
            zs = []
            for z in zl:
                d = dict(z)
                at = d.pop("at")
                d["t"] = bt(at)
                d["dur"] = d.get("dur", 0.5) * B          # move length in beats
                zs.append(d)
            shot["zooms"] = zs
            if s.get("velocity", sp == "normal" and bool(s.get("zooms"))):
                # time-remap peaks synced to the zoom moves (the "graph peak on the marker" rule)
                us = [(z["t"] - o0) / max(o1 - o0, 1e-6) for z in zs]
                vel = s.get("velocity") if isinstance(s.get("velocity"), dict) else {}
                prof = {"type": "pulses", "at": us, "hi": vel.get("hi", 2.2), "lo": vel.get("lo", 0.35),
                        "w": vel.get("w", 0.35 * B / max(o1 - o0, 1e-6))}
                _, _, mean, _ = remap_table(prof)
                span = (o1 - o0) * mean
                src_in = _fit(src, peak, span, dur, workdir, spec.get("guard_cuts", True))
                shot.update(profile=prof, src_in=src_in, src_span=span)
        if "cx" in s:
            shot["cx"], shot["cy"] = s["cx"], s.get("cy", 0.45)
        else:
            shot["track"] = _track(src, src_in, src_in + span)
        if min(prof.get("speed", 1), prof.get("lo", 1)) < 0.6 and "interp" not in shot:
            shot["interp"] = spec.get("slowmo_interp", "flow")
        if s.get("voice"):   # a soundbite: the shot plays its own speech and the music ducks under it
            if abs(mean - 1) > 1e-3:
                print(f"  ! shot {s['from']}..{s['to']} carries a voice but isn't at normal speed; speech needs speed 1.0")
            voices.append((src, src_in, span, o0))
            if s.get("captions"):   # word-by-word captions of what is said (first run downloads Whisper)
                from .transcribe import transcribe, words_in
                tr = transcribe(src, os.path.join(workdir, "tr_" + os.path.splitext(os.path.basename(src))[0]))
                cap_words += [dict(w, s=w["s"] - src_in + o0, e=w["e"] - src_in + o0)
                              for w in words_in(tr["words"], src_in, src_in + span)]
                shot["captions"] = True
        print(f"  shot {s['from']:>6}..{s['to']:<6} {os.path.basename(src)}  src {src_in:.2f}-{src_in + span:.2f}s "
              f"({prof['type']})")
        if looks_like_slideshow(src, src_in, src_in + span):
            print(f"  ! shot {s['from']}..{s['to']} looks like a photo slideshow (sharp picture between blurred sides). "
                  f"Use real video footage instead.")
        shots.append(shot)

    # ------------------------------------------------------------ texts & images
    for tx in spec.get("texts", []):
        st = dict(TEXT_STYLES.get(tx.get("style", "title"), TEXT_STYLES["title"]))
        st.update({k: v for k, v in tx.items() if k not in ("from", "to", "style")})
        st["t0"] = bt(tx["from"]) + (0.04 if st.get("anim") == "type" else 0)
        st["t1"] = until(tx["to"])
        if st.get("follow"):   # ride along with the subject of the shot it starts on
            sh = next((x for x in shots if x["out"][0] <= st["t0"] < x["out"][1]), shots[-1])
            tr = sh.get("track") or _track(sh["src"], sh["src_in"], sh["src_in"] + sh["src_span"])
            fo = st["follow"] if isinstance(st["follow"], dict) else {}
            st["follow_track"] = dict(tr, src=sh["src"], dx=fo.get("dx", 0), dy=fo.get("dy", -260))
        texts.append(st)
    for im in spec.get("images", []):
        d = {k: v for k, v in im.items() if k not in ("from", "to")}
        d.update(path=P(im["path"]), t0=bt(im["from"]), t1=bt(im["to"]))
        images.append(d)

    overlays = []   # user-supplied overlay clips (light leaks, particles, dust), blended over the footage
    for o in spec.get("overlays", []):
        d = {k: v for k, v in o.items() if k not in ("from", "to")}
        d.update(path=P(o["path"]), t0=bt(o["from"]), t1=until(o["to"]))
        overlays.append(d)
    burst = spec.get("burst")
    if burst:   # photo strobe: each picture for a couple of frames
        step, tb = burst.get("frames", 2) / 30, bt(burst["from"])
        for i, pth in enumerate(burst["paths"]):
            images.append(dict(path=P(pth), t0=tb + i * step, t1=tb + (i + 1) * step, w=burst.get("w", 1080),
                               x=540, y=burst.get("y", 960), anim="cut", z=3))
        hits.append({"t": tb, "type": "punch", "amt": 0.04, "dur": 0.2, "_sfx": "shutter"})

    wall = spec.get("thumb_wall")
    if wall:
        every = wall.get("every", 0.5)
        y0, dy = wall.get("y", 730), wall.get("step", 122)
        for i, pth in enumerate(wall["paths"]):
            images.append(dict(path=P(pth), t0=bt(wall["from"] + i * every), t1=bt(wall["to"]),
                               w=wall.get("w", 860), radius=18, border=7, shadow=True, anim="drop", z=3,
                               x=540 + (60 if i % 2 else -60), y=y0 + i * dy, rot=5.0 if i % 2 else -5.0))
            hits.append({"t": bt(wall["from"] + i * every), "type": "punch", "amt": 0.04, "dur": 0.2,
                         "_sfx": "shutter"})

    cards = spec.get("cards")
    if cards and cards.get("items"):
        cd = os.path.join(workdir, "cards")
        os.makedirs(cd, exist_ok=True)
        span_b = cards["to"] - cards["from"]
        for i, c in enumerate(cards["items"][:5]):
            pth = assets.comment_card(c["text"], c.get("handle", "@viewer"), os.path.join(cd, f"c{i}.png"),
                                      c.get("likes"), idx=i)
            at = cards["from"] + i * span_b * 0.6 / max(1, len(cards["items"][:5]))
            images.append(dict(path=pth, t0=bt(at), t1=bt(cards["to"]), w=920, x=540,
                               y=cards.get("y", 430) + i * cards.get("step", 250), anim="pop", shadow=True, z=4))
            hits.append({"t": bt(at), "type": "punch", "amt": 0.03, "dur": 0.2, "_sfx": "shutter"})

    ec = spec.get("endcard")
    click = None
    if ec:
        ad = os.path.join(workdir, "assets")
        os.makedirs(ad, exist_ok=True)
        logo = P(ec["logo"])
        if ec.get("circle", True):
            logo = assets.circle_logo(logo, os.path.join(ad, "logo.png"))
        t_end = until(ec["to"])
        images.append(dict(path=logo, t0=bt(ec["from"]), t1=t_end, w=ec.get("logo_w", 640), x=540,
                           y=ec.get("logo_y", 760), anim="slam", glow=1.0, glow_radius=45,
                           glow_color=tuple(ec.get("glow_color", (255, 255, 255))), hum=0.15, hum_drop=False,
                           grow=0.012, z=6))
        hits.append({"t": bt(ec["from"]), "type": "zoom_in", "amt": 1.0, "dur": 0.15, "att": 0.12, "scale": 0.9})
        hits.append({"t": bt(ec["from"]), "type": "flash", "amt": 0.6, "dur": 0.12, "_sfx": "impact"})
        if ec.get("headline"):
            texts.append(dict(TEXT_STYLES["type"], text=ec["headline"], t0=bt(ec["from"] + 1), t1=t_end,
                              size=ec.get("headline_size", 76), y=330, type_dur=0.5))
        if ec.get("subscribe", True):
            sub, subd = assets.subscribe_buttons(ad, ec.get("button", "SUBSCRIBE"), ec.get("button_done", "SUBSCRIBED"))
            cur = assets.cursor(ad)
            click = bt(ec.get("click", ec["from"] + 4))
            appear = bt(ec.get("button_at", ec["from"] + 2))
            by = ec.get("button_y", 1330)
            images += [
                dict(path=sub, t0=appear, t1=click, w=560, x=540, y=by, anim="pop", glow=0.7, glow_radius=30,
                     glow_color=(255, 40, 40), z=7, kf=[[click - 0.12, 540, by, 1.0], [click - 0.02, 540, by, 0.9]]),
                dict(path=subd, t0=click, t1=t_end, w=640, x=540, y=by, anim="pop", z=7),
                dict(path=cur, t0=appear + 0.3, t1=t_end, w=110, z=9, anim="fade", fade_in=0.15,
                     kf=[[appear + 0.3, 980, 1820, 1.0], [click - 0.15, 620, by + 70, 1.0],
                         [click - 0.02, 620, by + 70, 0.82], [click + 0.1, 620, by + 70, 1.0],
                         [t_end, 760, by + 230, 1.0]])]
            hits += [{"t": click, "type": "punch", "amt": 0.06, "dur": 0.3},
                     {"t": click, "type": "flash", "amt": 0.35, "dur": 0.08}]

    # ------------------------------------------------------------ hits
    for h in spec.get("hits", []):
        d = dict(h)
        d["t"] = bt(d.pop("at"))
        d["_sfx"] = d.pop("sfx", A.SFX_FOR.get(d["type"]))   # "sfx": null silences it
        hits.append(d)
    L = spec.get("level", 6)   # edit level: 1 barely edited, 5 clean, 10 hyper
    posters = [(tx["t0"], tx["t1"]) for tx in texts if tx.get("kind") == "poster"]
    if len(posters) > (1 if END < 20 else 2):
        print(f"  ! {len(posters)} poster frames in {END:.0f}s - keep it to {1 if END < 20 else 2}; they only land when rare.")
    for o in [tx for tx in texts if tx.get("kind") != "poster"] + images:   # the renderer hides these under a poster
        if any(o["t0"] < b and o["t1"] > a for a, b in posters):
            print(f"  ! '{o.get('text') or os.path.basename(o['path'])}' overlaps a poster frame; it's hidden while the poster is up.")
    if spec.get("auto_hits", True):
        n0 = len(hits)
        trans = [x for x in spec.get("transitions", ["glitch", "whip", "zoom_in", "spin"]) if L >= 8 or x in ("whip", "zoom_in")]
        every = 2 if L >= 7 else 4 if L >= 4 else 0   # a transition every 2 beats, every bar, or never
        ti = 0
        mixed = {s["from"] for s in spec["shots"] if s.get("mix")}
        cut_beats = sorted({s["from"] for s in spec["shots"]} - {first} - mixed)
        for cb in cut_beats:
            c = bt(cb)
            if cb != 0 and not (ec and cb == ec["from"]):   # shot life, studied from pro project files:
                if lv(L, 5):   # the new shot pulls into focus
                    hits.append({"t": c, "type": "defocus", "amt": lv(L, 5), "dur": 0.3, "px": 12})
                if lv(L, 6):   # the old shot sinks toward black just before the cut (a blink)
                    hits.append({"t": c, "type": "black", "amt": 0.6 * lv(L, 6), "dur": 0.0001, "att": 0.15, "shape": "hold"})
            if cb < 0:
                if lv(L, 5):
                    hits.append({"t": c, "type": "exposure", "amt": 0.6 * lv(L, 5), "dur": 0.15, "_sfx": "shutter"})
                continue
            if cb == 0 or (ec and cb == ec["from"]):
                continue
            if lv(L, 4):
                hits.append({"t": c, "type": "punch", "amt": 0.12 * lv(L, 4), "dur": 0.6})   # zoom settles over the shot
            if lv(L, 6) and (cb % 4 == 0 or L >= 8):   # jolt peaking on the cut: bar lines from 6, every cut from 8
                hits.append({"t": c, "type": "jolt", "amt": 0.7 * lv(L, 6), "att": 0.07, "dur": 0.35, "speed": 0.6})
            if cb % 4 == 0 and lv(L, 6):
                hits += [{"t": c, "type": "flash", "amt": 0.85 * lv(L, 6), "dur": 0.1},
                         {"t": c, "type": "shake", "amt": 0.9 * lv(L, 6), "dur": 0.3, "freq": 16, "px": 50}]
            elif cb % 4 and lv(L, 8):
                hits.append({"t": c, "type": "rgb", "amt": lv(L, 8), "dur": 0.15, "px": 22})
            if every and trans and cb % every == 0 and cb > 0:
                typ = trans[ti % len(trans)]
                ti += 1
                if L >= 7:   # the music drops out for a few frames right before the transition
                    hits.append({"t": c, "type": "gap", "dur": 0.1, "db": -12})
                if typ == "glitch":
                    hits.append({"t": c, "type": "glitch", "amt": 0.9, "dur": 0.15, "att": 0.06, "_sfx": "glitch"})
                else:
                    hits.append({"t": c, "type": typ, "amt": 1.0, "dur": 0.13, "att": 0.1,
                                 "dir": (-1) ** ti, "scale": 0.8, "deg": 20, "_sfx": A.SFX_FOR.get(typ)})
        # the drop: (level it switches on at, hit); strengths grow with the level
        drop = [(3, {"t": DROP, "type": "black", "amt": 1.0, "dur": 0.0001, "att": 0.12, "shape": "hold"}),
                (3, {"t": DROP, "type": "flash", "amt": 1.0, "dur": 0.2}),
                (5, {"t": DROP, "type": "shake", "amt": 1.4, "dur": 0.55, "freq": 17, "px": 60}),
                (6, {"t": DROP, "type": "bloom", "amt": 0.9, "dur": 0.5}),
                (7, {"t": DROP, "type": "rgb", "amt": 1.0, "dur": 0.45, "px": 34}),
                (8, {"t": bt(1), "type": "flash", "amt": 0.7, "dur": 0.1}),
                (8, {"t": bt(1), "type": "shake", "amt": 0.9, "dur": 0.3, "freq": 18, "px": 45}),
                (8, {"t": bt(-2), "type": "shake", "amt": 0.4, "dur": DROP - bt(-2), "freq": 22, "px": 20})]
        hits += [dict(h, amt=h["amt"] * (1 if h["type"] == "black" else lv(L, on))) for on, h in drop if lv(L, on)]
        if L >= 5:   # a pocket of silence right before the drop
            hits.append({"t": DROP, "type": "gap", "dur": 0.12, "db": -18})
        hits.append({"t": END - 0.15, "type": "black", "amt": 1.0, "dur": 0.4, "att": 0.25, "shape": "hold"})
        # poster frames hold still: no automatic hits while one is up (a cut can still land on its first frame)
        hits[n0:] = [h for h in hits[n0:] if h["type"] == "black" or not any(a + 0.05 < h["t"] < b for a, b in posters)]

    # ------------------------------------------------------------ audio
    mu = load_audio(P(m["path"]), A.SR)
    if m.get("fx") == "slowed":
        mu = A.reverb(A.resample_speed(mu, 0.85), 3.0, 0.3)
    elif m.get("fx") == "sped":
        mu = A.resample_speed(mu, 1.25)
    mix = mu[:, int(bt.M0 * A.SR):int((bt.M0 + END + 0.6) * A.SR)].copy()
    if mix.shape[1] < int((END + 0.6) * A.SR):
        mix = np.pad(mix, ((0, 0), (0, int((END + 0.6) * A.SR) - mix.shape[1])))
    mix = A.fade(mix, 0.02, 0.9)
    for h in hits:
        if h["type"] == "gap":   # audio-only hit: dip the music just before its moment
            mix = A.dip(mix, h["t"] - h.get("dur", 0.12), h["t"], h.get("db", -18))
    if L >= 3:   # the track loses its low end as the edit ends
        mix = A.thin_out(mix, END - 0.8, 0.8)
    if voices:   # soundbites over the music: speech sits just above the track, the music ducks under it
        vb, srcs = np.zeros_like(mix), {}
        for src, s0, span, o0 in voices:
            if src not in srcs:
                srcs[src] = load_audio(src, A.SR)
            A.place(vb, A.fade(srcs[src][:, int(s0 * A.SR):int((s0 + span) * A.SR)], 0.03, 0.08), o0)
        g = A.duck_envelope(vb, depth_db=spec.get("voice_duck", -14))
        vb *= 10 ** ((A.ref_db(mix) + 1 - A._rms_db(vb)) / 20)
        mix = mix * g[None, :mix.shape[1]] + vb
    if spec.get("sfx", True) and L >= 3:   # sound follows the level: none at 1-2, details from 5
        ev = [(DROP - 0.01, "drop")] + [(DROP, "riser")] * (L >= 5)
        ev += [(h["t"], h["_sfx"]) for h in hits if h.get("_sfx")]
        for sh in shots if L >= 4 else []:
            ev += [(z["t"], "swish") for z in sh.get("zooms", [])]          # each zoom-chain move
            pr = sh["profile"]
            if pr["type"] == "boomerang":                                    # the turn-around point
                ev.append((sh["out"][0] + pr.get("split", 0.5) * (sh["out"][1] - sh["out"][0]), "rewind"))
        for tx in texts if L >= 5 else []:
            if tx.get("kind") == "poster" or tx.get("anim") == "slam":
                ev.append((tx["t0"], "hit"))
            elif tx.get("anim") == "pop":
                ev.append((tx["t0"], "pop"))
            elif tx.get("anim") == "type":   # one key press per typed character
                step = tx.get("type_dur", 0.5) / max(1, len(tx["text"]))
                ev += [(tx["t0"] + j * step, "typing", 0.0, j % 4) for j, ch in enumerate(tx["text"]) if ch not in " []"]
        if click is not None:
            ev.append((click, "click"))
        A.mix_sfx(mix, ev, A.ref_db(mix))
    for h in hits:
        h.pop("_sfx", None)
    mix = A.normalize(mix)
    apath = os.path.join(workdir, "mix.wav")
    save_audio(apath, mix, A.SR)

    readable(texts, END, spec.get("reading", {}))

    import librosa
    on = librosa.onset.onset_strength(y=mix.mean(0), sr=A.SR, hop_length=A.SR // 30)
    on = np.clip(on / (np.percentile(on, 97) + 1e-9), 0, 1)
    on = np.maximum(on, np.concatenate([[0], on[:-1]]) * 0.6)

    plan = {"fps": 30, "width": 1080, "height": 1920, "look": spec.get("look", "teal_orange"),
            "duration": END, "shots": shots, "hits": hits, "texts": texts, "images": images, "audio": apath,
            "motion_blur": spec.get("motion_blur", "flow"), "fx": spec.get("fx", {}),
            "letterbox": spec.get("letterbox", 0), "audio_env": on.tolist(), "overlays": overlays,
            "captions": {"words": cap_words, "source_time": False, "y": spec.get("caption_y", 0.7)} if cap_words else None,
            "music": {"path": P(m["path"]), "start": bt.M0, "tempo": bt.ma["tempo"], "drop_out": DROP}}
    return plan


def load(path):
    return json.load(open(path))
