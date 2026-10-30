# Cloth (GPU)

![preview](preview.png)

A red gingham tablecloth drops onto a ball on a wooden floor and drapes over it. Grab it and pull it around.

- **Drag the cloth:** pinch that spot and pull it. Up to three fingers can each hold a spot. Let go mid-swing and it flies.
- **Drag empty space:** orbit the camera. **Pinch:** zoom.
- **Double-tap empty space:** drop a fresh cloth.

```bash
python run.py cloth --gpu
```

## How it works

- **Particles and constraints (Verlet cloth).** The cloth is a 24 × 24 grid of particles. Each remembers where it was last step, so its velocity is just "now minus before". That makes dragging easy: move a particle by hand and it has a velocity for free.
- **Each frame:** gravity and a gusty breeze (pushing on the face of the cloth) move every particle. Then the constraints are relaxed six times, nudging every pair of neighbours back toward its rest distance:
  - straight neighbours keep it from stretching
  - diagonal ones stop it shearing
  - pairs two apart give it a little stiffness, so it folds instead of crumpling
- **Collisions:** the ball and the floor push particles out, and friction makes the cloth grip instead of sliding off.
- **Cheap on the Pi:** numpy works on whole slices of the grid at once (every horizontal pair in one go, then every vertical pair, and so on), so a frame is a few dozen array operations whatever the cloth size.
- **Drawing:** the shape is uploaded as a fresh mesh every frame. Both sides are lit, and the gingham and its fine weave are worked out per pixel from the cloth coordinates. The shadow is the same squashed-mesh trick as the cubes.

## Settings worth playing with

| Setting | Try |
|---|---|
| Breeze | 2+ and the cloth flaps off the ball |
| Fold stiffness | 0 for silk, 1 for canvas |
| Grip | 0 and it slides off; 1 and it clings |
| Solver passes | 2 is stretchy and rubbery; 12 is crisp (slower) |
| Ball ↻ | 0 to drop it flat on the floor |
| Cloth detail ↻ | 36 for finer folds (slower on the Pi) |
