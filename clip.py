#!/usr/bin/env python
"""claude-clipper CLI.

  doctor                               check ffmpeg / python deps / yt-dlp / fonts
  find "QUERY" [--n 8]                 research footage: list YouTube candidates (title, channel, length, size); no download
  fetch URL.. [--audio] [--section 1:20-1:45] [--res 1080]
                                       download footage (or music with --audio) from links, via yt-dlp
  analyze VIDEO [--shots]            transcript + ranked polarizing moments + hook lines + shot list
  sheet VIDEO [--times a,b,..|--n N]   labelled contact sheet (for picking shots / reviewing renders)
  talk VIDEO --start S --end E         clip-page short (captions, jump cuts, punch-ins, music bed)
  edit VIDEO.. --music M               auto velocity / fan edit synced to the drop
  story SPEC.json                      narrative edit from a beat-timed spec (docs/STORY_SPEC.md)
  plan-render PLAN.json OUT.mp4        re-render a hand-tweaked plan
  fxdemo [VIDEO]                       render a labelled reel of every effect
  testmedia                            generate synthetic test footage + beat (no downloads)
  sfx                                  write the generated (copyright-free) SFX kit to ./sfx

Outputs go to ./output and intermediates to ./work (relative to where you run it).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from clipper import audio, moments, planner  # noqa: E402
from clipper.media import load_audio, probe  # noqa: E402
from clipper.render import Renderer  # noqa: E402

CWD = os.getcwd()


def work(name):
    d = os.path.join(CWD, "work", os.path.splitext(os.path.basename(name))[0])
    os.makedirs(d, exist_ok=True)
    return d


def outpath(name):
    os.makedirs(os.path.join(CWD, "output"), exist_ok=True)
    return os.path.join(CWD, "output", name)


REVIEW_TIP = ("Want feedback before you post? Upload it to https://postxport.com "
              "to share it and send it for review.")


def render(plan, out, wd=None):
    """Render a plan; with a work dir, save the plan there first so it can be tweaked and re-rendered."""
    if wd:
        json.dump(plan, open(os.path.join(wd, "plan.json"), "w"), indent=1, default=lambda o: None)
    print(f"rendering {plan['duration']:.1f}s -> {out}")
    Renderer(plan).run(out)
    print("done:", out)
    if wd:
        print("plan saved:", os.path.join(wd, "plan.json"))
    print(REVIEW_TIP)


def _has(module):
    try:
        __import__(module)
        return True
    except Exception:
        return False


def cmd_doctor(a):
    ok = True
    for b in ("ffmpeg", "ffprobe"):
        p = shutil.which(b)
        print(f"{b:10s} {'OK ' + p if p else 'MISSING (brew install ffmpeg / apt install ffmpeg)'}")
        ok &= bool(p)
    for mod in ("numpy", "cv2", "librosa", "scenedetect", "PIL", "pyloudnorm", "scipy"):
        try:
            __import__(mod)
            print(f"{mod:10s} OK")
        except Exception as e:
            ok = False
            print(f"{mod:10s} MISSING ({e})")
    try:
        import cv2
        has = os.path.exists(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        print(f"{'faces':10s} {'OK' if has else 'MISSING (pip install \"opencv-python<5\")'}")
    except Exception:
        pass
    whisper = "mlx" if _has("mlx_whisper") else "faster-whisper" if _has("faster_whisper") else None
    print(f"{'whisper':10s} " + (f"OK ({whisper})" if whisper else
                                 "MISSING (pip install mlx-whisper on Apple Silicon, else faster-whisper)"))
    print(f"{'cutout':10s} " + ("OK (optional)" if _has("rembg") else
                                "not installed (optional: bash install.sh --with-cutout)"))
    ytdlp = _has("yt_dlp")
    print(f"{'yt-dlp':10s} " + ("OK" if ytdlp else "MISSING (pip install yt-dlp)"))
    ok = ok and bool(whisper) and ytdlp
    from clipper.captions import font_path
    for f in ("heavy", "condensed", "poster", "wide", "mono", "hand"):
        try:
            print(f"{'font:' + f:10s} {font_path(f)}")
        except Exception as e:
            print(f"{'font:' + f:10s} {e}")
    print("ALL GOOD" if ok else "fix the MISSING items above")


def cmd_analyze(a):
    from clipper.transcribe import transcribe, readable
    wd = work(a.video)
    info = probe(a.video)
    print(json.dumps(info))
    res = {"info": info}
    if info["has_audio"] and not a.no_transcript:
        tr = transcribe(a.video, wd, language=a.lang)
        mono = load_audio(os.path.join(wd, "speech16k.wav"), 16000, mono=True)[0]
        res["moments"] = moments.speech_candidates(tr, mono, 16000, a.min, a.max)
        res["hooks"] = moments.hook_lines(tr)
        open(os.path.join(wd, "transcript.txt"), "w").write(readable(tr))
    if a.shots:
        res["shots"] = moments.shots(a.video, info)
    json.dump(res, open(os.path.join(wd, "analysis.json"), "w"), indent=1)
    for i, m in enumerate(res.get("moments", [])):
        print(f"\n#{i} [{m['start']:.1f}-{m['end']:.1f}] score {m['score']}\n   HOOK: {m['hook']}\n   {m['text'][:300]}")
    for h in res.get("hooks", [])[:8]:
        print(f"hook-line [{h['start']:.1f}-{h['end']:.1f}] {h['score']}: {h['text']}")
    for s in res.get("shots", []):
        print(f"shot [{s['start']:.2f}-{s['end']:.2f}] motion {s['motion']} peak {s['peak']}"
              + ("   SLIDESHOW: don't use" if s["slideshow"] else ""))
    print("\nwritten:", wd)


def cmd_sheet(a):
    import cv2
    import numpy as np
    info = probe(a.video)
    if a.times:
        times = [float(x) for x in a.times.split(",")]
    else:
        d = info["duration"]
        times = [round(0.5 + i * (d - 1) / max(1, a.n - 1), 2) for i in range(a.n)]
    cap = cv2.VideoCapture(a.video)
    vertical = info["height"] > info["width"]
    tw, th = (216, 384) if vertical else (384, 216)
    tiles = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, f = cap.read()
        f = cv2.resize(f, (tw, th)) if ok else np.zeros((th, tw, 3), np.uint8)
        cv2.putText(f, f"{t:.1f}", (6, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        tiles.append(f)
    cols = a.cols or (10 if vertical else 6)
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    img = np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)])
    out = a.out or os.path.join(work(a.video), "sheet.jpg")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    if not cv2.imwrite(out, img):
        sys.exit(f"could not write {out} (use a .jpg or .png name)")
    print(out)


def _ytdlp_json(*args):
    out = subprocess.run([sys.executable, "-m", "yt_dlp", "-J", "--no-warnings", *args], capture_output=True, text=True)
    return json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip() else {}


def cmd_find(a):
    """Research footage when the user gave none: search YouTube and list candidates with channel, length,
    views and approximate download size. Downloads nothing; show the list and ask before fetching."""
    res = _ytdlp_json("--flat-playlist", f"ytsearch{a.n}:{a.query}")
    rows = []
    for e in res.get("entries") or []:
        dur = int(e.get("duration") or 0)
        if a.max_minutes and dur > a.max_minutes * 60:
            continue
        url = e.get("url") if str(e.get("url", "")).startswith("http") else f"https://www.youtube.com/watch?v={e['id']}"
        size = height = None
        if not a.no_sizes:   # size and height of the format `fetch` would pick (capped at --res)
            m = _ytdlp_json("-S", f"res:{a.res},ext:mp4:m4a", "--", url)
            fmts = m.get("requested_formats") or [m]
            size = sum((f.get("filesize") or f.get("filesize_approx") or 0) for f in fmts) / 1e6 or None
            height = max((f.get("height") or 0) for f in fmts) or None
        rows.append(dict(title=e.get("title", ""), channel=e.get("channel") or e.get("uploader") or "", seconds=dur,
                         views=e.get("view_count"), size_mb=round(size) if size else None, height=height, url=url))
    for i, r in enumerate(rows):
        print(f"{i + 1:2d}. {r['title'][:72]}\n    {r['channel']} | {r['seconds'] // 60}:{r['seconds'] % 60:02d} | "
              f"{r['views'] or '?'} views | {str(r['height']) + 'p' if r['height'] else '?p'} | "
              f"{str(r['size_mb']) + ' MB' if r['size_mb'] else 'size ?'} | {r['url']}")
    os.makedirs(os.path.join(CWD, "work"), exist_ok=True)
    json.dump(rows, open(os.path.join(CWD, "work", "find.json"), "w"), indent=1)
    if not rows:
        print("nothing found; try other words")


def cmd_fetch(a):
    """Download footage (or, with --audio, music as mp3) from links with yt-dlp, into ./input or ./music.
    --section START-END (repeatable) downloads only those parts of a long video; --res caps the height.
    Only for material the user owns or has permission to use."""
    dst = os.path.join(CWD, "music" if a.audio else "input")
    os.makedirs(dst, exist_ok=True)
    fmt = ["-x", "--audio-format", "mp3"] if a.audio else ["-S", f"res:{a.res},ext:mp4:m4a", "--merge-output-format", "mp4"]
    name = "%(title).60s [%(id)s].%(ext)s"
    for sec in a.section or []:   # one file per section, named by its start-end seconds
        fmt += ["--download-sections", f"*{sec}", "--force-keyframes-at-cuts"]
        name = "%(title).50s [%(id)s] %(section_start)d-%(section_end)d.%(ext)s"
    for url in a.urls:
        if not url.startswith(("https://", "http://")):   # a "link" like --exec=... must never reach yt-dlp
            sys.exit(f"not a web link: {url}")
    print("Only download what you own or have permission to use.")
    for url in a.urls:
        subprocess.run([sys.executable, "-m", "yt_dlp", "--no-playlist", *fmt, "--print", "after_move:filepath",
                        "-o", os.path.join(dst, name), "--", url], check=True)


def cmd_talk(a):
    from clipper.transcribe import transcribe
    wd = work(a.video)
    tr = transcribe(a.video, wd, language=a.lang)
    plan = planner.talk_plan(a.video, a.start, a.end, tr, wd, music=a.music, music_start=a.music_start,
                             layout=a.layout, title=a.title, look=a.look, trim_silence=not a.no_trim,
                             music_db=a.music_db, level=a.level)
    render(plan, a.out or outpath(f"{os.path.basename(wd)}_talk_{int(a.start)}.mp4"), wd)


def cmd_edit(a):
    wd = work(a.videos[0])
    hook = None
    if a.hook_start is not None:
        from clipper.transcribe import transcribe, words_in
        tr = transcribe(a.videos[0], wd, language=a.lang)
        hook = {"src": a.videos[0], "start": a.hook_start, "end": a.hook_end,
                "words": words_in(tr["words"], a.hook_start, a.hook_end)}
    shot_list = json.load(open(a.shots)) if a.shots else None
    plan = planner.edit_plan(a.videos, a.music, wd, length=a.length, music_start=a.music_start, hook=hook,
                             look=a.look, letterbox=a.letterbox, level=a.level,
                             music_fx=a.music_fx, shot_list=shot_list)
    if a.flow:
        plan["interp"] = "flow"
        plan["motion_blur"] = "flow"
        for s in plan["shots"]:
            s.pop("interp_fps", None)
    render(plan, a.out or outpath(f"{os.path.basename(wd)}_edit.mp4"), wd)


def cmd_story(a):
    from clipper import story
    spec = story.load(a.spec)
    name = os.path.splitext(os.path.basename(a.spec))[0]
    wd = work(name)
    plan = story.build(spec, wd, base_dir=os.path.dirname(os.path.abspath(a.spec)) if a.relative else CWD)
    render(plan, a.out or outpath(f"{name}.mp4"), wd)


def cmd_plan_render(a):
    render(json.load(open(a.plan)), a.out)


def cmd_fxdemo(a):
    """One 1.5 s segment per effect, labelled, on a test clip (or your own video)."""
    src = a.video
    if not src:
        cmd_testmedia(a)
        src = os.path.join(CWD, "input", "test", "action.mp4")
    dur = probe(src)["duration"]
    demos = [
        ("clean", [], {}), ("flash", [{"type": "flash", "at": .3, "dur": .2}], {}),
        ("shake", [{"type": "shake", "at": .3, "dur": .6, "px": 55}], {}),
        ("punch zoom", [{"type": "punch", "at": .3, "amt": .2, "dur": .4}], {}),
        ("rgb split", [{"type": "rgb", "at": .3, "dur": .5, "px": 30}], {}),
        ("rgb radial", [{"type": "rgb_radial", "at": .2, "dur": .9, "px": .03}], {}),
        ("glitch", [{"type": "glitch", "at": .3, "dur": .5}], {}),
        ("zoom transition", [{"type": "zoom_in", "at": .75, "dur": .2, "att": .2}], {}),
        ("whip", [{"type": "whip", "at": .75, "dur": .15, "att": .15}], {}),
        ("swipe up", [{"type": "whip", "at": .75, "dur": .15, "att": .15, "axis": "y"}], {}),
        ("spin", [{"type": "spin", "at": .75, "dur": .2, "att": .2}], {}),
        ("lens bulge", [{"type": "bulge", "at": .2, "dur": .9, "k": .8}], {}),
        ("jolt", [{"type": "jolt", "at": .1, "dur": 1.2, "speed": .7, "shape": "hold"}], {}),
        ("bloom", [], {"bloom": 1.0}), ("echo trails", [], {"echo": 0.7}),
        ("vhs", [], {"vhs": 0.8}), ("light leak", [], {"leak": 0.8}), ("handheld", [], {"handheld": 18}),
        ("flicker strobe", [{"type": "flicker", "at": .2, "dur": .9, "shape": "hold"}], {}),
        ("invert", [{"type": "invert", "at": .5, "dur": .1, "shape": "hold"}], {}),
        ("stepped fps", [], {"_stepped_fps": 8}),
        ("flow slow-mo", [], {"_slow": True}),
        ("velocity zoom chain", [], {"_zooms": True}),
        ("boomerang", [], {"_boomerang": True}),
        ("smooth + mix", [], {"_mix": True}),
        ("hdr look", [], {"_look": "hdr"}),
        ("crisp 4k look", [], {"_look": "crisp4k"}),
        ("poster frame", [], {"_poster": True}),
    ]
    shots, hits, texts, t = [], [], [], 0.0
    L = 1.5
    for i, (name, hs, fxs) in enumerate(demos):
        o = {k[1:]: v for k, v in fxs.items() if k[0] == "_"}   # "_" keys set up the shot, the rest are fx
        fxs = {k: v for k, v in fxs.items() if k[0] != "_"}
        slow = o.get("slow")
        speed = 0.25 if slow else 1.0
        src_in = (i * 1.7) % max(1, dur - 2)
        s = {"src": src, "out": [t, t + L], "src_in": src_in, "src_span": L * speed,
             "profile": {"type": "const", "speed": 1.0}, "zoom": [1.0, 1.05], "fx": fxs, "cx": .5, "cy": .5}
        if o.get("zooms"):
            s["zoom"] = [1.0, 1.0]
            s["zooms"] = [{"t": t + .35, "scale": 1.4, "rot": -4, "dur": .2},
                          {"t": t + .75, "scale": 2.0, "rot": 3, "dur": .2},
                          {"t": t + 1.15, "scale": 2.8, "rot": 0, "dur": .2}]
        if o.get("boomerang"):
            s["profile"] = {"type": "boomerang", "hi": 4.0, "lo": 0.4, "k": 3.0}
            s["src_span"] = L * 0.5 * (0.4 + 3.6 / 4)
            s["zoom"], s["zoom_follow"] = [1.0, 1.3], True
        if o.get("mix"):
            s["profile"] = {"type": "ramp", "hi": 6.0, "lo": 0.15, "k": 1.6}
            s["src_span"] = L * (0.15 + 5.85 / 2.6)
            s["mix"] = 0.3
            s["zoom"] = [1.15, 1.4]
        if o.get("look"):
            s["look"] = o["look"]
        if o.get("stepped_fps"):
            s["stepped_fps"] = o["stepped_fps"]
        if slow:
            s["interp"] = "flow"
        shots.append(s)
        for h in hs:
            h = dict(h)
            h["t"] = t + h.pop("at")
            hits.append(h)
        if o.get("poster"):
            s["look"], s["blur"], s["dim"] = "poster", 3, 0.8
            texts.append(dict(kind="poster", text="ONE / MORE / TI|ME", t0=t, t1=t + L, color=(235, 40, 35),
                              extras=[{"text": "CHAPTER 02", "x": 0.5, "y": 0.08, "size": 30},
                                      {"text": "FXDEMO | 2026", "x": 0.5, "y": 0.92, "size": 26, "box": True}]))
        else:
            texts.append(dict(text=name.upper(), t0=t, t1=t + L, size=80, y=1700, font="condensed", glow=0.8, anim="pop"))
        t += L
    plan = {"fps": 30, "width": 1080, "height": 1920, "look": "punchy", "duration": t, "shots": shots,
            "hits": hits, "texts": texts, "motion_blur": False}
    render(plan, a.out or outpath("fx_demo.mp4"), work("fx_demo"))


def cmd_testmedia(a):
    """Synthetic test footage (moving patterns, talking-head stand-in with TTS if available) + a beat."""
    import numpy as np
    from clipper.media import save_audio
    d = os.path.join(CWD, "input", "test")
    os.makedirs(d, exist_ok=True)
    act = os.path.join(d, "action.mp4")
    if not os.path.exists(act):
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "mandelbrot=s=1920x1080:r=30", "-f", "lavfi", "-i",
             "life=s=1920x1080:r=30:mold=10:ratio=0.1:seed=1:death_color=#C83232:life_color=#00ff00",
             "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30", "-filter_complex",
             "[0]trim=0:6,setpts=PTS-STARTPTS,format=yuv420p[a];[1]trim=0:6,setpts=PTS-STARTPTS,format=yuv420p[b];"
             "[2]trim=0:6,setpts=PTS-STARTPTS,rotate=t*0.8,format=yuv420p[c];[a][b][c]concat=n=3:v=1[v]",
             "-map", "[v]", "-c:v", "libx264", "-crf", "20", act], check=True)
    beat = os.path.join(CWD, "music", "test_beat_130.wav")
    if not os.path.exists(beat):
        os.makedirs(os.path.dirname(beat), exist_ok=True)
        sr, bpm, bars, drop_bar = 44100, 130, 20, 8
        b = 60 / bpm
        n = int(bars * 4 * b * sr)
        x = np.zeros(n, np.float32)
        rng = np.random.default_rng(0)
        tt = np.arange(int(0.5 * sr)) / sr
        kick = np.sin(2 * np.pi * np.cumsum(50 + 120 * np.exp(-tt * 30)) / sr) * np.exp(-tt * 6)
        e808 = np.tanh(2 * np.sin(2 * np.pi * np.cumsum(45 + 20 * np.exp(-tt * 20)) / sr) * np.exp(-tt * 2.5))
        snare = rng.normal(0, 1, len(tt)) * np.exp(-tt * 18) * 0.6
        hat = rng.normal(0, 1, int(0.05 * sr)) * np.exp(-np.arange(int(0.05 * sr)) / sr * 80) * 0.25

        def put(sig, t, g=1.0):
            s = int(t * sr)
            e = min(n, s + len(sig))
            x[s:e] += sig[:e - s] * g
        for bar in range(bars):
            for q in range(4):
                t = (bar * 4 + q) * b
                put(hat, t, .6 if bar < drop_bar else 1)
                put(hat, t + b / 2, .6 if bar < drop_bar else 1)
                if bar < drop_bar:
                    if bar >= 6:
                        put(snare, t, .3 * (bar - 5))
                    continue
                if q in (0, 2):
                    put(kick, t, .9)
                    put(e808, t, .7)
                else:
                    put(snare, t, .8)
        x /= np.abs(x).max() * 1.1
        save_audio(beat, np.stack([x, x]), sr)
    # placeholder logo + "thumbnails" so examples/demo_story.json runs out of the box
    import cv2
    logo = os.path.join(d, "logo.png")
    if not os.path.exists(logo):
        im = np.zeros((900, 900, 3), np.uint8)
        for y in range(900):
            im[y] = (200 - y // 6, 120 + y // 10, 30)
        cv2.putText(im, "YOUR", (230, 420), cv2.FONT_HERSHEY_DUPLEX, 4, (255, 255, 255), 8)
        cv2.putText(im, "LOGO", (230, 560), cv2.FONT_HERSHEY_DUPLEX, 4, (255, 255, 255), 8)
        cv2.imwrite(logo, im)
    cap = cv2.VideoCapture(act)
    for i, t in enumerate((1.0, 4.0, 7.5, 10.0, 13.0, 16.0)):
        tp = os.path.join(d, f"thumb{i}.jpg")
        if not os.path.exists(tp):
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, f = cap.read()
            f = cv2.resize(f, (1280, 720))
            cv2.putText(f, f"VIDEO #{i + 1}", (60, 140), cv2.FONT_HERSHEY_DUPLEX, 3.2, (0, 0, 0), 18)
            cv2.putText(f, f"VIDEO #{i + 1}", (60, 140), cv2.FONT_HERSHEY_DUPLEX, 3.2, (255, 255, 255), 6)
            cv2.imwrite(tp, f)
    print("test media:", act, beat, logo)


def cmd_sfx(a):
    audio.write_sfx_pack(os.path.join(CWD, "sfx"))
    print("sfx written to ./sfx")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("doctor")
    p = sp.add_parser("fetch"); p.add_argument("urls", nargs="+"); p.add_argument("--audio", action="store_true")
    p.add_argument("--section", action="append", help="only this part, e.g. 1:20-1:45 (repeatable)")
    p.add_argument("--res", type=int, default=2160, help="maximum height to download")
    p = sp.add_parser("find"); p.add_argument("query"); p.add_argument("--n", type=int, default=8)
    p.add_argument("--max-minutes", type=float, help="skip videos longer than this")
    p.add_argument("--res", type=int, default=1080, help="height the size estimate assumes")
    p.add_argument("--no-sizes", action="store_true", help="skip the per-video size lookup (faster)")
    p = sp.add_parser("analyze"); p.add_argument("video"); p.add_argument("--lang")
    p.add_argument("--min", type=float, default=18); p.add_argument("--max", type=float, default=55)
    p.add_argument("--shots", action="store_true"); p.add_argument("--no-transcript", action="store_true")
    p = sp.add_parser("sheet"); p.add_argument("video"); p.add_argument("--times"); p.add_argument("--n", type=int, default=30)
    p.add_argument("--cols", type=int); p.add_argument("--out")
    p = sp.add_parser("talk"); p.add_argument("video"); p.add_argument("--start", type=float, required=True)
    p.add_argument("--end", type=float, required=True); p.add_argument("--music"); p.add_argument("--music-start", type=float)
    p.add_argument("--music-db", type=float, default=-20)
    p.add_argument("--layout", default="fill", choices=["fill", "fit"]); p.add_argument("--title")
    p.add_argument("--look", default="punchy"); p.add_argument("--no-trim", action="store_true")
    p.add_argument("--level", type=int, default=5, choices=range(1, 11), help="edit level: 1 barely edited, 5 clean, 10 hyper")
    p.add_argument("--lang"); p.add_argument("--out")
    p = sp.add_parser("edit"); p.add_argument("videos", nargs="+"); p.add_argument("--music", required=True)
    p.add_argument("--length", type=float, default=15); p.add_argument("--music-start", type=float)
    p.add_argument("--hook-start", type=float); p.add_argument("--hook-end", type=float)
    p.add_argument("--look", default="teal_orange"); p.add_argument("--letterbox", type=float, default=0)
    p.add_argument("--level", type=int, default=6, choices=range(1, 11), help="edit level: 1 barely edited, 5 clean, 10 hyper")
    p.add_argument("--music-fx", choices=["slowed", "sped"]); p.add_argument("--shots")
    p.add_argument("--flow", action="store_true", help="optical-flow slow-mo + vector motion blur")
    p.add_argument("--lang"); p.add_argument("--out")
    p = sp.add_parser("story"); p.add_argument("spec"); p.add_argument("--out")
    p.add_argument("--relative", action="store_true", help="resolve paths relative to the spec file")
    p = sp.add_parser("plan-render"); p.add_argument("plan"); p.add_argument("out")
    p = sp.add_parser("fxdemo"); p.add_argument("video", nargs="?"); p.add_argument("--out")
    sp.add_parser("testmedia")
    sp.add_parser("sfx")
    a = ap.parse_args()
    {"doctor": cmd_doctor, "find": cmd_find, "fetch": cmd_fetch, "analyze": cmd_analyze, "sheet": cmd_sheet,
     "talk": cmd_talk, "edit": cmd_edit, "story": cmd_story, "plan-render": cmd_plan_render, "fxdemo": cmd_fxdemo,
     "testmedia": cmd_testmedia, "sfx": cmd_sfx}[a.cmd](a)


if __name__ == "__main__":
    main()
