"""A foggy car window at blue hour on a rural Midwest road: wipe it to see out.

You're in the passenger seat of a small classic 1970s sedan, wide-angle, so
the big side window fills most of the view: thin pillars, bright chrome trim,
a front vent window with its own divider, a small round chrome mirror outside,
and a pleated vinyl door panel with a chrome window crank. The front of the
car is to your left, so the land slides past left to right.

- The land: looping layers drawn once (far tree lines and farmsteads with a
  lit window, a silo and a water tower; fields with round hay bales;
  telephone poles with sagging wires; a fence; roadside grass), scrolled at
  different speeds for depth (parallax). Blue-hour sky with a few early stars
  and a thin moon.
- The fog: a coarse density map over the glass. Each frame, a heavily
  blurred, brightened copy of the view is laid over the clear view with the
  fog density as its transparency.
- Wiping: your finger clears fog along its path, with soft edges.
- Weight: fog creeps back in from foggy neighbours and refills patchily over
  time. Droplets gather at the edges of a wipe and run down the glass,
  cutting thin clear trails that slowly fog over again.
"""
import math

import numpy as np
import pygame

from playground.noise import ValueNoise2D, lerp_color
from playground.scene import BaseScene, Param

LW, LH = 240, 320                       # drawing resolution (scaled 2x to the panel)
WIN = pygame.Rect(6, 22, 230, 232)      # bounding box of the glass (wide angle)
HORIZON = 156                           # where land meets sky, in drawing pixels
CELL = 3                                # fog grid cell, in drawing pixels
TILE = LW * 2                           # width of each looping layer

SKY = [(0.0, (14, 22, 58)), (0.45, (34, 56, 112)), (0.82, (88, 116, 170)), (0.95, (150, 150, 182)),
       (1.0, (182, 160, 172))]
FAR, FAR_LIGHT = (22, 32, 56), (30, 42, 68)
FIELD_A, FIELD_B = (26, 36, 54), (32, 42, 58)
NEAR = (12, 16, 26)
WARM = (255, 200, 120)
HAZE = np.array([150, 166, 200], np.float32)

VINYL, VINYL_DARK, VINYL_LIGHT = (70, 48, 34), (46, 30, 22), (96, 68, 48)     # cognac vinyl
HEADLINER = (54, 52, 50)
CHROME, CHROME_DARK, CHROME_LIGHT = (176, 182, 194), (92, 98, 112), (236, 240, 248)


def sky_color(t):
    for (t0, c0), (t1, c1) in zip(SKY, SKY[1:]):
        if t <= t1:
            return lerp_color(c0, c1, (t - t0) / (t1 - t0))
    return SKY[-1][1]


def glass_panes():
    """Main pane and front vent pane (polygons), plus the divider line between them."""
    a_bottom, a_top = (6, 254), (34, 30)                     # slanted front pillar
    div_bottom, div_top = (64, 254), (70, 26)                # vent window divider
    main = [div_bottom, div_top, (100, 24), (236, 22), (236, 254)]
    vent = [a_bottom, (8, 200), (16, 70), a_top, (52, 26), div_top, div_bottom]
    return main, vent, (div_bottom, div_top)


