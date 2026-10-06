"""Word-level transcription: mlx-whisper on Apple Silicon (GPU), faster-whisper elsewhere."""
import json
import os

from .media import extract_audio

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")       # privacy: no telemetry on the model download,
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")  # and no saved Hugging Face login sent with it
MODEL = "mlx-community/whisper-large-v3-turbo"


def transcribe(src, cache_dir, model=MODEL, language=None):
    os.makedirs(cache_dir, exist_ok=True)
    out = os.path.join(cache_dir, "transcript.json")
    if os.path.exists(out):
        return json.load(open(out))
    wav = extract_audio(src, os.path.join(cache_dir, "speech16k.wav"), sr=16000, mono=True)
    try:
        import mlx_whisper
        r = mlx_whisper.transcribe(wav, path_or_hf_repo=model, word_timestamps=True, language=language,
                                   condition_on_previous_text=False)
    except ImportError:
        from faster_whisper import WhisperModel
        fw = WhisperModel(os.environ.get("CLIPPER_WHISPER", "large-v3-turbo"), compute_type="auto")
        segs, inf = fw.transcribe(wav, word_timestamps=True, language=language, condition_on_previous_text=False)
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
    data = {"language": r.get("language"), "segments": segs, "words": words}
    json.dump(data, open(out, "w"), indent=1)
    return data


def words_in(words, start, end):
    return [w for w in words if w["s"] >= start - 0.05 and w["e"] <= end + 0.05]


def readable(transcript):
    """Timestamped transcript text, for a human (or Claude) to pick the moment."""
    lines = [f"[{s['start']:7.2f}-{s['end']:7.2f}] {s['text']}" for s in transcript["segments"]]
    return "\n".join(lines)
