# Effects reference

There are two ways to apply effects:

- **Hits** are timed events with an envelope: they attack over `att` seconds, then decay over `dur` seconds.
- **Continuous fx** stay on for a whole edit (`plan.fx`) or a single shot (`shot.fx`).

In story specs, hits use `"at"` (in beats); in raw plans they use `"t"` (in seconds).

```json
{"type": "shake", "at": 8, "amt": 1.0, "dur": 0.3, "freq": 16, "px": 50}
```

Common hit fields:
- `amt`: strength, 0–1.5.
- `dur`: decay time in seconds.
- `att`: attack time in seconds; use it when the effect should build into the cut.
- `shape`: `exp` (default), `lin`, or `hold` (full strength for the whole `dur`).

## Camera and transitions
| type | what it does | key params |
|---|---|---|
| `focus` | focus-hunting cut: racks soft over `att` before the cut, then the next shot hunts (nearly sharp, soft again, sharp) over `dur`, the frame breathing slightly; added on every cut automatically | `px` 10–16, `att` 0.1–0.2, `dur` 0.3–0.45 |
| `zoomcut` | zoom cut: pushes in over `att` before the cut, the next shot lands pushed in and eases back over `dur` (radial blur); the default on talking-clip jump cuts | `scale` 0.1–0.12, `att` 0.1, `dur` 0.28 |
| `punch` | zoom punch-in | `amt` 0.06–0.2 |
| `shake` | decaying sine shake with rotation and motion blur | `px` 20–60, `freq` 12–22, `rot` |
| `handheld` | smooth, Perlin-like drift | `px` 8–20, `speed` |
| `zoom_in` | zoom transition: pushes in before the cut and settles after, with radial blur | `scale` 0.6–1.2, `att` ≈ 0.1 |
| `zoom_out` | pull-out with radial blur | |
| `whip` | whip-pan: slides a full frame (with mirror edges) and blurs across the cut | `dir` ±1, `axis` `"y"` for a vertical swipe, `dist` (1 = one frame width) |
| `bounce` | damped-spring drop-in: the shot lands displaced, overshoots and settles | `px` (a quarter of the height), `freq` 3, `damp` 7, `axis` `"x"`, `dir` ±1, `dur` ≈ 0.5 |
| `stretch` | vertical stretch (`amt` 0.35 → 135% tall) or squash (`amt` −1 collapses to a line; use `att` to squash out into a cut) | `amt` −1…0.5 |
| `spin` | rotation transition with zoom and blur | `deg` 15–40 |
| `bulge` | lens distortion: fisheye bulge (`k>0`) or pinch (`k<0`), the zoom-transition "suck" | `k` −0.6…1.0 |

Edges are mirrored by default (plan or shot `"edge": "mirror"`, the motion-tile look), so shakes, spins and zoom-outs never show black borders. `"edge": "blur"` fills with a blurred, darkened copy instead (the clip-page default), and `"stretch"` repeats the edge pixels.

**Face-safe framing.** Shots with `"layout": "fill"` are framed on the faces found in them (YuNet, `clipper/reframe.py`): the speaker in a two-shot, eyes on the upper third, and a zoom limit per scene that keeps the whole head in frame. When a head doesn't fit even the plain 9:16 crop, the picture is shown smaller and the `edge` fill shows above and below. A shot's `"fit": false` turns the limit off; `cx`/`cy` set the centre by hand.

## Light and colour
| type | what it does |
|---|---|
| `flash` | white flash (2–5 frames on a beat) |
| `black` | dip to black; with `att` it fades in before a time (the blackout before a drop) |
| `exposure` | brightness pulse (`amt` > 0 brightens) |
| `flicker` | strobe that alternates bright and dark frames |
| `invert` | negative flash |
| `bloom` | highlight bloom (`amt`; continuous key `bloom`, `bloom_threshold`) |
| `leak` | procedural light leak drifting across the frame |
| `rgb` | RGB split, horizontal channel offset (`px` 10–35) |
| `rgb_radial` | radial chromatic aberration, like lens fringing (`px` 0.01–0.04) |
| `defocus` | lens defocus (a round, disc-shaped blur like a real lens); a focus pull into a shot when it decays (`px` 12) |
| `desat` | colour drains out (`amt` 1 = black and white) |
| `halftone` | print-dot screen flash (also continuous `fx` key `halftone`) |
| `rays` | light rays streaking out of the bright edges (`color`, `length` 0.35) |
| `sweep` | a band of light crossing the frame over `dur` (`angle`, `width`, `color`, `amt`) |
| `edges` | neon outline flash; the outline grows as it fades, like a ghost bursting out (`color`, `grow` 0.45) |
| `rim` | glowing rim around the person (`color`); needs the optional subject cut-out |

