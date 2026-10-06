# Translating other editors' effects

This is the only file that uses other products' names. They're here so a reference like "Twixtor
into a Deep Glow slam with S_Shake on the drop" can be read and rebuilt with this tool's own
effects. Everything else in the repo uses our names. All product names are trademarks of their owners;
this project isn't affiliated with any of them. Field details are in `EFFECTS.md` and `STORY_SPEC.md`.

## Units
| Theirs | Ours |
|---|---|
| frames | seconds = frames ÷ project fps. Story specs use **beats** (1 beat = 60 ÷ BPM s). |
| speed 400% / 4x | `4.0` |
| scale 120% | zoom `1.2` |
| rotation +10° (clockwise) | `rot: -10`; our positive angle turns counter-clockwise |
| position in px (1080×1920) | hit `px`, image `x`/`y` in px; shot framing `cx`/`cy` is 0–1 of the source |
| Easy Ease (F9) | the default smoothstep easing on shot `zoom: [a, b]` |
| steep graph-editor curves (influence 80–100%) | `zooms` with `ease` 4–6 |
| linear keyframes | hit `shape: "lin"` |
| opacity flicker | `flicker` hit, or `hum` on text and images |

## After Effects (and its plugins)
| Theirs | Ours | How to set it |
|---|---|---|
| Twixtor, Timewarp, Pixel Motion | flow slow-mo | shot `interp: "flow"` with a slow `speed` (`settle`, `slow`, `slower` or a number). Pros key Twixtor Speed between 100% and 20–35%, with short kicks to 150–200% |
| RSMB, Pixel Motion Blur | vector blur | `motion_blur: "flow"` (180° shutter) |
| Layer motion blur, Transform shutter angle | camera motion blur | `camera_blur` (on by default) |
| Twitch | jolt | `jolt` hit: Amount → `amt`, Speed → `speed` 0–1, Random Seed → `seed` |
| S_Shake, `wiggle(freq, amp)` | shake | `shake` hit: Frequency → `freq` Hz, Amplitude → `px`, plus `rot`. For a constant wiggle use `fx: {"handheld": px}` |
| Deep Glow, S_Glow, Glow | bloom | Threshold 60% → `bloom_threshold: 0.6`, Intensity → `amt` (hit) or `bloom` (fx); on text use `glow`, `glow_radius` and `glow_color` |
| Motion Tile (Mirror Edges) | mirror edges | on by default (`"edge": "mirror"`) |
| Optics Compensation | bulge | `bulge` hit: FOV 60–100 is about `k` 0.4–1.0; Reverse Lens Distortion is `k < 0` |
| Echo | echo | `echo` amount 0.4–0.8 (4 trails with 0.65 decay) |
| Posterize Time | stepped fps | shot `stepped_fps: 8–12` |
| Time Remap and the speed graph | speed profiles | `ramp` (U), `quick`/`ease_in`, `push`/`ease_out`, `decel`, `smooth`, or `{"type": "ramp", "hi", "lo", "k", "center"}` |
| Chained Null objects (scale, rotation, position) | zoom chain | `zooms: [{at, scale, x, y, rot, dur, ease}]` |
| Flow / ease presets | S-curve easing | `zooms` `ease`: 2 is soft, 4 snappy, 6 very snappy |
| Transform scale punch | punch | `punch` hit `amt` 0.06–0.2 |
| CC Radial Blur (zoom), zoom transitions | zoom transition | `zoom_in` / `zoom_out` hits (radial blur included) |
| Directional Blur | blur | `blur` hit `px` |
| Gaussian / Fast Box Blur background | background plate | shot `blur` + `dim` |
| Shift Channels, RGB split, Channel Offset | RGB split | `rgb` hit `px`; plan-wide `base_rgb` |
| Chromatic aberration (radial) | radial aberration | `rgb_radial` |
| Exposure flash, strobe | flash / flicker | `flash`, `exposure`, `flicker`; dip to black is `black` |
| Invert | invert | `invert` hit |
| Lumetri, Curves, Hue/Saturation, Vibrance | looks | `crisp4k`, `hdr`, `teal_orange`, `dark`, `mono`, `punchy`, `warm_film`, `clean`; add new ones in `fx.Look.PRESETS` |
| Sharpen, Unsharp Mask | look `sharp`, `clarity` | |
| Vignette, Noise/Grain | look `vig`, `grain` | |
| Light leak overlays | leak | `leak` (fx or hit) |
| VHS / CRT packs | vhs | `vhs` |
| Glitch packs | glitch | `glitch` hit |
| Cross Dissolve | mix | shot `mix: 0.3` |
| Typewriter / Scale-in / Slam text presets | text anim | `type`, `pop`, `slam`, `fade` |
| Title templates, poster / lockup layouts | poster frames | `"style": "poster"` (`stack`, `mark`, `bg`, `panel`) |
| Saber (glowing outline) | text glow | `glow` + `glow_color` (a soft glow, not a traced outline) |
| Cinematic bars | letterbox | `letterbox: 0.08–0.12` |
| BCC Lens Blur, Camera Lens Blur (Iris Scale keys) | defocus | `defocus` hit (`px`) |
| Focus hunting / rack focus (Camera Lens Blur keyed soft into a cut, then soft-sharp-soft-sharp) | focus-hunting cut | `focus` hit (automatic on every cut) |
| Zoom cut (Transform Scale push across a cut) | zoom cut | `zoomcut` hit (automatic on talking-clip jump cuts) |
| S_EdgeDetect / S_EdgeColorize + Deep Glow on a duplicate layer | neon edge ghost | `edges` hit (`color`, `grow`) |
| S_EdgeRays | light rays | `rays` hit |
| S_HalfTone, BCC Halftone | halftone | `halftone` hit or `fx` key |
| BCC Ripple Dissolve | ripple | `ripple` hit (`x`, `y`, `px`, `wavelength`) |
| CC Light Sweep | light sweep | `sweep` hit; on a cut-out subject use `rim` |
| CC Jaws | jaw bars | `jaws` hit (`depth`, `teeth`, `tilt`) |
| S_Flicker | film flicker | `fx: {"film_flicker": 0.15}` |
| S_FilmDamage, dust overlays | film damage | `fx: {"dust": 0.5}` |
| S_TVDamage (band shift, scanlines) | VHS | `vhs` |
| Color Balance (HLS) / Hue-Saturation saturation dips | desaturate | `desat` hit |
| Transform Scale Height (stretch or squash) | stretch | `stretch` hit (`amt` 0.35, or −1 with `att` to squash out) |
| S_BlurMoCurves Shift X/Y with wrap, Motion Tile + Position slide | full-frame slide | `whip` (`dist` 1, `axis`) |
| S_BlurMoCurves Shift Y with damped keys (−400, 50, −25, 10, 0) | spring drop-in | `bounce` hit |
| S_BlurMoCurves Z Dist from near 0 to 1 | fly-out of an extreme zoom | `zoom_in` hit with `scale` 1–2, or a `zooms` keyframe |
| Warp (Fisheye style, Bend −100) | pinch | `bulge` hit with `k` −0.8 and an `att` into the cut |
| 3D camera parented to a chain of nulls (one move per beat) | camera flow | shot `camera_flow` |
| Adjustment layer per beat (Lens Blur + Exposure keys) | beat pulse | shot `pulse` |
| Time Remap with one hold keyframe | freeze frame | `speed: "freeze"` |
| Roto Brush (text behind the subject, rim-lit cut-outs) | subject cut-out | text `behind: true`, `rim` hit (optional cut-out model) |
| Keylight on an overlay clip | chroma key | overlay `key` [r, g, b] |
| Overlay / particle / shadow clips in Screen, Add or Lighten | overlays | `overlays` with `blend`, `tint`, `rot`, `opacity` |
| Tracker → Null → parented text | tracked text | text `follow: true` |
| Text range selector Start (by characters or words) | reveal | `anim: "type"` or `"words"` |
| Text animators with random position, rotation and scale (TextEvo-style) | letters | `anim: "assemble"`, `exit: "scatter"` |
| Gradient Ramp on text | gradient text | text `gradient` |
| Stacked soft Drop Shadows on text | soft halo | `glow` + `glow_color` [0, 0, 0] |
| Picture-in-picture over a halftone / black-and-white copy | card | shot `layout: "card"` |
| Audio Levels dips before cuts, Bass & Treble cut at the end | music gaps, bass thin-out | `gap` hits; the thin-out is automatic |
| Turbulent Displace, Wave Warp, Displacement Map, Puppet, text on a path | none yet | build it on request (below) |