class Scene(BaseScene):
    TITLE = "Foggy car window"
    PARAMS = [
        Param("speed", 70, 0, 300, 5, "Driving speed", help="0 = stopped on the shoulder."),
        Param("regrow_time", 14, 1, 60, 0.5, "Fog return time", help="Seconds for a wiped patch to fog over."),
        Param("creep", 0.6, 0, 3, 0.05, "Fog creep", help="How much fog spreads in from foggy areas."),
        Param("fog_max", 0.96, 0.3, 1, 0.01, "Fog thickness"),
        Param("haze", 0.5, 0, 1, 0.01, "Fog brightness"),
        Param("brush", 26, 6, 80, 1, "Finger size", help="In screen pixels."),
        Param("wipe", 0.85, 0.1, 1, 0.05, "Wipe strength"),
        Param("drips", 0.6, 0, 4, 0.05, "Drips from wipes"),
        Param("ambient_drips", 0.15, 0, 2, 0.05, "Random drips"),
    ]
    PREVIEW_AFTER = 20

    # ------------------------------------------------------------------ setup
    def setup(self):
        self.rng = rng = np.random.default_rng(12)
        self.low = pygame.Surface((LW, LH))
        self.view = pygame.Surface((LW, LH))
        self._build_land()
        self._build_car()

        self.gw, self.gh = WIN.w // CELL + 1, WIN.h // CELL + 1
        self.fog = np.full((self.gw, self.gh), float(self.p.fog_max), np.float32)
        nz = ValueNoise2D(seed=8)
        gx, gy = np.meshgrid(np.arange(self.gw), np.arange(self.gh), indexing="ij")
        self.regrow_jit = (0.55 + 0.9 * nz(gx / 7.0, gy / 7.0)).astype(np.float32)   # patchy regrowth
        self.speckle = (0.9 + 0.2 * rng.random((self.gw, self.gh))).astype(np.float32)[..., None]
        self.fog_surf = pygame.Surface((self.gw, self.gh), pygame.SRCALPHA)
        self.off = np.zeros(5)
        self.finger = None
        self.prev = None
        self.drops = []                        # [x, y, vy, stuck_time, life]

    def _build_land(self):
        rng = self.rng
        # sky with a few early stars and a thin moon
        self.sky = pygame.Surface((LW, LH))
        for y in range(LH):
            pygame.draw.line(self.sky, sky_color(min(1.0, y / HORIZON)), (0, y), (LW, y))
        for _ in range(26):
            x, y = int(rng.uniform(10, LW - 4)), int(rng.uniform(24, HORIZON * 0.45))
            b = int(rng.uniform(120, 220))
            self.sky.set_at((x, y), (b, b, min(255, b + 20)))
        mx, my = 186, 52
        pygame.draw.circle(self.sky, (236, 232, 206), (mx, my), 7)
        pygame.draw.circle(self.sky, sky_color(my / HORIZON), (mx - 3, my - 2), 7)

        def tile():
            return pygame.Surface((TILE, LH), pygame.SRCALPHA)

        # far: tree lines (windbreaks) and farmsteads on the horizon
        far = tile()
        x = 0
        while x < TILE:
            w = int(rng.uniform(8, 40))
            if rng.random() < 0.65:
                for k in range(w // 3):
                    r = rng.uniform(2, 5)
                    pygame.draw.circle(far, FAR, (x + k * 3, HORIZON - r * 0.6), r)
            x += w + int(rng.uniform(0, 30))
        pygame.draw.rect(far, FAR, (0, HORIZON - 1, TILE, 3))
        self.lights = []                                         # (layer, x, y) for warm glows
        for fx in (60, 250, 400):
            fx += int(rng.uniform(-15, 15))
            pygame.draw.rect(far, FAR, (fx, HORIZON - 14, 4, 14))                     # silo
            pygame.draw.circle(far, FAR, (fx + 2, HORIZON - 14), 2)
            pygame.draw.polygon(far, FAR, [(fx + 6, HORIZON), (fx + 6, HORIZON - 6), (fx + 10, HORIZON - 10),
                                           (fx + 14, HORIZON - 6), (fx + 14, HORIZON)])  # barn
            pygame.draw.rect(far, FAR_LIGHT, (fx + 18, HORIZON - 5, 7, 5))            # farmhouse
            pygame.draw.polygon(far, FAR_LIGHT, [(fx + 17, HORIZON - 5), (fx + 21.5, HORIZON - 9), (fx + 26, HORIZON - 5)])
            far.set_at((fx + 20, HORIZON - 3), WARM)                                    # lit window
            self.lights.append((0, fx + 31, HORIZON - 8))                               # yard light
        wx = 330                                                                         # water tower
        for lx in (wx - 3, wx + 3):
            pygame.draw.line(far, FAR, (lx, HORIZON), (wx, HORIZON - 14), 1)
        pygame.draw.ellipse(far, FAR, (wx - 6, HORIZON - 22, 12, 9))
        self.far = far

        # mid: field texture and round hay bales
        mid = tile()
        for y in range(HORIZON + 2, 240):                       # runs down behind the fence
            t = min(1.0, (y - HORIZON) / 70)
            c = lerp_color(FIELD_A, FIELD_B, 0.5 + 0.5 * math.sin(y * 0.9))
            c = lerp_color(c, NEAR, t * 0.2)                    # stays light enough to silhouette the fence
            pygame.draw.line(mid, c, (0, y), (TILE, y))
        for _ in range(900):                                     # crop stubble flecks
            y = int(HORIZON + 2 + (238 - HORIZON - 2) * rng.random() ** 0.7)
            x = int(rng.uniform(0, TILE))
            t = min(1.0, (y - HORIZON) / 70)
            mid.set_at((x, y), lerp_color((44, 56, 76), NEAR, t * 0.6))
        for _ in range(9):
            bx = int(rng.uniform(0, TILE - 8))
            by = int(rng.uniform(HORIZON + 8, 196))
            r = 2 + (by - HORIZON) / 18
            pygame.draw.circle(mid, (40, 46, 58), (bx, by - r), r)
            pygame.draw.circle(mid, (56, 60, 70), (bx - r * 0.3, by - r * 1.2), r * 0.5)
        self.mid = mid

        # telephone poles with sagging wires (5 per tile so the wires loop seamlessly)
        poles = tile()
        spacing, top, base = TILE // 5, 58, 214
        pole_x = [int(spacing * i + 20) for i in range(5)]
        for px in pole_x:
            pygame.draw.line(poles, NEAR, (px, base), (px, top), 3)
            pygame.draw.line(poles, NEAR, (px - 9, top + 6), (px + 9, top + 6), 2)       # crossarm
        for wire_dy, wx_off in ((6, -8), (6, 8), (14, 0)):
            for i in range(5):
                x0 = pole_x[i] + wx_off
                x1 = pole_x[(i + 1) % 5] + wx_off + (TILE if i == 4 else 0)
                pts = []
                for k in range(25):
                    f = k / 24
                    pts.append((x0 + (x1 - x0) * f, top + wire_dy + 9 * math.sin(math.pi * f)))   # sag
                pygame.draw.lines(poles, (20, 26, 40), False, pts, 1)
                if i == 4:                                       # draw the wrapped part at the start too
                    pygame.draw.lines(poles, (20, 26, 40), False, [(x - TILE, y) for x, y in pts], 1)
        self.poles = poles

        # fence posts and wire close to the road
        fence = tile()
        for x in range(0, TILE, 16):
            pygame.draw.line(fence, NEAR, (x, 236), (x, 216), 2)
        for y in (221, 229):
            pygame.draw.line(fence, (22, 26, 38), (0, y), (TILE, y), 1)
        self.fence = fence

        # roadside grass, nearest and fastest
        grass = tile()
        pygame.draw.rect(grass, (10, 13, 20), (0, 236, TILE, LH - 236))
        for _ in range(500):
            x = rng.uniform(0, TILE)
            h = rng.uniform(6, 22)
            a = rng.normal(0.25, 0.2)
            c = lerp_color((10, 13, 20), (34, 44, 60), rng.random() * 0.7)
            pygame.draw.line(grass, c, (x, 254), (x + math.sin(a) * h, 254 - math.cos(a) * h), 1)
        self.grass = grass

        # warm glows (added on top of the far layer)
        self.glow = pygame.Surface((24, 24))
        for r in range(12, 0, -1):
            k = (1 - r / 12) ** 2
            pygame.draw.circle(self.glow, (int(140 * k), int(100 * k), int(50 * k)), (12, 12), r)

    def _build_car(self):
        main, vent, (d0, d1) = glass_panes()
        f = pygame.Surface((LW, LH), pygame.SRCALPHA)
        f.fill(HEADLINER)
        # door panel: pleated cognac vinyl below the window
        pygame.draw.rect(f, VINYL, (0, 254, LW, LH - 254))
        for y in range(272, LH, 5):
            pygame.draw.line(f, VINYL_DARK, (0, y), (LW, y), 1)
            pygame.draw.line(f, VINYL_LIGHT, (0, y + 1), (LW, y + 1), 1)
        pygame.draw.rect(f, VINYL_DARK, (0, 254, LW, 14))                                 # padded top rail
        pygame.draw.line(f, VINYL_LIGHT, (0, 256), (LW, 256), 1)
        # chrome window crank
        cx, cy = 168, 292
        pygame.draw.circle(f, CHROME_DARK, (cx, cy), 6)
        pygame.draw.circle(f, CHROME, (cx, cy), 4)
        pygame.draw.line(f, CHROME, (cx, cy), (cx + 20, cy + 10), 3)
        pygame.draw.line(f, CHROME_LIGHT, (cx + 1, cy - 1), (cx + 19, cy + 8), 1)
        pygame.draw.circle(f, VINYL_DARK, (cx + 22, cy + 11), 4)                         # knob
        pygame.draw.circle(f, (110, 80, 58), (cx + 21, cy + 10), 2)
        # chrome door pull
        pygame.draw.line(f, CHROME_DARK, (40, 284), (100, 284), 4)
        pygame.draw.line(f, CHROME_LIGHT, (40, 283), (100, 283), 1)
        # cut out the glass
        pygame.draw.polygon(f, (0, 0, 0, 0), main)
        pygame.draw.polygon(f, (0, 0, 0, 0), vent)
        # bright chrome trim around the glass and the vent divider
        for poly in (main, vent):
            pygame.draw.polygon(f, CHROME_DARK, poly, 4)
            pygame.draw.polygon(f, CHROME, poly, 2)
            for pt in poly:                                     # fill the gaps at the corners
                pygame.draw.circle(f, CHROME, pt, 1)
        pygame.draw.line(f, CHROME_DARK, d0, d1, 5)
        pygame.draw.line(f, CHROME, d0, d1, 3)
        pygame.draw.line(f, CHROME_LIGHT, (d0[0] - 1, d0[1]), (d1[0] - 1, d1[1]), 1)
        pygame.draw.line(f, CHROME_LIGHT, (8, 253), (236, 253), 1)                       # sill highlight
        self.frame = f
        self.mask = pygame.Surface((LW, LH), pygame.SRCALPHA)
        pygame.draw.polygon(self.mask, (255, 255, 255, 255), main)
        pygame.draw.polygon(self.mask, (255, 255, 255, 255), vent)
        self.sheen = pygame.Surface((LW, LH), pygame.SRCALPHA)
        for i, a in enumerate((13, 8)):
            x0 = 90 + i * 80
            pygame.draw.polygon(self.sheen, (255, 255, 255, a), [(x0, 22), (x0 + 30, 22), (x0 - 70, 254), (x0 - 100, 254)])
        self.sheen.blit(self.mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

        # small round chrome mirror outside the vent window, seen from behind
        m = pygame.Surface((40, 46), pygame.SRCALPHA)
        pygame.draw.line(m, CHROME_DARK, (22, 46), (20, 30), 4)                           # stalk
        pygame.draw.circle(m, CHROME_DARK, (20, 18), 16)
        for r, c in ((15, (120, 126, 140)), (12, CHROME), (7, (204, 210, 222))):        # domed shading
            pygame.draw.circle(m, c, (20 - (15 - r) * 0.35, 18 - (15 - r) * 0.35), r)
        pygame.draw.circle(m, CHROME_LIGHT, (14, 12), 3)                                   # highlight
        pygame.draw.arc(m, (40, 54, 84), (4, 2, 32, 32), -0.6, 0.9, 2)                     # glimpse of glass
        self.mirror = m
        self.mirror_pos = (16, 208)

    # ------------------------------------------------------------- preview
    def preview(self, step):
        """Wipe a zigzag for the gallery image."""
        for _ in range(90):
            self.update(step)
        pts = [(0.2, 0.22), (0.85, 0.24), (0.25, 0.4), (0.85, 0.5), (0.1, 0.66)]
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
        r = p.brush * LW / self.w / CELL                              # brush radius in fog cells
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
            fall = np.clip(1.15 - d, 0, 1)                             # soft edge
            self.fog[lo_x:hi_x, lo_y:hi_y] *= 1 - p.wipe * fall
        moved = math.hypot(x1 - x0, y1 - y0)
        if p.drips > 0 and self.rng.random() < p.drips * min(1.0, moved / 10) * 0.6:
            a = self.rng.uniform(0.15, math.pi - 0.15)                 # lower edge of the finger
            rr = r * CELL * 1.05
            self._spawn_drop(x1 + math.cos(a) * rr, y1 + math.sin(a) * rr)
        self.prev = self.finger

    def _spawn_drop(self, x, y):
        if WIN.collidepoint(x, y) and len(self.drops) < 60:
            self.drops.append([x, y, 0.0, self.rng.uniform(0.0, 0.6), self.rng.uniform(3, 9)])

    # ----------------------------------------------------------------- update
    def update(self, dt):
        p = self.p
        for i, k in enumerate((0.05, 0.22, 0.75, 1.15, 1.6)):         # far, mid, poles, fence, grass
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
            self._spawn_drop(self.rng.uniform(WIN.x + 10, WIN.right - 10), self.rng.uniform(WIN.y + 5, WIN.y + 60))
        alive = []
        for d in self.drops:
            d[4] -= dt
            if d[3] > 0:
                d[3] -= dt
            else:
                d[2] = min(d[2] + 60 * dt, 45)
                d[1] += d[2] * dt
                d[0] += self.rng.normal(0, 4) * dt
                if self.rng.random() < 0.4 * dt:                       # catch on the glass for a moment
                    d[3], d[2] = self.rng.uniform(0.2, 1.2), 0.0
            gx, gy = int((d[0] - WIN.x) / CELL), int((d[1] - WIN.y) / CELL)
            if 0 <= gx < self.gw and 0 <= gy < self.gh:
                f[gx, max(0, gy - 1):gy + 1] *= 0.35
            if d[4] > 0 and d[1] < WIN.bottom - 2:
                alive.append(d)
        self.drops = alive

    # ------------------------------------------------------------------- draw
    def _land(self, surf):
        surf.blit(self.sky, (0, 0))
        for layer, i in ((self.far, 0), (self.mid, 1), (self.poles, 2), (self.fence, 3), (self.grass, 4)):
            x0 = self.off[i] - TILE
            surf.blit(layer, (x0, 0))
            surf.blit(layer, (x0 + TILE, 0))
            if i == 0:                                              # yard lights glow over the far layer
                for _, lx, ly in self.lights:
                    for dx in (x0, x0 + TILE):
                        surf.blit(self.glow, (lx + dx - 12, ly - 12), special_flags=pygame.BLEND_RGB_ADD)
                        surf.set_at((int(lx + dx), ly), (255, 228, 170))

    def draw(self, surf):
        p = self.p
        view = self.view
        self._land(view)
        view.blit(self.mirror, self.mirror_pos)                         # outside the glass

        win = view.subsurface(WIN)
        tiny = pygame.transform.smoothscale(win, (max(2, self.gw // 4), max(2, self.gh // 4)))
        small = pygame.transform.smoothscale(tiny, (self.gw, self.gh))  # heavy blur: lights bloom
        rgb = pygame.surfarray.array3d(small).astype(np.float32)
        rgb = (rgb * 1.4 * (1 - p.haze * 0.55) + HAZE * p.haze * 0.55 + 6) * self.speckle
        pygame.surfarray.blit_array(self.fog_surf, np.clip(rgb, 0, 255).astype(np.uint8))
        alpha = pygame.surfarray.pixels_alpha(self.fog_surf)
        alpha[:] = np.clip(self.fog * 255, 0, 255).astype(np.uint8)
        del alpha
        fog_big = pygame.transform.smoothscale(self.fog_surf, (self.gw * CELL, self.gh * CELL))

        low = self.low
        low.blit(view, (0, 0))
        low.blit(fog_big, WIN.topleft, area=pygame.Rect(0, 0, WIN.w, WIN.h))
        for x, y, vy, stuck, life in self.drops:
            low.set_at((int(x), int(y)), (222, 230, 244))
            low.set_at((int(x), int(y) - 1), (146, 160, 186))
        low.blit(self.sheen, (0, 0))
        low.blit(self.frame, (0, 0))
        surf.blit(pygame.transform.scale(low, (self.w, self.h)), (0, 0))
