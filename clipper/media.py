"""Low-level media IO: probing, audio extraction, streaming frame reader, encoder pipe."""
import json
import os
import subprocess
import numpy as np

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


def probe(path):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path],
        capture_output=True, text=True, check=True).stdout
    info = json.loads(out)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    res = {"duration": float(info["format"]["duration"]), "has_audio": a is not None}
    if v:
        num, den = v.get("avg_frame_rate", "30/1").split("/")
        fps = float(num) / float(den) if float(den) else 30.0
        w, h = int(v["width"]), int(v["height"])
        rot = 0
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(sd["rotation"])
        if abs(rot) in (90, 270):
            w, h = h, w
        res.update(width=w, height=h, fps=fps if 1 < fps < 241 else 30.0)
    return res


def extract_audio(src, dst, sr=44100, mono=False):
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", src, "-vn", "-ac", "1" if mono else "2", "-ar", str(sr),
                    "-c:a", "pcm_s16le", dst], check=True)
    return dst


def load_audio(path, sr=44100, mono=False):
    """Decode any audio/video file to float32 numpy (channels, samples)."""
    ch = 1 if mono else 2
    raw = subprocess.run(
        [FFMPEG, "-v", "error", "-i", path, "-vn", "-ac", str(ch), "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, ch).T.copy()


def save_audio(path, audio, sr=44100):
    audio = np.clip(audio, -1, 1).astype(np.float32)
    ch = audio.shape[0]
    p = subprocess.Popen([FFMPEG, "-y", "-v", "error", "-f", "f32le", "-ac", str(ch), "-ar", str(sr),
                          "-i", "-", "-c:a", "pcm_s16le", path], stdin=subprocess.PIPE)
    p.stdin.write(audio.T.tobytes())
    p.stdin.close()
    p.wait()


class SegmentReader:
    """Streams frames of [start, start+dur) forward-only.
    get(t) returns the frame at source time t. In-between frames are made by:
      interp="blend"  cross-fade of neighbours (cheap; ghosting on big slow-mo)
      interp="flow"   optical-flow interpolation (see flow.py)
      interp_fps=N    pre-interpolate with ffmpeg minterpolate (MCI) to N fps"""

    def __init__(self, src, start, dur, width, height, fps, interp_fps=None, interp="blend"):
        self.start = start
        self.interp = interp
        self.flow = None
        if interp == "flow":
            from .flow import Flow
            self.flow = Flow(scale=0.5 if max(width, height) <= 1920 else 0.35)
        self.w, self.h = width, height
        self.fps = interp_fps or fps
        vf = []
        if interp_fps and interp_fps > fps:
            vf.append(f"minterpolate=fps={interp_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1")
        else:
            vf.append(f"fps={fps}")
        vf.append(f"scale={width}:{height}")
        cmd = [FFMPEG, "-v", "error", "-ss", f"{max(0, start):.3f}", "-i", src, "-t", f"{dur + 0.5:.3f}",
               "-an", "-vf", ",".join(vf), "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10 ** 8)
        self.frames = {}
        self.next_idx = 0
        self.last = None
        self.fsize = width * height * 3

    def _read(self):
        buf = self.proc.stdout.read(self.fsize)
        if len(buf) < self.fsize:
            return None
        f = np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3)
        self.frames[self.next_idx] = f
        self.last = f
        self.next_idx += 1
        # keep a small window only
        for k in [k for k in self.frames if k < self.next_idx - 12]:
            del self.frames[k]
        return f

    def _frame(self, i):
        while self.next_idx <= i:
            if self._read() is None:
                break
        return self.frames.get(i, self.last)

    def _pos(self, t):
        return max(0.0, (t - self.start) * self.fps)

    def get(self, t, blend=True):
        x = self._pos(t)
        i = int(x)
        a = self._frame(i)
        frac = x - i
        if not blend or frac < 0.08:
            return a
        b = self._frame(i + 1)
        if b is None or a is None or b is a:
            return a
        if frac > 0.92:
            return b
        if self.flow is not None:
            return self.flow.interpolate(a, b, frac, key=i)
        return (a.astype(np.float32) * (1 - frac) + b.astype(np.float32) * frac).astype(np.uint8)

    def motion(self, t):
        """(frame, forward flow to the next source frame) for vector motion blur."""
        from .flow import Flow
        if self.flow is None:
            self.flow = Flow(scale=0.35, preset="fast")
        i = int(self._pos(t))
        a, b = self._frame(i), self._frame(i + 1)
        if a is None or b is None or a is b:
            return a, None
        return a, self.flow.pair(a, b, key=i)[0]

    def close(self):
        try:
            self.proc.stdout.close()
            self.proc.kill()
        except Exception:
            pass


class Encoder:
    """Pipe BGR frames into ffmpeg and mux the audio."""

    def __init__(self, path, width, height, fps, audio=None, crf=17):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        cmd = [FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
               "-r", str(fps), "-i", "-"]
        if audio:
            cmd += ["-i", audio]
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
                "-profile:v", "high", "-movflags", "+faststart"]
        if audio:
            cmd += ["-c:a", "aac", "-b:a", "256k", "-shortest"]
        cmd.append(path)
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def write(self, frame):
        try:
            self.proc.stdin.write(np.ascontiguousarray(frame).tobytes())
        except BrokenPipeError:
            raise RuntimeError(f"ffmpeg stopped while writing {self.path}; its error is printed above") from None

    def close(self):
        try:
            self.proc.stdin.close()
        except BrokenPipeError:
            pass
        if self.proc.wait():
            raise RuntimeError(f"ffmpeg failed to write {self.path}; its error is printed above")


class CachedReader(SegmentReader):
    """Decodes the whole (short) segment up front for random access, so time can run
    backwards: boomerang / reverse / back-and-forth retiming. Keep segments to a few seconds."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.all = []
        while True:
            f = self._read()
            if f is None:
                break
            self.all.append(f)
        self.close()
        if not self.all:
            self.all = [np.zeros((self.h, self.w, 3), np.uint8)]

    def _frame(self, i):
        return self.all[max(0, min(i, len(self.all) - 1))]

    def _pos(self, t):
        return min(super()._pos(t), len(self.all) - 1.0)
