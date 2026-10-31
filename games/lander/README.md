# Lunar Lander

![preview](preview.png)

`python play.py lander`

Left thumb: rotate left / right. Right thumb: **THRUST**. Set down on a yellow pad:

- upright (tilt within 10°)
- under 12 ft/s down and 8 ft/s sideways
- feet both on the pad

The readouts turn green when they're inside the limits. x2 / x3 pads are narrower and score more.
Each level the gravity is a little stronger, the fuel a little shorter and the pads a little
narrower. Flying off one side wraps you round to the other.

## How it works

Hand-rolled physics (no pymunk): gravity plus thrust along the ship's nose, integrated at a
fixed 60 Hz, 1 canvas px = 1 ft. Touchdown checks the feet and hull against the terrain line.
The controls are `playground/ui.py` HoldButtons, so rotate and thrust work at the same time.

## Ideas

- A tilt sensor (MPU-6050 on I2C, now that HDMI frees the GPIO header) for steering.
- A camera that zooms in near the ground, like the arcade original.
- Ghost replay of your best landing.
