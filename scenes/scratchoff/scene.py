"""Scratch-off tickets at the corner store: how many cards before you go bust?

You start with $20. Each card costs $5. Scratch the six silver fields with
your finger; if three amounts match, you win that amount. Scratching leaves
silver dust on the ticket, and you can sweep it off with your finger.
When every field is revealed you see whether you won; tap for the next card.
When you can't afford another card, the run is over: you see how many cards
you scratched, how that ranks against previous runs, and it starts again.

How it works:
- The silver coating is a grid of "coating left" values over the ticket.
  Your finger's path is a line segment each frame; every cell within reach of
  the segment loses some coating, scaled by a fixed random roughness map, so
  the scratched edges look ragged and take a couple of passes.
- Coating you remove turns into dust particles. They slide with friction, and
  a moving finger sweeps the ones under it along. Dust is drawn by counting
  particles per cell, so it piles up visibly where it collects.
- A field counts as revealed once most of its coating is gone (Reveal at).
- Results are saved in ~/.config/physics-display/scratchoff_scores.json.
"""
import json
import math
import time
from pathlib import Path

import numpy as np
import pygame

from playground.scene import BaseScene, Param

SCORES = Path.home() / ".config" / "physics-display" / "scratchoff_scores.json"
TX, TY, TW, TH = 40, 132, 400, 428            # ticket on the counter (screen px)
FIELD_W, FIELD_H, GAP = 110, 100, 15
FIELDS = [(20 + c * (FIELD_W + GAP), 122 + r * (FIELD_H + 14), FIELD_W, FIELD_H)
          for r in range(2) for c in range(3)]  # relative to the ticket
CELL = 2                                       # coating grid cell size (px)
VALUES = [5, 10, 20, 50, 100, 500]
WORDS = {5: "FIVE", 10: "TEN", 20: "TWENTY", 50: "FIFTY", 100: "ONE HUN", 500: "FIV HUN"}
WIN_ODDS = {5: 0.12, 10: 0.07, 20: 0.035, 50: 0.012, 100: 0.004, 500: 0.0008}   # per card
TEASE = [0.30, 0.25, 0.18, 0.13, 0.09, 0.05]   # how often each amount shows up as a non-winner
MAX_DUST = 3000

WALL, SHELF = (58, 52, 50), (96, 90, 84)
COUNTER, COUNTER_DARK, COUNTER_LIGHT = (206, 198, 180), (176, 168, 150), (226, 220, 204)
SILVER = (182, 186, 192)
DUST = (132, 134, 142)            # darker than the latex so it shows on white fields


def load_scores():
    try:
        return json.loads(SCORES.read_text())
    except (OSError, ValueError):
        return []


def save_scores(runs):
    try:
        SCORES.parent.mkdir(parents=True, exist_ok=True)
        SCORES.write_text(json.dumps(runs[-200:], indent=1))
    except OSError:
        pass


