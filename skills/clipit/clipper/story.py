"""Story edits from a JSON spec, timed in BEATS relative to the music drop.

A story edit is a narrative fan edit: setup text over slow mono footage -> blackout -> drop ->
beat-cut hype -> end card. Every time field ("from", "to", "at") is a beat index relative to the
drop (0 = drop, -4 = one bar before, 8 = two bars after). Fractions are allowed (e.g. -19.5).
See docs/STORY_SPEC.md for every field.
"""
import json
import math
import os
import re

import numpy as np

from . import assets
from . import audio as A
from .beats import analyze
from .media import load_audio, probe
from .moments import PICTURES, STILL_ON_SCREEN, action_window, looks_like_slideshow, looks_still
from .planner import ASPECTS, _track, fit, lv, save_mix
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
    "velocity": {"type": "ramp", "hi": 2.0, "lo": 0.6, "k": 2.0},   # 200% -> 60% -> 200%, eased: the classic per-clip ramp
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
    # a meme label on a coloured bar, e.g. over the eyes on a freeze frame the beat before the drop
    "label": dict(font="wide", size=58, stroke=0, color=(255, 255, 255), accent=(255, 255, 255), bar=(200, 18, 32),
                  glow=0, shadow=False, anim="cut", y=760),
    # small subtitle-style line that fades in word by word (intros, quotes)
    "subtitle": dict(font="bold", size=44, stroke=0, color=(245, 245, 245), accent=(235, 40, 40), glow=0.4,
                     glow_radius=10, anim="words", type_dur=0.6, fade_out=0.25, y=1240),
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
        self.offset = 0.0   # output time where the beat grid starts (after a dialogue intro)

    def __call__(self, n):
        """Output time (s) of beat n relative to the drop; fractional beats interpolate."""
        lo = int(np.floor(n))
        f = n - lo
        i = self.di + lo
        a = self.beats[max(0, min(i, len(self.beats) - 1))]
        b = self.beats[max(0, min(i + 1, len(self.beats) - 1))]
        return self.offset + max(0.0, a + (b - a) * f)


_SCENES = {}
_ACTIVE = {}


def active_moments(src, n=4):
    """The most active moments of a source (seconds), strongest first: where to look for footage that moves."""
    if src not in _ACTIVE:
        from .moments import shots
        _ACTIVE[src] = [s["peak"] for s in sorted(shots(src, probe(src)), key=lambda x: -x["motion"]) if not s["slideshow"]]
    return _ACTIVE[src][:n]


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


def _scene(src, t, dur, workdir, guard=True):
    """(start, end) of the scene that contains source second t."""
    lo, hi = 0.0, dur
    for c in scene_cuts(src, workdir) if guard else []:
        if c <= t:
            lo = c + 0.04
        else:
            hi = c - 0.04
            break
    return lo, hi


def _fit(src, peak, span, dur, workdir, guard=True):
    """Centre the source window on `peak`, but keep it inside the scene that contains the peak,
    so speed-ups never spill across a cut into unrelated footage."""
    lo, hi = _scene(src, peak, dur, workdir, guard)
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


def _follow(item, shots, dy, below=None):
    """A track for text or a picture to ride on the eyes of the shot it starts on (dy px below them, or `below`
    eye-spacings, which scales with the face)."""
    sh = next((x for x in shots if x["out"][0] <= item["t0"] < x["out"][1]), shots[-1])
    fo = item["follow"] if isinstance(item["follow"], dict) else {}
    tr = sh["track"]
    return dict(t=tr["t"], x=tr["ex"], y=tr["ey"], src=sh["src"], dx=fo.get("dx", 0), dy=fo.get("dy", dy),
                below=fo.get("below", below), eyes=tr.get("eyes"))


