"""Speech: word-level transcription with OpenAI's Whisper (mlx-whisper on Apple Silicon, faster-whisper elsewhere),
language detection with a confidence, and cutting speech only at real pauses.

Two models: "turbo" (large-v3-turbo, the default: fast, about 1.5 GB) and "large" (the full large-v3, about 3 GB),
which is far better at Hindi and the other languages turbo handles poorly.

Subtitles are shown only when the language is certain. Whisper is always told which language to write, so it never
"helpfully" translates Hindi into English; and when the language is uncertain, or Hindi with the fast model, there
are no subtitles at all (the word timings are still used for cutting)."""
import json
import os

import numpy as np

from .media import extract_audio, load_audio

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")       # privacy: no telemetry on the model download,
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")  # and no saved Hugging Face login sent with it
MODELS = {"turbo": ("mlx-community/whisper-large-v3-turbo", "large-v3-turbo"),
          "large": ("mlx-community/whisper-large-v3-mlx", "large-v3")}   # (mlx repo, faster-whisper name)
WEAK_IN_TURBO = {"hi", "mr", "ne", "bn", "ta", "te", "kn", "ml", "gu", "pa", "ur"}   # Indic languages
SURE = 0.8   # language confidence needed before anything is subtitled
SR = 16000
_models = {}


def detect_language(audio, model="turbo"):
    """Language probabilities {code: p} for up to 30 s of 16 kHz speech. Hindi and Urdu are merged into "hi":
    spoken, they are one language, and Whisper splits its vote between them."""
    try:
        try:
            import mlx.core as mx
            from mlx_whisper import audio as wa, decoding, load_models
            if ("mlx", model) not in _models:
                _models[("mlx", model)] = load_models.load_model(MODELS[model][0], dtype=mx.float16)
            m = _models[("mlx", model)]
            mel = wa.log_mel_spectrogram(audio[:wa.N_SAMPLES], n_mels=m.dims.n_mels, padding=wa.N_SAMPLES)
            _, p = decoding.detect_language(m, wa.pad_or_trim(mel, wa.N_FRAMES, axis=-2).astype(mx.float16))
            p = dict(p[0] if isinstance(p, list) else p)
        except ImportError:
            from faster_whisper import WhisperModel
            if ("fw", model) not in _models:
                _models[("fw", model)] = WhisperModel(MODELS[model][1], compute_type="auto")
            p = dict(_models[("fw", model)].detect_language(audio[:30 * SR])[2])
    except Exception as e:   # no detector: treat the language as unknown (no subtitles)
        print(f"  ! language detection unavailable ({e}); no subtitles will be made")
        return {}
    p["hi"] = p.get("hi", 0.0) + p.pop("ur", 0.0)
    return {k: float(v) for k, v in p.items()}


def _language(audio, model):
    """(language, confidence, top three) over up to three 30 s stretches spread through the speech."""
    n = len(audio)
    starts = sorted({max(0, min(n - 30 * SR, int(n * f) - 15 * SR)) for f in (0.15, 0.5, 0.85)}) if n > 30 * SR else [0]
    probs = [detect_language(audio[s:s + 30 * SR], model) for s in starts]
    p = {k: float(np.mean([q.get(k, 0.0) for q in probs])) for k in set().union(*probs)} if any(probs) else {}
    if not p:
        return None, 0.0, []
    lang = max(p, key=p.get)
    if lang != "hi" and p.get("hi", 0.0) >= 0.25:   # Hindi clearly present (code-mixed Hinglish): treat it as Hindi
        lang = "hi"
    return lang, round(p[lang], 2), [(k, round(v, 2)) for k, v in sorted(p.items(), key=lambda kv: -kv[1])[:3]]


def transcribe(src, cache_dir, model=None, language=None):
    """Transcript {language, lang_conf, lang_probs, segments, words, model}, cached in cache_dir."""
    model = model or os.environ.get("CLIPIT_WHISPER", "turbo")
    os.makedirs(cache_dir, exist_ok=True)
    out = os.path.join(cache_dir, "transcript.json")
    if os.path.exists(out):
        data = json.load(open(out))
        if "lang_conf" in data and (data.get("model") == model or model not in MODELS):
            return data
    wav = extract_audio(src, os.path.join(cache_dir, "speech16k.wav"), sr=SR, mono=True)
    audio = load_audio(wav, SR, mono=True)[0]   # passed as samples, so Whisper never needs ffmpeg on PATH
    lang, conf, top = (language, 1.0, [(language, 1.0)]) if language else _language(audio, model)
    try:
        import mlx_whisper
        r = mlx_whisper.transcribe(audio, path_or_hf_repo=MODELS[model][0], word_timestamps=True, language=lang,
                                   condition_on_previous_text=False, task="transcribe")
    except ImportError:
        from faster_whisper import WhisperModel
        fw = WhisperModel(MODELS[model][1], compute_type="auto")
        segs, inf = fw.transcribe(audio, word_timestamps=True, language=lang, task="transcribe",
                                  condition_on_previous_text=False)
        r = {"language": inf.language, "segments": [
            {"start": s.start, "end": s.end, "text": s.text,
             "words": [{"word": w.word, "start": w.start, "end": w.end, "probability": w.probability}
                       for w in (s.words or [])]} for s in segs]}
    words, segs = [], []
    for s in r["segments"]:
        segs.append({"start": s["start"], "end": s["end"], "text": s["text"].strip()})
        for w in s.get("words", []):
            words.append({"w": w["word"].strip(), "s": round(w["start"], 3), "e": round(w["end"], 3),
                          "p": round(w.get("probability", 1.0), 3)})
    data = {"language": lang or r.get("language"), "lang_conf": conf, "lang_probs": top, "segments": segs,
            "words": words, "model": model}
    json.dump(data, open(out, "w"), indent=1)
    if not captions_ok(data):
        if data["language"] in WEAK_IN_TURBO and model == "turbo":
            print(f"  ! the speech is in '{data['language']}' ({top}). The fast model gets it wrong, so there will be no "
                  f"subtitles. Ask the user: install OpenAI's full Whisper model for it (`install.sh --with-hindi`, "
                  f"about 3 GB, then run again with --whisper large), or go without subtitles.")
        else:
            print(f"  ! not sure which language this is ({top}), so there will be no subtitles")
    return data


