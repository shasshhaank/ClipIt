# Motion techniques, studied from popular edit tutorials (2025–26)

These are distilled from desktop and mobile editing tutorials on velocity zooms, smooth transitions, the reverse trend, "4K" colour correction and HDR grading. Values are the ones shown on screen in those tutorials. `docs/TRANSLATE.md` maps the tutorials' tool names to ours.

## Velocity zooms with a zoom chain
- Layers:
  - The clip gets **mirror edges** with expanded output, so rotation and zoom never reveal borders.
  - A chain of parented **zoom layers** sits on top. Each animates **scale, rotation and position**, so each zoom compounds on the previous one.
- Timing:
  - Every move uses an aggressive S-curve ease; a manual graph-editor version works too.
  - The **peak of the speed graph is aligned to the beat marker.**
  - The time-remap velocity uses the same peak shape, so the footage itself speeds up into each zoom.
- Finish: motion blur on, and the last keyframe stops short of fully zoomed out.
- Implementation: `zooms` keyframes (log-space scale, S-curve with p≈4), `pulses` speed profile, sub-frame camera blur and mirror edges.

## Smooth transition
1. Auto-generate beats on the "intense" setting, then split each clip on a beat.
2. Custom speed curve: a 5-point **V curve**, 10x at the edges and 0.1x in the middle, with optical-flow slow motion on.
3. Keyframe scale from about 182% to about 219% across the clip, with a steep S-curve graph.
4. Add a cross-dissolve of about 0.3 s between clips.
- Implementation: the `smooth` speed preset, a `zoom` ramp, and `mix`.

## Reverse trend
1. Pre-slow the clip (optical-flow slow motion), export it, and re-import it as a 1.8 s clip.
2. Speed curve: drop the middle points and drag the start to 10x, giving a **10x → 1x deceleration**.
3. Keyframe the zoom in with **cubic-out** easing.
4. Duplicate the clip and **reverse the duplicate**: the result plays forward, then rewinds, synced to the beat.
- Implementation: the `boomerang` speed preset (forward decelerating, then mirrored) with `zoom_follow`.

## "4K" colour correction
On an adjustment layer:
1. Sharpen 10.
2. Unsharp mask: amount 25, radius about 10.
3. Brightness and contrast.
4. Colour panel: saturation about 126, vibrance about 21, split toning (teal shadows, warm highlights).
5. Glow: threshold 60%, low intensity.
6. Vignette.
- Implementation: the `crisp4k` look.

## HDR
- **Grade layer:** exposure 0.05–0.17, gamma 0.90–0.92, saturation +5%, vibrance 1.16, brightness −4 to −5%, contrast +6 to +11%.
- **Glow layer:** copy the background, apply threshold 0.83 and inner blur 0.15, then screen blend at 20%.
- **Detail layer:** copy the background, apply exposure −0.6 to −1.1 and inner blur about 0.12, then difference blend. Together with a contrast-blended layer, this is a local-contrast (clarity) boost.
- Implementation: the `hdr` look (gamma, shadow lift, clarity, vibrance, threshold glow).