def _speech(spec, src, workdir):
    """The transcript of a source (None when no speech model is installed)."""
    try:
        from .transcribe import transcribe
    except ImportError:
        return None
    try:
        return transcribe(src, os.path.join(workdir, "tr_" + os.path.splitext(os.path.basename(src))[0]),
                          model=spec.get("whisper"))
    except ImportError:
        print("  ! no speech model installed: lines are cut on pauses in the audio and get no subtitles")
        return None


def _dialogue(spec, P, workdir, edge):
    """The dialogue intro: whole spoken lines played in order at normal speed, timed by the speech, not the beat.
    Every line is widened to whole sentences and cut in real pauses. Subtitles only when the language is certain.
    Returns (shots, voices, caption words, length)."""
    from .transcribe import line_ok, snap_speech, words_in
    shots, voices, cap, t = [], [], [], 0.0
    for d in spec.get("dialogue", []):
        src = P(d["src"])
        tr = _speech(spec, src, workdir)
        s0, s1, clean = snap_speech(src, d["start"], d["end"], tr)
        span = s1 - s0
        subs = bool(tr) and d.get("captions", True) and line_ok(tr, src, s0, s1)
        words = words_in(tr["words"], s0, s1) if subs else []
        said = f'"{" ".join(w["w"] for w in words)}"' if subs else "(no subtitles: the language isn't certain or needs the full model)"
        print(f"  dialogue {os.path.basename(src)} {s0:.2f}-{s1:.2f}s {said}")
        if s1 - d["end"] > 1.5 or d["start"] - s0 > 1.5:
            print(f"  ! widened from {d['start']}-{d['end']} so the sentence isn't cut; pick a shorter line if this is too long")
        if not clean:
            print("  ! no clear pause at one end of that line; check it on playback, or pick another line")
        tr_v = _track(src, s0, s1)
        fz, zoom = fit(tr_v, d.get("zoom", [1.0, 1.04]))
        shot = {"src": src, "out": [t, t + span], "src_in": s0, "src_span": span, "profile": {"type": "const", "speed": 1.0},
                "zoom": zoom, "fit_z": fz, "track": tr_v, "layout": d.get("layout", "fill"), "voice": True,
                "captions": bool(words), "edge": d.get("edge", edge)}
        for key in ("look", "fx", "cx", "cy"):
            if key in d:
                shot[key] = d[key]
        shots.append(shot)
        voices.append((src, s0, span, t))
        cap += [dict(w, s=w["s"] - s0 + t, e=w["e"] - s0 + t) for w in words]
        t += span + d.get("gap", 0.0)
    return shots, voices, cap, t


