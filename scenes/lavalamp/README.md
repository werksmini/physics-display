# Lava Lamp (GPU)

![preview](preview.png)

A glowing glass rocket of warm wax. Blobs swell as the bulb below heats them, drift up to the top, cool, and sink back into the puddle on the bottom, joining and splitting as they pass.

- **Touch the glass:** warms the wax near your finger, so it swells and lifts off.
- **Drag:** stirs the wax.
- **Tap the base:** switches the lamp off (the glow fades, the wax cools and slumps) and on again.

```bash
python run.py lavalamp --gpu
```

## How it works

- **Physics (CPU, nine blobs):** each blob has a temperature.
  - The bulb heats whatever is near the bottom; everything cools a little, and faster near the cap.
  - Warm wax is lighter than the liquid, so it rises; cool wax sinks. The thick liquid (drag) keeps it lazy.
  - Big blobs warm and cool more slowly, which keeps them out of step with each other.
- **Drawing (GPU, one fragment shader): metaballs.**
  - Every pixel adds up `r² / distance²` from each blob, plus a puddle on the bottom. Where the sum passes 1, it's wax.
  - Because the field adds up, blobs that come close join smoothly and pull apart through a neck, just like real wax.
  - The bulb lights it all from below, and thin edges glow a little brighter.
  - The glass gets bright streaks and darker edges. The lamp throws a soft glow on the wall and the table.

The nine blobs go to the shader as nine `vec4`s (x, y, radius, temperature), inside the Pi's budget of about 16.

## Settings worth playing with

| Setting | Try |
|---|---|
| Colours | Classic, Sunset, Arctic, Slime |
| Bulb heat | 2+ for a busy lamp, 0.4 for a sleepy one |
| Liquid thickness | 3 for slow motion |
| Blob size | 1.4 for big merging globs |
