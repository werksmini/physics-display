# physics-display

Live, touch-interactive 2D physics on a Raspberry Pi Zero 2 W with a Waveshare 2.8" DPI touchscreen.

Notes, setup guides and research live in the Notion workspace ("Physics Display Project"). This repo holds code and config.

## Layout

- `run.py` – runs a scene and serves its control panel
- `scenes/` – **the scene collection**, one folder per scene; see the [gallery](scenes/README.md).
  The older CPU-drawn scenes are retired to `scenes/_cpu/`: off the menu, but `python run.py grass` still runs them
- `playground/` – the engine: scene loader, touch + framebuffer drivers, web control panel
- `tools/make_previews.py` – regenerates each scene's `preview.png` and the gallery
- `demos/` – earlier standalone experiments
- `config/` – known-good `config.txt` snippets, with OS version noted in each file

## Playground

```bash
python run.py pool            # on the Pi (fullscreen on the panel)
python run.py grass --window  # on the laptop (mouse acts as touch; CPU scenes only)
python run.py --list           # available scenes
```

Then open the control panel: `http://192.168.0.229:8000` (Pi) or `http://localhost:8000` (laptop).
Sliders change the running scene live; settings marked ↻ restart it. "Restart scene" also reloads
the scene's code, so after editing a scene file (or `git pull`) you don't need to stop the program.

### Writing a scene

Make a folder `scenes/<name>/` with a `scene.py` containing a `Scene` class: declare `PARAMS`
(and `LANDSCAPE = True` for a sideways 640×480 scene; the runner rotates it onto the panel),
then fill in `setup`, `update(dt)`, `draw(surf)` and `touch(kind, x, y)` (see `playground/scene.py`).
Add a `README.md`, then run `python tools/make_previews.py <name>`. "Save as default" in the panel
writes `scenes/<name>/preset.json`; commit it to keep it.

## GPU rendering

The Pi Zero 2 W's graphics chip (VideoCore IV, OpenGL ES 2.0) is used through a tiny ctypes layer,
`playground/gl.py`, so there's nothing extra to install. `python run.py --gpu` (the default on the
Pi) opens the panel through the GPU with vsync:

- ordinary scenes draw as before; their frame is uploaded and shown without tearing (landscape is
  rotated on the GPU)
- **GPU scenes** (`GPU = True`, e.g. `pool`) draw with shaders in `draw_gl(gl)`
- if the GPU can't be opened it falls back to `--fb`

GPU scenes don't run in the laptop window (Windows has no OpenGL ES library); `tools/make_previews.py`
renders them in software. Shaders are GLSL ES 1.00; see the notes at the top of `playground/gl.py`.

## Run at boot (no computer needed)

```bash
bash tools/install_autostart.sh            # install, start now, and start at every boot
bash tools/install_autostart.sh --remove   # turn it off
```

At boot the Pi opens the **home screen**: a scrolling grid of vignettes with a preview of each.
Tap one to open it (a yellow dot marks the one you had open last).

Getting around without a computer: **hold a finger still against an edge for two seconds**.
A soft half-moon of light grows from your finger while it counts:

| Edge | Glow | Goes to |
|---|---|---|
| Top | green | The home screen |
| Right | white | The next vignette |
| Left | white | The previous vignette |
| Bottom | blue | Start this vignette over |

Each vignette opens with its own illustrated title card. The display fonts live in
`playground/fonts` (SIL Open Font License; see the LICENSE file there), and the cards are drawn by
`playground/brand.py` from each scene's `BRAND`.

The control panel still works from a phone on the same Wi-Fi ("Home" is at the top of its scene list).

Handy commands: `sudo systemctl restart physics-display` (after `git pull`),
`sudo systemctl stop physics-display`, and `journalctl -u physics-display -f` to see errors.

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
