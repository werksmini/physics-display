"""Run a playground scene.

    python run.py                    # the home screen (how the boot service starts it)
    python run.py pool               # Pi: straight into a scene, fullscreen on the panel
    python run.py grass --window     # laptop: 480x640 window, mouse = touch
    python run.py --list             # show available scenes
    python run.py pool --gpu         # draw through the GPU (needed for shader scenes)

On the Pi, hold a finger still against an edge of the screen for three seconds:
    top edge    -> back to the home screen
    right edge  -> next vignette
    left edge   -> previous vignette

While it runs, open the control panel in a browser:
    http://<pi-address>:8000   (from the laptop or phone)
    http://localhost:8000      (when running on the laptop)
"""
import argparse
import errno
import math
import os
import signal
import socket
import sys
import time
import traceback
import urllib.request

import pygame

from playground.control import Controller, start_server
from playground.launcher import HOME, Launcher
from playground.loader import exists, list_scenes, load_module, preset_path
from playground.scene import Values
from playground import state
from playground.touch import EvdevTouch

W, H = 480, 640                   # panel resolution (portrait)
STEP = 1 / 60                     # fixed physics/animation time step
MAX_STEPS = 2                     # when a frame is slow, catch up at most this much
                                  # (more would make the next frame slower still)
HOLD_SECONDS = 3.0                # hold still against an edge this long to navigate
EDGE = 40                         # edge zone width, in pixels


def open_gpu():
    """Open the panel through the GPU (OpenGL ES 2.0, vsync). Returns (size, GL)."""
    from playground import gl as glmod
    os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")
    pygame.display.init()
    glmod.request_es2_context()
    flags = pygame.OPENGL | pygame.DOUBLEBUF
    size = (W, H)
    if os.environ["SDL_VIDEODRIVER"] == "kmsdrm":
        flags |= pygame.FULLSCREEN
        size = (0, 0)
    try:
        surf = pygame.display.set_mode(size, flags, vsync=1)
    except (pygame.error, TypeError):
        surf = pygame.display.set_mode(size, flags)
    pygame.mouse.set_visible(False)
    w, h = surf.get_size()
    return (w, h), glmod.GL(w, h)


def open_display(window, mode):
    """mode: 'gpu', 'fb' or 'auto'. Returns (screen_surface, framebuffer_or_None, gl_or_None)."""
    if window:
        screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("playground")
        return screen, None, None
    if mode in ("gpu", "auto"):
        try:
            size, gl = open_gpu()
            info = gl.info()
            print(f"GPU display: {info['renderer']} ({info['version']}), {size[0]}x{size[1]}")
            return pygame.Surface(size), None, gl
        except Exception as err:                 # no GPU path: fall back to the framebuffer
            if mode == "gpu":
                print(f"GPU display failed ({err}); drawing to /dev/fb0 instead")
            pygame.display.quit()
    from playground.framebuffer import FrameBuffer
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    fb = FrameBuffer()
    return pygame.Surface(fb.size), fb, None


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


