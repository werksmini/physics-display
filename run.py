"""Run a playground scene.

    python run.py grass              # Pi: fullscreen on the panel
    python run.py grass --window     # laptop: 480x640 window, mouse = touch
    python run.py --list             # show available scenes

While it runs, open the control panel in a browser:
    http://<pi-address>:8000   (from the laptop or phone)
    http://localhost:8000      (when running on the laptop)
"""
import argparse
import importlib
import os
import pkgutil
import socket
import sys
import traceback
from pathlib import Path

import pygame

from playground import scenes as scenes_pkg
from playground.control import Controller, start_server
from playground.scene import Values
from playground.touch import EvdevTouch

W, H = 480, 640                   # panel resolution (portrait)
STEP = 1 / 60                     # fixed physics/animation time step
MAX_STEPS = 4                     # never fall further behind than this per frame
ROOT = Path(__file__).parent


def list_scenes():
    out = {}
    for m in pkgutil.iter_modules(scenes_pkg.__path__):
        if m.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"playground.scenes.{m.name}")
            out[m.name] = getattr(mod.Scene, "TITLE", "") or m.name
        except Exception:
            out[m.name] = f"{m.name} (failed to load)"
    return out


def open_display(window, force_fb):
    """Return (screen_surface, framebuffer_or_None)."""
    if window:
        screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("playground")
        return screen, None
    if not force_fb:
        try:
            screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            pygame.mouse.set_visible(False)
            return screen, None
        except pygame.error as err:
            print(f"SDL display failed ({err}); drawing to /dev/fb0 instead")
    from playground.framebuffer import FrameBuffer
    pygame.display.quit()
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    fb = FrameBuffer()
    return pygame.Surface(fb.size), fb


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "localhost"


def build_scene(ctrl, name, w, h, switching):
    """Import (or re-import, picking up code edits) and construct a scene."""
    mod = importlib.import_module(f"playground.scenes.{name}")
    mod = importlib.reload(mod)
    if switching:
        ctrl.load_scene(name, mod.Scene)
    else:                                   # keep current values, refresh schema
        ctrl.schema = list(mod.Scene.PARAMS)
        for p in ctrl.schema:
            ctrl.values.setdefault(p.name, p.default)
    return mod.Scene(w, h, Values(ctrl))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scene", nargs="?", default="grass")
    ap.add_argument("--window", action="store_true", help="run in a window (laptop)")
    ap.add_argument("--fb", action="store_true", help="draw straight to /dev/fb0")
    ap.add_argument("--port", type=int, default=8000, help="control panel port")
    ap.add_argument("--no-panel", action="store_true", help="don't start the web panel")
    ap.add_argument("--list", action="store_true", help="list scenes and exit")
    args = ap.parse_args()

    available = list_scenes()
    if args.list:
        for n, t in available.items():
            print(f"{n:12s} {t}")
        return
    if args.scene not in available:
        sys.exit(f"unknown scene '{args.scene}'. Try: {', '.join(available)}")

    window = args.window or not sys.platform.startswith("linux")
    pygame.init()
    screen, fb = open_display(window, args.fb)
    w, h = screen.get_size()
    touch = None if window else EvdevTouch.open(w, h)
    font = pygame.font.Font(None, 22)
    clock = pygame.time.Clock()

    ctrl = Controller(available, ROOT / "presets")
    scene = build_scene(ctrl, args.scene, w, h, switching=True)

    if not args.no_panel:
        try:
            start_server(ctrl, args.port)
            host = "localhost" if window else local_ip()
            print(f"Control panel: http://{host}:{args.port}")
        except OSError as err:
            print(f"Control panel not started: {err}")

    acc = 0.0
    dragging = False
    try:
        while True:
            acc += min(clock.tick(60) / 1000, STEP * MAX_STEPS)

            # scene switch / rebuild requested from the panel
            name = ctrl.take_pending_scene()
            if name or ctrl.take_reset():
                try:
                    scene = build_scene(ctrl, name or ctrl.scene_name, w, h,
                                        switching=bool(name))
                    ctrl.last_error = ""
                except Exception:
                    ctrl.last_error = traceback.format_exc(limit=3)
                    print(ctrl.last_error)

            # input
            events = touch.events() if touch else []
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    return
                if e.type == pygame.KEYDOWN and e.key in (pygame.K_ESCAPE, pygame.K_q):
                    return
                if touch:
                    continue                 # touchscreen handled via evdev
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    dragging = True
                    events.append(("down", *e.pos))
                elif e.type == pygame.MOUSEMOTION and dragging:
                    events.append(("move", *e.pos))
                elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                    dragging = False
                    events.append(("up", *e.pos))
            for kind, x, y in events:
                scene.touch(kind, x, y)

            # fixed-step update, then draw
            while acc >= STEP:
                scene.update(STEP)
                acc -= STEP
            scene.draw(screen)
            if ctrl.show_fps:
                screen.blit(font.render(f"{clock.get_fps():3.0f} fps", True,
                                        (230, 230, 230), (0, 0, 0)), (4, 4))
            if fb:
                fb.show(screen)
            else:
                pygame.display.flip()
    except KeyboardInterrupt:
        pass
    finally:
        if fb:
            fb.clear()
            fb.close()
        pygame.quit()


if __name__ == "__main__":
    main()
