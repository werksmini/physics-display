# physics-display

Live, touch-interactive 2D physics on a Raspberry Pi Zero 2 W with a Waveshare 2.8" DPI touchscreen.

Notes, setup guides and research live in the Notion workspace ("Physics Display Project"). This repo holds code and config.

## Layout

- `demos/` – runnable experiments
- `config/` – known-good `config.txt` snippets, with OS version noted in each file

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 demos/touch_balls.py --window   # laptop: mouse acts as touch
python3 demos/touch_balls.py            # Pi: fullscreen on the panel
```

## Demos

| Demo | What it does |
|---|---|
| `touch_balls.py` | Balls bounce in a box; tap to blast nearby balls and spawn a new one |
