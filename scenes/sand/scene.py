"""Falling sand: pour sand, water and stone and watch them pile, flow and settle.

A cellular automaton. The screen is a grid; each cell is empty, sand, water
or stone, and every step each cell follows a few local rules:
- Sand falls straight down if it can, otherwise slides diagonally down.
  Sand sinks through water (they swap places).
- Water falls, then slides diagonally, then spreads sideways, so it finds
  its level.
- Stone never moves.
All cells are updated together with NumPy array shifts. Each pass moves in a
single direction (left or right, chosen at random), so two grains can never
claim the same empty cell.

Touch: pick a material from the palette at the top, then draw with your
finger. Restart scene (in the panel) clears the board.
"""
import numpy as np
import pygame

from playground.scene import BaseScene, Param

EMPTY, SAND, WATER, STONE = 0, 1, 2, 3
TOOLS = [("Sand", SAND), ("Water", WATER), ("Stone", STONE), ("Erase", EMPTY)]
BASE = {
    SAND: [(222, 186, 118), (210, 172, 102), (232, 200, 134), (198, 160, 94)],
    WATER: [(58, 120, 196), (66, 130, 206), (52, 112, 186), (72, 138, 212)],
    STONE: [(112, 112, 122), (98, 98, 108), (124, 122, 130), (88, 88, 98)],
}
BG_TOP, BG_LOW = (22, 24, 34), (40, 36, 44)
BAR = 44                                  # palette bar height, screen px


