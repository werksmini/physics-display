"""Touch games for the Waveshare 10.4" QLED (1600x720, HDMI, USB touch).

    python play.py                  # Pi: the games menu, fullscreen on the 10.4" panel
    python play.py hockey           # Pi: straight into a game
    python play.py lander --window  # laptop: a window, mouse = one finger
    python play.py --list           # available games
    python play.py hockey --shot out.png --frames 240   # headless: run, save a screenshot

Games draw on an 800x360 canvas that the GPU scales 2x onto the 1600x720 panel:
a quarter of the pixels to paint on the Pi Zero 2 W's CPU, and touch targets are
still big. Touch coordinates arrive already in canvas pixels.

Getting around: hold the small MENU tab at the top centre for a second to go back to
the menu. Esc or q quits (keyboard).

A game is a folder games/<name>/ with game.py defining `class Game` (see
games/README.md). Unlike the vignettes in run.py there's no web control panel;
the controls are on the screen.
"""
import argparse
import importlib.util
import os
import signal
import sys
import time
import traceback
from pathlib import Path

import pygame

from playground.touch import EvdevTouch
from playground.ui import Controls, HoldButton, font

CANVAS = (800, 360)              # what games draw on
PANEL = (1600, 720)              # the 10.4" QLED
STEP = 1 / 60
MAX_STEPS = 3
GAMES_DIR = Path(__file__).resolve().parent / "games"
MENU = "menu"


# ------------------------------------------------------------------ games on disk
def list_games():
    out = {}
    for d in sorted(GAMES_DIR.iterdir()):
        if d.is_dir() and (d / "game.py").exists() and not d.name.startswith("_"):
            try:
                out[d.name] = load(d.name).Game
            except Exception as err:
                print(f"games/{d.name} failed to load: {err}")
    return out


