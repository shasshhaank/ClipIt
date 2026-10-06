"""Word-level transcription with OpenAI's Whisper: mlx-whisper on Apple Silicon (GPU), faster-whisper elsewhere.
Two models: "turbo" (large-v3-turbo, the default: fast, about 1.5 GB) and "large" (the full large-v3, about 3 GB),
which is far better at Hindi and other languages turbo handles poorly. Hindi needs "large" for usable subtitles."""
import json
import os

from .media import extract_audio, load_audio

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")       # privacy: no telemetry on the model download,
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")  # and no saved Hugging Face login sent with it
MODELS = {"turbo": ("mlx-community/whisper-large-v3-turbo", "large-v3-turbo"),
          "large": ("mlx-community/whisper-large-v3-mlx", "large-v3")}   # (mlx repo, faster-whisper name)
WEAK_IN_TURBO = {"hi", "mr", "ne", "bn", "ta", "te", "kn", "ml", "gu", "pa", "ur"}   # Indic languages


def transcribe(src, cache_dir, model=None, language=None):
    """Transcript {language, segments, words, model}, cached in cache_dir (redone if a different model is asked)."""
    model = model or os.environ.get("CLIPPER_WHISPER", "turbo")
    os.makedirs(cache_dir, exist_ok=True)
    out = os.path.join(cache_dir, "transcript.json")
    if os.path.exists(out):
        data = json.load(open(out))
        if data.get("model", "turbo") == model or model not in MODELS:
            return data
    wav = extract_audio(src, os.path.join(cache_dir, "speech16k.wav"), sr=16000, mono=True)
    audio = load_audio(wav, 16000, mono=True)[0]   # passed as samples, so Whisper never needs ffmpeg on PATH
    try:
        import mlx_whisper
        r = mlx_whisper.transcribe(audio, path_or_hf_repo=MODELS[model][0], word_timestamps=True, language=language,
                                   condition_on_previous_text=False)
    except ImportError:
        from faster_whisper import WhisperModel
        fw = WhisperModel(MODELS[model][1], compute_type="auto")
        segs, inf = fw.transcribe(audio, word_timestamps=True, language=language, condition_on_previous_text=False)
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
    data = {"language": r.get("language"), "segments": segs, "words": words, "model": model}
    json.dump(data, open(out, "w"), indent=1)
    if data["language"] in WEAK_IN_TURBO and model == "turbo":
        print(f"  ! speech is in '{data['language']}': the fast model transcribes it poorly, so its subtitles would be wrong. "
              f"Ask the user: install OpenAI's full Whisper model for it (`install.sh --with-hindi`, about 3 GB, then "
              f"run again with --whisper large), or go without subtitles (--no-captions).")
    return data


def captions_ok(tr):
    """Subtitles only from a model that handles the language: Hindi and other Indic speech needs the large model.
    (The fast model's word timings are still fine for cutting.)"""
    return not (tr.get("language") in WEAK_IN_TURBO and tr.get("model", "turbo") == "turbo")


def words_in(words, start, end):
    return [w for w in words if w["s"] >= start - 0.05 and w["e"] <= end + 0.05]


def readable(transcript):
    """Timestamped transcript text, for a human (or Claude) to pick the moment."""
    lines = [f"[{s['start']:7.2f}-{s['end']:7.2f}] {s['text']}" for s in transcript["segments"]]
    return "\n".join(lines)