## Alight Motion
| Theirs | Ours |
|---|---|
| Keyframe graph / Velocity easing | `zooms` `ease`, shot `speed` profiles |
| Shake | `shake` hit; Swing is `handheld` or `spin` |
| Motion Blur | `camera_blur` (camera moves), `motion_blur` (fast footage) |
| Tile / Mirror | mirror edges (default) |
| Glow, Neon | `bloom`, text `glow` |
| Chromatic Aberration, RGB split | `rgb_radial`, `rgb` |
| Zoom Blur, Radial Blur | `zoom_in` / `zoom_out` |
| Fisheye, Lens Distortion | `bulge` |
| The HDR set-up (Exposure, Gamma, Vibrance, threshold glow, inner-blur difference layer) | `hdr` look |
| Color & Fill, Exposure, Contrast | looks, `exposure` hit |
| Speed & Duration, Time Remap | shot `speed` profiles |
| Lens Blur, Halftone, Ripple | `defocus`, `halftone`, `ripple` |
| Wave, Turbulence, Warp | none yet; build it on request |

## CapCut
| Theirs | Ours |
|---|---|
| Speed → Curve: Montage | `{"type": "ramp", "hi": 4, "lo": 0.3}` |
| Speed → Curve: Hero | `{"type": "ramp", "hi": 3, "lo": 0.2, "k": 3}` (bigger `k` = longer slow middle) |
| Speed → Curve: Bullet | `{"type": "ramp", "hi": 1.5, "lo": 0.1, "k": 3}` |
| Speed → Curve: Jump Cut | `quick` |
| Speed → Curve: Flash In / Flash Out | `decel` / `push` |
| Speed → Curve: Custom V (10x, 0.1x, 10x) | `smooth` |
| Smooth slow-mo (better quality) | `interp: "flow"` |
| Auto beats / beat markers | built-in beat and drop detection; story times are beats |
| Mix transition | `mix` |
| Pull in, Zoom lens | `zoom_in` / `zoom_out` |
| Slide, Swipe | `whip` (`"axis": "y"` for up/down) |
| Spin, Glitch, Flash, Shake transitions | `spin`, `glitch`, `flash`, `shake` |
| Effects: Shake, Blur, Strobe, RGB split, VHS/Retro, Light leak, Glow/Neon, Fisheye, Black flash | `shake`, `blur`, `flicker`, `rgb`, `vhs`, `leak`, `bloom`, `bulge`, `black` |
| Reverse | `speed: "reverse"` |
| Reverse trend (clip + reversed copy) | `speed: "boomerang"` |
| Keyframe scale with graph easing | shot `zoom: [a, b]` or `zooms` |
| Text animations: Typewriter, Pop up, Bounce/Blast | `type`, `pop`, `slam` |
| Adjust: brightness, contrast, saturation, sharpen | looks |

## Building something that isn't here
1. **Break it down.** What moves (scale, position, rotation, time), its keyframes and easing, and any blur, colour or blend mode.
2. **Use what exists first.** Hits (`t`, `att`, `dur`, `shape`), shot `speed` profiles, `zooms`, image `kf`, looks and `fx` cover most tutorials.
3. **Otherwise add it.** Write `def name(frame, amt, ...)` in `clipper/fx.py` (uint8 BGR in, uint8 BGR out). In `clipper/render.py`, read the hit's strength in the `Renderer._camera` hit loop (`elif typ == "name": c["name"] = max(c.get("name", 0), a * e)`), then apply it in `_shot_image` next to the other pixel effects (`if c.get("name", 0) > 0.01: img = fx.name(img, c["name"])`). Camera-style moves add to `c["zoom"]`, `c["dx"]`, `c["dy"]` or `c["rot"]` instead.
4. **Ship it properly.** Add a row to `docs/EFFECTS.md` and to this file, give it a default sound in `audio.SFX_FOR` if it's a transition, and check it with `fxdemo` or a short `plan-render` plus a `sheet`.