## Texture and time
| type | what it does |
|---|---|
| `glitch` | slice displacement plus channel offset |
| `vhs` | scanlines, chroma bleed, noise and a rolling tracking band |
| `echo` | frame trails (`amt` 0.4–0.8) |
| `blur` | directional blur (`px`) |
| `jolt` | jolts across blur, colour, light, scale, slide and time stutter, re-rolled every 2 frames. `speed` 0–1 sets the density and `seed` the variation |
| `jaws` | jagged black bars biting in from top and bottom (`depth` 0.2, `teeth` 9, `tilt` ±6, `opacity` 0.8); about half a beat, on the beat |
| `ripple` | water ripple spreading from `x`, `y` (0–1) with a shine on the crests (`px` 22, `wavelength` 90) |
| `gap` | audio only: dips the music by `db` (−18) for `dur` (0.12 s) right before its moment. Never automatic; viewers hear it as the music cutting, so use it only when asked |

Continuous `fx` keys (plan-wide or per shot) also include `film_flicker` (0.12–0.2, an irregular exposure flicker), `dust` (old-film specks and scratches) and `halftone`.

Shot options:
- `"stepped_fps": 8–12` gives a choppy, stepped frame rate (stepped fps).
- `"interp": "flow"` gives flow slow-mo (optical-flow slow motion).
- `"blur": 10, "dim": 0.5` produces a blurred, darkened background plate for overlays.

## Flow slow-mo and vector blur (`clipper/flow.py`)
- **Slow motion (`interp`):**
  - `"flow"` uses DIS optical flow and Super-SloMo flow approximation, with an occlusion test: where the two warped neighbours disagree, it takes the nearer frame instead of ghosting. It looks clean on moderate motion (faces, bodies, cars). On extreme whip-fast motion thin edges can still warp; cut away or speed up there.
  - `"blend"` (the default) is a cheap cross-fade.
  - `interp_fps: 60` pre-interpolates with ffmpeg `minterpolate`.
- **Motion blur (`plan.motion_blur`):**
  - `"flow"` gives vector blur along the optical flow, scaled by playback speed with a 180° shutter.
  - `true` averages sub-frames.
  - `false` turns it off.

## Looks (grades)
`clean`, `punchy`, `teal_orange`, `dark`, `mono`, `warm_film`, `bright` (wholesome: airy, colourful, glowing highlights), plus `crisp4k`, `hdr` and `poster` below. Each is a contrast S-curve with shadow and highlight tint, saturation, sharpening, grain and vignette. A shot's `look` overrides the plan default, so a story can go from mono in the setup to colour on the drop.

## Text layers
Fields:
- `anim`: `pop`, `slam`, `type` (letters), `words` (word by word, in place, over `type_dur`), `assemble` (letters fly in from scattered spots, spinning and growing) or `fade`.
- `exit: "scatter"`: in the last `exit_dur` (0.6 s) the letters fly apart, spin and shrink (`scatter_px` 520, `scatter_rot` 360). Use `assemble` and `scatter` with Latin text; joined scripts break when split into letters.
- `gradient`: `[[r,g,b], [r,g,b]]`, a top-to-bottom fill. `rot`: degrees (90 = sideways). `x`, `y`: centre in px.
- `follow: true` (story) rides the text along with the subject of the shot it starts on, 260 px above it by default (`{"dx": 0, "dy": -260}`). `behind: true` puts the person in front of the text; it needs the optional subject cut-out, so give behind-text the lowest `z`.
- A soft dark halo for readability: `glow` 0.8 with `glow_color` `[0, 0, 0]`.
- `glow`: 0–1.2, with `glow_radius` and `glow_color`.
- `hum`: 0–0.6 sets the depth of the audio-reactive 50 Hz flicker. A 50 Hz sine sampled at 30 fps aliases to a slow three-frame shimmer. Its depth follows the music's onset envelope, and the hardest onsets drop the layer for one frame. Set `hum_drop: false` to keep logos solid.
- `[brackets]`: words inside brackets use the `accent` colour.
- `bar`: `[r,g,b]`, a solid bar behind each line (`bar_pad` 0.35 of the size), for meme labels such as a red bar reading MOGGED across the eyes (the `label` style; put it on a freeze frame with `follow: {"dy": 0}` to sit on the eyes).
- Story text styles: `title`, `slam`, `type`, `subtitle` (small, white, word by word, fading out), `label` and `poster`.
- Captions (`plan.captions.style`): `clip` (big, bold, 1–3 words, the clip-page style) or `edit` (one small line that fades up word by word as it is spoken, key words in red; the default for story dialogue). Hindi and other non-Latin scripts switch to a font that contains them. Joined scripts render best where Pillow has complex-text layout (libraqm); without it a few joined letters may not form.
- `font`: `heavy`, `condensed`, `bold`, `regular`, `poster`, `wide`, `mono`, `hand` (thin handwritten), or a path to a .ttf file.