def build(spec, workdir, base_dir="."):
    P = lambda p: p if os.path.isabs(p) else os.path.join(base_dir, p)
    for s in [spec] + spec["shots"] + [s[k] for s in spec["shots"] for k in ("top", "bottom") if k in s]:
        if str(s.get("look", "")).endswith(".cube"):   # a fitted LUT (match-look) is a file like any other
            s["look"] = P(s["look"])
    os.makedirs(workdir, exist_ok=True)
    m = spec["music"]
    bt = Beats(P(m["path"]), m.get("drop", "auto"), m.get("bars_before", 5), m.get("bars_after", 7))
    B = bt.B
    first = min(s["from"] for s in spec["shots"])
    last = spec.get("end", bt.end_beat)
    edge = spec.get("edge", "mirror")
    # dialogue first (timed by the words), then the beat-timed montage starts where it ends
    shots, voices, cap_words, intro = _dialogue(spec, P, workdir, edge)
    bt.offset = intro
    END, DROP = bt(last), bt(0)
    until = lambda b: END if b >= last else bt(b)   # end time of anything that runs to `b` (or to the end)
    hits, texts, images = [], [], []

    # ------------------------------------------------------------ shots
    stills_ok = spec.get("allow_stills", False)   # only when the user explicitly asks for photos or a slideshow

    def no_stills(what):
        if not stills_ok:
            raise SystemExit(f"! {what}. ClipIt edits real moving footage: no photos, slideshows or freeze frames "
                             f"unless the user explicitly asks for them (then set \"allow_stills\": true).")
    if spec.get("burst") or spec.get("thumb_wall"):
        no_stills("this spec puts a sequence of photos on screen (burst / thumb_wall)")
    queue = sorted(spec["shots"], key=lambda x: x["from"])
    while queue:
        s = queue.pop(0)
        o0 = intro if s["from"] == first else bt(s["from"])
        o1 = until(s["to"])
        if s.get("layout") == "split":   # two feeds stacked top/bottom, playing in real time with their own sound
            panels = []
            for key in ("top", "bottom"):
                q = s[key]
                src = P(q["src"])
                dur, span = probe(src)["duration"], o1 - o0
                src_in = float(np.clip(q["start"] if "start" in q else q.get("peak", dur / 2) - span / 2, 0, max(0, dur - span)))
                tr = _track(src, src_in, src_in + span)
                fz, zoom = fit(tr, q.get("zoom", [1.0, 1.04]))
                panels.append(dict({k: q[k] for k in ("cx", "cy", "look") if k in q}, src=src, out=[o0, o1], src_in=src_in,
                                   src_span=span, profile={"type": "const", "speed": 1.0}, zoom=zoom, fit_z=fz, track=tr,
                                   layout="fill", edge=s.get("edge", edge), look=q.get("look", s.get("look", spec.get("look", "teal_orange")))))
                if s.get("audio", "mix") in (key, "mix"):
                    voices.append((src, src_in, span, o0))
            shots.append(dict(panels[0], split=panels, voice=True, captions=False))
            print(f"  shot {s['from']:>6}..{s['to']:<6} split: {os.path.basename(panels[0]['src'])} / {os.path.basename(panels[1]['src'])}")
            continue
        if os.path.splitext(s.get("src", ""))[1].lower() in PICTURES:
            no_stills(f"shot {s['from']}..{s['to']} is a picture file ({os.path.basename(s['src'])}), not video")
        if s.get("speed") == "freeze":
            no_stills(f"shot {s['from']}..{s['to']} is a freeze frame")
        sp = s.get("speed", "velocity")   # the go-to: a fast-slow-fast ramp with flow slow-mo in the middle
        if s.get("voice") and sp not in ("normal", 1, 1.0):
            print(f"  ! shot {s['from']}..{s['to']} carries a voice, so it plays at normal speed (speed '{sp}' ignored)")
            sp = "normal"
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
        elif not s.get("voice") and s.get("speed") not in ("hold", "freeze") and s.get("look") != "poster":
            # keep the shot on the action: slow motion of a calm moment barely changes on screen and reads as a still
            lo, hi = _scene(src, src_in, dur, workdir, spec.get("guard_cuts", True))
            moved, life = action_window(src, src_in, span, prof, o1 - o0, lo, hi)
            if abs(moved - src_in) > 0.05:
                print(f"  shot {s['from']}..{s['to']}: moved to source {moved:.2f}s, where it shows more movement")
                src_in = moved
            if life < STILL_ON_SCREEN and o1 - o0 > 1.0:
                # nothing stands still on screen for more than a second: keep a second of it (whole beats, or
                # half beats on slow songs), then cut to the clip's liveliest moments, each under a second
                step = max(0.5, math.floor(2.0 / B) / 2)
                cuts = list(np.arange(s["from"], s["to"], step)) + [s["to"]]
                lively = [m for m in active_moments(src, 8) if abs(m - (src_in + span / 2)) > 1.0] or [peak]
                pieces = [dict(s, **{"from": float(a), "to": float(b)}, peak=lively[j % len(lively)], speed="normal")
                          for j, (a, b) in enumerate(zip(cuts[1:-1], cuts[2:]))]
                print(f"  shot {s['from']}..{s['to']} stood still on screen ({life:.1f}): kept {step:g} beat(s) of it, "
                      f"then cut to the liveliest moments of the clip ({', '.join('%.1fs' % x['peak'] for x in pieces)})")
                queue[:0] = [dict(s, to=float(cuts[1]))] + pieces
                continue
        shot = {"src": src, "out": [o0, o1], "src_in": src_in, "src_span": span, "profile": prof,
                "zoom": s.get("zoom", [1.0, 1.1]), "layout": s.get("layout", "fill"), "captions": False,
                "voice": bool(s.get("voice")), "edge": s.get("edge", edge)}
        for key in ("look", "blur", "dim", "fx", "stepped_fps", "posterize", "interp", "mix", "zoom_follow", "zoom_ease"):
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
            if s.get("velocity", sp == "normal" and bool(s.get("zooms"))) and not s.get("voice"):
                # time-remap peaks synced to the zoom moves (the "graph peak on the marker" rule)
                us = [(z["t"] - o0) / max(o1 - o0, 1e-6) for z in zs]
                vel = s.get("velocity") if isinstance(s.get("velocity"), dict) else {}
                prof = {"type": "pulses", "at": us, "hi": vel.get("hi", 2.2), "lo": vel.get("lo", 0.35),
                        "w": vel.get("w", 0.35 * B / max(o1 - o0, 1e-6))}
                _, _, mean, _ = remap_table(prof)
                span = (o1 - o0) * mean
                src_in = _fit(src, peak, span, dur, workdir, spec.get("guard_cuts", True))
                shot.update(profile=prof, src_in=src_in, src_span=span)
        shot["track"] = _track(src, src_in, src_in + span)   # faces: where to frame and how close is safe
        if "cx" in s:
            shot["cx"], shot["cy"] = s["cx"], s.get("cy", 0.45)
        if s.get("fit", True) and shot["layout"] == "fill":
            shot["fit_z"], shot["zoom"] = fit(shot["track"], shot["zoom"])
        if min(prof.get("speed", 1), prof.get("lo", 1)) <= 0.6 and "interp" not in shot:
            shot["interp"] = spec.get("slowmo_interp", "flow")
        if s.get("voice"):   # a soundbite: its own speech, music ducked; the voice runs on under the next shot
            from .transcribe import line_ok, snap_speech, words_in   # until the sentence ends (an L-cut)
            tr = _speech(spec, src, workdir)
            heard = max(span, snap_speech(src, src_in, src_in + span, tr)[1] - src_in)
            if heard > span + 0.05:
                print(f"  shot {s['from']}..{s['to']}: the speech runs {heard - span:.1f}s past the cut so the sentence finishes")
            voices.append((src, src_in, heard, o0))
            if s.get("captions") and tr and line_ok(tr, src, src_in, src_in + heard):
                cap_words += [dict(w, s=w["s"] - src_in + o0, e=w["e"] - src_in + o0)
                              for w in words_in(tr["words"], src_in, src_in + heard)]
                shot["captions"] = True
        print(f"  shot {s['from']:>6}..{s['to']:<6} {os.path.basename(src)}  src {src_in:.2f}-{src_in + span:.2f}s "
              f"({prof['type']})")
        if looks_like_slideshow(src, src_in, src_in + span):
            no_stills(f"shot {s['from']}..{s['to']} is a photo slideshow (a sharp picture between blurred copies of itself)")
        elif sp == "hold" and s.get("look") != "poster":
            no_stills(f"shot {s['from']}..{s['to']} is a near-freeze (\"hold\" is only for poster frames)")
        elif not s.get("voice") and looks_still(src, src_in, src_in + max(span, 0.5)):
            no_stills(f"shot {s['from']}..{s['to']} is a still picture (nothing in it moves)")
        shots.append(shot)

    # ------------------------------------------------------------ texts & images
    for tx in spec.get("texts", []):
        st = dict(TEXT_STYLES.get(tx.get("style", "title"), TEXT_STYLES["title"]))
        st.update({k: v for k, v in tx.items() if k not in ("from", "to", "style")})
        st["t0"] = bt(tx["from"]) + (0.04 if st.get("anim") == "type" else 0)
        st["t1"] = until(tx["to"])
        if st.get("follow"):   # ride along with the subject of the shot it starts on
            st["follow_track"] = _follow(st, shots, -260)
        texts.append(st)
    for n, im in enumerate(spec.get("images", [])):
        d = {k: v for k, v in im.items() if k not in ("from", "to")}
        d.update(t0=bt(im["from"]), t1=until(im["to"]))
        if "emoji" in im:   # a colour emoji, e.g. on the chest at the drop
            d.update(path=assets.emoji_png(im["emoji"], im.get("w", 300), os.path.join(workdir, f"emoji{n}.png")),
                     w=im.get("w", 300), y=im.get("y", 1190), anim=im.get("anim", "pop"))
        else:
            d["path"] = P(im["path"])
        if d.get("follow"):
            d["follow_track"] = _follow(d, shots, 0, below=3.5)   # on the chest
        if d["path"]:
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
    for sh, s in zip(shots[len(shots) - len(spec["shots"]):], sorted(spec["shots"], key=lambda x: x["from"])):
        if "edge" not in s and any(sh["out"][0] < b and sh["out"][1] > a for a, b in posters):
            sh["edge"] = "blur"   # calm, blurred fill behind a poster, never mirrored copies of a face
    if len(posters) > (1 if END < 20 else 2):
        print(f"  ! {len(posters)} poster frames in {END:.0f}s - keep it to {1 if END < 20 else 2}; they only land when rare.")
    for o in [tx for tx in texts if tx.get("kind") != "poster"] + images:   # the renderer hides these under a poster
        if any(o["t0"] < b and o["t1"] > a for a, b in posters):
            print(f"  ! '{o.get('text') or os.path.basename(o['path'])}' overlaps a poster frame; it's hidden while the poster is up.")
    if spec.get("auto_hits", True):
        n0 = len(hits)
        # every change of shot flows: a focus-hunting cut (soft into the cut, hunting sharp after it) or a zoom cut
        # (push in, land close, ease back). Beat cuts get a quick one so the hit still lands on the beat.
        style = spec.get("cuts", "focus")
        cuts = [(sh["out"][0], sh) for sh in shots[1:] if not sh.get("mix")]
        for i, (c, sh) in enumerate(cuts):
            kind = sh.get("cut", style)
            dialogue = sh.get("voice") or c <= intro + 1e-3   # cuts between spoken lines get the slow, full hunt
            prev = shots[shots.index(sh) - 1]
            if kind == "focus" and not dialogue and min(sh["out"][1] - c, c - prev["out"][0]) < 1.5:
                kind = "zoom"   # fast beat cuts stay sharp: a zoom cut, not a blurry hunt on a short shot
            if kind == "focus":
                hits.append({"t": c, "type": "focus", "amt": 1.0, "att": 0.2 if dialogue else 0.1,
                             "dur": 0.45 if dialogue else 0.3, "px": 16 if dialogue else 11})
            elif kind == "zoom":
                hits.append({"t": c, "type": "zoomcut", "amt": 1.0, "att": 0.12, "dur": 0.3, "scale": 0.12})
        mixed = {s["from"] for s in spec["shots"] if s.get("mix")}
        voiced = {s["from"] for s in spec["shots"] if s.get("voice")}
        for cb in sorted({s["from"] for s in spec["shots"]} - {first} - mixed):
            c = bt(cb)
            if cb == 0 or (ec and cb == ec["from"]):
                continue
            bar = cb % 4 == 0
            if bar and lv(L, 5):   # the old shot dips toward dark into a bar-line cut (a blink)
                hits.append({"t": c, "type": "black", "amt": 0.45 * lv(L, 5), "dur": 0.0001, "att": 0.12, "shape": "hold"})
            if cb > 0 and bar and lv(L, 7) and cb not in voiced:   # a short jolt on bar lines after the drop
                hits.append({"t": c, "type": "jolt", "amt": 0.5 * lv(L, 7), "att": 0.06, "dur": 0.3, "speed": 0.5})
            if cb > 0 and bar and lv(L, 9):
                hits += [{"t": c, "type": "flash", "amt": 0.5 * lv(L, 9), "dur": 0.08},
                         {"t": c, "type": "shake", "amt": 0.6 * lv(L, 9), "dur": 0.25, "freq": 16, "px": 40}]
            if cb > 0 and cb % 8 == 0 and lv(L, 9):   # transitions only in hyper edits, and only every 2 bars
                typ = spec.get("transitions", ["whip", "zoom_in"])[(cb // 8) % len(spec.get("transitions", ["whip", "zoom_in"]))]
                hits.append({"t": c, "type": typ, "amt": 1.0, "dur": 0.13, "att": 0.1, "dir": (-1) ** (cb // 8),
                             "scale": 0.8, "deg": 20, "_sfx": A.SFX_FOR.get(typ)})
        # the drop: (level it switches on at, hit). At 4-6 the cut itself is the hit: dark beat, then clean footage.
        drop = [(4, {"t": DROP, "type": "black", "amt": 1.0, "dur": 0.0001, "att": 0.12, "shape": "hold"}),
                (6, {"t": DROP, "type": "bloom", "amt": 0.6, "dur": 0.5}),
                (7, {"t": DROP, "type": "flash", "amt": 0.6, "dur": 0.15}),
                (7, {"t": DROP, "type": "shake", "amt": 0.7, "dur": 0.35, "freq": 16, "px": 40}),
                (9, {"t": DROP, "type": "rgb", "amt": 0.8, "dur": 0.3, "px": 26}),
                (9, {"t": bt(1), "type": "flash", "amt": 0.5, "dur": 0.1}),
                (9, {"t": bt(1), "type": "shake", "amt": 0.7, "dur": 0.3, "freq": 18, "px": 35})]
        hits += [dict(h, amt=h["amt"] * (1 if h["type"] == "black" else lv(L, on))) for on, h in drop if lv(L, on)]
        # a clean close: the last beat fades to black while the music fades out
        hits.append({"t": END - 0.05, "type": "black", "amt": 1.0, "dur": 0.4, "att": min(0.8, B), "shape": "hold"})
        # poster frames hold still: no automatic hits while one is up (a cut can still land on its first frame)
        hits[n0:] = [h for h in hits[n0:] if h["type"] == "black" or not any(a + 0.05 < h["t"] < b for a, b in posters)]

    # ------------------------------------------------------------ audio
    mu = load_audio(P(m["path"]), A.SR)
    if m.get("fx") == "slowed":
        mu = A.reverb(A.resample_speed(mu, 0.85), 3.0, 0.3)
    elif m.get("fx") == "sped":
        mu = A.resample_speed(mu, 1.25)
    m0 = int((bt.M0 - intro) * A.SR)   # with a dialogue intro the song starts earlier, under the speech
    mix = mu[:, max(0, m0):int((bt.M0 - intro + END + 0.6) * A.SR)].copy()
    if m0 < 0:
        mix = np.pad(mix, ((0, 0), (-m0, 0)))
    if mix.shape[1] < int((END + 0.6) * A.SR):
        mix = np.pad(mix, ((0, 0), (0, int((END + 0.6) * A.SR) - mix.shape[1])))
    mix = A.fade(mix, 0.3 if intro else 0.05, 1.5)   # the music never starts or stops abruptly
    for mu in spec.get("muffle", []):   # the music behind a wall, opening up on the cut
        mix = A.muffle(mix, mu["t0"] if "t0" in mu else bt(mu["from"]), mu["t1"] if "t1" in mu else bt(mu["to"]),
                       mu.get("hz", 500))
    for h in hits:
        if h["type"] == "gap":   # audio-only hit, only when the spec asks: dip the music just before its moment
            mix = A.dip(mix, h["t"] - h.get("dur", 0.12), h["t"], h.get("db", -18))
    if L >= 3:   # the track loses its low end as the edit ends
        mix = A.thin_out(mix, END - 0.8, 0.8)
    vb = np.zeros_like(mix)
    if voices:   # soundbites over the music: speech sits just above the track, the music ducks under it
        srcs = {}
        for src, s0, span, o0 in voices:
            if src not in srcs:
                srcs[src] = load_audio(src, A.SR)
            A.place(vb, A.fade(srcs[src][:, int(s0 * A.SR):int((s0 + span) * A.SR)], 0.03, 0.08), o0)
        g = A.duck_envelope(vb, depth_db=spec.get("voice_duck", -14))
        vb *= 10 ** ((A.ref_db(mix) + 1 - A._rms_db(vb)) / 20)
        for b in spec.get("bleeps", []):   # censor: the word drops out under a 1 kHz tone
            t0, d = (b["t"] if "t" in b else bt(b["at"])), b.get("dur", 0.35)
            vb[:, int(t0 * A.SR):int((t0 + d) * A.SR)] *= 0.03
            tt = np.arange(int(d * A.SR)) / A.SR
            tone = np.sin(2 * np.pi * 1000 * tt) * np.clip(np.minimum(tt, d - tt) / 0.01, 0, 1) * 10 ** (A._rms_db(vb) / 20)
            A.place(vb, np.stack([tone, tone]).astype(np.float32), t0)
        mix = mix * g[None, :mix.shape[1]]
    mix = mix + vb
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
        fx_bus = np.zeros_like(mix)
        A.mix_sfx(fx_bus, ev, A.ref_db(mix))
        mix += fx_bus
        vb += fx_bus   # the no-music version keeps speech and sound effects
    for h in hits:
        h.pop("_sfx", None)
    apath, nomusic = save_mix(workdir, mix, vb if spec.get("export_no_music") else None)

    readable(texts, END, spec.get("reading", {}))

    import librosa
    on = librosa.onset.onset_strength(y=mix.mean(0), sr=A.SR, hop_length=A.SR // 30)
    on = np.clip(on / (np.percentile(on, 97) + 1e-9), 0, 1)
    on = np.maximum(on, np.concatenate([[0], on[:-1]]) * 0.6)

    H = ASPECTS[spec.get("aspect", "9:16")]
    for item in texts + images if H != 1920 else []:   # positions are written for a 1920-tall frame; scale them
        item["y"] = item.get("y", 960) * H / 1920
        if item.get("follow_track"):
            item["follow_track"]["dy"] *= H / 1920
        if item.get("kf"):
            item["kf"] = [[k[0], k[1], k[2] * H / 1920, k[3]] for k in item["kf"]]
    plan = {"fps": 30, "width": 1080, "height": H, "look": spec.get("look", "teal_orange"),
            "duration": END, "shots": shots, "hits": hits, "texts": texts, "images": images, "audio": apath,
            "motion_blur": spec.get("motion_blur", "flow"), "fx": spec.get("fx", {}),
            "letterbox": spec.get("letterbox", 0), "audio_env": on.tolist(), "overlays": overlays,
            "captions": {"words": cap_words, "source_time": False, "y": spec.get("caption_y", 0.7),
                         "style": spec.get("caption_style", "edit")} if cap_words else None,
            "music": {"path": P(m["path"]), "start": bt.M0, "tempo": bt.ma["tempo"], "drop_out": DROP},
            "audio_nomusic": nomusic, "song_start": round(bt.M0 - intro, 2)}
    return plan


def load(path):
    return json.load(open(path))
