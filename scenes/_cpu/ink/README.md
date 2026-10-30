# Ink in water

![preview](preview.png)

Stir coloured ink through water with your finger. A real fluid simulation: Jos Stam's *stable fluids* (1999), running on a coarse grid and smoothed up to the screen.

```bash
python run.py ink            # Pi
python run.py ink --window   # laptop
```

## Touch

Drag to stir; each new touch picks the next ink colour. When nobody touches it, a slow drifting emitter keeps adding a little ink (**Idle ink**), so it never sits blank.

## How it works

Each step:

1. **Forces:** your finger pushes the water and drops in ink.
2. **Vorticity confinement:** a nudge that keeps small swirls spinning instead of smearing out (**Swirliness**).
3. **Advection:** the velocity carries itself along. Each cell looks *backwards* along the flow and takes the value it finds there, which is what keeps this stable at any time step.
4. **Projection:** water can't be squashed, so a pressure field is solved with a few relaxation passes and its gradient removed. What's left is pure swirl (**Pressure passes**).
5. **Ink** is carried by the flow the same way, and slowly fades (**Ink fade**).

## Settings worth playing with

| Setting | Try |
|---|---|
| Swirliness | 0 for smooth, blurry flow; 4+ for lots of tight curls |
| Ink fade | 0 to fill the tank; 1+ for fleeting wisps |
| Grid width | Higher is finer and slower; 40 is fast and soft |
| Smooth scaling | Off for a pixelated look |

## Ideas

- Obstacles the ink flows around (draw them with a second finger)
- Ink that rises like smoke (buoyancy)
- Use it as the lake surface in the hillside scene
