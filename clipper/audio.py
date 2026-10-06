"""Audio for edits: a generated, copyright-free SFX kit placed at levels relative to the music,
slowed+reverb / sped-up, music beds with sidechain-style ducking under dialogue, and loudness
normalisation to -14 LUFS."""
import functools
import os
import numpy as np

SR = 44100


def _lp(x, alpha):
    """One-pole lowpass with per-sample alpha (array or scalar)."""
    y = np.empty_like(x)
    acc = 0.0
    al = np.broadcast_to(alpha, x.shape)
    for i in range(len(x)):
        acc += al[i] * (x[i] - acc)
        y[i] = acc
    return y


def _sweep(rng, dur, a0, a1, shape):
    """Filtered-noise swell that brightens (lowpass a0 -> a1) and pans across: whoosh family."""
    n = int(dur * SR)
    t = np.linspace(0, 1, n)
    x = _lp(rng.normal(0, 1, n).astype(np.float32), (a0 + (a1 - a0) * t ** 2).astype(np.float32))
    x *= np.sin(np.pi * t ** shape) ** 2
    return np.stack([x * (1 - 0.4 * t), x * (0.6 + 0.4 * t)])


@functools.lru_cache(maxsize=None)
def sfx(kind, seed=0):
    """Generated sound effects: made from noise and sine waves here, so they're copyright-free."""
    rng = np.random.default_rng(seed)
    if kind == "whoosh":          # filtered noise swell, 0.45 s, peak near the end
        x = _sweep(rng, 0.45, 0.02, 0.37, 1.6)
    elif kind == "swoosh":        # shorter, brighter whoosh for whips and swipes
        x = _sweep(rng, 0.3, 0.05, 0.6, 1.3)
    elif kind == "swish":         # very short air flick for zoom-chain moves
        x = _sweep(rng, 0.16, 0.25, 0.9, 1.0)
    elif kind == "hit":           # short punchy thump + click, for slam text
        n = int(0.35 * SR)
        t = np.arange(n) / SR
        sub = np.sin(2 * np.pi * np.cumsum(60 + 120 * np.exp(-t * 40)) / SR) * np.exp(-t * 12)
        x = np.tanh(1.5 * sub + 0.4 * rng.normal(0, 1, n) * np.exp(-t * 400))
    elif kind == "drop":          # the drop: impact layered with an 808 boom
        x = sfx("impact", seed).copy()
        b = sfx("boom", seed)
        x = np.pad(x, ((0, 0), (0, b.shape[1] - x.shape[1]))) + 0.55 * b
    elif kind == "sub_drop":      # sine falling 100 -> 30 Hz
        n = int(1.6 * SR)
        t = np.arange(n) / SR
        x = np.tanh(1.6 * np.sin(2 * np.pi * np.cumsum(30 + 70 * np.exp(-t * 2.5)) / SR) * np.exp(-t * 1.5))
    elif kind == "downlifter":    # a riser played backwards: loud start, falling away
        x = sfx("riser", seed)[:, ::-1]
    elif kind == "reverse_cymbal":  # bright noise swelling into a hard stop (ends on the moment)
        n = int(1.5 * SR)
        t = np.arange(n) / SR
        w = rng.normal(0, 1, n).astype(np.float32)
        x = ((w - _lp(w, 0.3)) * np.exp(-t * 3))[::-1]
    elif kind == "glitch":        # bit-crushed square/noise stutter, 0.25 s
        n = int(0.25 * SR)
        t = np.arange(n) / SR
        step = (t * 40).astype(int)
        sq = np.sign(np.sin(2 * np.pi * np.where(step % 2, 900, 1700) * t))
        x = (0.6 * sq + 0.4 * np.round(rng.normal(0, 1, n) * 4) / 4) * (step % 3 != 2) * np.exp(-t * 6)
    elif kind == "rewind":        # tape-rewind chirp for boomerang / reverse shots
        n = int(0.7 * SR)
        t = np.linspace(0, 1, n)
        f = (300 + 2500 * t ** 2) * (1 + 0.08 * np.sin(2 * np.pi * 18 * t))
        w = rng.normal(0, 1, n).astype(np.float32)
        x = (0.5 * np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.3 * (w - _lp(w, 0.2))) * np.sin(np.pi * t) ** 0.5
    elif kind == "pop":           # bubble pop for pop-in text
        n = int(0.09 * SR)
        t = np.arange(n) / SR
        x = np.sin(2 * np.pi * np.cumsum(200 + 700 * np.exp(-t * 60)) / SR) * np.exp(-t * 45)
    elif kind == "click":         # UI click (subscribe button)
        n = int(0.03 * SR)
        t = np.arange(n) / SR
        x = (0.6 * np.sin(2 * np.pi * 3000 * t) + 0.4 * rng.normal(0, 1, n)) * np.exp(-t * 700)
    elif kind == "typing":        # one key press; vary `seed` per character
        n = int(0.05 * SR)
        t = np.arange(n) / SR
        w = rng.normal(0, 1, n).astype(np.float32)
        x = (_lp(w, 0.35) - _lp(w, 0.05)) * np.exp(-t * 250) + 0.3 * np.sin(2 * np.pi * 180 * t) * np.exp(-t * 120)
    elif kind == "impact":        # sub thump + noise crack, 1.2 s
        n = int(1.2 * SR)
        t = np.arange(n) / SR
        f = 35 + 90 * np.exp(-t * 18)
        sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.2)
        crack = _lp(rng.normal(0, 1, n).astype(np.float32), 0.5) * np.exp(-t * 30)
        x = np.tanh(1.8 * sub + 0.5 * crack)
    elif kind == "boom":          # 808-style long boom, 2 s
        n = int(2.0 * SR)
        t = np.arange(n) / SR
        f = 45 + 60 * np.exp(-t * 25)
        x = np.tanh(2.5 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.6))
    elif kind == "riser":         # 2 s noise + pitch sweep up, ends abruptly (lands on the drop)
        n = int(2.0 * SR)
        t = np.linspace(0, 1, n)
        noise = _lp(rng.normal(0, 1, n).astype(np.float32), (0.01 + 0.5 * t ** 2).astype(np.float32))
        tone = np.sin(2 * np.pi * np.cumsum(200 + 1800 * t ** 2) / SR) * 0.3
        x = (noise + tone) * t ** 2
    elif kind == "shutter":       # camera click for flash frames
        n = int(0.12 * SR)
        t = np.arange(n) / SR
        x = rng.normal(0, 1, n) * (np.exp(-t * 300) + 0.6 * np.exp(-np.maximum(t - 0.05, 0) * 300) * (t > 0.05))
    elif kind == "tape_stop":     # a short pitch down-sweep, for a fake-out before a drop
        n = int(0.6 * SR)
        t = np.linspace(0, 1, n)
        x = np.sin(2 * np.pi * np.cumsum(300 * (1 - t) ** 2 + 30) / SR) * (1 - t)
    else:
        raise ValueError(kind)
    if x.ndim == 1:
        x = np.stack([x, x])
    x = x.astype(np.float32)
    return x / (np.abs(x).max() + 1e-9) * 0.9


