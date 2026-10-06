"""Find the most clippable / polarizing moments.

Two signals:
  * speech: transcript windows scored for hook strength, polarizing language, emotional
    intensity, numbers/stakes, questions, loudness peaks and laughter-like energy bursts.
  * visual: shots scored by motion + loudness (for music edits with no dialogue).
The ranked list is a shortlist. The final pick is made by reading the candidates (Claude in the loop).
"""
import re
import cv2
import numpy as np

POLAR = {  # word -> weight
    # absolutes & confrontation
    "never": 2, "always": 1.5, "nobody": 2, "everyone": 1.5, "everybody": 1.5, "worst": 2.5, "best": 1.5,
    "hate": 2.5, "wrong": 2, "lie": 2.5, "lying": 2.5, "liar": 3, "fake": 2.5, "overrated": 3, "underrated": 2,
    "stupid": 2.5, "idiot": 3, "trash": 3, "garbage": 3, "disrespect": 3, "disrespectful": 3, "goat": 2.5,
    "truth": 2, "honestly": 1, "controversial": 3, "unpopular": 3, "opinion": 1, "fight": 2, "beef": 3,
    "war": 1.5, "kill": 1.5, "die": 1.5, "dead": 1.5, "crazy": 1.5, "insane": 2, "ridiculous": 2,
    "shut": 1.5, "fired": 2, "quit": 2, "cheat": 3, "cheated": 3, "cheating": 3, "divorce": 3, "broke": 2,
    "millions": 2, "billion": 2.5, "billionaire": 2.5, "rich": 1.5, "poor": 1.5, "money": 1.5,
    "secret": 2, "exposed": 3, "scam": 3, "problem": 1, "racist": 3, "women": 1.5, "men": 1, "god": 1.5,
    "refuse": 2, "won't": 1, "can't": 0.5, "should": 0.5, "must": 1, "disagree": 2.5, "ruined": 2.5,
    "mistake": 2, "regret": 2.5, "shocked": 2, "embarrassing": 2.5, "toxic": 3, "respect": 1.5,
}
PHRASES = {"i don't care": 3, "let me tell you": 2, "the truth is": 3, "here's the thing": 2.5,
           "no one talks about": 3, "nobody talks about": 3, "i'm gonna be honest": 2.5, "to be honest": 1.5,
           "hot take": 3, "the problem is": 2, "you're wrong": 3, "that's not true": 3, "shut up": 3,
           "are you serious": 2.5, "what are you talking about": 3, "i'll never": 3, "i will never": 3,
           "number one": 1.5, "of all time": 2.5, "the reason why": 1.5, "the biggest": 2}
HOOK_OPENERS = ("the truth", "nobody", "no one", "i never", "here's", "let me", "you're", "if you",
                "the problem", "i hate", "this is why", "stop", "why", "what", "everyone", "the worst", "the best")


def _rms_curve(audio_mono, sr, hop=0.1):
    n = int(sr * hop)
    k = len(audio_mono) // n
    a = audio_mono[: k * n].reshape(k, n)
    return np.sqrt((a ** 2).mean(axis=1) + 1e-12)


def sentence_units(words, gap=0.6):
    """Group words into sentence-ish units using punctuation and pauses."""
    units, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        end_p = w["w"].endswith((".", "?", "!"))
        pause = nxt is not None and nxt["s"] - w["e"] > gap
        if end_p or pause or nxt is None:
            units.append({"s": cur[0]["s"], "e": cur[-1]["e"], "text": " ".join(x["w"] for x in cur), "words": cur})
            cur = []
    return units


def score_text(text):
    t = text.lower()
    toks = re.findall(r"[a-z']+", t)
    s = sum(POLAR.get(x, 0) for x in toks)
    s += sum(v * t.count(p) for p, v in PHRASES.items())
    s += 1.2 * t.count("?") + 0.8 * t.count("!")
    s += 0.8 * len(re.findall(r"\b\d[\d,.]*\s?(%|percent|million|billion|k\b|years?)", t))
    s += 0.6 * len(re.findall(r"\b(you|your)\b", t)) ** 0.5  # direct address
    return s


