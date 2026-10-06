"""Edit planners: turn (source, moment, music) into a render plan + mixed audio.

talk_plan  -> clip-page style: polarizing talking segment, jump-cut silences, word captions,
              punch-ins on sentence starts & keywords, hook title, ducked music bed, whoosh/impact.
edit_plan  -> fan/velocity edit: optional dialogue hook, then music drop; beat-synced cuts,
              velocity ramps, flashes, shakes, zoom/whip/spin transitions, RGB/glitch accents.
"""
import os
import numpy as np

from . import audio as A
from . import reframe
from .beats import analyze, choose_window
from .media import load_audio, probe, save_audio
from .moments import POLAR, shots as detect_shots
from .render import remap_table
from .transcribe import captions_ok, words_in

SR = A.SR


def _track(src, s0, s1):
    return reframe.track(src, max(0, s0 - 0.3), s1 + 0.3)


def fit(track, zoom):
    """(fit_z, zoom): keep the framed head whole through the shot's own zoom move. A head that only just fits
    loses the zoom-in. One that doesn't fit at all is shown smaller, with fill around it: the renderer scales the
    shot by min(1, scene limit / fit_z) at every moment, so each scene in the window is framed on its own terms."""
    zm = (track or {}).get("zmax")
    z0, z1 = zoom
    if not zm or zm >= max(z0, z1):
        return None, [z0, z1]
    if zm >= 0.92:   # nearly fits: flatten the zoom instead of showing thin fill strips
        z0, z1 = min(z0, max(1.0, zm)), min(z1, max(1.0, zm))
    return max(z0, z1), [z0, z1]


def lv(level, on):
    """How strongly an effect fires at edit `level` (1 = barely edited, 5 = clean, 10 = hyper):
    0 below `on`, 0.55 at `on`, rising to 1.0 at 10."""
    return 0.0 if level < on else 0.55 + 0.45 * (level - on) / max(1, 10 - on)