# Loudness of each sound relative to the loud parts of the music, in dB. Sounds sit well under
# the track: felt, not noticed. Even the drop stays 13 dB down; clicks and typing are near-subliminal.
SFX_DB = {"drop": -13, "impact": -15, "boom": -17, "sub_drop": -18, "hit": -20, "riser": -20, "tape_stop": -20,
          "whoosh": -20, "swoosh": -21, "rewind": -21, "reverse_cymbal": -21, "downlifter": -22,
          "swish": -24, "glitch": -24, "shutter": -26, "pop": -26, "click": -27, "typing": -32}
# Seconds a sound starts before its moment, so its peak (or its end, for swells) lands on the beat.
SFX_LEAD = {"whoosh": 0.38, "swoosh": 0.22, "swish": 0.1, "riser": 2.0, "reverse_cymbal": 1.5,
            "shutter": -0.02, "glitch": 0.02}
SWELLS = ("riser", "reverse_cymbal", "downlifter")   # long beds: always layered, never de-duplicated
# The sound each transition gets by default.
SFX_FOR = {"zoom_in": "whoosh", "spin": "whoosh", "whip": "swoosh", "bounce": "swoosh", "ripple": "swish", "zoom_out": "downlifter",
           "glitch": "glitch", "jolt": "glitch"}


