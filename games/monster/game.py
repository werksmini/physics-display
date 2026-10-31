"""Monster Mash-up: draw a creature together, one slice each, without peeking.

A digital "exquisite corpse". Artist 1 draws the head and lets some lines run off
the bottom edge. The screen covers itself; artist 2 sees only a thin strip of the
head's bottom edge (with markers where lines cross it) and draws the body, and so
on. At the end the whole monster is revealed top to bottom, named and saved.

Screens (self.state): setup -> cover -> draw -> cover -> draw ... -> reveal -> setup
                                                                       +-> gallery
Touches: fingers() gets where every finger is now; trails() gets every point each
finger passed through since the last frame, so strokes stay smooth even at 10 fps.
"""
import math
import random
import time
from pathlib import Path

import pygame

from playground.ui import Controls, Button, HoldButton, font, text, rounded

W, H = 800, 360
SW, SH = 440, 290                 # one slice of the monster (the paper you draw on)
PEEK = 26                         # how much of the previous slice the next artist sees
AX, AY = (W - SW) // 2, 24 + PEEK  # where the paper sits on the screen
AREA = pygame.Rect(AX, AY, SW, SH)

PAPER = (250, 246, 236)
TABLE = (38, 32, 56)
PANEL = (52, 45, 76)
INK = (245, 242, 235)
DIM = (190, 182, 210)
GOOD = (120, 220, 140)
WARN = (255, 190, 90)
COLORS = [(30, 28, 34), (222, 56, 56), (245, 140, 40), (250, 205, 50), (70, 175, 80),
          (50, 120, 230), (150, 80, 200), (130, 85, 50)]
SIZES = [3, 7, 14]
ERASER = None                     # the ninth swatch

SLICES = {3: ["Head", "Body", "Legs"], 4: ["Head", "Body", "Legs", "Feet"]}
TIPS = {
    "Head": "Draw a head. Let the neck (or hair, or tentacles) run off the bottom edge.",
    "Body": "Join up to the marks at the top. Arms, belly, wings: anything! Let the waist run off the bottom.",
    "Legs": "Join up to the marks at the top and give it legs.",
    "Feet": "Join up to the marks and finish it off: feet, claws, wheels, roots...",
}
THEMES = ["anything goes", "lives at the bottom of the sea", "is secretly a kitchen appliance",
          "guards a castle", "just woke up from a very long nap", "is made of fruit",
          "came from outer space", "is a very good dog", "runs a small bakery",
          "is scared of mice", "has far too many eyes", "won a dance contest"]
GALLERY = Path(__file__).resolve().parent / "gallery"


def wrap(string, size, width):
    """Break a string into lines that fit `width` pixels at font `size`."""
    f, lines, line = font(size, False), [], ""
    for word in string.split():
        trial = f"{line} {word}".strip()
        if f.size(trial)[0] <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + ([line] if line else [])


def monster_name(rng=random):
    first = ["Glorp", "Snag", "Wib", "Mun", "Blort", "Fizz", "Grum", "Squee", "Tod", "Zan", "Plonk", "Quib"]
    mid = ["a", "o", "i", "u", "ble", "dle", "ster", ""]
    end = ["saurus", "tron", "wump", "gle", "nugget", "ella", "zilla", "pants", "mungus", "bert"]
    title = ["Magnificent", "Unlikely", "Slightly Damp", "Ever-Hungry", "Very Polite", "Wobbly",
             "Terrible", "Fabulous", "Sleepy", "Unstoppable"]
    return f"{rng.choice(first)}{rng.choice(mid)}{rng.choice(end)} the {rng.choice(title)}"


def edge_runs(sheet):
    """Where ink crosses the bottom edge of a slice: [(x centre, colour), ...].
    Looks at the last 3 rows of pixels and groups neighbouring inked columns."""
    import numpy as np
    px = pygame.surfarray.pixels3d(sheet)            # shape (width, height, 3), no copy
    rows = px[:, SH - 3:SH, :].astype(int)
    del px                                           # unlock the surface
    inked = (abs(rows - PAPER).sum(axis=2) > 60)     # (width, 3) True where not paper
    cols = inked.any(axis=1)
    runs, start = [], None
    for x in range(len(cols) + 1):
        on = x < len(cols) and cols[x]
        if on and start is None:
            start = x
        elif not on and start is not None:
            cx = (start + x - 1) // 2
            y = SH - 3 + int(inked[cx].argmax())
            runs.append((cx, tuple(sheet.get_at((cx, y)))[:3]))
            start = None
    return runs


