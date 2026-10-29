"""A foggy car window on a dreary San Francisco day: wipe it to see out.

Landscape. You're in the passenger seat of a small classic 1970s sedan,
looking out the passenger door. Wide-angle, laid out like a photo taken in a
BMW 2002: a sliver of windshield and black dash at the left (with an
intermittent wiper), a slanted black A-pillar, the front vent window with a
chrome divider, the big side window, the B-pillar at the right, a tan vinyl
door panel below and a beige headliner with the sun visor above. A
rectangular chrome mirror sits outside at the front of the door.

The street: overcast sky with fog banks drifting, a hill of houses fading
into the mist, rows of muted Victorian and Edwardian houses with bay windows
and garages stepping along a hilly street, street trees, parked cars, wet
asphalt and drizzle. The front of the car is to your left, so it all slides
past left to right (parallax: far layers slower).

Fog on the glass: a coarse density map. A heavily blurred, brightened copy of
the view is laid over the clear view with the density as its transparency.
Your finger wipes it away with soft edges. It grows back patchily and creeps
in from foggy areas, and droplets gather at wipe edges and run down,
leaving clear trails.
"""
import math

import numpy as np
import pygame

from playground.noise import ValueNoise2D, lerp_color
from playground.scene import BaseScene, Param

LW, LH = 320, 240                       # drawing resolution (scaled 2x to 640x480)
WIN = pygame.Rect(78, 32, 230, 144)     # bounding box of the side glass (vent + main)
CELL = 3                                # fog grid cell, in drawing pixels
TILE = LW * 2                           # width of each looping layer
CURB = 160                              # curb line on the near side of the street

SKY_TOP, SKY_LOW = (196, 199, 203), (170, 174, 180)
HILL, HILL_HOUSE = (150, 156, 164), (160, 164, 172)
HOUSES = [(160, 168, 146), (146, 160, 174), (202, 190, 162), (176, 152, 142), (188, 180, 138),
          (138, 140, 148), (170, 176, 182), (196, 170, 150)]
TRIM = (222, 220, 212)
WIN_DARK, WIN_LIT = (84, 94, 106), (214, 186, 132)
SIDEWALK, ASPHALT, ASPHALT_WET = (136, 138, 140), (70, 72, 78), (96, 100, 108)
TREE, TREE_DARK, TRUNK = (82, 98, 80), (62, 76, 62), (52, 46, 42)
CARS = [(120, 40, 36), (60, 76, 96), (190, 186, 172), (52, 54, 58), (96, 110, 88), (150, 128, 90)]
HAZE = np.array([226, 230, 236], np.float32)

HEADLINER, VISOR, VISOR_EDGE = (206, 190, 156), (222, 208, 176), (184, 168, 136)
VINYL, VINYL_DARK, VINYL_LIGHT = (200, 172, 122), (164, 138, 94), (220, 196, 148)
BLACK, BLACK_EDGE = (24, 24, 26), (52, 52, 56)
CHROME, CHROME_DARK, CHROME_LIGHT = (184, 190, 200), (100, 106, 118), (238, 242, 248)


def panes():
    windshield = [(0, 34), (106, 30), (74, 150), (0, 150)]
    vent = [(86, 174), (118, 36), (132, 35), (124, 174)]
    main = [(128, 174), (136, 35), (308, 38), (308, 174)]
    a_pillar = [(72, 176), (106, 28), (120, 30), (86, 176)]
    divider = ((126, 174), (134, 35))
    return windshield, vent, main, a_pillar, divider


