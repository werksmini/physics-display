# Pin art (GPU)

![preview](preview.png)

The desk toy: a board of polished steel pins. Press the screen and the pins under your fingers slide out toward you, like pressing a hand into the back of the board. They stay where you pushed them.

- **Touch:** pushes pins out in the shape of a fingertip
- **Hold still:** presses deeper
- **Drag:** draws a groove
- **Several fingers:** each one presses
- **Double-tap:** tips the board up, and the pins slide back row by row

```bash
python run.py pinart --gpu
```

## How it works

- **The pins** are a grid of heights between 0 and 1, one per pin, stored in numpy. A touch raises the pins inside a rounded fingertip profile (pins only ever move out, never back), and holding makes the profile deeper.
- **Drawing** is one fragment shader. The heights go to the GPU as a tiny texture with one texel per pin. We look at the board slightly from above, so a pin pushed out by `h` appears `h × pin length` pixels lower, with its shaft running back up to its hole. For each pixel the shader checks its own pin and the few pins above it that could reach down that far, and keeps the one sticking out furthest (the nearest to you).
- **Steel heads** are shaded as little domes: a reflected bright-room / dark-floor gradient, a sharp highlight from the light at the upper left, and a shadow when a neighbour up and to the left sticks out further.
- **Tipping the board:** every pin starts sliding back under gravity after a small delay that grows down the board, so it empties top to bottom.

## Settings worth playing with

| Setting | Try |
|---|---|
| Fingertip size | 60+ for palm prints |
| Pin length | 40 for deep relief; 0 flattens it into a dot picture |
| Pin spacing ↻ | 7 for fine detail, 16 for a chunky toy |
| Polish | 0 for brushed pewter |