def speech_candidates(transcript, audio_mono=None, sr=16000, min_len=18, max_len=55, top=8):
    words = transcript["words"]
    if not words:
        return []
    units = sentence_units(words)
    rms = None
    if audio_mono is not None:
        rms = _rms_curve(audio_mono, sr)
        rms = (rms - np.median(rms)) / (np.std(rms) + 1e-9)
    cands = []
    for i in range(len(units)):
        for j in range(i, len(units)):
            s, e = units[i]["s"], units[j]["e"]
            L = e - s
            if L > max_len:
                break
            if L < min_len:
                continue
            text = " ".join(u["text"] for u in units[i:j + 1])
            n_words = sum(len(u["words"]) for u in units[i:j + 1])
            pol = score_text(text) / (L / 30) ** 0.5   # density, mildly length-normalised
            hook = 2.0 * score_text(units[i]["text"]) + (3 if units[i]["text"].lower().startswith(HOOK_OPENERS) else 0)
            pace = min(n_words / L, 4.0)          # words/sec; energetic talk ~3+
            energy = 0.0
            if rms is not None:
                seg = rms[int(s * 10): int(e * 10)]
                if len(seg):
                    energy = float(np.mean(np.sort(seg)[-max(1, len(seg) // 8):]))  # loud peaks
            ending = 1.5 if units[j]["text"].rstrip().endswith(("?", "!", ".")) else 0
            score = pol + 0.6 * hook + 0.8 * pace + 1.2 * energy + ending
            cands.append({"start": round(s, 2), "end": round(e, 2), "score": round(score, 2),
                          "hook": units[i]["text"], "text": text})
    cands.sort(key=lambda c: -c["score"])
    picked = []
    for c in cands:  # non-overlapping
        if all(c["end"] <= p["start"] or c["start"] >= p["end"] for p in picked):
            picked.append(c)
        if len(picked) >= top:
            break
    return picked


def hook_lines(transcript, max_len=7.0, top=10):
    """Short punchy single lines (2-7s) to open a music edit with a quote."""
    units = sentence_units(transcript["words"], gap=0.45)
    res = []
    for u in units:
        L = u["e"] - u["s"]
        if 1.2 <= L <= max_len and len(u["words"]) >= 3:
            res.append({"start": round(u["s"], 2), "end": round(u["e"], 2),
                        "score": round(score_text(u["text"]) / max(L, 2) ** 0.3, 2), "text": u["text"]})
    res.sort(key=lambda r: -r["score"])
    return res[:top]


# ---------------------------------------------------------------- visual shots
SLIDESHOW_RATIO = 0.15   # measured: photo slideshows 0.02-0.03; real broadcast, studio and news video 0.4-2.8


def side_sharpness(gray):
    """Sharpness of the left and right fifths relative to the centre. Photo slideshows and re-uploads
    put a sharp picture between blurred copies of itself, which drives this far below real footage."""
    w = gray.shape[1]
    lap = lambda a: float(cv2.Laplacian(a, cv2.CV_32F).var())
    return (lap(gray[:, : w // 5]) + lap(gray[:, w - w // 5:]) + 1) / (2 * lap(gray[:, int(w * .3):int(w * .7)]) + 1)


def looks_like_slideshow(src, t0, t1, n=4):
    """True when a source window has the slideshow layout (sharp centre, blurred sides)."""
    cap = cv2.VideoCapture(src)
    r = []
    for t in np.linspace(t0, t1, n + 2)[1:-1]:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, f = cap.read()
        if ok:
            r.append(side_sharpness(cv2.cvtColor(cv2.resize(f, (480, 270)), cv2.COLOR_BGR2GRAY)))
    cap.release()
    return bool(r) and float(np.median(r)) < SLIDESHOW_RATIO


def shots(src, info, sample_fps=6, scene_thresh=27.0):
    """Detect shots and score each by motion intensity (for velocity edits). Shots with the photo
    slideshow layout are marked `slideshow` and should never be used."""
    from scenedetect import detect, ContentDetector
    scenes = detect(src, ContentDetector(threshold=scene_thresh), show_progress=False)
    bounds = [(a.get_seconds(), b.get_seconds()) for a, b in scenes] or [(0.0, info["duration"])]
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, int(round(fps / sample_fps)))
    motion, prev, idx, times, sides = [], None, 0, [], []
    while True:
        ok = cap.grab()
        if not ok:
            break
        if idx % step == 0:
            _, f = cap.retrieve()
            g = cv2.cvtColor(cv2.resize(f, (160, 90)), cv2.COLOR_BGR2GRAY).astype(np.float32)
            motion.append(0.0 if prev is None else float(np.mean(np.abs(g - prev))))
            sides.append(side_sharpness(cv2.cvtColor(cv2.resize(f, (480, 270)), cv2.COLOR_BGR2GRAY)))
            times.append(idx / fps)
            prev = g
        idx += 1
    cap.release()
    motion, times, sides = np.array(motion), np.array(times), np.array(sides)
    out = []
    for a, b in bounds:
        m = motion[(times >= a + 0.1) & (times < b - 0.1)]
        if b - a < 0.4 or len(m) == 0:
            continue
        inside = (times >= a) & (times < b)
        peak_t = float(times[inside][np.argmax(motion[inside])])   # the most active moment in the shot
        out.append({"start": round(a, 2), "end": round(b, 2), "motion": round(float(np.mean(m)), 2),
                    "peak": round(peak_t, 2), "slideshow": bool(np.median(sides[inside]) < SLIDESHOW_RATIO)})
    return out