def _rms_db(x, floor=0.05):
    """Loudness (dBFS) of the audible part of x: samples above `floor` x its peak."""
    m = np.abs(x).max(axis=0)
    a = x[:, m > floor * (m.max() + 1e-9)]
    return 10 * np.log10(float((a ** 2).mean()) + 1e-12)


def ref_db(bus):
    """Reference loudness of a track: its loud parts (90th percentile of 100 ms RMS), in dBFS."""
    mono = bus.mean(axis=0)
    n = SR // 10
    k = max(1, len(mono) // n)
    r = np.sqrt((mono[:k * n].reshape(k, -1) ** 2).mean(axis=1) + 1e-12)
    return 20 * np.log10(float(np.percentile(r, 90)) + 1e-9)


def mix_sfx(bus, events, ref, gap=0.12):
    """Place events [(t, kind) or (t, kind, trim_db)] on `bus` at SFX_DB relative to `ref` dBFS.
    Two short sounds within `gap` s of each other don't stack: only the louder one plays."""
    placed = []
    for ev in sorted(events, key=lambda e: -SFX_DB[e[1]]):
        t, kind = ev[0], ev[1]
        lvl = SFX_DB[kind] + (ev[2] if len(ev) > 2 else 0.0)
        if kind not in SWELLS and any(abs(t - pt) < gap and pl > lvl for pt, pl in placed):
            continue
        clip = sfx(kind, int(ev[3]) if len(ev) > 3 else 0)
        place(bus, clip, t - SFX_LEAD.get(kind, 0.0), 10 ** ((ref + lvl - _rms_db(clip)) / 20))
        if kind not in SWELLS:
            placed.append((t, lvl))


def write_sfx_pack(folder):
    from .media import save_audio
    os.makedirs(folder, exist_ok=True)
    for k in SFX_DB:
        save_audio(os.path.join(folder, f"{k}.wav"), sfx(k), SR)


def reverb(x, decay=3.0, wet=0.32, seed=1):
    """Convolution reverb with a synthetic exponentially-decaying stereo IR."""
    from scipy.signal import fftconvolve
    rng = np.random.default_rng(seed)
    n = int(decay * SR)
    t = np.arange(n) / SR
    env = np.exp(-6.9 * t / decay)
    out = np.empty_like(x)
    for c in range(x.shape[0]):
        ir = (rng.normal(0, 1, n) * env).astype(np.float32)
        ir[: int(0.02 * SR)] = 0  # pre-delay
        ir /= np.sqrt((ir ** 2).sum())
        wetc = fftconvolve(x[c], ir)[: x.shape[1]]
        out[c] = (1 - wet) * x[c] + wet * wetc * 0.6
    return out


def resample_speed(x, factor):
    """Vinyl-style speed change (pitch follows). factor<1 = slowed, >1 = sped up."""
    n = int(x.shape[1] / factor)
    idx = np.linspace(0, x.shape[1] - 1, n)
    return np.stack([np.interp(idx, np.arange(x.shape[1]), c) for c in x]).astype(np.float32)


def dip(x, t0, t1, db=-18.0, ramp=0.015):
    """Duck the whole bus by `db` between t0 and t1 s (short ramps, no clicks): the pocket of
    near-silence editors leave right before a drop or a big cut."""
    s, e, r = int(max(0, t0) * SR), int(max(0, t1) * SR), int(ramp * SR)
    if e <= s or s >= x.shape[1]:
        return x
    g = np.ones(x.shape[1], np.float32)
    lo = 10 ** (db / 20)
    g[s:e] = lo
    g[max(0, s - r):s] = np.linspace(1, lo, s - max(0, s - r))
    g[e:e + r] = np.linspace(lo, 1, len(g[e:e + r]))
    return x * g


def thin_out(x, at, dur=0.8):
    """From `at` s on, progressively cut the low end (bass falls away as the edit ends)."""
    s = int(max(0, at) * SR)
    if s >= x.shape[1]:
        return x
    tail = x[:, s:]
    low = np.stack([_lp(c.astype(np.float32), 0.02) for c in tail])   # ~140 Hz one-pole lowpass
    ramp = np.clip(np.arange(tail.shape[1]) / max(1, int(dur * SR)), 0, 1) ** 2
    y = x.copy()
    y[:, s:] = tail - low * ramp
    return y


def fade(x, fin=0.0, fout=0.0):
    x = x.copy()
    if fin:
        n = int(fin * SR)
        x[:, :n] *= np.linspace(0, 1, n)
    if fout:
        n = int(fout * SR)
        x[:, -n:] *= np.linspace(1, 0, n)
    return x


def duck_envelope(voice, depth_db=-18, attack=0.015, release=0.3, thresh=0.02):
    """Gain envelope for the music that dips whenever `voice` is active (sidechain)."""
    v = np.abs(voice).max(axis=0)
    win = int(0.03 * SR)
    lvl = np.sqrt(np.convolve(v ** 2, np.ones(win) / win, mode="same"))
    target = np.where(lvl > thresh, 10 ** (depth_db / 20), 1.0).astype(np.float32)
    # attack/release smoothing, done at 1 kHz control rate for speed
    step = SR // 1000
    ctl = target[::step]
    g = np.empty_like(ctl)
    acc = 1.0
    ka, kr = 1 - np.exp(-1 / (attack * 1000)), 1 - np.exp(-1 / (release * 1000))
    for i, tv in enumerate(ctl):
        acc += (tv - acc) * (ka if tv < acc else kr)
        g[i] = acc
    return np.repeat(g, step)[: voice.shape[1]]


def place(bus, clip, at, gain=1.0):
    s = int(at * SR)
    if s >= bus.shape[1]:
        return
    if s < 0:
        clip = clip[:, -s:]
        s = 0
    n = min(clip.shape[1], bus.shape[1] - s)
    bus[:, s:s + n] += clip[:, :n] * gain


def normalize(x, lufs=-14.0, peak_db=-1.0):
    import pyloudnorm as pyln
    meter = pyln.Meter(SR)
    try:
        loud = meter.integrated_loudness(x.T)
        x = x * 10 ** ((lufs - loud) / 20)
    except Exception:
        pass
    lim = 10 ** (peak_db / 20)
    knee = 0.7 * lim   # soft-knee limiter: untouched below the knee, smoothly capped at `lim` above it
    a = np.abs(x)
    over = a > knee
    x = np.where(over, np.sign(x) * (knee + (lim - knee) * np.tanh((a - knee) / (lim - knee))), x)
    return x.astype(np.float32)


if __name__ == "__main__":   # self-check: python -m clipper.audio
    music = np.random.default_rng(9).normal(0, 0.1, (2, SR * 4)).astype(np.float32)
    ref = ref_db(music)
    for kind, t in (("whoosh", 1.0), ("typing", 3.0)):
        bus = np.zeros_like(music)
        mix_sfx(bus, [(t, kind)], ref)
        got = _rms_db(bus)
        assert abs(got - (ref + SFX_DB[kind])) < 0.5, (kind, got, ref + SFX_DB[kind])
    bus = np.zeros_like(music)
    mix_sfx(bus, [(2.0, "drop"), (2.05, "hit"), (2.0, "riser")], ref)   # hit is swallowed, riser layers
    alone = np.zeros_like(music)
    mix_sfx(alone, [(2.0, "drop"), (2.0, "riser")], ref)
    assert np.allclose(bus, alone)
    assert np.array_equal(sfx("glitch"), sfx.__wrapped__("glitch"))     # deterministic
    loud = normalize(np.concatenate([music * 8, music], axis=1))           # limiter never clips
    assert np.abs(loud).max() <= 10 ** (-1 / 20) + 1e-6
    print("audio self-check OK")
