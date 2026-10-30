# Cubes (GPU, 3D)

![preview](preview.png)

A real 3D scene: a grey studio with a grid floor fading into haze, and cubes you pick up with your fingers and spin like in a CAD program. Let go and they fall with gravity, tumble and settle. Then the next cube is presented. Old cubes stay on the floor, so you can stack them, or pick them up again.

```bash
python run.py cubes --gpu      # Pi
```

## Controls

The screen is smaller than two fingertips, so you never touch the cube itself. Gestures work **anywhere**, like a laptop trackpad, and steer the active cube:

| Gesture | What it does |
|---|---|
| **1 finger drag** | Tumble the cube (trackball: drag right, it spins right) |
| **2 fingers** | Move it around; **twist** to roll it; **pinch** to push it away, **spread** to pull it closer |
| **3 fingers** | Tumble it too |
| **Lift your fingers** | It stays where you left it, so you can adjust in several moves |
| **Double-tap** | Set it down: it falls with gravity, tumbles and settles |
| **Quick 2-finger flick** | Throw it |
| **Tap a cube on the floor** | Pick it back up (anything resting on it falls) |
| **Drag / pinch with no active cube** | Orbit / zoom the camera (while the last cube lands) |

When a dropped cube settles, the next one is presented. The active cube glows slightly.

## How it works

**Rendering (GPU, OpenGL ES 2.0)**, each frame:
1. Background gradient.
2. The floor: one big square, with the grid drawn in its shader. Lines get wider with distance so they stay about a pixel wide, and fade into haze.
3. Shadows: each cube flattened onto the floor along the light direction and drawn dark and translucent. The stencil buffer makes sure overlapping triangles don't darken twice, and shadows fade as a cube rises.
4. Cubes: 36 triangles each with per-face colours, lit with a key light, sky light and a soft specular highlight. The shader darkens near edges for a bevelled look. A depth buffer sorts what's in front.

**Picking:** a ray from the camera through your finger is tested against each cube (in the cube's own frame it's a simple box test). If you're near a cube on screen, that counts too.

**Physics:** each cube is a rigid body (position, velocity, rotation, spin).
- Contacts come from the cube's 8 corners hitting the floor, and from corners and edge midpoints poking into other cubes. Edge points matter: two cubes meeting edge-to-edge have no corner inside the other.
- Each contact gets an impulse that stops it sinking in, with a little bounce and friction. Because the push lands off-centre, it changes the spin too, which is what makes cubes tumble and settle onto a face.
- Cubes that stop moving go to sleep (cost nothing) until a hard knock wakes them.
- Kept light for the Pi: two small steps and two contact rounds per frame, a cheap distance check (once per step) before any detailed test, one merged contact per touching pair, and the small-vector maths in plain Python floats (numpy is slow for 3-number vectors). A busy pile of 7 tumbling cubes takes about 1 ms per frame on a desktop CPU.

**Multi-touch:** the panel's Goodix controller reports up to 5 fingers (Linux multi-touch slots); `playground/touch.py` tracks them and the runner passes `{finger id: (x, y)}` to any scene with a `fingers()` method.

## Settings worth playing with

| Setting | Try |
|---|---|
| Gravity | 0.2 for moon-like floaty tumbling |
| Bounciness | 0.8 for rubbery cubes |
| Friction | 0 for ice: cubes slide and spin on the floor |
| Throw strength | 2 to really hurl cubes with a flick |
| Spin / Move sensitivity | Lower for precise CAD-style positioning |

## Ideas

- Other shapes: dice with pips, long beams, a ramp to slide down
- Build a tower and see how high it gets before it topples
- Textured faces (wood, marble) and a real reflection on the floor