class EdgeHold:
    """Getting around with no computer: hold a finger still against an edge.
    Top edge: home screen. Right edge: next vignette. Left edge: previous.
    Coordinates are the scene's (so "top" is the top as you look at it)."""

    ACTIONS = {"top": ("home", "Home"), "right": ("next", "Next  \u203a"), "left": ("prev", "\u2039  Previous")}

    def __init__(self):
        self.start = None                     # (edge, x, y, time)
        self.font = pygame.font.Font(None, 26)

    def feed(self, kind, x, y, w, h, now):
        if kind == "down":
            near = {"top": y, "left": x, "right": w - 1 - x}
            edge = min(near, key=near.get)
            self.start = (edge, x, y, now) if near[edge] < EDGE else None
        elif kind == "move" and self.start and math.hypot(x - self.start[1], y - self.start[2]) > 25:
            self.start = None                 # moved away: it's a normal touch
        elif kind == "up":
            self.start = None

    def check(self, now):
        """'home', 'next' or 'prev' when a hold completes."""
        if self.start and now - self.start[3] >= HOLD_SECONDS:
            edge = self.start[0]
            self.start = None
            return self.ACTIONS[edge][0]
        return None

    def indicator(self, w, h, now):
        """(surface, (x, y)) showing the hold filling up, once it's clearly a hold."""
        if not self.start or now - self.start[3] < 0.5:
            return None
        edge, x, y, t0 = self.start
        frac = min(1.0, (now - t0) / HOLD_SECONDS)
        label = self.font.render(self.ACTIONS[edge][1], True, (245, 245, 245))
        bw = max(label.get_width() + 28, 120)
        img = pygame.Surface((bw, 44), pygame.SRCALPHA)
        pygame.draw.rect(img, (0, 0, 0, 170), img.get_rect(), border_radius=12)
        img.blit(label, label.get_rect(center=(bw // 2, 17)))
        pygame.draw.rect(img, (255, 255, 255, 60), (12, 33, bw - 24, 4), border_radius=2)
        pygame.draw.rect(img, (246, 206, 60), (12, 33, int((bw - 24) * frac), 4), border_radius=2)
        if edge == "top":
            pos = (min(max(x - bw // 2, 6), w - bw - 6), EDGE + 16)
        elif edge == "left":
            pos = (EDGE + 16, min(max(y - 22, 6), h - 50))
        else:
            pos = (w - bw - EDGE - 16, min(max(y - 22, 6), h - 50))
        return img, pos


class Banner:
    """Shows the scene name for a moment after switching."""

    def __init__(self):
        self.text, self.until = "", 0.0
        self.font = pygame.font.Font(None, 40)

    def show(self, text, now, secs=2.5):
        self.text, self.until = text, now + secs

    def image(self, now):
        """The banner as a small surface, or None when it isn't showing."""
        if now > self.until or not self.text:
            return None
        txt = self.font.render(self.text, True, (245, 245, 245))
        img = pygame.Surface(txt.get_rect().inflate(36, 22).size, pygame.SRCALPHA)
        pygame.draw.rect(img, (0, 0, 0, 170), img.get_rect(), border_radius=12)
        img.blit(txt, txt.get_rect(center=img.get_rect().center))
        return img

    def draw(self, surf, now):
        img = self.image(now)
        if img:
            surf.blit(img, img.get_rect(center=(surf.get_width() // 2, surf.get_height() // 2)))


class Stage:
    """Where scenes draw. Portrait scenes draw straight to the screen. Landscape
    scenes (Scene.LANDSCAPE = True) draw on a 640x480 canvas that is rotated onto
    the portrait panel, with touches rotated to match; in a laptop window they
    simply get a landscape window.

    In GPU mode (self.gl set), ordinary scenes still draw on a canvas Surface,
    which is uploaded as a texture and presented with vsync (rotated on the GPU
    for landscape). GPU scenes (Scene.GPU = True) draw with shaders directly."""

    def __init__(self, screen, fb, window, gl=None):
        self.screen, self.fb, self.window, self.gl = screen, fb, window, gl
        self.landscape = False
        self.canvas = screen
        self.gpu_scene = False

    def configure(self, landscape, gpu_scene=False):
        self.gpu_scene = gpu_scene
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
        if self.gl:                               # upload the canvas, draw it, swap with vsync
            tex = self.gl.surface_texture(self.canvas, "canvas")
            self.gl.screen()
            self.gl.blit(tex, rot=(2 if flip else 1) if self.landscape else 0)
            pygame.display.flip()
            return
        if self.landscape and not self.window:
            self.screen.blit(pygame.transform.rotate(self.canvas, -90 if flip else 90), (0, 0))
        if self.fb:
            self.fb.show(self.screen)
        else:
            pygame.display.flip()

    def present_gl(self, overlays):
        """For GPU scenes: draw small overlay surfaces [(surf, (x, y))] then swap."""
        for i, (img, pos) in enumerate(overlays):
            self.gl.blit_at(self.gl.surface_texture(img, f"overlay{i}"), *pos)
        pygame.display.flip()


def build_scene(ctrl, name, stage, switching, menu=None, last=None):
    """Import (or re-import, picking up code edits) and construct a scene."""
    if name == HOME:                        # the home screen: drawn on the GPU when there is one
        ctrl.load_scene(HOME, Launcher)
        stage.configure(False, stage.gl is not None)
        return Launcher(*stage.size, Values(ctrl), gl=stage.gl, scenes=menu, last=last)
    mod = load_module(name)
    if switching:
        ctrl.load_scene(name, mod.Scene)
    else:                                   # keep current values, refresh schema
        ctrl.schema = list(mod.Scene.PARAMS)
        for p in ctrl.schema:
            ctrl.values.setdefault(p.name, p.default)
    gpu_scene = bool(getattr(mod.Scene, "GPU", False))
    if gpu_scene and stage.gl is None:
        raise RuntimeError(f"'{name}' draws with the GPU: run with --gpu on the Pi")
    stage.configure(bool(getattr(mod.Scene, "LANDSCAPE", False)), gpu_scene)
    return mod.Scene(*stage.size, Values(ctrl), gl=stage.gl)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scene", nargs="?", default=None,
                    help="scene to run (default: the last one shown, else grass)")
    ap.add_argument("--window", action="store_true", help="run in a window (laptop)")
    ap.add_argument("--fb", action="store_true", help="draw straight to /dev/fb0 (no GPU)")
    ap.add_argument("--gpu", action="store_true",
                    help="draw through the GPU with vsync (default on the Pi, falls back to --fb)")
    ap.add_argument("--port", type=int, default=8000, help="control panel port")
    ap.add_argument("--no-panel", action="store_true", help="don't start the web panel")
    ap.add_argument("--list", action="store_true", help="list scenes and exit")
    args = ap.parse_args()

    available = list_scenes()
    if args.list:
        for n, t in available.items():
            print(f"{n:12s} {t}")
        return
    saved = state.load()
    if args.scene is None:
        args.scene = HOME
    if args.scene not in available and args.scene != HOME:
        if not exists(args.scene):
            sys.exit(f"unknown scene '{args.scene}'. Try: {', '.join(available)}")
        available[args.scene] = list_scenes(retired=True).get(args.scene, args.scene)   # retired, asked for by name

    window = args.window or not sys.platform.startswith("linux")
    signal.signal(signal.SIGTERM, _stop_on_signal)
    if hasattr(signal, "SIGHUP"):                  # SSH window closed
        signal.signal(signal.SIGHUP, _stop_on_signal)

    # claim the panel first, so a copy that's already running hands over the screen
    menu = dict(available)                       # the vignettes, in order (for the home screen and next/prev)
    available = {HOME: "Home (vignettes)", **available}
    ctrl = Controller(available, preset_path)
    ctrl.flip_landscape = bool(saved.get("flip_landscape", False))
    if not args.no_panel:
        try:
            claim_panel(ctrl, args.port)
            host = "localhost" if window else local_ip()
            print(f"Control panel: http://{host}:{args.port}")
        except OSError as err:
            print(f"Control panel not started: {err}")

    pygame.init()
    mode = "fb" if args.fb else "gpu" if args.gpu else "auto"
    screen, fb, gl = open_display(window, mode)
    w, h = screen.get_size()
    touch = None if window else EvdevTouch.open(w, h)
    font = pygame.font.Font(None, 22)
    clock = pygame.time.Clock()
    stage = Stage(screen, fb, window, gl)
    try:
        scene = build_scene(ctrl, args.scene, stage, True, menu, saved.get("scene"))
    except Exception as err:                     # e.g. a GPU scene but no GPU (--fb): use a CPU scene
        print(f"Couldn't start '{args.scene}': {err}\nStarting 'grass' instead.")
        args.scene = "grass"
        available.setdefault("grass", "Grass")
        scene = build_scene(ctrl, args.scene, stage, True, menu)
    if args.scene != HOME:
        state.save(scene=args.scene)
    edges = EdgeHold()
    banner = Banner()
    if args.scene != HOME:
        banner.show(available[args.scene], time.time(), 2.0)
    names = list(menu) or [HOME]
    flip_seen = ctrl.flip_landscape

    acc = 0.0
    dragging = False
    mouse_finger = None
    try:
        while True:
            acc += min(clock.tick(60) / 1000, STEP * MAX_STEPS)
            if ctrl.quit_requested:                # another copy took over, or Stop in the panel
                print("Stopping (requested from the control panel or a new run).")
                return

            now = time.time()
            action = edges.check(now)              # edge hold: home / next / previous
            if action == "home":
                ctrl.request_scene(HOME)
            elif action:
                cur = ctrl.scene_name
                if cur in names:
                    k = names.index(cur) + (1 if action == "next" else -1)
                else:                              # from home (or a retired scene): first / last
                    k = 0 if action == "next" else -1
                ctrl.request_scene(names[k % len(names)])
            if ctrl.flip_landscape != flip_seen:
                flip_seen = ctrl.flip_landscape
                state.save(flip_landscape=flip_seen)

            # scene switch / rebuild requested from the panel
            name = ctrl.take_pending_scene()
            if name or ctrl.take_reset():
                try:
                    scene = build_scene(ctrl, name or ctrl.scene_name, stage, bool(name),
                                        menu, state.load().get("scene"))
                    ctrl.last_error = ""
                    if name and name != HOME:
                        state.save(scene=name)
                        banner.show(available[name], now)
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
                sx, sy = stage.map_touch(x, y, ctrl.flip_landscape)
                edges.feed(kind, sx, sy, *stage.size, now)
                scene.touch(kind, sx, sy)
                if kind == "down":
                    mouse_finger = (x, y)
                elif kind == "move" and mouse_finger:
                    mouse_finger = (x, y)
                elif kind == "up":
                    mouse_finger = None
            if hasattr(scene, "fingers"):           # multi-touch scenes get every finger, every frame
                raw = touch.fingers if touch else ({0: mouse_finger} if mouse_finger else {})
                scene.fingers({k: stage.map_touch(x, y, ctrl.flip_landscape) for k, (x, y) in raw.items()})

            # fixed-step update, then draw
            while acc >= STEP:
                scene.update(STEP)
                acc -= STEP
            if getattr(scene, "launch", None):      # the home screen picked a vignette
                ctrl.request_scene(scene.launch)
                scene.launch = None
            fps_img = font.render(f"{clock.get_fps():3.0f} fps", True, (230, 230, 230), (0, 0, 0)) \
                if ctrl.show_fps else None
            if stage.gpu_scene:
                stage.gl.screen()
                scene.draw_gl(stage.gl)
                stage.gl.reset_state()
                overlays = [(fps_img, (4, 4))] if fps_img else []
                b = banner.image(now)
                if b:
                    overlays.append((b, ((w - b.get_width()) // 2, (h - b.get_height()) // 2)))
                ind = edges.indicator(*stage.size, now)
                if ind:
                    overlays.append(ind)
                stage.present_gl(overlays)
            else:
                canvas = stage.canvas
                scene.draw(canvas)
                if fps_img:
                    canvas.blit(fps_img, (4, 4))
                banner.draw(canvas, now)
                ind = edges.indicator(*stage.size, now)
                if ind:
                    canvas.blit(*ind)
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
