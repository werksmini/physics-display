# Bouncing balls

![preview](preview.png)

Rigid-body balls in a box, simulated with pymunk (Chipmunk2D). The first demo, ported to a scene.

```bash
python run.py balls            # Pi
python run.py balls --window   # laptop
```

## Touch

Tap to blast nearby balls outward and spawn a new ball under your finger.

## How it works

pymunk handles collision detection and the contact solver; see the "Inside a rigid-body engine" section of the deep dive. Each frame the scene applies the current slider values (gravity, bounciness, friction) to the simulation, then steps it twice (substeps) for stability.

## Settings worth playing with

| Setting | Try |
|---|---|
| Gravity | Negative to make everything fall upward |
| Bounciness | 1.0 for balls that never settle; 0 for dead drops |
| Blast strength + radius | Big radius, low strength = gentle push |

## Ideas

- Tilt gravity by touch position
- Different shapes (boxes, triangles)
- Balls that merge when they collide
