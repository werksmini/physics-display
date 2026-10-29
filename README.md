# physics-display

Live, touch-interactive 2D physics on a Raspberry Pi Zero 2 W with a Waveshare 2.8" DPI touchscreen.

Notes, setup guides and research live in the Notion workspace ("Physics Display Project"). This repo holds code and config.

## Layout

- `run.py` – runs a scene and serves its control panel
- `scenes/` – **the scene collection**, one folder per scene; see the [gallery](scenes/README.md)
- `playground/` – the engine: scene loader, touch + framebuffer drivers, web control panel
- `tools/make_previews.py` – regenerates each scene's `preview.png` and the gallery
- `demos/` – earlier standalone experiments
- `config/` – known-good `config.txt` snippets, with OS version noted in each file

## Playground

```bash
python run.py grass            # on the Pi (fullscreen on the panel)
python run.py grass --window   # on the laptop (mouse acts as touch)
python run.py --list           # available scenes
```

Then open the control panel: `http://192.168.0.229:8000` (Pi) or `http://localhost:8000` (laptop).
Sliders change the running scene live; settings marked ↻ restart it. "Restart scene" also reloads
the scene's code, so after editing a scene file (or `git pull`) you don't need to stop the program.

### Writing a scene

Make a folder `scenes/<name>/` with a `scene.py` containing a `Scene` class: declare `PARAMS`,
then fill in `setup`, `update(dt)`, `draw(surf)` and `touch(kind, x, y)` (see `playground/scene.py`).
Add a `README.md`, then run `python tools/make_previews.py <name>`. "Save as default" in the panel
writes `scenes/<name>/preset.json`; commit it to keep it.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 demos/touch_balls.py --window   # laptop: mouse acts as touch
python3 demos/touch_balls.py            # Pi: fullscreen on the panel
```

## On the Pi (Pi OS Lite, no desktop)

```bash
sudo apt install -y python3-pygame python3-evdev python3-numpy
python3 -m venv --system-site-packages .venv && source .venv/bin/activate
pip install pymunk
sudo usermod -aG input,video,render $USER   # then log out and back in
python3 demos/touch_balls.py
```

Touch is read straight from the Goodix controller (`demos/touchinput.py`), which reports a 640×480 range on a 480×640 screen; the module rescales it.

## Demos

| Demo | What it does |
|---|---|
| `touch_balls.py` | Balls bounce in a box; tap to blast nearby balls and spawn a new one |