class Game:
    TITLE = "Monster Mash-up"
    COLOR = (150, 70, 120)
    SMOOTH = True

    @staticmethod
    def icon(surf):
        """Menu card picture: a monster in three mismatched slices."""
        w, h = surf.get_size()
        surf.fill(PAPER)
        cx, s = w // 2, h / 3
        pygame.draw.circle(surf, COLORS[5], (cx, int(s * 0.55)), int(s * 0.42), 3)       # head
        pygame.draw.circle(surf, COLORS[0], (cx - 9, int(s * 0.5)), 4)
        pygame.draw.circle(surf, COLORS[0], (cx + 9, int(s * 0.5)), 4)
        pygame.draw.polygon(surf, COLORS[2], [(cx - 30, s), (cx + 30, s), (cx + 18, 2 * s), (cx - 18, 2 * s)], 3)
        pygame.draw.line(surf, COLORS[2], (cx - 30, s * 1.2), (cx - 55, s * 0.9), 3)    # arms
        pygame.draw.line(surf, COLORS[2], (cx + 30, s * 1.2), (cx + 55, s * 1.5), 3)
        for dx in (-14, 0, 14):                                                          # three legs
            pygame.draw.line(surf, COLORS[4], (cx + dx, 2 * s), (cx + dx * 2, h - 8), 3)
        for y in (s, 2 * s):
            pygame.draw.line(surf, (200, 190, 175), (8, y), (w - 8, y), 1)

    def __init__(self, w, h):
        self.n = 3
        self.theme = THEMES[0]
        self.dirty = True
        self.last_fingers = {}
        self.stale = set()            # fingers already down when the screen changed: ignored
        self.active = {}              # finger id -> the stroke it is drawing
        self.ignored = set()          # fingers that started outside the paper
        self.saved_path = None
        GALLERY.mkdir(exist_ok=True)
        self._enter("setup")

    # ------------------------------------------------------------ screens
    def _enter(self, state):
        """Switch screens: build that screen's buttons from scratch."""
        self.state = state
        self.ui = Controls()
        self.holds = []
        self.stale = set(self.last_fingers)
        self.active, self.ignored = {}, set()
        self.dirty = True
        getattr(self, f"_build_{state}")()

    def _build_setup(self):
        self.count_btns = {}
        for i, n in enumerate((3, 4)):
            self.count_btns[n] = self.ui.add(Button((300 + i * 112, 158, 96, 52), f"{n} artists",
                                                    on_tap=lambda n=n: self._set_count(n)))
            self.count_btns[n].draw = lambda surf: None          # drawn by _draw_setup
        self.ui.add(Button((612, 234, 110, 40), "Shuffle", on_tap=self._shuffle))
        self.ui.add(Button((W // 2 - 120, 292, 240, 52), "Start drawing", color=(170, 70, 120),
                           on_tap=self._start))
        self.ui.add(Button((660, 306, 120, 38), "Gallery", on_tap=lambda: self._enter("gallery")))

    def _build_cover(self):
        b = self.ui.add(HoldButton((W // 2 - 130, 250, 260, 64), "Hold to start", color=(170, 70, 120),
                                   hold_secs=0.7, on_hold=lambda: self._enter("draw")))
        self.holds.append(b)

    def _build_draw(self):
        self.tool_btns = []
        for i in range(len(COLORS) + 1):                      # 8 colours + eraser, 3 x 3
            r = pygame.Rect(20 + (i % 3) * 48, 56 + (i // 3) * 48, 40, 40)
            c = COLORS[i] if i < len(COLORS) else ERASER
            b = self.ui.add(Button(r, "", on_tap=lambda c=c: self._pick_color(c)))
            b.draw = lambda surf: None
            self.tool_btns.append((r, c))
        self.size_btns = []
        for i, s in enumerate(SIZES):
            r = pygame.Rect(20 + i * 48, 208, 40, 40)
            b = self.ui.add(Button(r, "", on_tap=lambda s=s: self._pick_size(s)))
            b.draw = lambda surf: None
            self.size_btns.append((r, s))
        self.ui.add(Button((20, 270, 66, 44), "Undo", on_tap=self._undo))
        self.holds.append(self.ui.add(HoldButton((92, 270, 64, 44), "Clear", hold_secs=0.8,
                                                 on_hold=self._clear)))
        self.holds.append(self.ui.add(HoldButton((644, 284, 140, 54), "Done", color=(70, 140, 90),
                                                 hold_secs=0.5, on_hold=self._finish_slice)))
        self._bg = self._draw_background()

    def _build_reveal(self):
        self.reveal_t = 0.0
        self.reveal_btns = [
            self.ui.add(Button((420, 292, 150, 48), "Play again", color=(170, 70, 120),
                               on_tap=lambda: self._enter("setup"))),
            self.ui.add(Button((582, 292, 110, 48), "Gallery", on_tap=lambda: self._enter("gallery")))]
        for b in self.reveal_btns:                          # appear once the monster is revealed
            b.visible = b.enabled = False

    def _build_gallery(self):
        self.ui.add(Button((680, 10, 104, 36), "Back", on_tap=lambda: self._enter("setup")))
        files = sorted(GALLERY.glob("*.png"), reverse=True)[:4]
        self.gallery = []
        for f in files:
            try:
                img = pygame.image.load(str(f))
            except pygame.error:
                continue
            k = min(170 / img.get_width(), 262 / img.get_height())
            img = pygame.transform.smoothscale(img, (int(img.get_width() * k), int(img.get_height() * k)))
            name = f.stem.split("_", 1)[-1].replace("-", " ")
            self.gallery.append((img, name))

    # ------------------------------------------------------------ setup actions
    def _set_count(self, n):
        self.n = n
        self.dirty = True

    def _shuffle(self):
        self.theme = random.choice([t for t in THEMES if t != self.theme])
        self.dirty = True

    def _start(self):
        self.slice = 0
        self.sheets = [pygame.Surface((SW, SH)) for _ in range(self.n)]
        for s in self.sheets:
            s.fill(PAPER)
        self.strokes = [[] for _ in range(self.n)]
        self.color, self.size = COLORS[0], SIZES[1]
        self.peek_marks = []
        self.my_marks = []
        self._enter("cover")

    # ------------------------------------------------------------ drawing tools
    def _pick_color(self, c):
        self.color = c
        self.dirty = True

    def _pick_size(self, s):
        self.size = s
        self.dirty = True

    def _undo(self):
        if self.strokes[self.slice]:
            self.strokes[self.slice].pop()
            self._redraw_sheet()

    def _clear(self):
        self.strokes[self.slice] = []
        self._redraw_sheet()

    def _redraw_sheet(self):
        """Paint the current slice again from its stroke list (after undo / clear)."""
        sheet = self.sheets[self.slice]
        sheet.fill(PAPER)
        for st in self.strokes[self.slice]:
            pts = st["pts"]
            self._dot(sheet, st, pts[0])
            for a, b in zip(pts, pts[1:]):
                self._segment(sheet, st, a, b)
        self._update_marks()
        self.dirty = True

    @staticmethod
    def _ink(st):
        return PAPER if st["color"] is ERASER else st["color"]

    def _dot(self, sheet, st, p):
        r = max(1, st["w"] // 2)
        pygame.draw.circle(sheet, self._ink(st), (int(p[0]), int(p[1])), r)

    def _segment(self, sheet, st, a, b):
        """One piece of a stroke: a thick line plus a round end, so joints stay round."""
        c = self._ink(st)
        pygame.draw.line(sheet, c, a, b, st["w"])
        pygame.draw.circle(sheet, c, (int(b[0]), int(b[1])), max(1, st["w"] // 2))

    def _update_marks(self):
        """How many lines reach this slice's bottom edge (shown in the side panel)."""
        self.my_marks = edge_runs(self.sheets[self.slice]) if self.slice < self.n - 1 else []

    def _finish_slice(self):
        if self.slice < self.n - 1:
            self.peek_marks = edge_runs(self.sheets[self.slice])
            self.slice += 1
            self.my_marks = []
            self._enter("cover")
        else:
            self._reveal()

    # ------------------------------------------------------------ the reveal
    def _reveal(self):
        self.whole = pygame.Surface((SW, SH * self.n))
        for i, s in enumerate(self.sheets):
            self.whole.blit(s, (0, i * SH))
        self.name = monster_name()
        self.fit = 336 / self.whole.get_height()
        self.small = pygame.transform.smoothscale(
            self.whole, (int(SW * self.fit), int(self.whole.get_height() * self.fit)))
        self.saved_path = self._save()
        self._enter("reveal")

    def _save(self):
        """Write the monster, with its name underneath, to games/monster/gallery/."""
        m = 24
        img = pygame.Surface((SW + 2 * m, self.whole.get_height() + 2 * m + 40))
        img.fill(PAPER)
        img.blit(self.whole, (m, m))
        label = font(22).render(self.name, True, (60, 50, 70))
        img.blit(label, label.get_rect(midbottom=(img.get_width() // 2, img.get_height() - 16)))
        safe = "".join(ch if ch.isalnum() else "-" for ch in self.name)
        path = GALLERY / f"{time.strftime('%Y%m%d-%H%M%S')}_{safe}.png"
        try:
            pygame.image.save(img, str(path))
            return path
        except (pygame.error, OSError):
            return None

    REVEAL_HOLD, ZOOM = 0.7, 1.1

    def _reveal_times(self):
        pan = 1.0 * self.n
        return self.REVEAL_HOLD, self.REVEAL_HOLD + pan, self.REVEAL_HOLD + pan + self.ZOOM

    # ------------------------------------------------------------ input
    def fingers(self, fingers):
        self.last_fingers = dict(fingers)
        self.stale &= set(fingers)                           # forget stale fingers once lifted
        live = {k: v for k, v in fingers.items() if k not in self.stale}
        before = len(self.ui.owner)
        self.ui.feed(live)
        if len(self.ui.owner) != before:
            self.dirty = True                                # a button went down or up
        for fid in [f for f in self.active if f not in fingers]:      # strokes that ended
            del self.active[fid]
            self._update_marks()
            self.dirty = True
        self.ignored &= set(fingers)

    def trails(self, trails):
        if self.state != "draw":
            return
        sheet = self.sheets[self.slice]
        for fid, pts in trails.items():
            if fid in self.stale or fid in self.ignored or not pts:
                continue
            local = [(x - AX, y - AY) for x, y in pts]
            st = self.active.get(fid)
            if st is None:
                if not AREA.collidepoint(pts[0]) or self.ui.owner.get(fid):
                    self.ignored.add(fid)                    # started on a button or off the paper
                    continue
                w = self.size * 3 if self.color is ERASER else self.size
                st = {"color": self.color, "w": w, "pts": [local[0]]}
                self.strokes[self.slice].append(st)
                self.active[fid] = st
                self._dot(sheet, st, local[0])
                local = local[1:]
            for p in local:
                if p != st["pts"][-1]:
                    self._segment(sheet, st, st["pts"][-1], p)
                    st["pts"].append(p)
            self.dirty = True

    # ------------------------------------------------------------ update / draw
    @property
    def idle(self):
        animating = self.state == "reveal" and self.reveal_t < self._reveal_times()[2] + 0.5
        return not self.dirty and not animating and not any(b.held for b in self.holds)

    def update(self, dt):
        self.ui.tick(dt)
        if self.state == "reveal":
            self.reveal_t += dt
            if self.reveal_t >= self._reveal_times()[2]:
                for b in self.reveal_btns:
                    b.visible = b.enabled = True

    def draw(self, surf):
        self.dirty = False
        getattr(self, f"_draw_{self.state}")(surf)
        self.ui.draw(surf)

    def _title(self, surf, s, y, size=44, color=(255, 214, 120)):
        img = text(size, s, color)
        surf.blit(img, img.get_rect(midtop=(W // 2, y)))

    def _draw_setup(self, surf):
        surf.fill(TABLE)
        self._title(surf, "Monster Mash-up", 26)
        self._title(surf, "Draw a creature together, one slice each, without peeking.", 88, 17, DIM)
        self._title(surf, "How many artists?", 128, 17, INK)
        for n, b in self.count_btns.items():
            on = n == self.n
            rounded(surf, (170, 70, 120) if on else PANEL, b.rect, 14)
            rounded(surf, (255, 255, 255, 140) if on else (255, 255, 255, 60), b.rect, 14, 2)
            img = text(19, b.label, INK)
            surf.blit(img, img.get_rect(center=b.rect.center))
        box = pygame.Rect(80, 228, 640, 52)
        rounded(surf, PANEL, box, 12)
        lines = wrap(f"Theme: a monster that {self.theme}" if self.theme != THEMES[0]
                     else "Theme: anything goes", 17, 500)
        for i, line in enumerate(lines[:2]):
            img = text(17, line, INK, bold=False)
            surf.blit(img, (98, box.y + (16 if len(lines) == 1 else 6) + i * 21))

    def _draw_cover(self, surf):
        surf.fill((22, 20, 32))
        name = SLICES[self.n][self.slice]
        self._title(surf, f"Artist {self.slice + 1} of {self.n}", 40, 22, DIM)
        self._title(surf, f"You're drawing the {name.upper()}", 76, 40)
        lines = ["Everyone else: look away!" if self.slice else "Everyone else: no peeking!",
                 "You'll only see the bottom edge of the last slice." if self.slice
                 else "Start at the top of the creature."]
        for i, line in enumerate(lines):
            self._title(surf, line, 146 + i * 28, 19, INK)
        if self.theme != THEMES[0]:
            self._title(surf, f"Theme: a monster that {self.theme}", 212, 16, DIM)

    def _draw_background(self):
        bg = pygame.Surface((W, H))
        bg.fill(TABLE)
        rounded(bg, PANEL, (10, 46, 158, 304), 14)                  # toolbar
        rounded(bg, PANEL, (632, 46, 160, 304), 14)                 # side panel
        pygame.draw.rect(bg, (16, 12, 26), AREA.move(4, 5), border_radius=4)    # paper shadow
        return bg

    def _draw_draw(self, surf):
        surf.blit(self._bg, (0, 0))
        surf.blit(self.sheets[self.slice], AREA.topleft)
        strip = pygame.Rect(AX, AY - PEEK, SW, PEEK)
        if self.slice:                                   # the previous artist's bottom edge
            prev = self.sheets[self.slice - 1]
            surf.blit(prev, strip.topleft, area=pygame.Rect(0, SH - PEEK, SW, PEEK))
            shade = pygame.Surface(strip.size, pygame.SRCALPHA)
            shade.fill((40, 30, 70, 50))
            surf.blit(shade, strip.topleft)
            for x, c in self.peek_marks:                 # markers where lines continue
                px = AX + x
                pygame.draw.polygon(surf, (255, 255, 255), [(px - 8, AY + 1), (px + 8, AY + 1), (px, AY + 12)])
                pygame.draw.polygon(surf, c, [(px - 6, AY + 2), (px + 6, AY + 2), (px, AY + 10)])
        else:
            img = text(13, "top of the monster", DIM, bold=False)
            surf.blit(img, img.get_rect(center=strip.center))
        for x in range(AX, AX + SW, 12):                 # dashed seam between strip and paper
            pygame.draw.line(surf, (150, 140, 190), (x, AY - 1), (x + 6, AY - 1), 2)
        if self.slice < self.n - 1:                      # the zone the next artist will see
            zone = pygame.Surface((SW, PEEK), pygame.SRCALPHA)
            zone.fill((110, 130, 255, 26))
            surf.blit(zone, (AX, AY + SH - PEEK))
            for x in range(AX, AX + SW, 12):
                pygame.draw.line(surf, (150, 160, 240), (x, AY + SH - PEEK), (x + 6, AY + SH - PEEK), 1)
        self._draw_tools(surf)
        self._draw_side(surf)

    def _draw_tools(self, surf):
        for r, c in self.tool_btns:
            if c is ERASER:
                pygame.draw.rect(surf, PAPER, r, border_radius=8)
                pygame.draw.line(surf, (200, 80, 80), (r.x + 9, r.bottom - 9), (r.right - 9, r.y + 9), 3)
                img = text(11, "erase", (90, 80, 90), bold=False)
                surf.blit(img, img.get_rect(midbottom=(r.centerx, r.bottom - 1)))
            else:
                pygame.draw.rect(surf, c, r, border_radius=8)
            if c is self.color:
                pygame.draw.rect(surf, (255, 255, 255), r.inflate(6, 6), 3, border_radius=10)
        for r, s in self.size_btns:
            on = s == self.size
            pygame.draw.rect(surf, (90, 80, 120) if on else (70, 62, 98), r, border_radius=8)
            if on:
                pygame.draw.rect(surf, (255, 255, 255), r.inflate(6, 6), 3, border_radius=10)
            ink = PAPER if self.color is ERASER else self.color
            pygame.draw.circle(surf, PAPER, r.center, s // 2 + 3)
            pygame.draw.circle(surf, ink if ink != PAPER else (120, 120, 120), r.center, max(2, s // 2))

    def _draw_side(self, surf):
        name = SLICES[self.n][self.slice]
        x = 646
        surf.blit(text(12, f"ARTIST {self.slice + 1} OF {self.n}", DIM), (x, 58))
        surf.blit(text(30, name, (255, 214, 120)), (x, 74))
        for i, line in enumerate(wrap(TIPS[name], 13, 134)[:6]):
            surf.blit(text(13, line, INK, bold=False), (x, 116 + i * 17))
        if self.slice < self.n - 1:
            k = len(self.my_marks)
            ok = k > 0
            pygame.draw.circle(surf, GOOD if ok else WARN, (x + 6, 244), 5)
            msg = (f"{k} line{'s' if k != 1 else ''} reach" + ("" if k != 1 else "es") + " the bottom") if ok \
                else "Nothing reaches the bottom edge yet"
            for i, line in enumerate(wrap(msg, 13, 118)[:2]):
                surf.blit(text(13, line, GOOD if ok else WARN, bold=False), (x + 16, 236 + i * 16))

    def _draw_reveal(self, surf):
        surf.fill(TABLE)
        t0, t1, t2 = self._reveal_times()
        t = self.reveal_t
        H_ALL, VIEW_Y, VIEW_H = self.whole.get_height(), 12, 336
        ease = lambda u: 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, u)))
        if t < t2:                                       # pan down at full size, then zoom out
            if t < t1:
                off = ease((t - t0) / (t1 - t0)) * (H_ALL - VIEW_H)
                rect = pygame.Rect(W // 2 - SW // 2, VIEW_Y, SW, VIEW_H)
                pygame.draw.rect(surf, (16, 12, 26), rect.move(4, 5))
                surf.set_clip(rect)
                surf.blit(self.whole, (rect.x, VIEW_Y - off))
                surf.set_clip(None)
            else:
                e = ease((t - t1) / (t2 - t1))
                s = 1 + (self.fit - 1) * e
                img = pygame.transform.smoothscale(self.whole, (int(SW * s), int(H_ALL * s)))
                cx = W // 2 + (230 - W // 2) * e
                y = VIEW_Y + VIEW_H - H_ALL * s
                surf.set_clip(pygame.Rect(0, VIEW_Y, W, VIEW_H))
                surf.blit(img, (cx - img.get_width() / 2, y))
                surf.set_clip(None)
            return
        r = self.small.get_rect(center=(230, VIEW_Y + VIEW_H // 2))
        pygame.draw.rect(surf, (16, 12, 26), r.move(4, 5))
        surf.blit(self.small, r)
        a = min(1.0, (t - t2) / 0.5)
        col = lambda c: tuple(int(TABLE[i] + (c[i] - TABLE[i]) * a) for i in range(3))
        surf.blit(text(16, "Meet", col(DIM)), (420, 60))
        for i, line in enumerate(wrap(self.name, 34, 360)[:3]):
            surf.blit(text(34, line, col((255, 214, 120))), (420, 82 + i * 42))
        if self.theme != THEMES[0]:
            for i, line in enumerate(wrap(f"a monster that {self.theme}", 15, 360)[:2]):
                surf.blit(text(15, line, col(INK), bold=False), (420, 214 + i * 19))
        saved = f"Saved to games/monster/gallery/" if self.saved_path else "Couldn't save the picture"
        surf.blit(text(12, saved, col(DIM), bold=False), (420, 262))

    def _draw_gallery(self, surf):
        surf.fill(TABLE)
        surf.blit(text(28, "Gallery", (255, 214, 120)), (24, 12))
        if not self.gallery:
            self._title(surf, "No monsters yet. Go and draw one!", 160, 19, INK)
            return
        for i, (img, name) in enumerate(self.gallery):
            cx = 104 + i * 180
            r = img.get_rect(midtop=(cx, 52))
            surf.blit(img, r)
            for j, line in enumerate(wrap(name, 12, 170)[:2]):
                l = text(12, line, INK, bold=False)
                surf.blit(l, l.get_rect(midtop=(cx, r.bottom + 4 + j * 14)))
