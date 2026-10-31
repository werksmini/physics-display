"""Play a whole game of Monster Mash-up with scripted "fingers", no screen needed,
and save a screenshot of every screen. Run from the repo folder:

    python games/monster/selftest.py            # screenshots go to games/monster/shots/

It taps the real buttons and draws through the same fingers()/trails() calls the
touchscreen uses, so if this passes, the game's logic works; what's left to check on
the Pi is how it feels.
"""
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pygame                                        # noqa: E402

pygame.font.init()
pygame.display.init()
pygame.display.set_mode((1, 1))

import importlib.util                                # noqa: E402
spec = importlib.util.spec_from_file_location("monster", Path(__file__).with_name("game.py"))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

OUT = Path(__file__).resolve().parent / "shots"
OUT.mkdir(exist_ok=True)
M.GALLERY = OUT / "gallery"                          # keep test monsters out of the real gallery
STEP = 1 / 60
screen = pygame.Surface((M.W, M.H))


def frame(g, fingers, trails=None):
    """One frame, the way play.py runs it."""
    g.fingers(fingers)
    g.trails(trails if trails is not None else {k: [v] for k, v in fingers.items()})
    g.update(STEP)


def tap(g, rect, fid=90):
    c = rect.center if hasattr(rect, "center") else rect
    frame(g, {fid: c})
    frame(g, {})


def hold(g, rect, secs, fid=91):
    for _ in range(int(secs / STEP) + 2):
        frame(g, {fid: rect.center})
    frame(g, {})


def stroke(g, pts, fid=1, per_frame=6):
    """Drag one finger through pts, delivering several points per frame (like a slow Pi)."""
    for i in range(0, len(pts), per_frame):
        chunk = pts[i:i + per_frame]
        frame(g, {fid: chunk[-1]}, {fid: chunk})
    frame(g, {})


def arc(cx, cy, rx, ry, a0, a1, n=48):
    return [(cx + rx * math.cos(a0 + (a1 - a0) * i / n), cy + ry * math.sin(a0 + (a1 - a0) * i / n))
            for i in range(n + 1)]


def line(x0, y0, x1, y1, n=20):
    return [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n + 1)]


def pick(g, color_index=None, size_index=None):
    if color_index is not None:
        tap(g, g.tool_btns[color_index][0])
    if size_index is not None:
        tap(g, g.size_btns[size_index][0])


def shot(g, name):
    g.draw(screen)
    pygame.image.save(screen, str(OUT / f"{name}.png"))
    print("saved", OUT / f"{name}.png")


def find(g, label):
    return next(b for b in g.ui.items if getattr(b, "label", None) == label)


def main():
    g = M.Game(M.W, M.H)
    assert g.state == "setup"
    tap(g, g.count_btns[3].rect)
    tap(g, find(g, "Shuffle").rect)
    shot(g, "1-setup")
    tap(g, find(g, "Start drawing").rect)
    assert g.state == "cover", g.state
    shot(g, "2-cover")
    hold(g, find(g, "Hold to start").rect, 0.8)
    assert g.state == "draw", g.state

    # --- artist 1: the head (y 50..340 is the paper)
    pick(g, 4, 1)
    stroke(g, arc(400, 165, 92, 80, 0, 2 * math.pi, 64))          # head
    stroke(g, arc(368, 150, 14, 14, 0, 2 * math.pi, 20))          # eyes
    stroke(g, arc(432, 150, 14, 14, 0, 2 * math.pi, 20))
    pick(g, 0, 2)
    stroke(g, line(368, 152, 368, 153, 1))
    stroke(g, line(432, 152, 432, 153, 1))
    pick(g, 1, 1)
    stroke(g, arc(400, 185, 40, 22, 0.2, math.pi - 0.2, 24))      # grin
    pick(g, 6, 1)
    stroke(g, line(340, 100, 300, 60) + line(300, 60, 350, 92))   # horns
    stroke(g, line(460, 100, 500, 60) + line(500, 60, 450, 92))
    pick(g, 4, 1)
    stroke(g, line(372, 240, 362, 346))                           # neck, off the bottom edge
    stroke(g, line(428, 240, 438, 346))
    assert len(g.my_marks) == 2, g.my_marks
    hold(g, find(g, "Done").rect, 0.6)
    assert g.state == "cover" and g.slice == 1

    # --- artist 2: the body
    hold(g, find(g, "Hold to start").rect, 0.8)
    assert [round(x) for x, _ in g.peek_marks] and len(g.peek_marks) == 2, g.peek_marks
    left, right = (M.AX + g.peek_marks[0][0], M.AX + g.peek_marks[1][0])
    pick(g, 2, 1)
    stroke(g, line(left, 52, left - 70, 130) + arc(400, 210, 110, 90, math.pi * 1.1, math.pi * 1.9, 30)[::-1][:1]
           + line(left - 70, 130, 330, 346))
    stroke(g, line(right, 52, right + 70, 130) + line(right + 70, 130, 470, 346))
    stroke(g, line(left - 60, 140, 230, 90) + line(230, 90, 205, 70))      # arms
    stroke(g, line(right + 60, 140, 570, 190) + line(570, 190, 600, 175))
    pick(g, 3, 2)
    stroke(g, arc(400, 220, 34, 34, 0, 2 * math.pi, 36))                   # a belly spot
    shot(g, "3-draw-body")
    # undo + redo the spot, to exercise undo
    n = len(g.strokes[1])
    tap(g, find(g, "Undo").rect)
    assert len(g.strokes[1]) == n - 1
    stroke(g, arc(400, 220, 34, 34, 0, 2 * math.pi, 36))
    hold(g, find(g, "Done").rect, 0.6)

    # --- artist 3: the legs
    hold(g, find(g, "Hold to start").rect, 0.8)
    marks = [M.AX + x for x, _ in g.peek_marks]
    assert len(marks) == 2, g.peek_marks
    pick(g, 5, 1)
    a, b = marks
    stroke(g, line(a, 52, a - 20, 200) + line(a - 20, 200, a - 10, 300) + line(a - 10, 300, a - 60, 318))
    stroke(g, line(a + 30, 60, a + 25, 200) + line(a + 25, 200, a + 35, 300) + line(a + 35, 300, a - 10, 300))
    stroke(g, line(b, 52, b + 20, 200) + line(b + 20, 200, b + 10, 300) + line(b + 10, 300, b + 60, 318))
    stroke(g, line(b - 30, 60, b - 25, 200) + line(b - 25, 200, b - 35, 300) + line(b - 35, 300, b + 10, 300))
    stroke(g, line(a + 30, 60, b - 30, 60))
    shot(g, "4-draw-legs")
    hold(g, find(g, "Done").rect, 0.6)

    # --- the reveal
    assert g.state == "reveal" and g.saved_path and g.saved_path.exists(), g.saved_path
    t0, t1, t2 = g._reveal_times()
    while g.reveal_t < (t0 + t1) / 2:
        frame(g, {})
    shot(g, "5-reveal-pan")
    while g.reveal_t < t2 + 0.6:
        frame(g, {})
    assert g.idle
    shot(g, "6-reveal")
    tap(g, find(g, "Gallery").rect)
    assert g.state == "gallery" and g.gallery
    shot(g, "7-gallery")
    tap(g, find(g, "Back").rect)
    assert g.state == "setup"
    print("all checks passed")


if __name__ == "__main__":
    main()
