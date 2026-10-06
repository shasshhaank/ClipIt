# claude-clipper

An open-source clipping studio and a [Claude Code](https://claude.com/claude-code) skill. It turns long videos into short-form vertical clips and fan edits:

- **Find the moment:** word-level transcription, then a ranked list of the most polarizing, hook-heavy windows.
- **Clip-page shorts:** face-tracked 9:16 reframing, jump-cut pauses, word-by-word pop captions, punch-ins on charged words, a hook title and a ducked music bed.
- **Velocity and story edits:** beat and drop detection, cuts on the beat, speed ramps, beat-synced velocity zoom chains (mirror edges and camera motion blur), boomerang / reverse-trend retiming, smooth V-curve transitions with cross-dissolves, flow slow-mo, flashes, shakes, glitch, whip, zoom and spin transitions, glowing flickering text, thumbnail walls, comment cards, and a logo with a subscribe click.
- **Effects:**
  - flow slow-mo, vector blur, jolt, shake, bloom, mirror edges, bulge and echo
  - defocus pulls, neon edge ghosts, light rays and sweeps, halftone, water ripple, jaw bars, spring bounces, squash/stretch, film flicker and dust
  - beat-driven camera flow and pulses, user overlay clips with blend modes, photo bursts, and a picture-in-picture card
  - text that reveals word by word, assembles or scatters letter by letter, follows the subject, or sits behind the person (optional cut-out)
  - VHS, light leaks, chromatic aberration, stepped fps and handheld drift
  - eight colour grades, including `crisp4k` ("4K" edit look) and `hdr`
- **Edit level and poster frames:** you choose how much editing you want (5 is clean, 10 is a hyper edit), and a rare `poster` style turns a key moment into a frame that reads like a printed poster.
- **Audio:** a generated, copyright-free sound kit (whoosh, swoosh, swish, impact, hit, drop, riser, downlifter, glitch, rewind, pop, click, typing and more), placed automatically on every transition and levelled against the music, plus sidechain ducking, slowed + reverb or sped-up music, and loudness at −14 LUFS.

Everything runs locally with Python, OpenCV and ffmpeg, and it needs no plugins or stock packs. The tool has no telemetry and uploads nothing; its only network use is the one-time Whisper model download and any links you ask it to fetch.

It also reads effect references from popular desktop and mobile editors and rebuilds them with its own effects ([`docs/TRANSLATE.md`](docs/TRANSLATE.md)).

## Install

```bash
git clone https://github.com/<you>/claude-clipper.git
cd claude-clipper
bash install.sh            # asks before installing anything missing; creates .venv and runs `clip.py doctor`
```

It installs the Python packages (Whisper, OpenCV, librosa, yt-dlp, ...) into `.venv`, and on macOS offers to install ffmpeg and Python with Homebrew if they're missing (`--yes` skips the questions). On Ubuntu, run `sudo apt install ffmpeg python3-venv` first.
Transcription uses `mlx-whisper` on Apple Silicon and `faster-whisper` elsewhere; the model downloads on first use.
Optional fonts go in `fonts/`, for example Montserrat Black and Anton (both free under the SIL OFL licence).

### Use it as a Claude Code skill

```bash
# for one project
mkdir -p .claude/skills && ln -s /path/to/claude-clipper .claude/skills/clipping
# or for every project
mkdir -p ~/.claude/skills && ln -s /path/to/claude-clipper ~/.claude/skills/clipping
```

Claude opens every job by asking for the footage (files or links), the music and the on-screen text, plus any specific direction. If something is missing or the request is vague, it decides for itself: it researches the story (and verifies every number it puts on screen), plans the shots, finds and downloads real motion footage (never photo slideshows), picks the song section, and builds the edit, telling you what it chose. Then ask something like: *"clip the most controversial 40 seconds of input/podcast.mp4 with captions"* or *"make a comeback hype edit of these videos on music/song.mp3, drop at 1:01"*. Claude reads `SKILL.md`, runs the tools, reviews contact sheets of its own renders and iterates.

## CLI

```bash
PY=.venv/bin/python
$PY clip.py testmedia                                  # synthetic footage + beat + placeholder logo
$PY clip.py fxdemo                                     # labelled reel of every effect -> output/fx_demo.mp4
$PY clip.py story examples/demo_story.json             # narrative edit from a beat-timed spec

$PY clip.py find "india vs west indies odi highlights"  # research footage: candidates with channel, length, size; no download
$PY clip.py fetch https://youtu.be/VIDEO_ID           # footage from a link (yt-dlp) -> input/; --audio for music
$PY clip.py fetch URL --section 3:10-3:40 --res 1080  # just the part you need
$PY clip.py analyze input/podcast.mp4 --shots          # transcript, ranked moments, hook lines, shots
$PY clip.py sheet input/podcast.mp4 --n 30             # contact sheet for picking shots
$PY clip.py talk input/podcast.mp4 --start 812 --end 851 --title "HE SAID WHAT?" --music music/bed.mp3
$PY clip.py edit input/game.mp4 --music music/phonk.mp3 --length 14 --flow
$PY clip.py plan-render work/podcast/plan.json output/v2.mp4   # re-render a hand-tweaked plan
$PY clip.py sfx                                        # write the sound kit to ./sfx
```

Outputs go to `./output/` and intermediates to `./work/`, both relative to where you run the command.

## Share and get reviews
When a render is done, upload it to **[postxport.com](https://postxport.com)** to share it and send it for review before you post.

## How it works

| Stage | Module | Approach |
|---|---|---|
| Transcribe | `transcribe.py` | Whisper large-v3-turbo with word timestamps |
| Moments | `moments.py` | polarizing lexicon and phrases, hook openers, speech pace and loudness peaks; non-overlapping windows |
| Shots | `moments.py` | PySceneDetect cuts, plus a motion score and peak time per shot |
| Reframe | `reframe.py` | face detection with a motion-saliency fallback and dead-zone smoothing |
| Music | `beats.py` | librosa beats, downbeats from low-end phase, and the drop as the biggest energy jump |
| Plan | `planner.py`, `story.py` | cut grid, speed curves, effect choreography and audio mix |
| Render | `render.py`, `fx.py`, `flow.py` | per-frame time remap, then one-warp camera, effects, grade, text and image layers, piped to ffmpeg |
| Overlays | `captions.py`, `assets.py` | Pillow text (no libass needed), cards, buttons, cursor and logo cut-outs |

Docs:
- [`docs/PLAYBOOK.md`](docs/PLAYBOOK.md): the editing rules
- [`docs/EFFECTS.md`](docs/EFFECTS.md): every effect and its parameters
- [`docs/STORY_SPEC.md`](docs/STORY_SPEC.md): the story format
- [`docs/TRANSLATE.md`](docs/TRANSLATE.md): other editors' effect names mapped to ours
- [`docs/research/motion_techniques.md`](docs/research/motion_techniques.md): motion techniques studied from edit tutorials

## Responsible use
- You need the rights to the footage and music you edit, including anything you `fetch` from a link. Copyrighted songs on fan pages are often claimed or muted.
- Use only real comments and testimonials. The comment-card tool always masks handles.
- Don't use it to impersonate people, fabricate statements, or cut quotes so they mean something else.
- claude-clipper is an independent project. It isn't made or endorsed by Anthropic, or by the makers of any editor or plugin named in `docs/TRANSLATE.md`.

## License
MIT © [Shashank Pandey](https://shashankpandey.com) · [LinkedIn](https://www.linkedin.com/in/xhashank). See [LICENSE](LICENSE).