# =================================================================== TALK CLIP
def talk_plan(src, start, end, transcript, workdir, music=None, music_start=None, layout="fill",
              title=None, look="punchy", trim_silence=True, music_db=-20, level=5, cuts="zoom", captions=True):
    words = words_in(transcript["words"], start, end)
    # --- keep-ranges: cut pauses > 0.45 s down to ~0.12 s (jump cuts keep pace)
    ranges = []
    if trim_silence and words:
        a = max(start, words[0]["s"] - 0.1)
        prev_e = words[0]["e"]
        for w in words[1:]:
            if w["s"] - prev_e > 0.45:
                ranges.append([a, prev_e + 0.08])
                a = w["s"] - 0.06
            prev_e = w["e"]
        ranges.append([a, min(end, prev_e + 0.25)])
    else:
        ranges = [[start, end]]

    track = _track(src, start, end) if layout == "fill" else None
    tight = 1.15 if len(ranges) > 1 and lv(level, 4) else 1.0
    fz, _ = fit(track, [1.0, tight + 0.03])   # one limit for the clip, so wide/tight stay distinct
    shots, t = [], 0.0
    zoom_state = 1.0
    hits = []
    for i, (a, b) in enumerate(ranges):
        d = b - a
        # alternate framing on each jump cut (wide / tight) like a 2-camera podcast edit
        if i > 0:
            zoom_state = tight if zoom_state == 1.0 else 1.0
        shots.append({"src": src, "out": [t, t + d], "src_in": a, "src_span": d, "profile": {"type": "const"},
                      "zoom": [zoom_state, zoom_state + 0.03], "fit_z": fz, "layout": layout, "track": track})
        t += d
    total = t

    def src_to_out(st):
        acc = 0.0
        for a, b in ranges:
            if st < a:
                return acc
            if st <= b:
                return acc + st - a
            acc += b - a
        return acc

    # punch-ins on strong words, (subtle) shake on the most intense ones
    for w in words:
        k = POLAR.get(w["w"].lower().strip(".,!?"), 0)
        if k >= 2.5 and lv(level, 4):
            hits.append({"t": src_to_out(w["s"]), "type": "punch", "amt": 0.08 * lv(level, 4), "dur": 0.45, "att": 0.04})
        if k >= 3 and lv(level, 8):
            hits.append({"t": src_to_out(w["s"]), "type": "shake", "amt": 0.35 * lv(level, 8), "dur": 0.25, "freq": 14})
    if lv(level, 3):
        hits.append({"t": 0.0, "type": "punch", "amt": 0.12 * lv(level, 3), "dur": 0.5})  # opening punch
    for sh in shots[1:]:   # every jump cut flows: a zoom cut (push in, land close, ease back) or a focus hunt
        c = sh["out"][0]
        if cuts == "zoom":
            hits.append({"t": c, "type": "zoomcut", "amt": 1.0, "att": 0.1, "dur": 0.28, "scale": 0.1})
        elif cuts == "focus":
            hits.append({"t": c, "type": "focus", "amt": 1.0, "att": 0.1, "dur": 0.32, "px": 10})

    # ---- audio
    full = load_audio(src, SR)
    segs = [full[:, int(a * SR):int(b * SR)] for a, b in ranges]
    voice = np.concatenate([A.fade(x, 0.008, 0.008) if x.shape[1] > 2 * int(0.008 * SR) else x for x in segs], axis=1)
    mix = voice.copy()
    if music:
        m = load_audio(music, SR)
        ms = int((music_start or 0) * SR)
        m = m[:, ms:ms + voice.shape[1]]
        if m.shape[1] < voice.shape[1]:
            m = np.pad(m, ((0, 0), (0, voice.shape[1] - m.shape[1])))
        m = A.fade(m, 0.5, 1.5) * 10 ** (music_db / 20) * 3.0   # the bed runs continuously under every jump cut
        g = A.duck_envelope(voice, depth_db=-10)
        mix += m * g[None, : m.shape[1]]
    if lv(level, 4):
        A.mix_sfx(mix, [(0.38, "whoosh", -4)], A.ref_db(voice))   # intro whoosh under the hook title
    mix = A.normalize(mix)
    os.makedirs(workdir, exist_ok=True)
    apath = os.path.join(workdir, "mix.wav")
    save_audio(apath, mix, SR)

    plan = {"fps": 30, "width": 1080, "height": 1920, "look": look, "duration": total, "shots": shots,
            "hits": hits, "audio": apath, "motion_blur": False, "edge": "blur",
            "captions": {"words": words, "source_time": True} if captions and captions_ok(transcript) else None}
    if title:
        plan["title"] = {"text": title, "t0": 0, "t1": min(total, 4.0), "y": 330}
    return plan


