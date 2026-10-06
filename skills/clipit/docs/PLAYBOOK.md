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
   - Put them in the spec's `dialogue` list (source, start, end). Each plays at normal speed with its own sound, is snapped to whole words, gets small word-by-word subtitles, and joins the next with a focus-hunting cut; the music runs quietly under them.
   - Read each printed line back. Keep it only if it is a complete thought that says what the story needs.
   - Headline flashes and dejected or lonely shots of him can follow as the first montage shots, in mono or dark, while the music is still in its quiet intro.
   - End on the harshest line.
2. **The turn.** A dark last beat (a `black` hit, or a slow-motion shot with a `label` across the eyes), then the moment that answered them, landing on the drop. The music keeps playing; the dark beat does the work.
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
| 1–3 minimal | every bar, straight speed | flowing cuts and a fade out, nothing else | music (+ the drop impact from 3) |
| 4–6 clean (default 5) | every 2 beats, one consistent ramp per clip | flowing cuts, a dark beat before the drop, blinks into bar-line cuts (5), bloom on the drop (6) | the drop, riser and text sounds from 5 |
| 7–8 punchy | hero + quick cuts | + a small flash and shake on the drop, short jolts on bar lines after the drop | all of the above |
| 9–10 hyper | hero + quick cuts | + flash and shake on bar lines, a whip or zoom transition every two bars, RGB on the drop | everything |

Effects you write into a spec by hand (`hits`, `zooms`, speeds) always play; the level only governs the automatic ones. Poster frames don't scale with the level. Every level gets flowing cuts and a music bed that never cuts abruptly.

Effects you write into a spec by hand (`hits`, `zooms`, speeds) always play; the level only governs the automatic ones. Poster frames don't scale with the level.

## The house style: clean, beat-synced, meaningful
Studied from reference edits (a "mogged" meme edit, a wholesome lyric edit, and a step-by-step After Effects tutorial for "hard" fan edits). What they share:
- **Few cuts, all on the music.** Cuts land on the strong beats (the ones an editor would mark), not on every beat. Inside a shot, the rhythm comes from speed and push, not from effects.
- **The same treatment on every clip.** One velocity ramp per clip (200% → 60% → 200%, eased like a water slide) and one gentle eased push toward the face. Editors copy the same keyframes onto every clip on purpose: consistency is what reads as "clean".
- **Framed on the face, from the front.** The subject stays centred with the whole head in frame; pick clips where the face is visible and there is some movement, not extremes.
- **Setup in real time, then the drop.** The setup plays at normal speed with its own sound (a quote, a meme moment). One beat before the drop the frame goes black and white and gets a label (e.g. a red bar reading MOGGED across the eyes); the reference freezes here, but keep it in slow motion unless a freeze is asked for, since frozen frames read as stills. On the drop: a hard cut to the best clean footage, in colour.
- **Dark blinks, not flashes.** Between shots there is at most a dip to black for a frame or two.
- **A clean close.** A slow push on a hero close-up, then a fade to black while the music fades.
- **Text is small and in time.** Dialogue text is small (about 4% of the frame width tall), white with a soft glow and shadow, one key word in red, revealed word by word exactly as it's spoken, fading out before the next line.
- **Wholesome edits** go the other way on colour: bright, saturated, glowing (`bright` look), slow motion, mirror-tile motion, and sometimes lyric typography on black for the intro, each word appearing as it's sung.

Never fill the gaps with random transitions. If an effect isn't motivated by the footage, the words or the music, leave it out.

## Make it mean something
Plan the edit from its story, fresh each time. Write the beats (what is said or sung, what happens), then choose footage that *shows* each beat:
- They call him a gangster or a villain: him putting on sunglasses, a slow walk, a stare into the lens.
- A nerd, a sweetheart, a wholesome turn: bright, colourful slow motion (`bright` look), smiles, hugs, tears catching the light (`hdr` or bloom on the close-up).
- Doubt and criticism: mono or dark grade, lonely or dejected shots, real voices saying it.
- The answer: the performance and the proof, in full colour, on the drop.
Effects follow the same rule: a whip only when the subject or camera moves that way, a flash only on a real flash or a camera shutter, a zoom only to reveal something.

