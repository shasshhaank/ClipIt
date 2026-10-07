"""Learning from reference edits: measure a clip's style (study), find a clip's raw moment inside the full video
(locate), and fit a colour LUT to a reference's grade (match_look)."""
import json
import os
import re
import subprocess
import sys

import cv2
import numpy as np

from .media import FFMPEG, load_audio, probe


# ------------------------------------------------------------------------- study
def _fetch(src, d):
    """The clip as d/video.mp4 (a local file is linked) and its platform metadata."""
    os.makedirs(d, exist_ok=True)
    vid = os.path.join(d, "video.mp4")
    if os.path.exists(src):
        if not os.path.exists(vid):
            os.symlink(os.path.abspath(src), vid)
        return vid, {"title": os.path.basename(src)}
    if not src.startswith(("https://", "http://")):   # never pass anything but a web link to yt-dlp
        raise ValueError(f"not a file or web link: {src}")
    j = subprocess.run([sys.executable, "-m", "yt_dlp", "--no-warnings", "-J", "--", src], capture_output=True, text=True)
    m = json.loads(j.stdout) if j.returncode == 0 and j.stdout.strip() else {}
    meta = {k: m.get(k) for k in ("title", "channel", "view_count", "duration", "webpage_url")}
    if not os.path.exists(vid):
        subprocess.run([sys.executable, "-m", "yt_dlp", "--no-warnings", "-q", "-f", "bv*[height<=1920]+ba/b",
                        "--merge-output-format", "mp4", "-o", vid, "--", src], check=True)
        from .ytsubs import save
        save(src, vid)   # its own subtitles, so --transcribe needs no speech model
    return vid, meta


def _colour(vid):
    """Look per half second, sustained grade changes (the drop) and black-and-white stretches."""
    cap = cv2.VideoCapture(vid)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    rows, i = [], 0
    while True:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, f = cap.read()
        if not ok:
            break
        f = cv2.resize(f, (240, int(240 * f.shape[0] / f.shape[1]))).astype(np.float32) / 255
        b, g, r = f[..., 0], f[..., 1], f[..., 2]
        y = 0.114 * b + 0.587 * g + 0.299 * r
        rows.append({"t": round(i / fps, 2), "luma": float(y.mean()), "contrast": float(y.std()),
                     "sat": float(cv2.cvtColor((f * 255).astype(np.uint8), cv2.COLOR_BGR2HSV)[..., 1].mean() / 255),
                     "warm": float((r - b).mean()), "magenta": float(((r + b) / 2 - g).mean())})
        i += max(1, int(fps / 2))
    a = {k: np.array([x[k] for x in rows]) for k in rows[0]}
    shifts = []
    for i in range(2, len(rows) - 2):   # ~1 s either side, so ordinary cuts between similar shots don't count
        d = {k: a[k][i:i + 2].mean() - a[k][i - 2:i].mean() for k in ("sat", "magenta", "warm")}
        if abs(d["sat"]) / 0.15 + abs(d["magenta"]) / 0.06 + abs(d["warm"]) / 0.12 > 1.6 and \
                (not shifts or rows[i]["t"] - shifts[-1][0] > 1.5):
            kind = ("to black and white" if a["sat"][i:i + 2].mean() < 0.1 else "cooler" if d["warm"] < -0.08 else
                    "warmer" if d["warm"] > 0.08 else "more magenta" if d["magenta"] > 0.04 else
                    "desaturated" if d["sat"] < -0.12 else "more saturated" if d["sat"] > 0.12 else "tint change")
            shifts.append((rows[i]["t"], kind))
    med = {k: float(np.median(a[k])) for k in ("luma", "contrast", "sat", "warm", "magenta")}
    words = ["bright" if med["luma"] > 0.5 else "dark" if med["luma"] < 0.33 else "mid exposure",
             "punchy contrast" if med["contrast"] > 0.24 else "soft contrast" if med["contrast"] < 0.16 else "normal contrast",
             "saturated" if med["sat"] > 0.45 else "muted" if med["sat"] < 0.25 else "moderate saturation",
             "warm" if med["warm"] > 0.06 else "cool" if med["warm"] < -0.02 else "neutral"]
    words += ["pink cast"] * (med["magenta"] > 0.03) + ["green cast"] * (med["magenta"] < -0.03)
    bw = [x["t"] for x in rows if x["sat"] < 0.08 and x["luma"] > 0.08]
    return ", ".join(words), shifts, bw