# =================================================================== VELOCITY / FAN EDIT
def edit_plan(sources, music, workdir, length=15.0, music_start=None, hook=None, look="teal_orange",
              letterbox=0.0, level=6, music_fx=None, shot_list=None):
    """sources: list of video paths. hook: optional {src, start, end, words} dialogue intro.
    shot_list: optional manual [{src, peak}] in priority order (otherwise auto by motion)."""
    ma = analyze(music)
    hook_len = (hook["end"] - hook["start"]) if hook else 0.0
    beat = 60.0 / ma["tempo"]
    if music_start is None:
        pre = hook_len + 0.05 if hook else min(3.5, length * 0.28)
        m0, _ = choose_window(ma, length, pre_drop=pre)
    else:
        m0 = music_start
    bar = 4 * beat   # end on a bar line, so the music finishes a phrase instead of stopping mid-bar
    length = max(bar, round(length / bar) * bar)
    m1 = m0 + length
    beats = [b - m0 for b in ma["beats"] if m0 - 1e-3 <= b < m1]
    downs = set(round(b - m0, 3) for b in ma["downbeats"] if m0 - 1e-3 <= b < m1)
    drop = ma["drop"] - m0
    if not (0 < drop < length):
        drop = beats[len(beats) // 4] if beats else length * 0.3

    # ---- candidate shots
    pool = []
    if shot_list:
        pool = [dict(x) for x in shot_list]
    else:
        for s in sources:
            for sh in detect_shots(s, probe(s)):
                if sh["slideshow"]:   # never cut photo slideshows into an edit
                    continue
                sh["src"] = s
                pool.append(sh)
        pool.sort(key=lambda x: -x["motion"])
    if not pool:
        raise RuntimeError("no usable video shots found (photo slideshows are skipped); find real footage")

    # ---- cut grid
    cuts = []
    if hook:
        cuts.append(0.0)
    pre_beats = [b for b in beats if b < drop - 1e-3] if not hook else []
    # pre-drop: cut every 2 beats (every bar below level 5); from level 7 the last half-bar cuts every beat
    step = 2 if level >= 5 else 4
    for i, b in enumerate(pre_beats):
        if i % step == 0 or (level >= 7 and b > drop - 2 * beat):
            cuts.append(b)
    cuts.append(drop)
    post = [b for b in beats if b > drop + 1e-3]
    # post-drop rhythm: from level 7 a hero (2 beats, velocity ramp) on every downbeat with 1-beat quick
    # cuts between; levels 4-6 cut every 2 beats; 1-3 every bar
    i = 0
    while i < len(post):
        cuts.append(post[i])
        i += (2 if round(post[i], 3) in downs else 1) if level >= 7 else 2 if level >= 4 else 4
    cuts = sorted(set(round(c, 3) for c in cuts if c < length - 0.2))
    if cuts[0] > 0:
        cuts.insert(0, 0.0)
    bounds = cuts + [length]

    shots_out, hits = [], []
    used = 0
    for si in range(len(bounds) - 1):
        o0, o1 = bounds[si], bounds[si + 1]
        d = o1 - o0
        is_hook = hook and si == 0
        if is_hook:
            tr = _track(hook["src"], hook["start"], hook["start"] + d)
            fz, zoom = fit(tr, [1.0, 1.08])
            shots_out.append({"src": hook["src"], "out": [o0, o1], "src_in": hook["start"], "src_span": d,
                              "profile": {"type": "const"}, "zoom": zoom, "fit_z": fz, "layout": "fill",
                              "track": tr, "voice": True})
            continue
        cand = pool[used % len(pool)]
        used += 1
        post_drop = o0 >= drop - 1e-3
        n_beats = d / beat
        if not post_drop:
            # build-up: smooth slow motion
            prof = {"type": "const", "speed": 0.45}
        elif level >= 7 and n_beats >= 1.7:   # pro velocity edits peak around 1.5-2x, not 4x
            prof = {"type": "ramp", "hi": 1.5 + 0.5 * lv(level, 7), "lo": 0.22, "k": 2.2}
        elif level >= 7:   # a kick that slides into slow-mo
            prof = {"type": "ease_in", "hi": 1.6, "lo": 0.35}
        elif level >= 4:   # clean: real time decelerating into slow-mo, no whiplash
            prof = {"type": "ease_in", "hi": 1.0, "lo": 0.4, "k": 2.0}
        else:
            prof = {"type": "const", "speed": 1.0}
        _, _, mean, _ = remap_table(prof)
        span = d * mean
        sh_s, sh_e = cand.get("start", 0), cand.get("end", 1e9)
        peak = cand.get("peak", (sh_s + min(sh_e, sh_s + 10)) / 2)
        src_in = peak - span * 0.5
        src_in = float(np.clip(src_in, sh_s, max(sh_s, sh_e - span)))
        info = probe(cand["src"])
        src_in = float(np.clip(src_in, 0, max(0, info["duration"] - span - 0.1)))
        tr = _track(cand["src"], src_in, src_in + span)
        fz, zoom = fit(tr, [1.0, 1.1])   # the same gentle push on every shot, toward the face
        shot = {"src": cand["src"], "out": [o0, o1], "src_in": src_in, "src_span": span, "profile": prof,
                "zoom": zoom, "fit_z": fz, "layout": "fill", "track": tr, "captions": False}
        if min(prof.get("lo", 1), prof.get("speed", 1)) < 0.5:
            shot["interp"] = "flow"  # optical-flow slow motion
        shots_out.append(shot)

    # ---- hits (effects choreography): every cut flows, extras switch on with the level (see lv())
    for c in bounds[1:-1]:
        on_down = round(c, 3) in downs
        if lv(level, 2):   # a quick focus-hunting cut, so the change of shot doesn't jar
            hits.append({"t": c, "type": "focus", "amt": 1.0, "att": 0.1, "dur": 0.3, "px": 11})
        if on_down and lv(level, 5):   # the old shot dips toward dark into a bar-line cut (a blink)
            hits.append({"t": c, "type": "black", "amt": 0.45 * lv(level, 5), "dur": 0.0001, "att": 0.12, "shape": "hold"})
        if on_down and c > drop + 0.1 and lv(level, 7):   # a short jolt on bar lines after the drop
            hits.append({"t": c, "type": "jolt", "amt": 0.5 * lv(level, 7), "att": 0.06, "dur": 0.3, "speed": 0.5})
        if on_down and c > drop + 0.1 and lv(level, 9):
            hits += [{"t": c, "type": "flash", "amt": 0.5 * lv(level, 9), "dur": 0.08},
                     {"t": c, "type": "shake", "amt": 0.6 * lv(level, 9), "dur": 0.25, "freq": 16, "px": 40}]
    for j, dbt in enumerate(sorted(d for d in downs if d > drop + 0.1)):   # transitions: hyper edits only
        if level >= 9 and j % 2 == 1:
            typ = ["zoom_in", "whip"][(j // 2) % 2]
            hits.append({"t": dbt, "type": typ, "amt": 1.0, "dur": 0.13, "att": 0.1, "dir": (-1) ** (j // 2)})
    # THE DROP: (level it switches on at, hit). At 4-6 the cut itself is the hit.
    drop_hits = [(4, {"t": drop, "type": "black", "amt": 1.0, "dur": 0.0001, "att": 0.12, "shape": "hold"}),
                 (6, {"t": drop, "type": "bloom", "amt": 0.6, "dur": 0.5}),
                 (7, {"t": drop, "type": "flash", "amt": 0.6, "dur": 0.15}),
                 (7, {"t": drop, "type": "shake", "amt": 0.7, "dur": 0.35, "freq": 16, "px": 40}),
                 (9, {"t": drop, "type": "rgb", "amt": 0.8, "dur": 0.3, "px": 26}),
                 (9, {"t": drop + beat, "type": "flicker", "amt": 0.5, "dur": beat * 0.9, "shape": "hold"})]
    hits += [dict(h, amt=h["amt"] * (1 if h["type"] == "black" else lv(level, on))) for on, h in drop_hits if lv(level, on)]
    # a clean close: the last beat fades to black while the music fades out
    hits.append({"t": length - 0.05, "type": "black", "amt": 1.0, "dur": 0.3, "att": min(0.8, beat), "shape": "hold"})

    # ---- audio
    m = load_audio(music, SR)
    if music_fx == "slowed":
        m = A.reverb(A.resample_speed(m, 0.85), 3.0, 0.3)
    elif music_fx == "sped":
        m = A.resample_speed(m, 1.25)
    seg = m[:, int(m0 * SR):int(m1 * SR)]
    mix = A.fade(seg, 0.05, 1.5)   # starts on a downbeat, ends on a bar line with a long fade: never abrupt
    if level >= 3:   # the low end falls away at the end
        mix = A.thin_out(mix, length - 0.8, 0.8)
    ref = A.ref_db(mix)
    ev = [(drop - 0.01, "drop")] * (level >= 3) + [(h["t"], A.SFX_FOR[h["type"]]) for h in hits
                                    if h["type"] in A.SFX_FOR and h["t"] > drop + 0.1]
    if hook:
        v = load_audio(hook["src"], SR)[:, int(hook["start"] * SR):int(hook["end"] * SR)]
        v = A.fade(v, 0.02, 0.06)
        vb = np.zeros_like(mix)
        A.place(vb, v * 1.6, 0.0)
        g = A.duck_envelope(vb, depth_db=-16)
        # music under hook sits low anyway until the drop
        pre = np.ones(mix.shape[1], np.float32)
        pre[: int(drop * SR)] = 0.35
        mix = mix * (g * pre)[None, :] + vb
        if level >= 5:
            ev.append((drop, "riser"))
    A.mix_sfx(mix, ev, ref)
    mix = A.normalize(mix)
    os.makedirs(workdir, exist_ok=True)
    apath = os.path.join(workdir, "mix.wav")
    save_audio(apath, mix, SR)

    plan = {"fps": 30, "width": 1080, "height": 1920, "look": look, "letterbox": letterbox,
            "duration": length, "shots": shots_out, "hits": hits, "audio": apath, "motion_blur": "flow",
            "music": {"path": music, "start": m0, "tempo": ma["tempo"], "drop": drop}}
    if hook and hook.get("words"):
        plan["captions"] = {"words": hook["words"], "source_time": True, "y": 0.68}
    return plan
