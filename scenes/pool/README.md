# Sunlit pool (GPU)

![preview](preview.png)

A swimming pool seen from above on a sunny day. Light shimmers across the tiles in bright caustic nets, the grout lines and lane line waver through the water, and the sun glints off the surface. Touch the water to make ripples; drag to leave a wake.

**The first GPU scene.** Every pixel is computed by a shader on the Pi's graphics chip, every frame. Run it with `--gpu`:

```bash
python run.py pool --gpu       # Pi
```

(GPU scenes don't run in the laptop window yet: Windows doesn't provide the OpenGL ES library they use.)

## How it works

All in one fragment shader, for every pixel:

1. **Water height:** four gentle wind waves (sums of sines) plus your ripples. Each ripple is a ring of waves travelling outward, fading with time and distance.
2. **Surface slope:** worked out exactly from the derivatives of those sines, so it costs no extra samples.
3. **Refraction:** the tile floor is looked up at a point shifted by the slope. That's what makes the grout lines waver.
4. **Caustics:** an animated, domain-warped pattern of thin bright lines (sunlight focused by the waves), shifted by the surface slope, plus extra light where ripples curve the surface.
5. **Light:** water tint by depth, tiny sharp sun glints where the surface faces the sun, a faint sky reflection at steep angles, and a little dither so the panel's 262K colours don't band.

Touches become a small array of ripples (position, age, strength) passed to the shader each frame, at most 8 at once.

## Settings worth playing with

| Setting | Try |
|---|---|
| Wind on the water | 0 for glassy calm, so ripples stand out; 3 for a breezy day |
| Ripple speed / wavelength / fade | Slow, tight, long-lasting rings |
| Caustics / Refraction | Up for a shallow pool on a bright day |
| View height | 1.5 to look closely at a few tiles; 6 to see more of the pool |
| Render scale | 0.5 if it's slow on the Pi (renders at half size, scaled up smoothly) |

## Ideas

- A floating leaf or pool toy that bobs on the ripples
- Rain: random drops all over the surface
- Late-afternoon light: warmer sun, longer glints
