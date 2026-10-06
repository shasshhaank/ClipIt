# Clipping playbook: the taste, as rules
All numbers are at 30 fps. One beat = 1800/BPM frames (130 BPM ≈ 14f ≈ 0.46 s).

## Picking the moment (the most important step)
- Hook in the first 0–2 s: the boldest claim, an absolute ("nobody", "never", "the truth is"), a direct attack, or a number with stakes. If the best line sits mid-clip, **open on it** (cold open), then cut back.
- A polarizing clip makes half the viewers want to comment "W" and the other half "L". It takes a side and names a target.
- Clip page: 20–60 s and one complete idea, ending on a punchline or open question (a loop or a comment bait). Cut pauses over 0.45 s down to 0.12 s.
- Fan edit: 7–15 s = 4–8 bars, with the drop at 2–4 s (or straight after a 2–5 s dialogue hook). End on a beat, fade or flash to black, and land the last frame close to the first so it loops.

## Comeback reels: doubts first, then the answer
For "they doubted him" stories, build the doubt out of real voices before the comeback:
1. **The doubts (about 35–45% of the runtime).**
   - Make a compilation of 3–5 real soundbites of people speaking against him: pundits, news panels, press conferences. Each is 2–4 s and is the sharpest single sentence.
   - Play each as a `voice` shot (its own audio, with the music ducked) with `captions` so every word reads.
   - Put headline flashes and dejected or lonely shots of him between them, in mono or dark, with the music sparse or in its quiet intro.
   - Cut the voices closer and closer together so the pressure builds, and end on the harshest line.
2. **The turn.** A beat of silence or blackout (a `gap` and a `black` hit), then the moment that answered them, landing on the drop.
3. **The comeback (about 45–55%).**
   - Show the performance, the celebration and the proof (stats you verified), in full colour with velocity and jolts.
   - A strong move is a callback: echo one critic's line, then answer it with the result.
4. **The close.** A calm hero shot and one status line.

Finding the soundbites:
- Search for debate or panel videos about the subject (`find`), then run `analyze` on them. The transcript and the ranked moments surface absolute, confrontational lines.
- Pick lines that are about the subject and mean what they say. Use them verbatim and in context, never cut to reverse their meaning.
- Name the speaker or outlet with a small label if it helps.

## Edit level (asked in the intake, 1–10)
How much the edit does by itself. Clean is about 5 and hyper is 10; when in doubt go one step cleaner.

| level | cuts | effects | sound |
|---|---|---|---|
| 1–2 barely edited | every bar, straight speed | none, just the grade and a fade out | music only |
| 3 minimal | every bar | a blackout and a soft flash on the drop | the drop |
| 4–5 clean | every 2 beats, gentle ramps | soft punch-ins, a zoom or whip every 4th downbeat, a light drop shake (5) | transitions, riser and text sounds from 5 |
| 6–7 punchy | hero + quick cuts from 7 | flash and shake on bar lines, bloom on the drop, transitions every 2 beats (7) | all of the above |
| 8–10 hyper | hero + quick cuts | adds RGB split, glitch and spin transitions, a second drop hit and a pre-drop rumble, all stronger toward 10 | everything |

Effects you write into a spec by hand (`hits`, `zooms`, speeds) always play; the level only governs the automatic ones. Poster frames don't scale with the level.

## Cutting to music
- Cuts land ON the beat (kick). Build-up: every 2 beats, then every beat in the final half-bar. Drop: a hero shot (2 beats, velocity ramp), then 1-beat quick cuts, with a hero on every downbeat.
- Velocity ramp: fast (350–450%) → slow (25%) → fast, U-shaped, with the slow part on the action peak. Speed into the cut, not out of it.
- Build-up shots: constant 40–50% smooth slow-mo (motion-interpolated).
- Silence or a tape stop 0.5–1 beat before the drop is a fake-out; the riser ends exactly on the drop.

## Effects menu (what fires when)
| Moment | Effect | Parameters |
|---|---|---|
| THE DROP | white flash + heavy shake + zoom transition + RGB split + impact/boom SFX, then 1 bar of flicker | flash 4–5f, shake 60px/18 Hz decaying over 15f, zoom 200%→100% |
| Downbeat cut | flash + shake | flash 3f, shake 50px/16 Hz for 9f |
| Strong beat | RGB split | 22px fading over 4–5f |
| Other cuts | punch-in + exposure pulse | +10% zoom easing back over 8f |
| Every 2nd downbeat post-drop | transition: zoom-in / whip / spin / glitch (rotating) + whoosh 0.38 s early | 3f attack, 4f release |
| Talk keywords | punch-in +8% (and light shake on the hardest words) | 14f |
| Jump cuts (talk) | alternate 100% / 118% framing | gives a 2-camera feel |

