"""Run a playground scene.

    python run.py grass              # Pi: fullscreen on the panel
    python run.py grass --window     # laptop: 480x640 window, mouse = touch
    python run.py --list             # show available scenes

While it runs, open the control panel in a browser:
    http://<pi-address>:8000   (from the laptop or phone)
    http://localhost:8000      (when running on the laptop)
"""
import argparse
import errno
import os
import signal
import socket
import sys
import time
import traceback
import urllib.request

import pygame

from playground.control import Controller, start_server
from playground.loader import list_scenes, load_module, preset_path
from playground.scene import Values
from playground.touch import EvdevTouch

W, H = 480, 640                   # panel resolution (portrait)
STEP = 1 / 60                     # fixed physics/animation time step
MAX_STEPS = 4                     # never fall further behind than this per frame


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


def claim_panel(ctrl, port):
    """Start the control panel. If another copy of run.py already holds the port,
    ask it to stop (handoff), then take over."""
    asked = False
    deadline = time.time() + 5
    while True:
        try:
            return start_server(ctrl, port)
        except OSError as err:
            if err.errno != errno.EADDRINUSE:
                raise
            if not asked:
                print("Another scene is already running; asking it to stop...")
                try:
                    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/quit", data=b"{}",
                                                 headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(req, timeout=1.5)
                except Exception:
                    pass                      # not one of ours, or too old to know /api/quit
                asked = True
            if time.time() > deadline:
                raise OSError(errno.EADDRINUSE,
                              f"port {port} is still in use. Stop the other program with: pkill -f run.py")
            time.sleep(0.2)


def _stop_on_signal(signum, frame):
    raise KeyboardInterrupt          # run the normal clean-up (clear screen, free the port)


class Stage:
    """Where scenes draw. Portrait scenes draw straight to the screen. Landscape
    scenes (Scene.LANDSCAPE = True) draw on a 640x480 canvas that is rotated onto
    the portrait panel, with touches rotated to match; in a laptop window they
    simply get a landscape window."""

    def __init__(self, screen, fb, window):
        self.screen, self.fb, self.window = screen, fb, window
        self.landscape = False
        self.canvas = screen

    def configure(self, landscape):
        if landscape == self.landscape and self.canvas is not None:
            return
        self.landscape = landscape
        if self.window:
            self.screen = pygame.display.set_mode((H, W) if landscape else (W, H))
            self.canvas = self.screen
        else:
            sw, sh = self.screen.get_size()
            self.canvas = pygame.Surface((sh, sw)) if landscape else self.screen

    @property
    def size(self):
        return self.canvas.get_size()

    def map_touch(self, x, y, flip):
        if not self.landscape or self.window:
            return x, y
        cw, ch = self.canvas.get_size()
        if flip:                              # canvas rotated clockwise onto the panel
            return y, ch - 1 - x
        return cw - 1 - y, x                  # canvas rotated counter-clockwise (default)

    def present(self, flip):
        if self.landscape and not self.window:
            self.screen.blit(pygame.transform.rotate(self.canvas, -90 if flip else 90), (0, 0))
        if self.fb:
            self.fb.show(self.screen)
        else:
            pygame.display.flip()


def build_scene(ctrl, name, stage, switching):
    """Import (or re-import, picking up code edits) and construct a scene."""
    mod = load_module(name)
    if switching:
        ctrl.load_scene(name, mod.Scene)
    else:                                   # keep current values, refresh schema
        ctrl.schema = list(mod.Scene.PARAMS)
        for p in ctrl.schema:
            ctrl.values.setdefault(p.name, p.default)
    stage.configure(bool(getattr(mod.Scene, "LANDSCAPE", False)))
    return mod.Scene(*stage.size, Values(ctrl))


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
    signal.signal(signal.SIGTERM, _stop_on_signal)
    if hasattr(signal, "SIGHUP"):                  # SSH window closed
        signal.signal(signal.SIGHUP, _stop_on_signal)

    # claim the panel first, so a copy that's already running hands over the screen
    ctrl = Controller(available, preset_path)
    if not args.no_panel:
        try:
            claim_panel(ctrl, args.port)
            host = "localhost" if window else local_ip()
            print(f"Control panel: http://{host}:{args.port}")
        except OSError as err:
            print(f"Control panel not started: {err}")

    pygame.init()
    screen, fb = open_display(window, args.fb)
    w, h = screen.get_size()
    touch = None if window else EvdevTouch.open(w, h)
    font = pygame.font.Font(None, 22)
    clock = pygame.time.Clock()
    stage = Stage(screen, fb, window)
    scene = build_scene(ctrl, args.scene, stage, switching=True)

    acc = 0.0
    dragging = False
    try:
        while True:
            acc += min(clock.tick(60) / 1000, STEP * MAX_STEPS)
            if ctrl.quit_requested:                # another copy took over, or Stop in the panel
                print("Stopping (requested from the control panel or a new run).")
                return

            # scene switch / rebuild requested from the panel
            name = ctrl.take_pending_scene()
            if name or ctrl.take_reset():
                try:
                    scene = build_scene(ctrl, name or ctrl.scene_name, stage,
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
                scene.touch(kind, *stage.map_touch(x, y, ctrl.flip_landscape))

            # fixed-step update, then draw
            while acc >= STEP:
                scene.update(STEP)
                acc -= STEP
            canvas = stage.canvas
            scene.draw(canvas)
            if ctrl.show_fps:
                canvas.blit(font.render(f"{clock.get_fps():3.0f} fps", True,
                                        (230, 230, 230), (0, 0, 0)), (4, 4))
            stage.present(ctrl.flip_landscape)
    except KeyboardInterrupt:
        pass
    finally:
        if fb:
            fb.clear()
            fb.close()
        pygame.quit()


if __name__ == "__main__":
    main()