class Scene(BaseScene):
    TITLE = "Falling sand"
    PREVIEW_AFTER = 120
    PARAMS = [
        Param("brush", 10, 2, 40, 1, "Brush size", help="In screen pixels... per side, roughly."),
        Param("flow", 0.5, 0.05, 1, 0.05, "Pour density", help="How full each stroke is (sand and water)."),
        Param("speed", 3, 1, 8, 1, "Simulation speed", help="Steps per frame."),
        Param("spread", 2, 0, 6, 1, "Water spread", help="Sideways moves per step: higher = runnier."),
        Param("tool", 0, 0, 3, 1, "Tool", help="0 sand, 1 water, 2 stone, 3 erase (also on-screen)."),
        Param("cell_size", 4, 2, 8, 1, "Grain size", reset=True),
        Param("demo", 1, 0, 1, 1, "Start with a demo layout", reset=True),
    ]

    def setup(self):
        self.cs = int(self.p.cell_size)
        self.gw, self.gh = self.w // self.cs, (self.h - BAR) // self.cs
        self.g = np.zeros((self.gw, self.gh), np.uint8)
        rng = self.rng = np.random.default_rng(3)
        self.var = rng.integers(0, 4, (self.gw, self.gh))
        lut = np.zeros((4, 4, 3), np.uint8)
        for m, cols in BASE.items():
            lut[m] = cols
        self.lut = lut
        ys = np.linspace(0, 1, self.gh)[None, :, None]
        self.bg = (np.array(BG_TOP) + (np.array(BG_LOW) - np.array(BG_TOP)) * ys).repeat(self.gw, 0).astype(np.uint8)
        self.low = pygame.Surface((self.gw, self.gh))
        self.finger = None
        self.prev = None
        self.font = pygame.font.Font(None, 22)
        if self.p.demo:
            self._demo_layout()

    def _demo_layout(self):
        g, gw, gh = self.g, self.gw, self.gh
        # a couple of stone ledges and a cup, so the first pour has something to land on
        g[int(gw * 0.08):int(gw * 0.45), int(gh * 0.42):int(gh * 0.42) + 2] = STONE
        g[int(gw * 0.55):int(gw * 0.92), int(gh * 0.62):int(gh * 0.62) + 2] = STONE
        cup_l, cup_r, cup_b = int(gw * 0.3), int(gw * 0.7), gh - 3
        g[cup_l:cup_r, cup_b:cup_b + 2] = STONE
        g[cup_l:cup_l + 2, int(gh * 0.82):cup_b] = STONE
        g[cup_r - 2:cup_r, int(gh * 0.82):cup_b] = STONE
        g[int(gw * 0.15):int(gw * 0.35), int(gh * 0.2):int(gh * 0.28)] = SAND
        g[int(gw * 0.62):int(gw * 0.85), int(gh * 0.45):int(gh * 0.55)] = WATER

    # ------------------------------------------------------------------ input
    def touch(self, kind, x, y):
        if kind == "down" and y < BAR:
            idx = min(len(TOOLS) - 1, int(x / (self.w / len(TOOLS))))
            self.p._c.set_params({"tool": idx})                    # also moves the panel slider
            self.finger = None
            return
        if kind in ("down", "move"):
            pt = (x / self.cs, (y - BAR) / self.cs)
            self.prev = pt if kind == "down" or self.prev is None else self.prev
            self.finger = pt
        else:
            self.finger, self.prev = None, None

    def _paint(self):
        """Stamp the brush along the line from the last finger position."""
        p = self.p
        mat = TOOLS[int(p.tool)][1]
        r = max(1.0, p.brush / self.cs)
        (x0, y0), (x1, y1) = self.prev, self.finger
        steps = int(max(abs(x1 - x0), abs(y1 - y0)) / max(1, r * 0.5)) + 1
        xs, ys = np.meshgrid(np.arange(self.gw), np.arange(self.gh), indexing="ij")
        for t in np.linspace(0, 1, steps):
            cx, cy = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            lo_x, hi_x = int(max(0, cx - r)), int(min(self.gw, cx + r + 1))
            lo_y, hi_y = int(max(0, cy - r)), int(min(self.gh, cy + r + 1))
            if lo_x >= hi_x or lo_y >= hi_y:
                continue
            sub = self.g[lo_x:hi_x, lo_y:hi_y]
            inside = (xs[lo_x:hi_x, lo_y:hi_y] - cx) ** 2 + (ys[lo_x:hi_x, lo_y:hi_y] - cy) ** 2 <= r * r
            if mat in (SAND, WATER):
                inside &= (sub == EMPTY) & (self.rng.random(sub.shape) < p.flow * 0.5)
            sub[inside] = mat
        self.prev = self.finger

    # ----------------------------------------------------------------- update
    def _fall(self, mat, into):
        a, b = self.g[:, :-1], self.g[:, 1:]                       # cell, cell below
        m = (a == mat) & (b == into)
        a[m], b[m] = into, mat

    def _diag(self, mat, into, d):
        g = self.g
        if d > 0:
            a, b, below = g[:-1, :-1], g[1:, 1:], g[:-1, 1:]
        else:
            a, b, below = g[1:, :-1], g[:-1, 1:], g[1:, 1:]
        m = (a == mat) & (b == into) & (below != into) & (below != EMPTY)
        m &= self.rng.random(m.shape) < 0.8
        a[m], b[m] = into, mat

    def _side(self, d):
        g = self.g
        if d > 0:
            a, b = g[:-1, :], g[1:, :]
        else:
            a, b = g[1:, :], g[:-1, :]
        m = (a == WATER) & (b == EMPTY) & (self.rng.random(a.shape) < 0.7)
        a[m], b[m] = EMPTY, WATER

    def update(self, dt):
        if self.finger is not None:
            self._paint()
        for _ in range(int(self.p.speed)):
            self._fall(SAND, EMPTY)
            self._fall(SAND, WATER)                                # sand sinks through water
            d = 1 if self.rng.random() < 0.5 else -1
            self._diag(SAND, EMPTY, d)
            self._diag(SAND, WATER, -d)
            self._fall(WATER, EMPTY)
            self._diag(WATER, EMPTY, d)
            for k in range(int(self.p.spread)):
                self._side(d if k % 2 == 0 else -d)

    # ------------------------------------------------------------------- draw
    def draw(self, surf):
        g = self.g
        img = self.lut[g, self.var]
        img = np.where((g == EMPTY)[..., None], self.bg, img)
        pygame.surfarray.blit_array(self.low, img)
        surf.fill((0, 0, 0))
        surf.blit(pygame.transform.scale(self.low, (self.gw * self.cs, self.gh * self.cs)), (0, BAR))
        self._palette(surf)

    def _palette(self, surf):
        wd = self.w / len(TOOLS)
        sel = int(self.p.tool)
        for i, (name, mat) in enumerate(TOOLS):
            rect = pygame.Rect(int(i * wd) + 3, 4, int(wd) - 6, BAR - 8)
            col = BASE[mat][0] if mat != EMPTY else (40, 40, 48)
            pygame.draw.rect(surf, col, rect, border_radius=6)
            if i == sel:
                pygame.draw.rect(surf, (250, 250, 250), rect, 3, border_radius=6)
            label = self.font.render(name, True, (20, 20, 24) if mat in (SAND,) else (235, 235, 240))
            surf.blit(label, label.get_rect(center=rect.center))