def load(name):
    path = GAMES_DIR / name / "game.py"
    spec = importlib.util.spec_from_file_location(f"games_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ display
class Display:
    """Opens the panel (GPU with vsync, else /dev/fb0) or a laptop window, and
    presents the 800x360 canvas on it."""

    def __init__(self, window, mode, zoom, headless=False):
        self.gl = self.fb = None
        self.zoom = zoom
        self.canvas = pygame.Surface(CANVAS)
        if headless:
            os.environ["SDL_VIDEODRIVER"] = "dummy"
            pygame.display.init()
            pygame.display.set_mode((1, 1))
            self.kind, self.size = "headless", CANVAS
            return
        if window:
            self.kind = "window"
            self.size = (int(CANVAS[0] * zoom), int(CANVAS[1] * zoom))
            self.screen = pygame.display.set_mode(self.size)
            pygame.display.set_caption("games")
            return
        if mode in ("gpu", "auto"):
            try:
                self._open_gpu()
                return
            except Exception as err:
                print(f"GPU display failed ({err}); drawing to /dev/fb0 instead")
                pygame.display.quit()
        from playground.framebuffer import FrameBuffer
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        pygame.display.init()
        pygame.display.set_mode((1, 1))
        self.fb = FrameBuffer()
        self.kind, self.size = "fb", self.fb.size
        self.screen = pygame.Surface(self.size)
        print(f"Framebuffer display {self.size[0]}x{self.size[1]}")

    def _open_gpu(self):
        from playground import gl as glmod
        os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")
        pygame.display.init()
        glmod.request_es2_context()
        flags = pygame.OPENGL | pygame.DOUBLEBUF | pygame.FULLSCREEN
        try:
            surf = pygame.display.set_mode((0, 0), flags, vsync=1)
        except (pygame.error, TypeError):
            surf = pygame.display.set_mode((0, 0), flags)
        pygame.mouse.set_visible(False)
        self.size = surf.get_size()
        self.gl = glmod.GL(*self.size)
        self.kind = "gpu"
        info = self.gl.info()
        print(f"GPU display: {info['renderer']}, {self.size[0]}x{self.size[1]}")
        if self.size != PANEL:
            print(f"  note: expected {PANEL[0]}x{PANEL[1]}; see the Notion quick start (HDMI mode)")

    def present(self, smooth=True):
        if self.kind == "gpu":
            tex = self.gl.surface_texture(self.canvas, "canvas", smooth=smooth)
            self.gl.screen()
            self.gl.blit(tex)
            pygame.display.flip()
        elif self.kind == "fb":
            scale = pygame.transform.smoothscale if smooth else pygame.transform.scale
            scale(self.canvas, self.size, self.screen)
            self.fb.show(self.screen)
        elif self.kind == "window":
            if self.zoom == 1:
                self.screen.blit(self.canvas, (0, 0))
            else:
                pygame.transform.smoothscale(self.canvas, self.size, self.screen)
            pygame.display.flip()

    def close(self):
        if self.fb:
            self.fb.clear()
            self.fb.close()


# ------------------------------------------------------------------ the menu
class Menu:
    """Big cards, one per game. Tap a card to play."""
    TITLE = "Games"

    def __init__(self, w, h, games):
        self.w, self.h = w, h
        self.games = games                       # {name: Game class}
        self.launch = None
        self.ui = Controls()
        names = list(games)
        n = max(1, len(names))
        cols = min(n, 3)
        cw, ch, gap = 230, 200, 24
        x0 = (w - (cols * cw + (cols - 1) * gap)) // 2
        rows = (n + cols - 1) // cols
        y0 = max(90, (h - (rows * ch + (rows - 1) * gap)) // 2 + 30)
        self.cards = []
        for i, name in enumerate(names):
            r = pygame.Rect(x0 + (i % cols) * (cw + gap), y0 + (i // cols) * (ch + gap), cw, ch)
            from playground.ui import Button
            b = self.ui.add(Button(r, "", on_tap=lambda name=name: self._pick(name)))
            b.visible = False                    # drawn as a card below
            self.cards.append((name, r, b))
        self.t = 0.0
        self.icons = {}
        for name, r, _ in self.cards:
            g = games[name]
            icon = pygame.Surface((r.w - 20, r.h - 70), pygame.SRCALPHA)
            try:
                g.icon(icon)                     # optional: a little picture of the game
            except Exception:
                icon.fill((40, 44, 60))
            self.icons[name] = icon

    def _pick(self, name):
        self.launch = name

    def fingers(self, f):
        self.ui.feed(f)

    def update(self, dt):
        self.t += dt

    def draw(self, surf):
        for y in range(0, self.h, 4):            # dusk gradient
            k = y / self.h
            pygame.draw.rect(surf, (int(18 + 20 * k), int(20 + 12 * k), int(40 + 30 * k)), (0, y, self.w, 4))
        title = font(40).render("Games", True, (250, 236, 200))
        surf.blit(title, title.get_rect(midtop=(self.w // 2, 22)))
        for name, r, b in self.cards:
            g = self.games[name]
            lift = -3 if b.down else 0
            card = r.move(0, lift)
            pygame.draw.rect(surf, (0, 0, 0), card.move(0, 6), border_radius=18)
            pygame.draw.rect(surf, g.COLOR if hasattr(g, "COLOR") else (70, 80, 120), card, border_radius=18)
            surf.blit(self.icons[name], (card.x + 10, card.y + 10))
            label = font(26).render(getattr(g, "TITLE", name), True, (255, 255, 255))
            surf.blit(label, label.get_rect(midbottom=(card.centerx, card.bottom - 12)))
        hint = font(14, False).render("tap a game  ·  hold MENU at the top to come back here", True, (190, 190, 210))
        surf.blit(hint, hint.get_rect(midbottom=(self.w // 2, self.h - 8)))


# ------------------------------------------------------------------ runner
def build(name, games):
    w, h = CANVAS
    if name == MENU:
        return Menu(w, h, games)
    mod = load(name)                             # fresh from disk: picks up code edits
    return mod.Game(w, h)


def scripted_fingers(frame, script):
    """--shot helper: {finger id: (x, y)} from a list of (start, end, id, x0, y0, x1, y1)."""
    out = {}
    for f0, f1, fid, x0, y0, x1, y1 in script:
        if f0 <= frame < f1:
            t = (frame - f0) / max(1, f1 - f0 - 1)
            out[fid] = (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
    return out


def _stop(signum, frame):
    raise KeyboardInterrupt


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("game", nargs="?", default=MENU)
    ap.add_argument("--window", action="store_true", help="run in a window (laptop)")
    ap.add_argument("--zoom", type=float, default=1.0, help="window size multiplier (2 = full 1600x720)")
    ap.add_argument("--fb", action="store_true", help="draw straight to /dev/fb0 (no GPU)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--fps", action="store_true", help="show frame rate")
    ap.add_argument("--shot", help="headless: save a screenshot here after --frames frames")
    ap.add_argument("--frames", type=int, default=180)
    args = ap.parse_args()

    games = list_games()
    if args.list:
        for n, g in games.items():
            print(f"{n:10s} {getattr(g, 'TITLE', n)}")
        return
    if args.game != MENU and args.game not in games:
        sys.exit(f"unknown game '{args.game}'. Try: {', '.join(games)}")

    signal.signal(signal.SIGTERM, _stop)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _stop)
    pygame.init()
    window = args.window or not sys.platform.startswith("linux")
    headless = bool(args.shot)
    disp = Display(window and not headless, "fb" if args.fb else "auto", args.zoom, headless)
    touch = None
    if disp.kind in ("gpu", "fb"):
        touch = EvdevTouch.open(*CANVAS, name=None)      # scaled straight to canvas pixels
        if touch:
            print(f"Touch: {touch.dev.name} (raw {touch.raw[0]}x{touch.raw[1]})")
        else:
            print("No touchscreen found: is the USB-C touch cable in the Pi's USB data port?")

    current = args.game
    game = build(current, games)
    shell = Controls()                                   # the runner's own controls (home tab)
    want_home = []
    home = shell.add(HoldButton((CANVAS[0] // 2 - 26, 0, 52, 20), "MENU", hold_secs=1.0,
                                on_hold=lambda: want_home.append(1)))
    home.visible = current != MENU
    home.enabled = current != MENU
    script = getattr(game, "DEMO_TOUCHES", []) if headless else []
    clock = pygame.time.Clock()
    acc, frame, mouse_down = 0.0, 0, False
    fps_font = font(13, False)
    try:
        while True:
            ms = clock.tick(0 if headless else 60)
            acc += STEP if headless else min(ms / 1000, STEP * MAX_STEPS)

            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    return
                if e.type == pygame.KEYDOWN and e.key in (pygame.K_ESCAPE, pygame.K_q):
                    return
                if e.type == pygame.KEYDOWN and e.key == pygame.K_h:
                    want_home.append(1)
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    mouse_down = True
                elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                    mouse_down = False

            if touch:
                touch.events()
                fingers = dict(touch.fingers)
            elif headless:
                fingers = scripted_fingers(frame, script)
            elif mouse_down:
                mx, my = pygame.mouse.get_pos()
                fingers = {0: (mx / disp.zoom, my / disp.zoom)}
            else:
                fingers = {}

            free = shell.feed(fingers)                   # home tab first
            game.fingers(free)
            shell.tick(STEP)

            while acc >= STEP:
                game.update(STEP)
                acc -= STEP

            nxt = getattr(game, "launch", None)
            if want_home and current != MENU:
                nxt = MENU
            want_home.clear()
            if nxt:
                try:
                    game = build(nxt, games)
                    current = nxt
                except Exception:
                    traceback.print_exc()
                    game, current = build(MENU, games), MENU
                home.visible = home.enabled = current != MENU
                shell = Controls()
                shell.add(home)

            game.draw(disp.canvas)
            shell.draw(disp.canvas)
            if args.fps:
                img = fps_font.render(f"{clock.get_fps():3.0f} fps", True, (230, 230, 230), (0, 0, 0))
                disp.canvas.blit(img, (4, CANVAS[1] - 18))
            disp.present(getattr(game, "SMOOTH", True))

            frame += 1
            if headless and frame >= args.frames:
                pygame.image.save(disp.canvas, args.shot)
                print(f"saved {args.shot}")
                return
    except KeyboardInterrupt:
        pass
    finally:
        disp.close()
        pygame.quit()


if __name__ == "__main__":
    main()