def _sound(vid):
    """Loudness, music stops, drop candidates, tempo and whether a music bed runs under it."""
    from .beats import analyze
    x = load_audio(vid, 22050, mono=True)[0]
    if len(x) < 22050:
        return {}
    w = 2205   # 100 ms
    db = 20 * np.log10(np.sqrt((x[:len(x) // w * w].reshape(-1, w) ** 2).mean(1)) + 1e-9)
    quiet = db < np.median(db) - 18
    stops, i = [], 0
    while i < len(quiet):
        j = i
        while j < len(quiet) and quiet[j]:
            j += 1
        if j - i >= 3:
            stops.append(f"{i * 0.1:.1f}s ({(j - i) * 0.1:.1f}s)")
        i = j + 1
    spec = np.abs(np.fft.rfft(x[:len(x) // 4096 * 4096].reshape(-1, 4096) * np.hanning(4096), axis=1))
    sub = float(np.median((spec[:, :int(120 / (22050 / 4096))] ** 2).sum(1) / ((spec ** 2).sum(1) + 1e-9)))
    a = analyze(vid)
    return {"stops": stops, "tempo": round(a["tempo"]), "drops": [round(t, 2) for t in a["drop_candidates"][:3]],
            "bed": "music bed under it" if sub > 0.12 else "dialogue-led, little or no music"}


def study(inputs, out, transcribe=False):
    """Measure reference clips: out/<name>/report.md, 1 fps sheets and caption crops, plus out/summary.md."""
    from .story import scene_cuts
    rows = []
    for n, src in enumerate(inputs):
        m = re.search(r"(?:v=|shorts/|youtu\.be/|reel/|video/)([\w-]{6,})", src)
        name = m.group(1) if m else os.path.splitext(os.path.basename(src))[0] or f"clip{n}"
        d = os.path.join(out, name)
        print(f"[{n + 1}/{len(inputs)}] {name}")
        try:
            vid, meta = _fetch(src, d)
        except (ValueError, subprocess.CalledProcessError) as e:
            print(f"  ! skipped: {e}")
            continue
        info, cuts = probe(vid), scene_cuts(vid, d)
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", vid, "-vf", "fps=1,scale=300:-2,tile=6x2:padding=4:color=white",
                        os.path.join(d, "sheet_%02d.jpg")], check=True)   # tile n = second n
        cap, bands = cv2.VideoCapture(vid), []
        for t in np.linspace(0.6, max(0.7, info["duration"] - 0.6), 8):   # the caption zone at 8 moments
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, f = cap.read()
            if ok:
                b = cv2.resize(f[int(f.shape[0] * 0.22):int(f.shape[0] * 0.78)], (540, int(540 * f.shape[0] * 0.56 / f.shape[1])))
                cv2.putText(b, f"{t:.1f}s", (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
                bands.append(b)
        if bands:
            cv2.imwrite(os.path.join(d, "captions.jpg"), np.vstack(bands))
        look, shifts, bw = _colour(vid)
        snd = _sound(vid)
        speech = ""
        if transcribe:
            from .transcribe import transcribe as tr
            words = tr(vid, d)["words"]
            speech = f"{len(words) / max(info['duration'], 1):.1f} words/s, first word at {words[0]['s'] if words else '-'}s"
        aspect = min({"9:16": 9 / 16, "3:4": 3 / 4, "4:5": 4 / 5, "1:1": 1, "16:9": 16 / 9}.items(),
                     key=lambda kv: abs(kv[1] - info["width"] / info["height"]))[0]
        report = f"""# {meta.get('title') or name}
{info['duration']:.1f}s · {aspect} ({info['width']}x{info['height']}){f" · {meta['view_count']:,} views" if meta.get('view_count') else ""}

## Measured
- **Pacing:** {len(cuts)} cuts, one every {info['duration'] / (len(cuts) + 1):.1f}s; at {', '.join(f'{c:.1f}' for c in cuts) or 'none'}
- **Look:** {look}
- **Grade changes:** {', '.join(f'{t}s {k}' for t, k in shifts) or 'none'}
- **Black and white:** {f'{len(bw)} half-seconds from {bw[0]}s' if bw else 'none'}
- **Sound:** {snd.get('bed', '?')}; tempo ~{snd.get('tempo', '?')} bpm; drop candidates {', '.join(map(str, snd.get('drops', []))) or 'none'}; music stops {', '.join(snd.get('stops', [])) or 'none'}
- **Speech:** {speech or 'not transcribed (--transcribe)'}

## Fill in by eye (sheet_*.jpg: tile n = second n; captions.jpg)
- Hook (first 2 s) · structure and beats with times · captions (font, case, words per screen, colours and what
  they mean, animation) · framing · effects (zooms, flashes, freezes, slow motion, emoji, glowing eyes) · the grade
  and what changes at the payoff · sound (genre, where the music stops and drops, sound effects) · the recipe in
  3-5 steps · which ClipIt fields rebuild it
"""
        open(os.path.join(d, "report.md"), "w").write(report)
        rows.append(f"| {(meta.get('title') or name)[:40]} | {info['duration']:.0f}s | {aspect} | "
                    f"{len(cuts) / info['duration']:.2f} | {look} | {snd.get('bed', '?')} | {', '.join(map(str, snd.get('drops', [])[:2]))} |")
    if rows:
        open(os.path.join(out, "summary.md"), "w").write(
            "# Reference summary\n\n| clip | length | aspect | cuts/s | look | sound | drop |\n|---|---|---|---|---|---|---|\n"
            + "\n".join(rows) + "\n")
        print("summary:", os.path.join(out, "summary.md"))


# ------------------------------------------------------------------------- locate
def locate(long, short, probes=((0.2, 2.0), (3.0, 5.0), (7.0, 9.0))):
    """Where windows of a short clip's audio occur inside a long source (audio cross-correlation), as
    [(t0, t1, time in long, score)]. Steady offsets mean continuous footage; a score over ~40 is a sure match."""
    sr = 8000
    L, Q = load_audio(long, sr, mono=True)[0], load_audio(short, sr, mono=True)[0]
    n = 1 << int(np.ceil(np.log2(len(L) + sr * 10)))
    FL = np.fft.rfft(L, n)
    energy = np.cumsum(np.concatenate([[0], L.astype(np.float64) ** 2]))
    out = []
    for t0, t1 in probes:
        q = Q[int(t0 * sr):int(t1 * sr)]
        if len(q) < sr // 2:
            continue
        q = (q - q.mean()) / (q.std() + 1e-9)
        c = np.fft.irfft(FL * np.conj(np.fft.rfft(q, n)), n)[:len(L) - len(q)]
        c = c / (np.sqrt(energy[len(q):len(q) + len(c)] - energy[:len(c)]) + 1e-6)
        i = int(np.argmax(c))
        out.append((t0, t1, i / sr, float(c[i])))
    return out


# ------------------------------------------------------------------------- match_look
def _frame(path, t):
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, f = cap.read()
    if not ok:
        raise ValueError(f"can't read {path} at {t}s")
    return f


def _align(ref, src):
    """src warped onto ref's framing (feature matching), and where the warp is valid; None if they don't match."""
    orb = cv2.ORB_create(6000)
    k1, d1 = orb.detectAndCompute(cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY), None)
    k2, d2 = orb.detectAndCompute(cv2.cvtColor(src, cv2.COLOR_BGR2GRAY), None)
    if d1 is None or d2 is None:
        return None
    m = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d2, d1)
    if len(m) < 30:
        return None
    M, inl = cv2.estimateAffinePartial2D(np.float32([k2[x.queryIdx].pt for x in m]),
                                         np.float32([k1[x.trainIdx].pt for x in m]), method=cv2.RANSAC)
    if M is None or inl.sum() < 25:
        return None
    size = (ref.shape[1], ref.shape[0])
    valid = cv2.warpAffine(np.ones(src.shape[:2], np.uint8), M, size) > 0
    return cv2.warpAffine(src, M, size, flags=cv2.INTER_AREA), cv2.erode(valid.astype(np.uint8), np.ones((15, 15))) > 0


def _rgb(bgr):
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).reshape(-1, 3).astype(np.float32) / 255


def _grid(n=33):
    g = np.linspace(0, 1, n)
    B, G, R = np.meshgrid(g, g, g, indexing="ij")   # .cube order: red changes fastest
    return np.stack([R.ravel(), G.ravel(), B.ravel()], 1)


def _fit_paired(X, Y):
    """Per-channel tone curves plus a root-polynomial colour matrix, refitted while dropping outliers (captions,
    stickers), baked onto the LUT grid."""
    def feats(Z):
        r, g, b = Z[:, 0], Z[:, 1], Z[:, 2]
        return np.stack([r, g, b, np.sqrt(r * g), np.sqrt(g * b), np.sqrt(r * b), np.ones_like(r)], 1)
    keep, bins = np.ones(len(X), bool), np.linspace(0, 1, 33)
    centres = (bins[:-1] + bins[1:]) / 2
    for _ in range(4):
        curves = []
        for c in range(3):
            idx = np.clip(np.digitize(X[keep, c], bins) - 1, 0, 31)
            med = np.array([np.median(Y[keep, c][idx == b]) if (idx == b).sum() > 50 else np.nan for b in range(32)])
            ok = ~np.isnan(med)
            curves.append(np.maximum.accumulate(np.interp(centres, centres[ok], med[ok])))   # monotone
        tone = lambda Z: np.clip(np.stack([np.interp(Z[:, c], centres, curves[c]) for c in range(3)], 1), 1e-4, 1)
        M = np.linalg.lstsq(feats(tone(X[keep])), Y[keep], rcond=None)[0]
        err = np.abs(feats(tone(X)) @ M - Y).sum(1)
        keep = err < max(np.percentile(err[keep], 85), 0.04)
    return np.clip(feats(tone(_grid())) @ M, 0, 1)


def _fit_stats(X, Y):
    """Overall tone and tint transfer (Lab mean and spread), baked onto the LUT grid."""
    lab = lambda Z: cv2.cvtColor(Z.reshape(-1, 1, 3).astype(np.float32), cv2.COLOR_RGB2Lab).reshape(-1, 3)
    lx, ly = lab(X), lab(Y)
    out = (lab(_grid()) - lx.mean(0)) / (lx.std(0) + 1e-6) * ly.std(0) + ly.mean(0)
    return np.clip(cv2.cvtColor(out.reshape(-1, 1, 3).astype(np.float32), cv2.COLOR_Lab2RGB).reshape(-1, 3), 0, 1)


def match_look(ref, src, out, pairs=None, ref_times=None, src_times=None, check=None):
    """Fit a .cube LUT that makes `src` footage look like `ref`. With `pairs` [(ref_t, src_t)] showing the same
    moment (the reference edit used this footage; `locate` finds the times) the fit is near exact; otherwise
    `ref_times`/`src_times` match the overall tone and tint. `check` writes source | graded | reference strips."""
    from .fx import apply_lut, load_cube
    X, Y, shown = [], [], []
    if pairs:
        rng = np.random.default_rng(0)
        for rt, st in pairs:
            ref_f = _frame(ref, rt)
            best = None
            for dt in (-2, -1, 0, 1, 2):   # allow a frame or two of drift
                a = _align(ref_f, _frame(src, st + dt / 30))
                if a is not None:
                    diff = np.abs(ref_f.astype(int) - a[0].astype(int)).mean(2)[a[1]].mean()
                    best = min(best, (diff, a), key=lambda x: x[0]) if best else (diff, a)
            if best is None:
                print(f"  ! skipped {rt}:{st}, the frames don't line up")
                continue
            warped, valid = best[1]
            idx = rng.choice(np.flatnonzero(valid.ravel()), min(int(valid.sum()), 60000), replace=False)
            X.append(_rgb(warped)[idx])
            Y.append(_rgb(ref_f)[idx])
            shown.append((warped, ref_f))
        if not X:
            raise ValueError("no frame pairs lined up; check the times, or use ref_times/src_times")
        lut = _fit_paired(np.concatenate(X), np.concatenate(Y))
    else:
        X = np.concatenate([_rgb(cv2.resize(_frame(src, t), (480, 270))) for t in src_times])
        Y = np.concatenate([_rgb(cv2.resize(_frame(ref, t), (270, 480))) for t in ref_times])
        lut = _fit_stats(X, Y)
        shown = [(_frame(src, src_times[0]), _frame(ref, ref_times[0]))]
    with open(out, "w") as f:
        f.write("LUT_3D_SIZE 33\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n" + "".join(f"{r:.6f} {g:.6f} {b:.6f}\n" for r, g, b in lut))
    if check:
        L = load_cube(out)
        fit = lambda im: cv2.resize(im, (360, int(360 * im.shape[0] / im.shape[1])))
        cv2.imwrite(check, np.vstack([np.hstack([fit(s), fit(apply_lut(s, L)), cv2.resize(r, (360, fit(s).shape[0]))])
                                      for s, r in shown[:4]]))
    return out