def captions_ok(tr):
    """Subtitles only when the language is certain and the model handles it (Hindi and other Indic speech need the
    large model). Uncertain or unknown language: no subtitles, never a translation."""
    conf = tr.get("lang_conf", 0.0)
    if tr.get("language") in WEAK_IN_TURBO:
        return tr.get("model") == "large" and conf >= 0.6
    return conf >= SURE


def line_ok(tr, src, s0, s1):
    """captions_ok for one spoken line: the line itself must also clearly be in the transcript's language."""
    if not captions_ok(tr):
        return False
    p = detect_language(load_audio(src, SR, mono=True, start=s0, dur=s1 - s0)[0], tr.get("model", "turbo"))
    need = 0.6 if tr.get("language") in WEAK_IN_TURBO else SURE
    return p.get(tr.get("language"), 0.0) >= need


def pauses(src, t0, t1, words=()):
    """Pauses in speech between t0 and t1, as [(start, end)]: quiet stretches in the audio plus gaps between words."""
    t0 = max(0.0, t0)
    a = load_audio(src, SR, mono=True, start=t0, dur=t1 - t0)[0]
    hop = SR // 50   # 20 ms
    n = len(a) // hop
    if n < 3:
        return []
    db = 20 * np.log10(np.sqrt((a[:n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-7)
    thr = max(np.percentile(db, 85) - 20, np.percentile(db, 10) + 4)
    quiet = np.convolve(db < thr, np.ones(3) / 3, mode="same") > 0.5
    out, i = [], 0
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            if (j - i) * 0.02 >= 0.08:
                out.append((t0 + i * 0.02, t0 + j * 0.02))
            i = j
        else:
            i += 1
    for w, nx in zip(words, words[1:]):
        if t0 <= w["e"] <= t1 and nx["s"] - w["e"] >= 0.12:
            out.append((w["e"], nx["s"]))
    return sorted(out)


def snap_speech(src, s0, s1, tr=None, back=2.5, ahead=4.0):
    """Move a spoken line's cuts so nobody is cut off mid-word or mid-sentence. With a trustworthy transcript
    (captions_ok) the line first widens to whole sentences (Whisper's segments); then both cuts move into real pauses
    in the audio: the start back to the pause before the sentence (0.25 s+), the end forward to the pause after it
    (0.3 s+). Without a trustworthy transcript (Hindi on the fast model, unsure language) only the audio is used.
    Returns (start, end, clean); clean = both ends landed in a sentence-length pause."""
    trusted = tr is not None and captions_ok(tr)
    words = tr["words"] if trusted else []
    for seg in tr["segments"] if trusted else []:
        if seg["start"] <= s0 + 0.2 < seg["end"] and s0 - seg["start"] <= back:
            s0 = seg["start"]
        if seg["start"] < s1 - 0.2 <= seg["end"] and seg["end"] - s1 <= ahead:
            s1 = seg["end"]
    gaps = pauses(src, s0 - back, s1 + ahead, words)
    before = [g for g in gaps if g[0] <= s0 + 0.15]   # pauses that begin before the line (or the one it starts in)
    big = [g for g in before if g[1] - g[0] >= 0.25]
    start, ok0 = s0, False
    if big or before:
        g = (big or before)[-1]
        start, ok0 = g[1] - min(0.1, (g[1] - g[0]) / 2), bool(big)
    after = [g for g in gaps if g[1] >= s1 - 0.15]
    big = [g for g in after if g[1] - g[0] >= 0.3]
    end, ok1 = s1, False
    if big or after:
        g = (big or after)[0]
        end, ok1 = g[0] + min(0.2, (g[1] - g[0]) / 2), bool(big)
    return round(max(0.0, start), 3), round(end, 3), ok0 and ok1


def words_in(words, start, end):
    return [w for w in words if w["s"] >= start - 0.05 and w["e"] <= end + 0.05]


def readable(transcript):
    """Timestamped transcript text, for a human (or Claude) to pick the moment."""
    head = (f"language: {transcript.get('language')} (confidence {transcript.get('lang_conf')}; "
            f"subtitles {'OK' if captions_ok(transcript) else 'OFF'})\n")
    return head + "\n".join(f"[{s['start']:7.2f}-{s['end']:7.2f}] {s['text']}" for s in transcript["segments"])