## Poster frames (`"style": "poster"`)
Full-frame display type composed like a printed poster. Use them rarely (see `PLAYBOOK.md`). While a poster is up it is the only overlay drawn: other text, images, captions and titles are hidden.

| field | what it does |
|---|---|
| `layout` | `stack` (default): one line per word, or split lines with `/`. `mark`: one wordmark |
| `fit` | stack only: `block` (default) sets one size from the widest line; `lines` makes every line fill the width |
| `w`, `h` | width as a fraction of the frame (stack 0.86, mark 0.6; above 1 bleeds off the edges); the stack's maximum height (0.62) |
| `y`, `align` | vertical centre in px (960); `l`, `c` or `r` |
| `leading`, `step` | gap between lines (0.07 of a line); how far a `|` split drops the rest of its line (0.45) |
| `font`, `color` | `poster` (Anton), `wide` (Archivo Black), `bold`, `mono`, or a .ttf path; one RGB colour |
| `sup`, `tag` | mark only: a small superscript such as `®`; a 2–3 line lockup to the right (`"CREATIVE\nCONTENT\nAGENCY"`) |
| `rot`, `skew` | tilt in degrees (positive turns counter-clockwise); oblique slant in degrees |
| `bg`, `panel` | a solid colour card behind the type; a paper panel `{"y": 0.76, "color": [245, 245, 242]}` from y to the bottom |
| `extras` | small labels `{text, x, y (0–1), size, font (mono), align, box, color}` |
| `anim` | `cut` (default), `stack` (one line at a time over `reveal` s), or `zoom` (flies in through the letters from `zoom_from` 6x over `zoom_dur` 0.35 s) |
| `texture`, `soft` | speckled ink (0.15) and edge softness in px (0.6); raise both for a printed feel, or set 0 for crisp vector type |
| `grow`, `fade_out` | slow scale creep per second (0.008); fade at the end in seconds |

The `poster` look (heavy grain, rich colour, no sharpening) and `"speed": "hold"` make the footage underneath behave like the image on a poster.

## Shot extras
- `"layout": "card"`: picture-in-picture. The shot shrinks to `card_scale` (0.78) with rounded corners and a soft shadow over a treated copy of itself (`card_bg`: `halftone`, `mono` or `blur`).
- `"speed": "freeze"`: a freeze frame. `hold` is a near-freeze with a little life.
- `"camera_flow": {"every": 1, "zoom": 0.12, "roll": 10, "pan": 0, "dur": 1.6, "ease": 2.5}` (story shots): every beat adds a new eased camera move on top of the last, alternating dolly in/out and roll left/right. Use `true` for the defaults.
- `"pulse": 1` (story shots): every N beats, an exposure kick (+0.7) and a defocus snap that decay over the beat.
- `zooms` keyframes take `"curve": "out"`: the move bursts out on its beat and glides to rest, instead of an S-curve centred on the beat.

## Overlays and photo bursts
- `overlays` (story or plan): user-supplied clips such as light leaks, particles, dust or smoke, blended over the footage. Fields: `{path, from, to, blend: screen|add|lighten|multiply|overlay, opacity, tint [r,g,b], key [r,g,b] (chroma key, key_tol 90), scale, rot (90 turns a landscape clip upright), speed, src_in}`. The tool ships no overlay footage; use your own or royalty-free packs.
- `burst` (story): a photo strobe, only with photos the user supplies for it (never a stand-in for footage). `{"paths": [...], "from": beat, "frames": 2, "w": 1080, "y": 960}` shows each picture for 2 frames.

## Image layers
Thumbnails, logos and cards take these fields:
- `w`, `x`, `y`, `rot` for size, position and rotation.
- `radius`, `border`, `shadow`, `circle` for shape.
- `glow`, `hum` as for text.
- `anim`: `pop`, `slam`, `drop` or `fade`.
- `grow`: slow scale creep.
- `kf: [[t, x, y, scale], ...]`: keyframed motion with smoothstep easing (used for the cursor and button press).

## Velocity zoom chain (`zooms`)
A chain of zoom keyframes, each with scale, rotation and position, where every move builds on the last. Every zoom lands on a beat and pushes **further** into a new point, such as the chest, then the face, then the eyes. The edges stay mirrored the whole time, and each move is motion-blurred.