## How pros build these edits (studied from real project files)
Patterns that came up again and again in working After Effects projects for velocity, gym, lyric and emotional edits.

**Speed is gentler than you think.** Across every speed keyframe, normal speed (100%) was the anchor and slow motion sat at 20–35%. Fast parts were short kicks to 150–160% and only rarely 200%; nothing went higher. The workhorse is `settle`: real time decelerating into 30%. `quick` kicks to 1.6x and slides to 35%. A `ramp` peaks at 1.8x.

**Every shot has a life.** In velocity sections (shots of 0.6–1.3 s):
- It starts at 100% speed (or kicks to 150%) and decelerates to 20–60%.
- It starts zoomed in (about 1.2–1.4x) and settles outward over the whole shot, fast at first, then gliding.
- It starts slightly defocused and snaps into focus within about 0.3 s.
- It starts bright and holds, then sinks toward black in the last frames before the cut, so every cut "blinks".
- A small jolt or shake peaks on the cut.

`story` and `edit` add the zoom settle from level 4, the focus pull from level 5 and the blink from level 6.

**Transitions they actually use:**
- Full-width slide with mirror edges (`whip`, `dist` 1): accelerate out of the old shot, decelerate into the new one.
- Damped-spring drop-in (`bounce`): the new shot lands displaced, overshoots and settles in about 0.4 s.
- Squash out (`stretch` with `amt` -1 and an `att`): the old shot collapses vertically into the cut.
- Zoom-through: `zoom_in` plus `spin` (about -45°) out of one shot, then the next shot flies back out of it.
- Jagged black bars biting in for half a beat (`jaws`), repeated on the beat in hype sections.
- A neon edge ghost (`edges`): the outline flashes on the first frames of a shot and grows as it fades.

**Beat-driven camera.** In hype sections, every beat adds a new eased camera move on top of the last: a dolly in or out, a roll of 10–40° and a small drift (`camera_flow`). Optionally, a `pulse` on every beat adds about +0.7 stop of exposure and a defocus snap, both decaying over the beat. Strong vector motion blur and a slow handheld drift sit over the whole edit.

**Climax montage:** micro-shots of 6–15 frames, each with a flash-in, a 1–3 frame blur and jolt at both ends, a slowdown from 100% to 60%, a bright-to-dark exposure ramp and a vertical `stretch` to 1.35. A photo `burst` (2 frames per picture) works the same way.

**Emotional / lyric edits:** shots of 2–2.5 s, each decelerating from 100% to 20–50%, darkening at the tail and pulling focus at the head. Water ripples and soft dissolves join them, and there's no shake.

**Intros:** slow and dark. Fade up from black over about 1.5 s, a long focus pull, 100% → 10% speed, a subtle handheld drift, and one small lowercase caption (the `hand` font).

**Text in these edits:**
- Lyrics and dialogue are small (55–70 px), in italic, handwritten or condensed faces, and revealed word by word (`anim: "words"`) over 0.6–1.3 s.
- They fade out over the last 0.15–0.3 s, with glow plus a soft dark halo (`glow_color` [0, 0, 0]).
- They're sometimes turned sideways (`rot` 90) or filled with a gradient (`gradient`).
- When a subject moves, pros track the text to them. That isn't automatic here yet, so place the text in clear space instead.

**Texture:** a constant subtle film flicker (`film_flicker` 0.12–0.2), light, particle or shadow overlay clips in screen blend, tinted to the edit's colour (`overlays`), and the sharpen + clarity + look stack (`crisp4k`).

**Sources:** they upscale and clean their sources before editing, and they cut real motion footage, never photo slideshows. Always fetch the highest resolution available; slow it with flow slow-mo and hit the cuts with jolts.

## Sound design
- Sounds follow the picture. Each transition has its own sound (whoosh for zoom and spin, swoosh for whip, glitch for glitch), and every zoom-chain move gets a short swish. The drop gets a riser that ends on it, then impact + boom. Slam text gets a hit, pop text a pop, and typed text quiet key presses.
- Set levels against the music, not in absolute terms. The drop sits about 13 dB under the track, transitions about 20 dB under, and small details (clicks, pops, typing) 26–32 dB under. You should feel them, not notice them; if a click or swoosh stands out on playback, it is too loud.
- One sound per moment. If a slam lands on the drop, the drop's impact covers it.
- Leave a gap. Pros dip the music 10–20 dB for 3–7 frames right before a drop or a big cut, so the hit lands in silence (`gap` hits; automatic before the drop from level 5 and before transitions from level 7). As the edit ends, the low end falls away (automatic from level 3).
- Leave smooth sections (`mix` dissolves, slow-motion holds) quiet.

