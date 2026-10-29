# Meadow, hands in the grass

![preview](preview.png)

The same overhead meadow as [Meadow from above](../meadow/README.md), but your finger touches the grass instead of steering the wind. Press it down, comb paths through it, and watch the trails slowly heal.

```bash
python run.py meadowtouch            # Pi
python run.py meadowtouch --window   # laptop
```

## Touch

- **Press:** blades around your finger are pushed outward, flattening a starburst ring like a hand pressed into the lawn.
- **Drag:** blades near your finger are also swept the way you're moving, so you comb a path through the field.
- **Let go:** the blades you pushed stay bent for a while (**Trail depth**) and slowly stand back up (**Recovery time**).

The ambient weather keeps going underneath the whole time: a gentle steady breeze, a slowly changing swirl, and drifting local breezes.

## How it works

Each blade tip is a 2D damped spring, as in the original meadow, with two additions:

1. **Hand force:** for blades within **Hand size** of your finger, a push outward from the finger plus a push along your drag direction, both fading toward the edge of your reach.
2. **Lasting bend:** each push also moves the blade's *rest point* in the direction it was pushed. The spring pulls toward that bent rest point, which decays back to upright over **Recovery time**. That's what makes the trails.

## Settings worth playing with

| Setting | Try |
|---|---|
| Recovery time | 30 to draw pictures in the grass; 1 for grass that springs straight back |
| Trail depth | 0 for no trails, just the live push |
| Press vs Sweep | High press, low sweep for stamping; low press, high sweep for combing |
| Hand size | Small for a fingertip; big for a whole palm |
| Palette | 2 (frost) makes the trails look like footprints in frosty grass |

## Ideas

- Two fingers: pinch to part the grass
- Footsteps: a slow walker leaving trampled prints across the field
- Insects or a mouse that hide in the long grass and dart away from your finger