```json
"zooms": [{"at": -3, "scale": 1.35, "x": 0.5, "y": 0.55, "rot": -4},
          {"at": -2, "scale": 1.9,  "x": 0.5, "y": 0.42, "rot": 3},
          {"at": -1, "scale": 2.6,  "x": 0.5, "y": 0.33, "rot": -2}]
```
- `scale` is the absolute zoom at that keyframe. Scales interpolate in log space, so each step feels the same size. To "keep zooming", keep raising it, then pull back to about 1.1 at the end; never land all the way out.
- `x`, `y` are the normalised source point to centre on, and `rot` is the tilt in degrees.
- `dur` is the move length in beats (default 0.5).
- `ease` is the S-curve steepness (default 4, a snappy S-curve). The velocity peaks exactly on the beat.
- **Velocity sync.** Unless the shot sets its own `speed`, playback speed is remapped to spike on each zoom beat. This is the "align the speed-graph peak with the marker" rule. Tune it with `"velocity": {"hi": 2.2, "lo": 0.35}`, or turn it off with `"velocity": false`.

## Camera motion blur
Camera motion blur is on by default (`plan.camera_blur`). Whenever the camera moves fast (zoom chains, punches, shakes, spins, whips), the warp is re-rendered at up to 10 sub-frame times across a 180° shutter and averaged. Fast moves smear naturally, and holds stay sharp.

## Retiming presets
| `speed` | curve | look |
|---|---|---|
| `smooth` | V curve: about 6x → 0.15x → 6x | the "smooth transition" feel; pair it with `mix` |
| `decel` | 8x → 1x, cubic out | a whip into the moment |
| `boomerang` | forward, decelerating 4x → 0.4x, then the same frames **backwards** | the reverse / back-and-forth trend; the zoom follows the time (`zoom_follow`), in going forward and out coming back |
| `reverse` | plays backwards, landing slow | rewind beats |

Boomerang and reverse shots decode their segment into memory for random access, so keep them short (1–3 s of source).

## Dissolve (`mix`)
`"mix": 0.3` on a shot cross-dissolves into it from the previous shot over 0.3 s, while the previous shot keeps playing; it doesn't freeze. Cuts with `mix` skip the automatic flash and shake, so smooth sections stay smooth.

## Scene-cut guard
Speed-ups consume more source than the shot's length. `story` detects scene cuts once per source (cached in `work/`) and slides each shot's source window inside the scene that contains its `peak`. If the scene is too short, it prints a warning naming the shot. When you see one, use a slower speed, a shorter shot or a different peak. Turn it off with `"guard_cuts": false`.

## More looks
- `crisp4k`, the "4K" edit grade:
  - sharpen, plus a big-radius unsharp mask for clarity
  - a brightness lift and contrast boost
  - saturation of about 1.2, plus vibrance
  - a teal/orange split tone, highlight glow and vignette
- `hdr`, the HDR look:
  - exposure and gamma lift, with shadows lifted and highlights held
  - strong local contrast (the inverted-blur difference trick)
  - vibrance of 1.16
  - highlight glow at threshold 0.83, screen-blended at about 20%

## Sound effects
Every sound is generated in code from noise and sine waves, so it's copyright-free. `clip.py sfx` writes the kit to `./sfx`.

| sound | used for | level vs the music |
|---|---|---|
| `drop` (impact + boom), `impact` | the drop, the end-card slam | −13 / −15 dB |
| `boom`, `sub_drop` | low-end hits | −17 / −18 dB |
| `riser` | swells into the drop and ends exactly on it | −20 dB |
| `hit` | slam text | −20 dB |
| `whoosh` | `zoom_in` and `spin` transitions | −20 dB |
| `swoosh` | `whip` / swipe transitions | −21 dB |
| `rewind` | the turn-around point of a `boomerang` | −21 dB |
| `reverse_cymbal`, `downlifter` | a swell into a moment, `zoom_out` | −21 / −22 dB |
| `swish` | each `zooms` move | −24 dB |
| `glitch` | `glitch` and `jolt` | −24 dB |
| `shutter`, `pop`, `click` | thumbnails and cards, pop-in text, the subscribe click | −26 / −26 / −27 dB |
| `typing` | one key press per character of `type` text | −32 dB |
| `tape_stop` | a fake-out before a drop | −20 dB |

How placement works:
- Levels are measured against the loud parts of the actual track, so they sit right whether the song is quiet or brickwalled. The whole mix is then normalised to −14 LUFS.
- Swells (whoosh, riser and reverse cymbal) start early so their peak or end lands on the beat.
- When two short sounds land within 0.12 s of each other, only the louder one plays, so a slam on the drop doesn't stack a hit on the impact.
- In story specs, every hit takes `"sfx"`: a sound name to override its default, or `null` for silence. `"sfx": false` at the top level turns all sounds off.
