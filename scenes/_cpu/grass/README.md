# Grass in the wind

![preview](preview.png)

A side view of a low-resolution field of grass at sunset. Gusts roll across the field and your finger controls the wind.

```bash
python run.py grass            # Pi
python run.py grass --window   # laptop
```

## Touch

Touch left or right of centre to blow the wind that way; further from centre = stronger. Let go and the wind eases back to the **Breeze** setting.

## How it works

- Each blade is a **damped spring**: an angle that wind pushes and stiffness pulls back upright, stepped with semi-implicit Euler.
- **Wind** = steady breeze (or your finger) + **gusts** from a 2D noise field that slides across the field in the wind's direction.
- Blades are sorted back to front; far ones are shorter and darker for depth.
- Everything is drawn on a small surface and scaled up for chunky pixels.

## Settings worth playing with

| Setting | Try |
|---|---|
| Blade damping | Near 0 for wobbly, springy grass; high for heavy, slow grass |
| Gust size / speed | Big and slow for rolling waves; small and fast for flicker |
| Pixel size | 1–2 for fine grass, 6–8 for very chunky |

## Ideas

- Flowers or seed heads on some blades that lag behind (heavier tips)
- Time-of-day palette slider
- Swipe speed sets wind strength instead of position