class Scene(BaseScene):
    TITLE = "Foggy car window"
    LANDSCAPE = True
    PARAMS = [
        Param("speed", 40, 0, 200, 5, "Driving speed", help="0 = parked."),
        Param("regrow_time", 14, 1, 60, 0.5, "Fog return time", help="Seconds for a wiped patch to fog over."),
        Param("creep", 0.6, 0, 3, 0.05, "Fog creep", help="How much fog spreads in from foggy areas."),
        Param("fog_max", 0.95, 0.3, 1, 0.01, "Fog thickness"),
        Param("haze", 0.6, 0, 1, 0.01, "Fog brightness"),
        Param("brush", 26, 6, 80, 1, "Finger size", help="In screen pixels."),
        Param("wipe", 0.85, 0.1, 1, 0.05, "Wipe strength"),
        Param("drips", 0.6, 0, 4, 0.05, "Drips from wipes"),
        Param("ambient_drips", 0.15, 0, 2, 0.05, "Random drips"),
        Param("drizzle", 1.0, 0, 3, 0.05, "Drizzle"),
        Param("wiper_every", 6, 1, 20, 0.5, "Wiper interval", help="Seconds between windshield wipes."),
    ]
    PREVIEW_AFTER = 20

    # ------------------------------------------------------------------ setup
    def setup(self):
        self.rng = rng = np.random.default_rng(14)
        self.low = pygame.Surface((LW, LH))
        self.view = pygame.Surface((LW, LH))
        self._build_street()
        self._build_ahead()
        self._build_car()

        self.gw, self.gh = WIN.w // CELL + 1, WIN.h // CELL + 1
        self.fog = np.full((self.gw, self.gh), float(self.p.fog_max), np.float32)
        nz = ValueNoise2D(seed=8)
        gx, gy = np.meshgrid(np.arange(self.gw), np.arange(self.gh), indexing="ij")
        self.regrow_jit = (0.55 + 0.9 * nz(gx / 7.0, gy / 7.0)).astype(np.float32)
        self.speckle = (0.9 + 0.2 * rng.random((self.gw, self.gh))).astype(np.float32)[..., None]
        self.fog_surf = pygame.Surface((self.gw, self.gh), pygame.SRCALPHA)
        self.off = np.zeros(4)
        self.finger = None
        self.prev = None
        self.drops = []
        self.rain = rng.uniform(0, 1, (70, 2)) * [LW, LH]
        self.wind_drops = []                   # drizzle dots on the windshield
        self.wiper_t = 0.0                     # time since last wipe
        self.wiper_angle = 0.0
        self.t = 0.0

    def _base(self, x):
        """Street level along the hill (periodic over one tile so it loops)."""
        return CURB - 12 - 10 * math.sin(2 * math.pi * x / TILE * 2) - 4 * math.sin(2 * math.pi * x / TILE * 5)

    def _build_street(self):
        rng = self.rng
        self.sky = pygame.Surface((LW, LH))
        for y in range(LH):
            pygame.draw.line(self.sky, lerp_color(SKY_TOP, SKY_LOW, min(1, y / 120)), (0, y), (LW, y))

        def tile():
            return pygame.Surface((TILE, LH), pygame.SRCALPHA)

        # far hill with houses, washed out by fog
        far = tile()
        pts = [(x, 92 - 18 * math.sin(2 * math.pi * x / TILE) - 8 * math.sin(2 * math.pi * x / TILE * 3 + 1))
               for x in range(0, TILE + 4, 4)]
        pygame.draw.polygon(far, HILL, pts + [(TILE, 140), (0, 140)])
        for _ in range(140):
            x = rng.uniform(0, TILE)
            top = 92 - 18 * math.sin(2 * math.pi * x / TILE) - 8 * math.sin(2 * math.pi * x / TILE * 3 + 1)
            y = rng.uniform(top + 2, 136)
            c = lerp_color(HILL_HOUSE, (176, 180, 186), rng.random() * 0.6)
            pygame.draw.rect(far, c, (x, y, rng.uniform(3, 6), rng.uniform(2, 4)))
        self.far = far

        # row houses stepping along the hilly street
        mid = tile()
        x = 0
        while x < TILE:
            w = int(rng.uniform(30, 42))
            base = self._base(x + w / 2)
            h = rng.uniform(50, 76)
            top = base - h
            col = HOUSES[int(rng.integers(len(HOUSES)))]
            shade = lerp_color(col, (40, 44, 50), 0.25)
            pygame.draw.rect(mid, col, (x, top, w, h + 30))
            pygame.draw.rect(mid, shade, (x + w - 3, top, 3, h + 30))                  # side shadow
            pygame.draw.rect(mid, TRIM, (x, top, w, 4))                                # cornice
            pygame.draw.rect(mid, lerp_color(TRIM, (90, 90, 96), 0.4), (x, top + 4, w, 1))
            if rng.random() < 0.5:                                                     # gable roof
                pygame.draw.polygon(mid, lerp_color(col, (60, 60, 66), 0.35),
                                    [(x, top), (x + w / 2, top - 10), (x + w, top)])
            gh = 16
            pygame.draw.rect(mid, (64, 66, 72), (x + 4, base - gh, w * 0.45, gh))       # garage
            for gy in range(int(base - gh) + 3, int(base), 4):
                pygame.draw.line(mid, (78, 80, 86), (x + 4, gy), (x + 4 + w * 0.45, gy))
            sx = x + w * 0.62                                                           # entry stairs
            for k in range(5):
                pygame.draw.line(mid, TRIM, (sx + k * 2, base - k * 3), (sx + k * 2 + 6, base - k * 3))
            bx, bw = x + 4, w * 0.5                                                      # bay window column
            for fy in (top + 10, top + 10 + (h - 30) / 2):
                bh = (h - 34) / 2
                pygame.draw.rect(mid, lerp_color(col, TRIM, 0.3), (bx - 1, fy - 1, bw + 2, bh + 2))
                for k in range(3):
                    wc = WIN_LIT if rng.random() < 0.18 else WIN_DARK
                    pygame.draw.rect(mid, wc, (bx + 1 + k * bw / 3, fy + 1, bw / 3 - 2, bh - 2))
            for fy in (top + 10, top + 10 + (h - 30) / 2):                             # side windows
                wc = WIN_LIT if rng.random() < 0.15 else WIN_DARK
                pygame.draw.rect(mid, wc, (x + w * 0.66, fy + 2, w * 0.2, (h - 34) / 2 - 4))
            x += w
        for xx in range(0, TILE, 2):                                                    # sidewalk down to the curb
            b = int(self._base(xx))
            pygame.draw.line(mid, SIDEWALK, (xx, b), (xx, CURB), 2)
        pygame.draw.line(mid, (110, 112, 116), (0, CURB), (TILE, CURB), 1)
        self.mid = mid

        # near: street trees and parked cars, then the wet street
        near = tile()
        x = 10
        while x < TILE - 60:
            if rng.random() < 0.45:                                                    # tree
                tx = x + 20
                pygame.draw.line(near, TRUNK, (tx, CURB - 2), (tx, CURB - 34), 3)
                for _ in range(12):
                    cx, cy = tx + rng.normal(0, 10), CURB - 48 + rng.normal(0, 8)
                    r = rng.uniform(6, 11)
                    pygame.draw.circle(near, TREE_DARK, (cx, cy + 2), r)
                    pygame.draw.circle(near, TREE, (cx - 1, cy), r * 0.85)
                x += 44
            else:                                                                       # parked car
                cl = int(rng.uniform(46, 56))
                col = CARS[int(rng.integers(len(CARS)))]
                y0 = CURB + 2
                pygame.draw.rect(near, col, (x, y0 - 14, cl, 11), border_radius=4)
                pygame.draw.polygon(near, col, [(x + cl * 0.22, y0 - 13), (x + cl * 0.32, y0 - 23),
                                                (x + cl * 0.72, y0 - 23), (x + cl * 0.84, y0 - 13)])
                pygame.draw.polygon(near, (70, 80, 92), [(x + cl * 0.27, y0 - 14), (x + cl * 0.35, y0 - 21),
                                                         (x + cl * 0.69, y0 - 21), (x + cl * 0.79, y0 - 14)])
                pygame.draw.line(near, lerp_color(col, (255, 255, 255), 0.3), (x + 2, y0 - 13), (x + cl - 2, y0 - 13))
                for wx in (x + cl * 0.2, x + cl * 0.8):
                    pygame.draw.circle(near, (24, 24, 26), (wx, y0 - 3), 4)
                    pygame.draw.circle(near, (90, 92, 96), (wx, y0 - 3), 1)
                x += cl + int(rng.uniform(4, 14))
        pygame.draw.rect(near, ASPHALT, (0, CURB + 2, TILE, LH - CURB))
        for _ in range(160):                                                            # wet sheen
            sx, sy = rng.uniform(0, TILE), rng.uniform(CURB + 4, 180)
            pygame.draw.line(near, ASPHALT_WET, (sx, sy), (sx + rng.uniform(4, 14), sy))
        self.near = near

        # a soft fog bank to drift across the sky
        mist = pygame.Surface((160, 50), pygame.SRCALPHA)
        mist.fill((230, 232, 236, 0))
        for _ in range(40):
            pygame.draw.circle(mist, (230, 232, 236, 255), (rng.uniform(20, 140), rng.uniform(18, 34)), rng.uniform(6, 14))
        small = pygame.transform.smoothscale(mist, (40, 12))
        self.mist = pygame.transform.smoothscale(small, (160, 50))
        self.mist.set_alpha(120)

    def _build_ahead(self):
        """The street ahead, seen through the windshield sliver."""
        a = pygame.Surface((LW, LH), pygame.SRCALPHA)
        for y in range(LH):
            pygame.draw.line(a, lerp_color(SKY_TOP, SKY_LOW, min(1, y / 110)), (0, y), (LW, y))
        vx, vy = 44, 96                                                                  # vanishing point
        pygame.draw.polygon(a, (150, 154, 160), [(vx - 2, vy - 30), (vx - 2, vy), (-10, 150), (-10, 20)])
        pygame.draw.polygon(a, (140, 144, 150), [(vx + 2, vy - 26), (vx + 2, vy), (120, 150), (120, 30)])
        for k in range(10):                                                              # facade divisions
            f = k / 10
            xx = vx - 2 - (vx + 8) * f
            pygame.draw.line(a, (126, 130, 136), (xx, vy - 30 + 50 * f), (xx, vy + 54 * f), 1)
        pygame.draw.polygon(a, ASPHALT, [(vx, vy), (vx + 1, vy), (110, 150), (-20, 150)])
        self.ahead = a
        self.vp = (vx, vy)

    def _build_car(self):
        windshield, vent, main, a_pillar, (d0, d1) = panes()
        f = pygame.Surface((LW, LH), pygame.SRCALPHA)
        f.fill(HEADLINER)
        # door panel: tan vinyl with a padded top rail, door pull and crank
        pygame.draw.rect(f, VINYL, (0, 176, LW, LH - 176))
        pygame.draw.rect(f, VINYL_LIGHT, (0, 176, LW, 12), border_radius=4)
        pygame.draw.line(f, VINYL_DARK, (0, 188), (LW, 188), 1)
        for x in range(150, LW, 34):
            pygame.draw.line(f, VINYL_DARK, (x, 192), (x, LH), 1)
        pygame.draw.ellipse(f, VINYL_DARK, (156, 198, 34, 16))                           # pull recess
        pygame.draw.line(f, CHROME, (162, 206), (184, 206), 3)
        pygame.draw.line(f, CHROME_LIGHT, (162, 205), (184, 205), 1)
        cx, cy = 252, 214                                                                # window crank
        pygame.draw.circle(f, CHROME_DARK, (cx, cy), 6)
        pygame.draw.circle(f, CHROME, (cx, cy), 4)
        pygame.draw.line(f, CHROME, (cx, cy), (cx + 18, cy + 9), 3)
        pygame.draw.circle(f, BLACK, (cx + 20, cy + 10), 4)
        pygame.draw.circle(f, CHROME_DARK, (296, 196), 4)                                # lock button
        for poly in (windshield, vent, main):                                            # cut out the glass
            pygame.draw.polygon(f, (0, 0, 0, 0), poly)
        for poly in (vent, main):                                                        # chrome channel
            pygame.draw.polygon(f, CHROME_DARK, poly, 3)
            pygame.draw.polygon(f, CHROME, poly, 1)
        pygame.draw.line(f, CHROME_DARK, d0, d1, 5)
        pygame.draw.line(f, CHROME, d0, d1, 3)
        pygame.draw.line(f, CHROME_LIGHT, (d0[0] - 1, d0[1]), (d1[0] - 1, d1[1]), 1)
        pygame.draw.polygon(f, BLACK, a_pillar)                                          # black A-pillar
        pygame.draw.line(f, BLACK_EDGE, a_pillar[1], a_pillar[0], 2)
        pygame.draw.line(f, BLACK, (0, 31), (108, 28), 4)
        pygame.draw.rect(f, (60, 56, 52), (309, 30, 11, 150))                            # B-pillar
        pygame.draw.line(f, BLACK_EDGE, (309, 30), (309, 178), 1)
        pygame.draw.rect(f, VISOR, (-20, 2, 150, 24), border_radius=10)                  # sun visor
        pygame.draw.rect(f, VISOR_EDGE, (-20, 2, 150, 24), 1, border_radius=10)
        pygame.draw.line(f, VISOR_EDGE, (0, 32), (LW, 30), 1)
        pygame.draw.polygon(f, BLACK, [(0, 148), (76, 148), (90, 176), (104, LH), (0, LH)])   # dash
        pygame.draw.line(f, BLACK_EDGE, (0, 150), (76, 150), 1)
        pygame.draw.rect(f, (34, 34, 38), (10, 182, 66, 34), border_radius=4)             # glovebox
        pygame.draw.rect(f, (60, 60, 64), (36, 194, 14, 3))
        self.frame = f

        self.side_mask = pygame.Surface((LW, LH), pygame.SRCALPHA)
        for poly in (vent, main):
            pygame.draw.polygon(self.side_mask, (255, 255, 255, 255), poly)
        self.ws_mask = pygame.Surface((LW, LH), pygame.SRCALPHA)
        pygame.draw.polygon(self.ws_mask, (255, 255, 255, 255), windshield)
        self.sheen = pygame.Surface((LW, LH), pygame.SRCALPHA)
        for i, a in enumerate((12, 8)):
            x0 = 180 + i * 90
            pygame.draw.polygon(self.sheen, (255, 255, 255, a), [(x0, 34), (x0 + 30, 34), (x0 - 50, 176), (x0 - 80, 176)])
        self.sheen.blit(self.side_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

        # rectangular chrome mirror outside the front of the door
        mr = pygame.Rect(0, 0, 52, 34)
        m = pygame.Surface((mr.w + 10, mr.h + 18), pygame.SRCALPHA)
        pygame.draw.polygon(m, CHROME_DARK, [(mr.w // 2 - 3, mr.h), (mr.w // 2 + 5, mr.h),
                                             (mr.w // 2 + 10, mr.h + 18), (mr.w // 2 + 2, mr.h + 18)])
        pygame.draw.rect(m, CHROME_DARK, mr, border_radius=6)
        pygame.draw.rect(m, CHROME, mr.inflate(-2, -2), border_radius=5)
        self.mirror = m
        self.mirror_glass = pygame.Rect(4, 4, mr.w - 8, mr.h - 8)
        self.mirror_pos = (126, 116)        # seen through the front of the side glass

    # ------------------------------------------------------------- preview
    def preview(self, step):
        for _ in range(90):
            self.update(step)
        pts = [(0.3, 0.2), (0.9, 0.22), (0.35, 0.4), (0.9, 0.5), (0.2, 0.62)]
        self.touch("down", pts[0][0] * self.w, pts[0][1] * self.h)
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            for i in range(1, 25):
                f = i / 24
                self.touch("move", (x0 + (x1 - x0) * f) * self.w, (y0 + (y1 - y0) * f) * self.h)
                self.update(step)
        self.touch("up", 0, 0)

    # ------------------------------------------------------------------ input
    def touch(self, kind, x, y):
        pt = (x * LW / self.w, y * LH / self.h)
        if kind == "down":
            self.finger = self.prev = pt
        elif kind == "move" and self.finger is not None:
            self.finger = pt
        elif kind == "up":
            self.finger = self.prev = None

    def _wipe(self):
        p = self.p
        (x0, y0), (x1, y1) = self.prev, self.finger
        r = p.brush * LW / self.w / CELL
        gx0, gy0 = (x0 - WIN.x) / CELL, (y0 - WIN.y) / CELL
        gx1, gy1 = (x1 - WIN.x) / CELL, (y1 - WIN.y) / CELL
        steps = int(math.hypot(gx1 - gx0, gy1 - gy0) / max(0.5, r * 0.3)) + 1
        for t in np.linspace(0, 1, steps):
            cx, cy = gx0 + (gx1 - gx0) * t, gy0 + (gy1 - gy0) * t
            lo_x, hi_x = int(max(0, cx - r - 1)), int(min(self.gw, cx + r + 2))
            lo_y, hi_y = int(max(0, cy - r - 1)), int(min(self.gh, cy + r + 2))
            if lo_x >= hi_x or lo_y >= hi_y:
                continue
            xs = np.arange(lo_x, hi_x)[:, None]
            ys = np.arange(lo_y, hi_y)[None, :]
            d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) / r
            self.fog[lo_x:hi_x, lo_y:hi_y] *= 1 - p.wipe * np.clip(1.15 - d, 0, 1)
        moved = math.hypot(x1 - x0, y1 - y0)
        if p.drips > 0 and self.rng.random() < p.drips * min(1.0, moved / 10) * 0.6:
            a = self.rng.uniform(0.15, math.pi - 0.15)
            rr = r * CELL * 1.05
            self._spawn_drop(x1 + math.cos(a) * rr, y1 + math.sin(a) * rr)
        self.prev = self.finger

    def _spawn_drop(self, x, y):
        if WIN.collidepoint(x, y) and len(self.drops) < 60:
            self.drops.append([x, y, 0.0, self.rng.uniform(0.0, 0.6), self.rng.uniform(3, 9)])

    # ----------------------------------------------------------------- update
    def update(self, dt):
        p = self.p
        self.t += dt
        for i, k in enumerate((0.06, 0.55, 1.0, 0.03)):              # far, houses, near, mist
            self.off[i] = (self.off[i] + p.speed * k * dt) % TILE
        if self.finger is not None:
            self._wipe()

        f = self.fog
        fmax = p.fog_max
        f += (fmax - f) * np.clip(dt / p.regrow_time * self.regrow_jit * 2.2, 0, 1)
        if p.creep > 0:
            nb = f.copy()
            nb[1:-1, 1:-1] = (f[2:, 1:-1] + f[:-2, 1:-1] + f[1:-1, 2:] + f[1:-1, :-2]) * 0.25
            f += np.maximum(nb - f, 0) * min(1.0, p.creep * dt * 3)
        np.clip(f, 0, fmax, out=f)

        if p.ambient_drips > 0 and self.rng.random() < p.ambient_drips * dt:
            self._spawn_drop(self.rng.uniform(WIN.x + 10, WIN.right - 10), self.rng.uniform(WIN.y + 5, WIN.y + 50))
        alive = []
        for d in self.drops:
            d[4] -= dt
            if d[3] > 0:
                d[3] -= dt
            else:
                d[2] = min(d[2] + 60 * dt, 45)
                d[1] += d[2] * dt
                d[0] += self.rng.normal(0, 4) * dt
                if self.rng.random() < 0.4 * dt:
                    d[3], d[2] = self.rng.uniform(0.2, 1.2), 0.0
            gx, gy = int((d[0] - WIN.x) / CELL), int((d[1] - WIN.y) / CELL)
            if 0 <= gx < self.gw and 0 <= gy < self.gh:
                f[gx, max(0, gy - 1):gy + 1] *= 0.35
            if d[4] > 0 and d[1] < WIN.bottom - 2:
                alive.append(d)
        self.drops = alive

        # drizzle outside, and drops gathering on the windshield until the wiper sweeps
        self.rain[:, 0] += (40 + p.speed * 0.6) * dt
        self.rain[:, 1] += 160 * dt
        self.rain %= [LW, LH]
        if p.drizzle > 0 and self.rng.random() < p.drizzle * 8 * dt and len(self.wind_drops) < 90:
            self.wind_drops.append((self.rng.uniform(0, 90), self.rng.uniform(34, 148)))
        self.wiper_t += dt
        sweep = 1.2
        if self.wiper_t > p.wiper_every:
            self.wiper_t = 0.0
        if self.wiper_t < sweep:                                    # up and back
            self.wiper_angle = math.sin(self.wiper_t / sweep * math.pi) * 1.45
            px, py = 66, 152
            self.wind_drops = [(x, y) for (x, y) in self.wind_drops
                               if math.atan2(py - y, px - x) > self.wiper_angle + 0.05 or math.hypot(x - px, y - py) > 120]
        else:
            self.wiper_angle = 0.0

    # ------------------------------------------------------------------- draw
    def _street(self, surf):
        surf.blit(self.sky, (0, 0))
        for mx, my in ((0, 40), (200, 70), (400, 56), (560, 86)):
            surf.blit(self.mist, ((mx + self.off[3]) % TILE - 160, my))
        for layer, i in ((self.far, 0), (self.mid, 1), (self.near, 2)):
            x0 = self.off[i] - TILE
            surf.blit(layer, (x0, 0))
            surf.blit(layer, (x0 + TILE, 0))
        if self.p.drizzle > 0:
            n = int(min(len(self.rain), 25 * self.p.drizzle))
            for x, y in self.rain[:n].tolist():
                pygame.draw.line(surf, (214, 218, 224), (x, y), (x + 2, y + 6))

    def _windshield(self, low):
        ws = self.ahead.copy()
        vx, vy = self.vp
        phase = (self.t * (0.6 + self.p.speed / 40)) % 1.0             # lane dashes rushing toward us
        for k in range(5):
            z = (k + phase) / 5
            y0, y1 = vy + 60 * z ** 2, vy + 60 * (z + 0.08) ** 2
            x0, x1 = vx + 20 * z ** 2, vx + 20 * (z + 0.08) ** 2
            pygame.draw.line(ws, (196, 190, 160), (x0, y0), (x1, y1), max(1, int(3 * z)))
        for x, y in self.wind_drops:
            ws.set_at((int(x), int(y)), (214, 218, 226))
        if self.wiper_angle > 0:
            px, py, L = 66, 152, 118
            ex, ey = px - math.cos(self.wiper_angle) * L, py - math.sin(self.wiper_angle) * L
            pygame.draw.line(ws, (20, 20, 22), (px, py), (ex, ey), 3)
        ws.blit(self.ws_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        low.blit(ws, (0, 0), area=pygame.Rect(0, 0, 110, 152))

    def _mirror(self, view):
        g = self.mirror_glass
        slice_ = view.subsurface(pygame.Rect(150, 100, 90, 60)).copy()
        img = pygame.transform.scale(pygame.transform.flip(slice_, True, False), g.size)
        img.fill((26, 28, 32), special_flags=pygame.BLEND_RGB_ADD)
        m = self.mirror.copy()
        m.blit(img, g.topleft)
        view.blit(m, self.mirror_pos)

    def draw(self, surf):
        p = self.p
        view = self.view
        self._street(view)
        self._mirror(view)

        win = view.subsurface(WIN)
        tiny = pygame.transform.smoothscale(win, (max(2, self.gw // 4), max(2, self.gh // 4)))
        small = pygame.transform.smoothscale(tiny, (self.gw, self.gh))
        rgb = pygame.surfarray.array3d(small).astype(np.float32)
        rgb = (rgb * (1 - p.haze * 0.7) + HAZE * p.haze * 0.7 + 6) * self.speckle   # milky white
        pygame.surfarray.blit_array(self.fog_surf, np.clip(rgb, 0, 255).astype(np.uint8))
        alpha = pygame.surfarray.pixels_alpha(self.fog_surf)
        alpha[:] = np.clip(self.fog * 255, 0, 255).astype(np.uint8)
        del alpha
        fog_big = pygame.transform.smoothscale(self.fog_surf, (self.gw * CELL, self.gh * CELL))

        low = self.low
        low.blit(view, (0, 0))
        low.blit(fog_big, WIN.topleft, area=pygame.Rect(0, 0, WIN.w, WIN.h))
        for x, y, vy, stuck, life in self.drops:
            low.set_at((int(x), int(y)), (236, 238, 242))
            low.set_at((int(x), int(y) - 1), (160, 166, 176))
        low.blit(self.sheen, (0, 0))
        self._windshield(low)
        low.blit(self.frame, (0, 0))
        surf.blit(pygame.transform.scale(low, (self.w, self.h)), (0, 0))