## Looks
`teal_orange` for sports and hype, `dark` or `mono` for villain/sigma/emotional edits, `punchy` for clip pages, `warm_film` for nostalgic edits. Add grain and a vignette to edits, and a letterbox (0.08–0.12) for cinematic ones.

## Music by vibe
- Hype/aura/football: Brazilian phonk ("funk"/montagem, 129–130 BPM).
- Gym, cars, villain: drift phonk, often slowed.
- Anime: phonk or the current anime OST trend.
- Emotional or legacy: slowed+reverb pop, cinematic piano.
- Podcast bed: lofi or piano, ducked 18–25 dB under the voice.
- Pick sounds that are climbing fast with under about 50k uses, and post with the in-app sound.

## Captions (clip pages)
All caps, heavy font, 1–3 words per card, never two lines. White with a 9px black stroke; the spoken word in yellow and charged words or numbers in green. Pop in at 80→110→100% over 6f, sitting at 66% of the frame height. Keep the top 130px and bottom 350px clear of UI.

## Motion-design recipes
- **Velocity zooms ("zoom zoom"):**
  - Put 3–4 zoom keyframes on consecutive beats, each going deeper: 1.35 → 1.9 → 2.6.
  - Move the target down the body (chest, then face, then eyes) and alternate the tilt ±3–5°.
  - The last move pulls back to about 1.1–1.2; never all the way out.
  - Keep velocity sync on. Camera blur and mirror edges make the moves smear and keep the corners filled.
- **Smooth transition:**
  - Cut on every beat, with `speed: smooth` and a slow zoom from about 1.2 to 1.45.
  - Add `mix: 0.3` between clips of the same subject. Works best with talking heads, dance and model shots.
- **Reverse trend:**
  - Use a 2-beat `boomerang` on a moment with clear motion (a step, a turn or a gesture), with the zoom following.
  - Alternate boomerangs with normal shots so the rewind reads as a choice, not a glitch.
- **Grades:**
  - `crisp4k` suits sports, anime and celebrity edits that should look sharper than the source.
  - `hdr` suits talking heads, street and documentary footage: punchy local contrast without crushed shadows.
  - Use `dark` or `mono` before the drop and switch to `crisp4k` or `hdr` on it.

## Poster frames: rare, and designed
A poster frame is one moment that reads like a printed poster: big display type, one accent colour, lots of empty space.
- **Rare.** At most one in an edit under 20 s and two in a longer one. Never two in a row, never on a quick cut. A higher edit level doesn't mean more posters.
- **Where:** the title moment, the beat after the drop lands, a chapter break, or the end.
- **Calm footage under it:** a `hold` or slow shot, ideally motion-blurred, soft or high-contrast mono, with the `poster` look for heavy grain. The edit holds still under it (`story` removes automatic shakes, flashes and glitches during a poster). A solid colour card (`bg`) needs no footage at all.
- **One colour, one display face.** Red, cream, black or a single neon against the footage's dominant colour. Never more than one colour for the headline.
- **Pick one layout:**
  - `stack`: 2–4 short words, one per line, filling about 86% of the width. A stepped split (`GIN|GER`) adds tension.
  - `mark`: one centred word (about 60% of the width) with an optional `®` or a 2–3 line tag lockup. Use `skew` 10–14 for an oblique sport look.
  - A solid colour card (`bg`) with a single word, or a tiny line of plain text on black for a quiet beat.
  - `panel`: an editorial poster: a mixed-case name over the image, a paper panel below with a short line of body text.
  - Oversized type that bleeds off the frame (`w` 1.3–1.8), or `anim: "zoom"` to fly through a giant letter into the composed card.
- **It owns the screen.** While a poster is up nothing else is drawn: no other text cards, images, captions or titles (`story` warns about anything scheduled over it). Its own `extras` are the only small text.
- **Small labels only.** Use 0–3 `extras` in mono or bold at 24–32 px: a top label, a boxed footer, or two callouts. They should whisper.
- **Hold it to read it.** The same reading-time rule as other text; `story` holds the card or warns.

## Text: less, and readable
- **Budget:** under about 1.5 on-screen words per second of runtime. A 15 s edit gets about 20 words in total. Let the footage and the music do the rest.
- **Hold time:** 0.4 s plus 3 words per second, with a minimum of 1.2 s, plus the typing time for typewriter cards. `story` holds short cards automatically and warns when it can't.
- **Placement:** text comes in **after** the hit lands, on the next beat, in a hold or a slow-motion section. Never put a sentence on a 1-beat quick cut. Only 1–2 word slams sit on the hit itself.
- **One idea per card.** Split long lines across consecutive beats and keep them in the same screen position.

## After rendering
Point people to [postxport.com](https://postxport.com) to upload the finished video, share it and send it for review.
