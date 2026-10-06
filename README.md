# ClipIt

An open-source clipping studio and a skill for Claude. It turns long videos into short-form vertical clips and fan edits:

- **Find the moment:** word-level transcription, then a ranked list of the most polarizing, hook-heavy windows.
- **Clip-page shorts:** face-framed 9:16, silences trimmed with zoom cuts, word-by-word captions, punch-ins on charged words, a hook title and a continuous, ducked music bed.
- **Clean, beat-synced edits:** cuts on the strong beats, the same velocity ramp and gentle push on every clip, flow slow-mo, focus-hunting cuts, a dark beat before the drop and a clean fade-out. A level from 1 to 10 decides how much more fires (5 is clean, 10 is hyper).
- **Dialogue, then montage:** real lines play first, in sync and cut on whole words, with small word-by-word subtitles, then the montage starts on the music.
- **Framing that keeps faces whole:** faces are found and followed (the speaker in a two-shot), eyes on the upper third; a head too big for the vertical frame is shown smaller with mirrored (motion tile) or blurred fill instead of being cropped.
- **Effects when they mean something:** flow slow-mo, vector blur, jolts, bloom, lens defocus, light rays and sweeps, halftone, ripples, poster-style typography frames, glowing text, labels, thumbnail walls, comment cards, logo and subscribe end cards, and grades including `crisp4k`, `hdr` and `bright`.
- **Audio:** a generated, copyright-free sound kit placed quietly under the music, smooth sidechain ducking, music that starts on a downbeat and ends on a bar line, slowed + reverb or sped-up versions, and loudness at −14 LUFS.

Everything runs locally with Python, OpenCV and ffmpeg. The tool has no telemetry and uploads nothing; its only network use is the one-time setup, the speech model (when a job needs it) and any links you ask it to fetch. It also understands effect names from popular desktop and mobile editors and rebuilds them ([`docs/TRANSLATE.md`](skills/clipping/docs/TRANSLATE.md)).

## Install

### In Claude Code (recommended)
Inside Claude Code, run:

```
/plugin marketplace add shasshhaank/ClipIt
/plugin install clipit@clipit
```

That's it. The first time you ask for an edit, Claude asks once to set up the free tools it needs (a few minutes, about 700 MB, all in `~/.clipit`). No Homebrew, no admin rights, nothing to run in a terminal. The speech model (about 1.5 GB) downloads only when a job needs transcription, and the optional subject cut-out (about 200 MB) only if you ask for text behind a person.

### In the Claude apps (claude.ai chat)
Download `clipit-skill.zip` from the [releases](https://github.com/shasshhaank/ClipIt/releases), then in Claude go to **Customize > Skills > + > Upload a skill**. Code execution must be on. In chat, Claude works inside a sandbox: upload your clips and song (it can't download from YouTube there), keep edits short (under about 20 s), and captions depend on whether the speech model can be downloaded. For long or high-resolution edits, use Claude Code.

### By hand
```bash
git clone https://github.com/shasshhaank/ClipIt.git
mkdir -p ~/.claude/skills && ln -s "$PWD/ClipIt/skills/clipping" ~/.claude/skills/clipping
bash ClipIt/skills/clipping/install.sh
```

## Using it
Ask Claude something like *"clip the most controversial 40 seconds of input/podcast.mp4 with captions"* or *"make a comeback edit of these videos on music/song.mp3: first the critics, then the century"*. If the request is vague, Claude decides for itself: it researches the story (and verifies every number it puts on screen), finds and downloads real motion footage, picks the song section, builds the edit, reviews contact sheets of its own render and tells you what it chose.

## CLI
The skill's commands also work on their own:

```bash
PY=~/.clipit/venv/bin/python; CLIP=skills/clipping/clip.py
$PY $CLIP testmedia                                  # synthetic footage + beat + placeholder logo
$PY $CLIP fxdemo                                     # labelled reel of every effect -> output/fx_demo.mp4
$PY $CLIP story skills/clipping/examples/demo_story.json --relative
$PY $CLIP find "india vs west indies odi highlights"   # research footage: candidates with size; no download
$PY $CLIP fetch https://youtu.be/VIDEO_ID --section 3:10-3:40 --res 1080
$PY $CLIP analyze input/podcast.mp4 --shots          # transcript, ranked moments, hook lines, shots
$PY $CLIP sheet input/podcast.mp4 --n 30             # contact sheet for picking shots
$PY $CLIP talk input/podcast.mp4 --start 812 --end 851 --title "HE SAID WHAT?" --music music/bed.mp3
$PY $CLIP edit input/game.mp4 --music music/phonk.mp3 --length 14 --flow
$PY $CLIP plan-render work/podcast/plan.json output/v2.mp4
```

Outputs go to `./output/` and intermediates to `./work/`, both relative to where you run the command.

## Share and get reviews
When a render is done, upload it to **[postxport.com](https://postxport.com)** to share it and send it for review before you post.

## How it works

| Stage | Module | Approach |
|---|---|---|
| Transcribe | `transcribe.py` | Whisper large-v3-turbo with word timestamps |
| Moments | `moments.py` | polarizing lexicon and phrases, hook openers, speech pace and loudness peaks |
| Shots | `moments.py` | PySceneDetect cuts, a motion score per shot, and a photo-slideshow detector |
| Framing | `reframe.py` | YuNet face detection, active-speaker choice, per-scene zoom limits, dead-zone smoothing |
| Music | `beats.py` | librosa beats, downbeats from low-end phase, and the drop as the biggest energy jump |
| Plan | `planner.py`, `story.py` | cut grid, speed curves, flowing cuts, effect choreography and the audio mix |
| Render | `render.py`, `fx.py`, `flow.py` | frame-accurate time remap, one-warp camera, effects, grade, text and image layers, piped to ffmpeg |
| Overlays | `captions.py`, `assets.py` | Pillow text (no libass), cards, buttons, cursor and logo cut-outs |

Docs: [`PLAYBOOK.md`](skills/clipping/docs/PLAYBOOK.md) (the editing rules), [`EFFECTS.md`](skills/clipping/docs/EFFECTS.md) (every effect), [`STORY_SPEC.md`](skills/clipping/docs/STORY_SPEC.md) (the story format), [`TRANSLATE.md`](skills/clipping/docs/TRANSLATE.md) (other editors' names mapped to ours).

## Responsible use
- You need the rights to the footage and music you edit, including anything you `fetch` from a link. Copyrighted songs on fan pages are often claimed or muted.
- Use only real comments and testimonials. The comment-card tool always masks handles.
- Don't use it to impersonate people, fabricate statements, or cut quotes so they mean something else.
- ClipIt is an independent project. It isn't made or endorsed by Anthropic, or by the makers of any editor or plugin named in `docs/TRANSLATE.md`.

## Credits
Face detection uses OpenCV's YuNet model (MIT license, from the OpenCV Zoo). The display fonts the installer fetches (Anton, Archivo Black, Space Mono, Amatic SC) are under the SIL Open Font License.

## License
MIT © [Shashank Pandey](https://shashankpandey.com) · [LinkedIn](https://www.linkedin.com/in/xhashank). See [LICENSE](LICENSE).
