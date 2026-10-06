"""Music analysis: tempo, beat grid, downbeats (bar starts), strong hits, and the drop."""
import numpy as np
import librosa

from .media import load_audio


def analyze(path, sr=22050):
    try:
        y, sr = librosa.load(path, sr=sr, mono=True)
    except Exception:   # formats libsndfile can't read (m4a, mp4, webm): decode with ffmpeg instead
        y = load_audio(path, sr, mono=True)[0]
    dur = len(y) / sr
    hop = 512
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    tempo, beats = librosa.beat.beat_track(onset_envelope=onset, sr=sr, hop_length=hop, tightness=120)
    tempo = float(np.atleast_1d(tempo)[0])
    beat_t = librosa.frames_to_time(beats, sr=sr, hop_length=hop)

    # low-end (kick / 808) energy and full-band RMS
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    low = S[(freqs >= 30) & (freqs <= 150)].sum(axis=0)
    low = low / (low.max() + 1e-9)
    rms = librosa.feature.rms(S=S)[0]
    rms = rms / (rms.max() + 1e-9)
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)

    # beat strength = onset + low end at each beat
    bstr = np.array([onset[b] / (onset.max() + 1e-9) + low[b] for b in beats]) if len(beats) else np.array([])

    # downbeats: choose the beat phase (0..3) whose beats carry the most low-end energy
    phase = 0
    if len(beats) >= 8:
        phase = int(np.argmax([bstr[p::4].mean() for p in range(4)]))
    downbeats = beat_t[phase::4]

    # drop: biggest jump in smoothed energy (2s after vs 2s before), on a downbeat
    win = int(2.0 * sr / hop)
    e = np.convolve(0.5 * rms + 0.5 * low, np.ones(win) / win, mode="same")
    jump = np.zeros_like(e)
    jump[win:-win] = e[2 * win:] - e[:-2 * win] if len(e) > 2 * win else 0
    jump_at = lambda t: jump[min(len(jump) - 1, int(t * sr / hop))]
    drops = sorted(downbeats, key=lambda t: -jump_at(t))
    drop = float(drops[0]) if len(drops) else (float(beat_t[len(beat_t) // 3]) if len(beat_t) else dur / 3)

    return {"tempo": tempo, "duration": dur, "beats": beat_t.tolist(), "beat_strength": bstr.tolist(),
            "downbeats": [float(x) for x in downbeats], "drop": drop,
            "drop_candidates": [float(x) for x in drops[:5]],
            "energy_t": times[::4].tolist(), "energy": e[::4].tolist()}


def choose_window(a, length, pre_drop=None):
    """Pick the music section for an edit: start on a downbeat so the drop lands ~25-35% in."""
    if pre_drop is None:
        pre_drop = min(4.0, length * 0.3)
    target = a["drop"] - pre_drop
    db = np.array(a["downbeats"]) if a["downbeats"] else np.array([0.0])
    start = float(db[np.argmin(np.abs(db - target))])
    start = max(0.0, min(start, a["duration"] - length))
    return start, start + length
