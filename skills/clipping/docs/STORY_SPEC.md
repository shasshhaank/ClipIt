# Story spec (`clip.py story SPEC.json`)

A story edit is a narrative fan edit:

1. **Setup:** slow, desaturated footage with typed text.
2. **Blackout**, then **the drop:** flash, shake and slam text.
3. **Beat-cut hype:** velocity ramps and transitions.
4. **End card:** logo, glow and a subscribe click.

**All times are beats relative to the drop.** `0` is the drop, `-4` is one bar before it, `8` is two bars after it, and fractions like `-19.5` work too. Change the song and the whole edit re-times itself.

Relative paths resolve from the folder you run the command in. Pass `--relative` to resolve them from the spec file's folder instead.

```jsonc
{
  "music": {
    "path": "music/track.mp3",
    "drop": 61.25,            // seconds into the song, or "auto" (biggest energy jump on a downbeat)
    "bars_before": 5,         // setup length
    "bars_after": 7,          // everything after the drop
    "fx": null                // or "slowed" (0.85x + reverb) / "sped" (1.25x)
  },
  "end": 28,                  // final beat (defaults to bars_after*4)
  "level": 5,                 // edit level from the intake: 1 barely edited, 5 clean, 10 hyper (docs/PLAYBOOK.md)
  "look": "teal_orange",      // default grade (per-shot "look" overrides)
  "fx": {"bloom": 0.15},      // continuous effects for the whole edit
  "motion_blur": "flow",      // "flow" (vector blur) | true | false
  "slowmo_interp": "flow",    // interpolation used automatically on shots slower than 0.6x
  "auto_hits": true,          // flowing cuts, blinks, the drop by level, and the end fade (docs/PLAYBOOK.md)
  "cuts": "focus",            // how every cut flows: "focus" (focus-hunting cut) | "zoom" (zoom cut) | "hard"
  "transitions": ["whip", "zoom_in"],   // only at levels 9-10, every two bars after the drop
  "edge": "mirror",           // fill around a picture shown smaller than the frame: "mirror" (motion tile) | "blur"
  "caption_style": "edit",    // dialogue captions: "edit" (small, word by word) | "clip" (big clip-page captions)
  "whisper": "turbo",         // speech model: "turbo" (fast) | "large" (OpenAI Whisper large-v3; needed for Hindi subtitles)
  "sfx": true,                // generated sound kit, auto-placed and levelled (docs/EFFECTS.md, "Sound effects")

  "dialogue": [               // optional: spoken lines that play FIRST, timed by the words, not the beat
    {"src": "input/panel.mp4", "start": 132.4, "end": 136.1},   // snapped to whole words; printed back to check
    {"src": "input/news.mp4", "start": 48.0, "end": 51.6, "look": "mono", "gap": 0.0}
  ],                          // the beat-timed shots below start where the dialogue ends; the music runs under it

  "shots": [                  // contiguous, sorted by "from"
    {"src": "input/a.mp4", "from": -20, "to": -16, "peak": 48.6,   // peak = source second centred in the shot
     "speed": "slow",         // normal | settle | slow | slower | ramp | quick | push | hold | freeze | 0.7 | {profile}
     "look": "mono", "zoom": [1.05, 1.15],
     "cx": 0.5, "cy": 0.45,   // fixed framing; omit for automatic face framing (whole heads, eyes on the upper third)
     "fit": true,             // keep heads whole: zoom limited per scene, picture shown smaller with fill if needed
     "cut": "zoom",           // how the cut INTO this shot flows (overrides the top-level "cuts")
     "layout": "fill",        // or "fit" (whole frame over a blurred copy, good for screenshots)
     "blur": 9, "dim": 0.55,  // background plate for overlays
     "fx": {"vhs": 0.5}, "stepped_fps": 10}
  ],

  "texts": [
    {"text": "THEN HE [VANISHED.]", "from": -10, "to": -8,
     "style": "slam",         // title | slam | type | poster   (any TextLayer field can override)
     "size": 120, "y": 1420, "hum": 0.5, "glow": 1.0, "font": "condensed"}
  ],

  "thumb_wall": {"paths": ["thumbs/1.jpg", "thumbs/2.jpg"], "from": -20, "to": -16, "every": 0.5},

  "burst": {"paths": ["pics/1.jpg", "pics/2.jpg", "pics/3.jpg"], "from": 4, "frames": 2},   // photo strobe

  "overlays": [{"path": "overlays/light.mp4", "from": 0, "to": 4, "blend": "screen", "opacity": 0.8,
                "tint": [255, 60, 40], "rot": 90}],                // your own light/particle/dust clips

  "cards": {                  // comment cards: use REAL comments the user provided; handles are always masked
    "items": [{"text": "this is the holy grail", "handle": "@someone", "likes": "2.1K"}],
    "from": -16, "to": -12
  },

  "images": [{"path": "brand/badge.png", "from": 4, "to": 8, "w": 300, "x": 540, "y": 300, "anim": "pop"}],

  "hits": [{"at": 6, "type": "jolt", "dur": 0.5, "shape": "hold"}],

  "endcard": {
    "logo": "brand/logo.png", "circle": true, "glow_color": [40, 150, 255],
    "from": 20, "to": 28, "headline": "NEW HOME",
    "subscribe": true, "button_at": 22, "click": 24     // the click lands on a beat
  }
}
```