## Flowing cuts
A hard cut between unrelated shots, or a jump cut in a talking clip, breaks the flow. Every cut is one of these instead (automatic in `talk`, `edit` and `story`):
- **Focus-hunting cut** (`focus` hit). Studied from explainer-style motion graphics: the old shot racks soft over the last 0.1–0.2 s, the cut happens while everything is blurred, then the new shot hunts for focus (nearly sharp, briefly soft again, then sharp) over 0.3–0.45 s, the frame breathing a touch as focus moves. Use it between dialogue lines and on longer, calmer shots. On fast beat cuts (shots under 1.5 s) a hunt would blur a third of every shot and the montage turns into smeared stills, so those get a zoom cut instead.
- **Zoom cut** (`zoomcut` hit). The old shot pushes in over the last 0.1 s, the new shot lands pushed in and eases back over 0.3 s, so the motion carries across the cut. The default for silence trims in talking clips, where it also alternates wide and tight framing like a two-camera shoot.
Choose with `"cuts": "focus" | "zoom" | "hard"` in a spec (or `--cuts` for `talk`), and per shot with `"cut"`.

## Framing 16:9 footage for 9:16
A 9:16 crop of 16:9 footage is only 56% of its width, so a close-up head is often wider than the frame. The framing is automatic:
- Faces are found a few times a second (OpenCV's YuNet model) and followed; in a two-shot the camera follows whoever is speaking (mouth movement) and switches with a cut, never a pan.
- The eyes sit on the upper third (about 38% down the frame), with a little headroom.
- Each scene gets a zoom limit: the closest the camera may get with the whole head (hair, ears, chin) inside the frame. When even the plain crop is too close, the picture is shown smaller and the space above and below is filled: mirrored copies (motion tile, `"edge": "mirror"`, the edit default) or a blurred copy (`"edge": "blur"`, the clip-page default).
- Zoom moves are clamped to that limit, so a push-in never ends with a cropped face.
- Override with `cx`/`cy` (manual centre) or `"fit": false` on a shot.

## Dialogue that syncs and makes sense
- Speech always plays at normal speed with its own sound. Dialogue shots never get speed ramps, jolts or stepped fps.
- **Nobody is cut off.** Every spoken line (dialogue lists, talk clips, hooks) is widened to whole sentences and cut inside real pauses in the audio: the start goes back to the pause before the sentence (0.25 s or longer), the end forward to the pause after it (0.3 s or longer). With a certain transcript, Whisper's sentence segments lead; otherwise only the audio is used. A voice shot inside the montage keeps talking under the next shot until its sentence ends (an L-cut).
- Choose short, complete lines; when `story` reports that a line was widened a lot, pick a shorter one.
- Read every printed line back against the user's story before rendering. A line that doesn't say what the story needs, or only says it out of context, goes.

## Subtitles: only when the language is certain
- YouTube's own subtitles come first. `fetch` saves them with the video (the uploader's in the spoken language, else YouTube's automatic captions in the spoken language, never a translated track), and they replace Whisper entirely for that video.
- The spoken language is measured before transcribing, over several stretches of the speech. Subtitles appear only at 80%+ confidence and with a model that handles the language. Hindi and Urdu count as one language, and Hindi that's clearly present (25%+, as in Hinglish commentary) makes the clip Hindi.
- Whisper is always told which language to write, so it never turns Hindi speech into English text. With an unsure or mixed language, or Hindi on the fast model, there are no subtitles at all.
- Hindi subtitles need OpenAI Whisper's full model; ask the user once whether to install it (`install.sh --with-hindi`) or go without.
- Without subtitles, the meaning travels in a few English core-word cards (`title` or `slam`: KING IS BACK, GANGSTERS DON'T STOP) and, at a key moment, a `poster` frame.
- Dialogue comes before the montage: the lines play first, timed by the words, and the beat-timed montage starts where they end. The song starts earlier so it runs under the lines, ducked.

## Music that never cuts
- Start on a downbeat with a short fade-in (or at the song's own start).
- Keep the bed continuous under jump cuts and dialogue: it ducks smoothly under speech (60 ms down, 450 ms back up) and never mutes.
- No dropouts: don't dip the music for "gaps" unless the song itself breaks there.
- End on a bar line (the `edit` planner rounds the length to whole bars) with a long fade-out of about 1.5 s, while the picture fades to black and the low end falls away.

## Cutting to music
- Cuts land ON the beat (kick). Build-up: every 2 beats (every bar at levels 1–4). After the drop: a hero shot (2 beats, velocity ramp) on every bar line, with 1-beat quick cuts between them from level 7.
- Velocity ramp: 200% → 60% → 200%, eased, the same on every clip (`velocity`), with the slow part on the action peak. Speed into the cut, not out of it.
- Build-up shots: constant 40–50% smooth slow-mo (motion-interpolated).
- A dark last beat before the drop is the fake-out; the riser ends exactly on the drop.

## Effects menu (what fires when)
| Moment | Effect | Level |
|---|---|---|
| Every cut | focus-hunting cut (zoom cut in talking clips) | all |
| Bar-line cut | a dip to dark into the cut | 5+ |
| The beat before the drop | fade to black | 4+ |
| THE DROP | a hard cut to clean footage; bloom (6+); a small flash and shake (7+); RGB and a second hit (9+) | by level |
| Bar lines after the drop | a short jolt (7+); flash and shake (9+) | 7+ |
| Every two bars after the drop | whip or zoom transition | 9+ |
| Talk keywords | punch-in +8% (and light shake on the hardest words at 8+) | 4+ |
| Jump cuts (talk) | zoom cut, alternating wide / tight framing | all |
| The end | fade to black over the last beat, music fading out | all |

## How pros build these edits (studied from real project files)
Patterns that came up again and again in working After Effects projects for velocity, gym, lyric and emotional edits.

**Speed is gentler than you think.** Across every speed keyframe, normal speed (100%) was the anchor and slow motion sat at 20–35%. Fast parts were short kicks to 150–160% and only rarely 200%; nothing went higher. The workhorse is `settle`: real time decelerating into 30%. `quick` kicks to 1.6x and slides to 35%. A `ramp` peaks at 1.8x.

**Every shot has a life.** In velocity sections (shots of 0.6–1.3 s):
- It starts at 100% speed (or kicks to 150%) and decelerates to 20–60%.
- It starts zoomed in (about 1.2–1.4x) and settles outward over the whole shot, fast at first, then gliding.
- It starts slightly defocused and snaps into focus within about 0.3 s.
- It starts bright and holds, then sinks toward black in the last frames before the cut, so every cut "blinks".
- A small jolt or shake peaks on the cut.

`story` and `edit` give every shot the same gentle push and a flowing cut, and add the blink into bar-line cuts from level 5.

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
- When a subject moves, pros track the text to them (`follow`, which rides with the face).

**Texture:** a constant subtle film flicker (`film_flicker` 0.12–0.2), light, particle or shadow overlay clips in screen blend, tinted to the edit's colour (`overlays`), and the sharpen + clarity + look stack (`crisp4k`).

**Sources:** they upscale and clean their sources before editing, and they cut real motion footage, never photo slideshows. Always fetch the highest resolution available; slow it with flow slow-mo and hit the cuts with jolts.

## Sound design
- Sounds follow the picture. Each transition has its own sound (whoosh for zoom and spin, swoosh for whip, glitch for glitch), and every zoom-chain move gets a short swish. The drop gets a riser that ends on it, then impact + boom. Slam text gets a hit, pop text a pop, and typed text quiet key presses.
- Set levels against the music, not in absolute terms. The drop sits about 13 dB under the track, transitions about 20 dB under, and small details (clicks, pops, typing) 26–32 dB under. You should feel them, not notice them; if a click or swoosh stands out on playback, it is too loud.
- One sound per moment. If a slam lands on the drop, the drop's impact covers it.
- The music never drops out on its own. A `gap` hit (a dip of a few frames before a moment) exists for the rare case the user wants one, but it isn't automatic: viewers hear it as the music cutting. As the edit ends, the low end falls away (automatic from level 3) and the track fades out over about 1.5 s.
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
