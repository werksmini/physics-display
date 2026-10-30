# Adult swim (GPU)

![preview](preview.png)

The sunlit pool, a little closer in, with people in it. The water is the same as "Sunlit pool": pale tiles, the lane line and its T, shifting caustic nets and sun glints. In the top corner the pool curves around a rounded stone-edged deck.

You're the swimmer in the **yellow cap**, treading water. **Tap anywhere in the water** and you swim there with a slow, head-up breaststroke, then tread again. Other swimmers drift in from off the left, right and bottom of the screen:

- someone swims up the lane to the wall, rests, and swims back
- someone floats on their back for a while
- someone kicks along on a pool noodle
- someone hangs on the wall by the deck
- someone just passes through
- someone drifts over to chat

Then they drift off again.

```bash
python run.py adultswim --gpu
```

## How it works

Three layers:

1. **The water surface** combines the sunlit pool's gentle wind waves with a small wave simulation. The simulation is a grid of heights, one cell per 5 screen pixels, updated with the wave equation (each cell is pulled toward the average of its neighbours). Swimmers poke it:
   - hands on every stroke
   - a soft bow wave at the head
   - little sculling ripples while treading

   Ripples spread and bounce off the curved pool wall. At the screen edges they fade out, since the pool carries on out of view. The slopes go to the GPU as a texture each frame.
2. **Bodies under the water** are drawn each frame from simple capsules (torso, upper and lower arms, legs) into a half-resolution image:
   - breaststroke: arms sweep out, meet under the chin and shoot forward; then a frog kick and a glide
   - treading: sculling arms and eggbeater legs
3. **The shader** is the sunlit pool's, plus the swimmers and the deck. For every pixel it:
   - refracts the floor
   - draws the caustics and glints
   - draws the bodies, bent by the surface and dappled by the caustics
   - casts their sun shadows down and to the left on the floor
   - draws the stone coping and concrete deck around the curved edge

Heads are above water, so they're drawn crisp on top, unbent (cap or hair, face toward where they're going).

## Settings worth playing with

| Setting | Try |
|---|---|
| Other swimmers | 0 for a pool all to yourself |
| Comings and goings | 3 for a busier afternoon |
| Swim pace | 2 if you're in a hurry |
| Ripple fade | 0.3 and every stroke rolls on for ages |
| View height ↻ | 4 for really close, 10 to see more pool |
| Render scale ↻ | 0.6 if the Pi needs more speed |