## Poster frames
A text with `"style": "poster"` becomes a full-frame poster (fields in `docs/EFFECTS.md`, rules in `docs/PLAYBOOK.md`). Use one, two at most:
```jsonc
{"text": "THEN CAME / SILENCE", "style": "poster", "from": -8, "to": -4, "color": [235, 30, 35],
 "extras": [{"text": "CHAPTER 02", "x": 0.5, "y": 0.08, "size": 28},
            {"text": "THE COMEBACK  |  2026", "x": 0.5, "y": 0.92, "size": 26, "box": true}]}
```
Put it on a calm shot, such as `"speed": "hold"` with `"look": "poster"`.

## More shot and text fields
```jsonc
{"src": "input/panel.mp4", "from": -20, "to": -16, "start": 132.4, "voice": true, "captions": true,
 "look": "mono"},   // a soundbite: plays its own speech from source second 132.4, music ducks, word captions
{"src": "input/a.mp4", "from": 8, "to": 16, "camera_flow": true, "pulse": 1},   // a new camera move + a pulse on every beat
{"src": "input/b.mp4", "from": 16, "to": 18, "layout": "card", "card_bg": "halftone"},
{"text": "this is where it started", "from": 2, "to": 5, "style": "type", "anim": "words", "font": "hand",
 "follow": true, "rot": 90, "glow": 0.8, "glow_color": [0, 0, 0]},
{"text": "LOOK AT ME", "from": 6, "to": 9, "style": "title", "anim": "assemble", "exit": "scatter", "behind": true}
```
Voice shots and `dialogue` lines always run at normal speed (a speed you set on a voice shot is ignored, with a note), and never get jolts. For several lines in a row, prefer the `dialogue` list: it isn't squeezed onto the beat grid, so lines are never cut mid-word. Top-level `"voice_duck"` (−14 dB) sets how far the music dips under speech and `"caption_y"` (0.7) sets where captions sit. The first captioned run downloads the Whisper model once.

Hits can also carry `"sfx"` (a sound name or `null`). A `{"type": "gap", "at": 8, "db": -15}` hit dips the music right before beat 8, but use it only when asked: viewers hear it as the music cutting.

## Speed profiles
| name | curve | use |
|---|---|---|
| `slow` | 0.5x constant (flow-interpolated) | setup, emotion |
| `slower` | 0.3x | hero moments |
| `settle` | 100% → 30%, decelerating | the workhorse: most shots in pro edits do this |
| `velocity` | 200% → 60% → 200%, eased | the clean per-clip ramp; use the same one on every clip |
| `ramp` | 180% → 22% → 180%, U-shaped | the classic velocity shot; the slow part lands on `peak` |
| `quick` | 160% → 35% | a kick that slides into slow-mo; 1-beat punches |
| `push` | 50% → 180% | accelerating into the drop |
| `hold` | 8%, a near-freeze | under poster frames |
| `freeze` | a freeze frame | stops on a moment |

Pro velocity edits rarely go past 2x (see `PLAYBOOK.md`); `smooth`, `decel` and `boomerang` are the stronger stylised curves.

## Tips
- Put the blackout on the beat just before the drop (`auto_hits` does this) and keep setup text short: 2–4 words per card.
- Swap grades at the drop, for example `mono` or `dark` before it and `teal_orange` or `punchy` after.
- Make cuts on bar lines (multiples of 4) the big moments; `auto_hits` gives them a flash and a shake.
- Render a sheet to review: `clip.py sheet output/x.mp4 --n 24`.

## Motion-design fields (per shot)
```jsonc
{"src": "input/a.mp4", "from": -4, "to": 0, "peak": 46.0, "cx": 0.5, "zoom": [1.0, 1.0],
 "zooms": [{"at": -3, "scale": 1.35, "x": 0.5, "y": 0.55, "rot": -4},   // velocity zoom chain on beats
           {"at": -2, "scale": 1.9,  "y": 0.42, "rot": 3},
           {"at": -1, "scale": 2.6,  "y": 0.33}],
 "velocity": {"hi": 2.2, "lo": 0.35}},                                   // speed spikes on each zoom beat
{"src": "input/a.mp4", "from": 0, "to": 2, "peak": 12.0, "speed": "boomerang", "zoom": [1.0, 1.3]},
{"src": "input/b.mp4", "from": 2, "to": 6, "peak": 30.0, "speed": "smooth", "zoom": [1.2, 1.45], "mix": 0.3, "look": "crisp4k"}
```
Top-level options: `"guard_cuts": true` (default) and `"look": "hdr" | "crisp4k" | ...`.
`story` prints each shot's source window, and warns when a shot would cross a scene cut.

## Readability
Every text card is held long enough for an average viewer to read it: 0.4 s plus 3 words per second, with a minimum of 1.2 s, plus the typing time for `type` cards. A card is extended up to the next card in the same screen area, and `story` prints `!` for anything still too short or for too much text overall. Tune it with `"reading": {"wps": 3.0, "min_on": 1.2}`, or turn it off with `"reading": {"off": true}`.
