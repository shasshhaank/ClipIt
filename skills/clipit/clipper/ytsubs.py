"""YouTube's own subtitles, used before Whisper. When footage is fetched from YouTube, its subtitles are saved next
to the video as `<video>.subs.json`, and transcribe() uses them instead of running a speech model.

Which track: the uploader's own subtitles in the spoken language first, else YouTube's automatic captions in the
spoken language (the "-orig" track). Never an auto-translated track: subtitles always show what was actually said."""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile


def sidecar(video):
    return os.path.splitext(video)[0] + ".subs.json"


def _ytdlp(*args):
    return subprocess.run([sys.executable, "-m", "yt_dlp", "--no-warnings", *args], capture_output=True, text=True)


def pick(info):
    """(kind, track) to use for a video's info dict, or None: own subtitles in the spoken language, else the
    automatic captions in the spoken language, else a lone uploaded track."""
    manual = [k for k in (info.get("subtitles") or {}) if k != "live_chat"]
    orig = [k for k in (info.get("automatic_captions") or {}) if k.endswith("-orig")]
    spoken = (info.get("language") or (orig[0][:-5] if orig else "")).split("-")[0].lower()
    own = [k for k in manual if spoken and k.split("-")[0].lower() == spoken]
    if own:
        return "own", own[0]
    if orig:
        return "auto", orig[0]
    if len(manual) == 1:
        return "own", manual[0]
    return None


def parse(j, offset=0.0, length=None):
    """json3 subtitles -> (words, segments) in the video's own time (shifted by `offset` for a downloaded section)."""
    words, segs = [], []
    for ev in j.get("events", []):
        parts = [(s.get("tOffsetMs", 0) / 1000, s.get("utf8", "")) for s in ev.get("segs") or []]
        text = " ".join("".join(p for _, p in parts).split())
        if not text:
            continue
        t0, dur = ev.get("tStartMs", 0) / 1000, ev.get("dDurationMs", 0) / 1000
        if len(parts) > 1 and any(o > 0 for o, _ in parts):   # automatic captions: a time for every word
            items = [(t0 + o, p.strip()) for o, p in parts if p.strip()]
        else:                                                 # uploaded subtitles: one time per line
            ws = text.split()
            items = [(t0 + dur * i / len(ws), w) for i, w in enumerate(ws)]
        for i, (s, w) in enumerate(items):
            e = min(items[i + 1][0] if i + 1 < len(items) else t0 + dur, s + 1.0)
            words.append({"w": w, "s": round(s - offset, 3), "e": round(max(e, s + 0.05) - offset, 3), "p": 1.0})
        segs.append({"start": round(t0 - offset, 3), "end": round(t0 + dur - offset, 3), "text": text})
    inside = (lambda a, b: b > 0 and (length is None or a < length))
    return [w for w in words if inside(w["s"], w["e"])], [s for s in segs if inside(s["start"], s["end"])]


def save(url, video):
    """Fetch YouTube's subtitles for `url` and save them next to `video`. A file downloaded with --section is named
    "... START-END.ext"; its subtitles are shifted to match. Returns a short description, or None."""
    try:
        info = json.loads(_ytdlp("-J", "--", url).stdout or "{}")
    except ValueError:
        return None
    choice = pick(info)
    if not choice:
        return None
    kind, track = choice
    sec = re.search(r" (\d+)-(\d+)\.\w+$", video)
    offset, length = (int(sec[1]), int(sec[2]) - int(sec[1])) if sec else (0.0, None)
    with tempfile.TemporaryDirectory() as d:
        _ytdlp("--skip-download", "--write-subs" if kind == "own" else "--write-auto-subs", "--sub-langs", track,
               "--sub-format", "json3", "-o", os.path.join(d, "s.%(ext)s"), "--", url)
        files = glob.glob(os.path.join(d, "*.json3"))
        if not files:
            return None
        words, segs = parse(json.load(open(files[0])), offset, length)
    if not words:
        return None
    lang = track.split("-")[0].lower()
    json.dump({"language": lang, "lang_conf": 1.0, "lang_probs": [[lang, 1.0]], "segments": segs, "words": words,
               "model": "youtube", "source": f"youtube {kind}"}, open(sidecar(video), "w"), indent=1)
    return f"YouTube's {'own' if kind == 'own' else 'automatic'} subtitles ({lang})"
