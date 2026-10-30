# Particle life

![preview](preview.png)

Coloured particles chase and flee each other by type. From a small random table of attractions, cell-like blobs, worms, chasers and orbiting clusters emerge.

```bash
python run.py particlelife            # Pi
python run.py particlelife --window   # laptop
```

## Touch

Drag to stir particles along with your finger; tap to scatter them. Change **Seed** in the panel to roll a completely new rule table: a whole new "world".

## How it works

- Each particle has a **type** (colour). A random table says how strongly each type is attracted to (+) or repelled by (−) every type, including its own. It doesn't have to be symmetric: red can chase blue while blue flees red, which is what makes things swim.
- Between two particles within the **Interaction range**:
  - closer than **Beta** × range, they always push apart, so nothing collapses to a point
  - further out, they attract or repel by the table value, strongest mid-range and fading to zero at the edge
- Heavy **friction** makes motion smooth and structured. The world wraps around at the edges.
- For speed, a cheap distance check runs over every pair, and the force maths only runs for pairs actually in range.

## Settings worth playing with

| Setting | Try |
|---|---|
| Seed | Flip through: 14 (default) makes cells with membranes; 9 makes a complex creature; 4 and 10 are also good |
| Types | 2–3 for simple worlds; 7–8 for chaos |
| Friction | Lower for wilder, faster motion |
| Trails | 0.9+ for glowing comet trails |

## Ideas

- Save favourite worlds as presets
- Mutate the rule table slowly over time so the world evolves