class Scene(BaseScene):
    TITLE = "Scratch-off at the corner store"
    PREVIEW_AFTER = 1
    PARAMS = [
        Param("start_cash", 20, 5, 100, 5, "Starting cash", reset=True),
        Param("card_price", 5, 1, 20, 1, "Card price"),
        Param("luck", 1.0, 0.2, 3, 0.05, "Luck", help="Scales the odds of winning. 1 = realistic (you lose)."),
        Param("scratch_size", 30, 10, 80, 1, "Scratch size", help="Width of your fingernail, in px."),
        Param("scratch_strength", 0.55, 0.1, 1, 0.05, "Scratch strength", help="Coating removed per pass."),
        Param("dust", 1.0, 0, 3, 0.05, "Dust amount"),
        Param("sweep", 1.0, 0, 3, 0.05, "Sweep strength"),
        Param("reveal_at", 0.7, 0.3, 0.95, 0.05, "Reveal at", help="Fraction scratched that counts as revealed."),
    ]

    # ------------------------------------------------------------------ setup
    def setup(self):
        self.rng = np.random.default_rng()
        self.f_big = pygame.font.Font(None, 66)
        self.f_mid = pygame.font.Font(None, 40)
        self.f_small = pygame.font.Font(None, 26)
        self.f_tiny = pygame.font.Font(None, 18)
        self.bg = self._build_store()
        self.shadow = pygame.Surface((TW, TH), pygame.SRCALPHA)
        pygame.draw.rect(self.shadow, (0, 0, 0, 70), self.shadow.get_rect(), border_radius=10)
        self.rough = self.rng.uniform(0.45, 1.45, (TW // CELL, TH // CELL)).astype(np.float32)
        self.coat_tex = self._build_coating_texture()
        self.coat_surf = pygame.Surface((TW, TH), pygame.SRCALPHA)
        self.dust_surf = pygame.Surface((self.w // CELL, self.h // CELL), pygame.SRCALPHA)
        self.dust_surf.fill((*DUST, 0))
        self.dpos = np.zeros((0, 2), np.float32)
        self.dvel = np.zeros((0, 2), np.float32)
        self.floats = []                      # floating "+$50" / "-$5" texts
        self.finger = None
        self.finger_v = np.zeros(2, np.float32)
        self.down_at = None
        self.t = 0.0
        self._new_run()

    def _new_run(self):
        self.cash = int(self.p.start_cash)
        self.cards = 0
        self.best_win = 0
        self.total_won = 0
        self.rank_info = None
        self._buy_card()

    def _buy_card(self):
        price = int(self.p.card_price)
        self.cash -= price
        self.cards += 1
        self.floats.append([f"-${price}", (220, 70, 60), 330, 600, 0.0])
        self.card_amounts, self.card_prize = self._make_card()
        self.ticket = self._build_ticket(self.card_amounts)
        self.coat = np.zeros((TW // CELL, TH // CELL), np.float32)
        for fx, fy, fw, fh in FIELDS:
            self.coat[fx // CELL:(fx + fw) // CELL, fy // CELL:(fy + fh) // CELL] = 1.0
        self.coat_dirty = True
        inside = ((self.dpos[:, 0] > TX) & (self.dpos[:, 0] < TX + TW) &
                  (self.dpos[:, 1] > TY) & (self.dpos[:, 1] < TY + TH))
        self.dpos, self.dvel = self.dpos[~inside], self.dvel[~inside]   # old card's dust leaves with it
        self.slide = 1.0
        self.state = "scratch"
        self.state_t = 0.0

    def _make_card(self):
        """Decide the outcome first, then lay out six amounts that show it."""
        rng, luck = self.rng, self.p.luck
        prize, roll = 0, rng.random()
        for v in reversed(VALUES):                 # rarest first
            if roll < WIN_ODDS[v] * luck:
                prize = v
                break
            roll -= WIN_ODDS[v] * luck
        counts = {v: 0 for v in VALUES}
        amounts = []
        if prize:
            amounts, counts[prize] = [prize] * 3, 3
        weights = np.array(TEASE)
        while len(amounts) < 6:
            v = int(rng.choice(VALUES, p=weights / weights.sum()))
            if counts[v] < 2:                      # never a second triple
                counts[v] += 1
                amounts.append(v)
        rng.shuffle(amounts)
        return amounts, prize

    # ------------------------------------------------------------------ art
    def _build_store(self):
        rng = np.random.default_rng(4)
        s = pygame.Surface((self.w, self.h))
        s.fill(WALL)
        # fluorescent tube and the back shelves of snacks
        pygame.draw.rect(s, (236, 240, 232), (60, 4, 360, 6), border_radius=3)
        for sy in (34, 70):
            pygame.draw.rect(s, SHELF, (0, sy + 22, 300, 4))
            x = 4
            while x < 290:
                w = int(rng.uniform(8, 18))
                h = int(rng.uniform(14, 22))
                c = tuple(int(v) for v in rng.integers(60, 230, 3))
                pygame.draw.rect(s, c, (x, sy + 22 - h, w, h))
                pygame.draw.rect(s, tuple(min(255, v + 40) for v in c), (x + 2, sy + 22 - h + 3, w - 4, 3))
                x += w + 2
        # ticket dispenser case on the wall: rows of colourful ticket strips
        pygame.draw.rect(s, (30, 30, 34), (306, 16, 92, 92), border_radius=4)
        for i in range(8):
            c = [(232, 70, 90), (250, 200, 60), (70, 180, 220), (120, 210, 120), (200, 120, 230),
                 (250, 140, 60), (90, 120, 240), (240, 240, 240)][i]
            x = 312 + (i % 4) * 21
            y = 22 + (i // 4) * 42
            pygame.draw.rect(s, c, (x, y, 17, 36))
            pygame.draw.line(s, tuple(v // 2 for v in c), (x, y + 18), (x + 16, y + 18))
        # slushie machine (its swirl is animated in draw)
        pygame.draw.rect(s, (40, 42, 48), (404, 12, 72, 100), border_radius=6)
        # counter: speckled laminate with a chrome front edge
        pygame.draw.rect(s, COUNTER, (0, 112, self.w, self.h - 112))
        for _ in range(9000):
            x, y = int(rng.uniform(0, self.w)), int(rng.uniform(116, self.h))
            s.set_at((x, y), COUNTER_DARK if rng.random() < 0.6 else COUNTER_LIGHT)
        pygame.draw.rect(s, (150, 154, 160), (0, 110, self.w, 6))
        pygame.draw.line(s, (220, 224, 230), (0, 111), (self.w, 111))
        # a quarter lying on the counter
        pygame.draw.circle(s, (130, 132, 136), (448, 598), 15)
        pygame.draw.circle(s, (176, 178, 182), (447, 597), 13)
        pygame.draw.circle(s, (150, 152, 156), (447, 597), 9, 1)
        return s

    def _build_ticket(self, amounts):
        t = pygame.Surface((TW, TH), pygame.SRCALPHA)
        for y in range(TH):                                   # blue to purple
            f = y / TH
            c = (int(30 + 70 * f), int(60 - 20 * f), int(150 + 30 * f))
            pygame.draw.line(t, c, (0, y), (TW, y))
        # sunburst behind the title
        cx, cy = TW // 2, 58
        for k in range(24):
            a0 = k * math.pi / 12
            pts = [(cx, cy), (cx + math.cos(a0) * 320, cy + math.sin(a0) * 320),
                   (cx + math.cos(a0 + 0.13) * 320, cy + math.sin(a0 + 0.13) * 320)]
            pygame.draw.polygon(t, (255, 200, 60) if k % 2 else (250, 160, 50), pts)
        pygame.draw.rect(t, (0, 0, 0, 0), (0, 110, TW, TH - 110))
        for y in range(110, TH):
            f = y / TH
            pygame.draw.line(t, (int(30 + 70 * f), int(60 - 20 * f), int(150 + 30 * f)), (0, y), (TW, y))
        self._text(t, "CORNER CASH", self.f_big, (255, 255, 255), (TW // 2 - 22, 44), outline=(120, 20, 60))
        pygame.draw.rect(t, (40, 20, 70), (0, 80, TW, 26))
        self._text(t, "MATCH 3 AMOUNTS, WIN THAT AMOUNT!", self.f_small, (255, 230, 120), (TW // 2, 94))
        pygame.draw.circle(t, (230, 40, 70), (TW - 34, 30), 24)
        pygame.draw.circle(t, (255, 255, 255), (TW - 34, 30), 24, 2)
        self._text(t, f"${int(self.p.card_price)}", self.f_mid, (255, 255, 255), (TW - 34, 31))
        for (fx, fy, fw, fh), v in zip(FIELDS, amounts):
            pygame.draw.rect(t, (250, 248, 238), (fx, fy, fw, fh), border_radius=8)
            col = (200, 30, 50) if v >= 100 else (30, 30, 40)
            self._text(t, f"${v}", self.f_big, col, (fx + fw // 2, fy + fh // 2 - 8))
            self._text(t, WORDS[v], self.f_tiny, (90, 90, 100), (fx + fw // 2, fy + fh - 14))
        self._text(t, "PRIZES  $5  $10  $20  $50  $100  $500", self.f_small, (240, 230, 255), (TW // 2, 362))
        x = 20
        rng = self.rng
        while x < 220:                                        # barcode
            w = int(rng.integers(1, 4))
            pygame.draw.rect(t, (20, 20, 24), (x, 384, w, 26))
            x += w + int(rng.integers(1, 4))
        pygame.draw.rect(t, (250, 250, 250), (16, 380, 210, 34), 0)
        x = 20
        while x < 222:
            w = int(rng.integers(1, 4))
            pygame.draw.rect(t, (20, 20, 24), (x, 383, w, 28))
            x += w + int(rng.integers(1, 4))
        self._text(t, f"No. {rng.integers(100000, 999999)}-{rng.integers(10, 99)}", self.f_tiny, (220, 220, 240), (310, 388))
        self._text(t, "FOR FUN ONLY", self.f_tiny, (220, 220, 240), (310, 406))
        pygame.draw.rect(t, (255, 255, 255), t.get_rect(), 2, border_radius=10)
        mask = pygame.Surface((TW, TH), pygame.SRCALPHA)           # rounded corners
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=10)
        t.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        return t

    def _build_coating_texture(self):
        rng = np.random.default_rng(9)
        n = rng.normal(0, 9, (TW, TH))
        rgb = np.clip(np.array(SILVER)[None, None, :] + n[..., None], 0, 255).astype(np.uint8)
        tex = pygame.Surface((TW, TH), pygame.SRCALPHA)
        pygame.surfarray.blit_array(tex, rgb)
        for (fx, fy, fw, fh) in FIELDS:                        # printed pattern on the latex
            for yy in range(fy + 10, fy + fh, 22):
                for xx in range(fx + 8 + (yy // 22 % 2) * 11, fx + fw - 8, 22):
                    self._text(tex, "$", self.f_small, (156, 160, 168), (xx, yy))
        return tex

    @staticmethod
    def _text(surf, text, font, color, center, outline=None):
        img = font.render(text, True, color)
        r = img.get_rect(center=center)
        if outline:
            o = font.render(text, True, outline)
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (2, 2)):
                surf.blit(o, r.move(dx, dy))
        surf.blit(img, r)

    # ------------------------------------------------------------------ input
    def touch(self, kind, x, y):
        pos = np.array([x, y], np.float32)
        now = self.t
        if kind == "down":
            self.finger, self.finger_v = pos, np.zeros(2, np.float32)
            self.down_at, self.down_pos = now, pos
            self._scratch(pos, pos)
        elif kind == "move" and self.finger is not None:
            self.finger_v = 0.5 * self.finger_v + 0.5 * (pos - self.finger) * 60
            self._scratch(self.finger, pos)
            self.finger = pos
        elif kind == "up":
            tap = (self.down_at is not None and now - self.down_at < 0.4
                   and np.hypot(*(pos - self.down_pos)) < 20)
            self.finger = None
            if tap:
                self._tap()

    def _tap(self):
        if self.state == "result" and self.state_t > 0.6:
            if self.cash >= int(self.p.card_price):
                self._buy_card()
            else:
                self._game_over()
        elif self.state == "bust" and self.state_t > 1.0:
            self._new_run()

    def _scratch(self, a, b):
        """Remove coating along the segment a->b; removed coating becomes dust."""
        if self.slide > 0:
            return
        p = self.p
        r = p.scratch_size / 2 / CELL
        ax, ay = (a[0] - TX) / CELL, (a[1] - TY) / CELL
        bx, by = (b[0] - TX) / CELL, (b[1] - TY) / CELL
        gw, gh = self.coat.shape
        x0, x1 = int(max(0, min(ax, bx) - r - 1)), int(min(gw, max(ax, bx) + r + 2))
        y0, y1 = int(max(0, min(ay, by) - r - 1)), int(min(gh, max(ay, by) + r + 2))
        if x0 >= x1 or y0 >= y1:
            return
        xs = np.arange(x0, x1, dtype=np.float32)[:, None] + 0.5
        ys = np.arange(y0, y1, dtype=np.float32)[None, :] + 0.5
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        tt = np.clip(((xs - ax) * dx + (ys - ay) * dy) / L2, 0, 1) if L2 > 1e-6 else 0.0
        d = np.hypot(xs - (ax + tt * dx), ys - (ay + tt * dy))   # distance to the finger's path
        fall = np.clip(1.2 - d / r, 0, 1)
        sub = self.coat[x0:x1, y0:y1]
        removed = np.minimum(sub, p.scratch_strength * fall * self.rough[x0:x1, y0:y1])
        total = float(removed.sum())
        if total <= 0:
            return
        sub -= removed
        self.coat_dirty = True
        n = int(min(400, total * p.dust * 0.35))
        if n:
            idx = self.rng.choice(removed.size, n, p=(removed / total).ravel())
            cx, cy = np.unravel_index(idx, removed.shape)
            pos = np.stack([(cx + x0) * CELL + TX, (cy + y0) * CELL + TY], 1).astype(np.float32)
            pos += self.rng.uniform(0, CELL, pos.shape)
            vel = self.finger_v[None, :] * 0.25 + self.rng.normal(0, 25, pos.shape)
            self.dpos = np.concatenate([self.dpos, pos])[-MAX_DUST:]
            self.dvel = np.concatenate([self.dvel, vel.astype(np.float32)])[-MAX_DUST:]

    # ----------------------------------------------------------------- update
    def update(self, dt):
        p = self.p
        self.t += dt
        self.state_t += dt
        if self.slide > 0:
            self.slide = max(0.0, self.slide - dt * 2.8)

        # sweep: a moving finger carries the dust under it along
        if len(self.dpos):
            if self.finger is not None and np.hypot(*self.finger_v) > 20:
                off = self.dpos - self.finger
                dist = np.sqrt((off ** 2).sum(1)) + 1e-3
                R = p.scratch_size * 1.3
                fall = np.clip(1 - dist / R, 0, 1)[:, None]
                push = self.finger_v[None, :] * p.sweep * 1.1 + off / dist[:, None] * 60
                self.dvel = self.dvel * (1 - fall) + push * fall
            self.dvel *= math.exp(-7 * dt)
            self.dpos += self.dvel * dt
            keep = ((self.dpos[:, 0] > -4) & (self.dpos[:, 0] < self.w + 4) &
                    (self.dpos[:, 1] > 116) & (self.dpos[:, 1] < self.h + 4))
            self.dpos, self.dvel = self.dpos[keep], self.dvel[keep]
        self.finger_v *= 0.8

        if self.state == "scratch" and self.slide == 0:
            if all(self._field_left(i) < 1 - p.reveal_at for i in range(len(FIELDS))):
                self._finish_card()

        for f in self.floats:
            f[4] += dt
        self.floats = [f for f in self.floats if f[4] < 1.6]

    def _field_left(self, i):
        fx, fy, fw, fh = FIELDS[i]
        return float(self.coat[fx // CELL:(fx + fw) // CELL, fy // CELL:(fy + fh) // CELL].mean())

    def _finish_card(self):
        self.state, self.state_t = "result", 0.0
        if self.card_prize:
            self.cash += self.card_prize
            self.total_won += self.card_prize
            self.best_win = max(self.best_win, self.card_prize)
            self.floats.append([f"+${self.card_prize}", (60, 170, 70), 330, 600, 0.0])
            self.record_win = max([r.get("best", 0) for r in load_scores()] + [0])

    def _game_over(self):
        runs = load_scores()
        run = {"cards": self.cards, "best": self.best_win, "won": self.total_won,
               "date": time.strftime("%b %d %H:%M")}
        runs.append(run)
        save_scores(runs)
        ranked = sorted(runs, key=lambda r: (-r["cards"], -r.get("best", 0)))
        rank = next(i for i, r in enumerate(ranked) if r is run) + 1
        self.rank_info = (rank, len(runs), ranked[:5], run)
        self.state, self.state_t = "bust", 0.0

    # ------------------------------------------------------------------- draw
    def draw(self, surf):
        surf.blit(self.bg, (0, 0))
        self._slushie(surf)
        tx = TX + int(self.slide * 520)
        surf.blit(self.shadow, (tx + 6, TY + 8))
        surf.blit(self.ticket, (tx, TY))
        if self.coat_dirty:
            self.coat_surf.blit(self.coat_tex, (0, 0))
            alpha = pygame.surfarray.pixels_alpha(self.coat_surf)
            alpha[:] = (np.repeat(np.repeat(self.coat, CELL, 0), CELL, 1) * 255).astype(np.uint8)
            del alpha
            self.coat_dirty = False
        surf.blit(self.coat_surf, (tx, TY))
        self._dust(surf)
        self._receipt(surf)
        if self.state == "result":
            self._stamp(surf, tx)
        for text, col, x, y, age in self.floats:
            img = self.f_mid.render(text, True, col)
            img.set_alpha(int(255 * max(0.0, 1 - age / 1.6)))
            surf.blit(img, img.get_rect(center=(x, y - age * 40)))
        if self.state == "bust":
            self._bust_screen(surf)

    def _slushie(self, surf):
        for i, col in enumerate(((60, 120, 230), (220, 50, 70))):
            x = 412 + i * 32
            pygame.draw.rect(surf, (200, 220, 240), (x, 20, 26, 70), border_radius=8)
            pygame.draw.rect(surf, col, (x + 2, 34, 22, 54), border_radius=6)
            ph = self.t * 2 + i
            for k in range(3):                                   # slowly turning slush
                yy = 40 + ((k * 16 + ph * 8) % 46)
                pygame.draw.arc(surf, tuple(min(255, v + 60) for v in col), (x + 3, yy, 20, 8), 0, math.pi, 2)

    def _dust(self, surf):
        if not len(self.dpos):
            return
        gw, gh = self.w // CELL, self.h // CELL
        ix = np.clip((self.dpos[:, 0] / CELL).astype(np.int32), 0, gw - 1)
        iy = np.clip((self.dpos[:, 1] / CELL).astype(np.int32), 0, gh - 1)
        counts = np.bincount(ix * gh + iy, minlength=gw * gh).reshape(gw, gh)
        alpha = pygame.surfarray.pixels_alpha(self.dust_surf)
        alpha[:] = np.clip(counts * 120, 0, 240).astype(np.uint8)
        del alpha
        surf.blit(pygame.transform.scale(self.dust_surf, (self.w, self.h)), (0, 0))

    def _receipt(self, surf):
        r = pygame.Rect(150, 572, 230, 62)
        pygame.draw.rect(surf, (0, 0, 0), r.move(3, 3))
        pygame.draw.rect(surf, (250, 250, 244), r)
        for x in range(r.x, r.right, 8):                          # torn top edge
            pygame.draw.polygon(surf, COUNTER, [(x, r.y), (x + 4, r.y + 4), (x + 8, r.y)])
        self._text(surf, f"CASH  ${self.cash}", self.f_mid, (30, 30, 34), (r.centerx, r.y + 22))
        self._text(surf, f"CARDS SCRATCHED  {self.cards}", self.f_tiny, (90, 90, 96), (r.centerx, r.y + 48))

    def _stamp(self, surf, tx):
        if self.card_prize:
            lines = [("WINNER!", self.f_big, (220, 30, 50)), (f"${self.card_prize}", self.f_big, (220, 30, 50))]
            note = f"best ever ${max(self.record_win, self.best_win)}" if self.best_win else ""
        else:
            lines = [("NO WIN", self.f_big, (70, 80, 100))]
            note = "better luck next card"
        w, h = 300, 80 * len(lines) + 62
        st = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(st, (255, 255, 255, 215), st.get_rect(), border_radius=12)
        pygame.draw.rect(st, lines[0][2], st.get_rect(), 5, border_radius=12)
        for i, (text, font, col) in enumerate(lines):
            self._text(st, text, font, col, (w // 2, 44 + i * 74))
        if note:
            self._text(st, note, self.f_small, (80, 80, 90), (w // 2, h - 48))
        if self.state_t > 0.6 and int(self.t * 2) % 2 == 0:            # blinking prompt
            price = int(self.p.card_price)
            msg = f"TAP FOR NEXT CARD (${price})" if self.cash >= price else "TAP TO CASH OUT"
            self._text(st, msg, self.f_small, (30, 30, 36), (w // 2, h - 20))
        st = pygame.transform.rotate(st, -8)
        k = min(1.0, self.state_t / 0.25)                          # thump down
        if k < 1:
            st = pygame.transform.smoothscale(st, (int(st.get_width() * (1.6 - 0.6 * k)), int(st.get_height() * (1.6 - 0.6 * k))))
        surf.blit(st, st.get_rect(center=(tx + TW // 2, TY + 230)))

    def _bust_screen(self, surf):
        shade = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        shade.fill((10, 10, 14, 215))
        surf.blit(shade, (0, 0))
        rank, total, top, mine = self.rank_info
        self._text(surf, "OUT OF CASH", self.f_big, (250, 210, 70), (self.w // 2, 80))
        cards = f"{mine['cards']} card" + ("" if mine["cards"] == 1 else "s")
        self._text(surf, f"You scratched {cards}", self.f_mid, (240, 240, 245), (self.w // 2, 140))
        self._text(surf, f"biggest win ${mine['best']}   total won ${mine['won']}", self.f_small, (190, 190, 200), (self.w // 2, 176))
        self._text(surf, f"Rank #{rank} of {total} run" + ("" if total == 1 else "s"), self.f_mid, (120, 220, 140), (self.w // 2, 228))
        self._text(surf, "BEST RUNS", self.f_small, (160, 160, 170), (self.w // 2, 284))
        for i, run in enumerate(top):
            col = (250, 210, 70) if run is mine else (220, 220, 228)
            y = 320 + i * 40
            self._text(surf, f"{i + 1}.", self.f_mid, col, (70, y))
            self._text(surf, f"{run['cards']} cards", self.f_mid, col, (180, y))
            self._text(surf, f"best ${run.get('best', 0)}", self.f_small, col, (310, y))
            self._text(surf, run.get("date", ""), self.f_tiny, (140, 140, 150), (410, y))
        if rank > 5:
            self._text(surf, f"{rank}.  {mine['cards']} cards  (you)", self.f_small, (250, 210, 70), (self.w // 2, 530))
        if self.state_t > 1.0 and int(self.t * 2) % 2 == 0:
            self._text(surf, f"TAP TO PLAY AGAIN WITH ${int(self.p.start_cash)}", self.f_small, (255, 255, 255), (self.w // 2, 590))

    # ------------------------------------------------------------- preview
    def preview(self, step):
        self.slide = 0.0
        for _ in range(10):
            self.update(step)
        for fi in (0, 1, 3, 4):                                  # scratch four fields
            fx, fy, fw, fh = FIELDS[fi]
            x0, y0 = TX + fx + 10, TY + fy + 10
            self.touch("down", x0, y0)
            for k in range(1, 40):
                f = k / 39
                x = x0 + (fw - 20) * (0.5 + 0.5 * math.sin(f * 13))
                y = y0 + (fh - 20) * f
                self.touch("move", x, y)
                self.update(step)
            self.touch("up", x, y)
        self.touch("down", 120, 420)                             # sweep some dust aside
        for k in range(1, 15):
            self.touch("move", 120 + k * 12, 420 + k * 6)
            self.update(step)
        self.touch("up", 300, 510)
