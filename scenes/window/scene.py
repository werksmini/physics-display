"""A foggy car window at night: wipe the condensation to see the city go by.

You're in the passenger seat looking out the side window, so the front of
the car is to your left and the city slides past left to right.

- The city: looping layers drawn once at startup (far skyline, nearer
  buildings with lit windows and neon, street lamps with glow), scrolled at
  different speeds for depth (parallax).
- The side mirror sits outside the glass at the front corner and shows a
  flipped slice of the street behind.
- The fog: a coarse density map over the glass. Each frame, a blurred,
  hazy copy of the view is laid over the clear view with the fog density
  as its transparency, so thick fog shows only soft lights.
- Wiping: your finger clears fog along its path, with soft edges.
- Weight: fog creeps back in from foggy neighbours and refills patchily over
  time. Droplets gather at the edges of a wipe and run down the glass,
  cutting thin clear trails that slowly fog over again.
- When a street lamp passes, it briefly lights the car interior.
"""
import math

import numpy as np
import pygame

from playground.noise import ValueNoise2D, lerp_color
from playground.scene import BaseScene, Param

LW, LH = 240, 320                       # drawing resolution (scaled 2x to the panel)
WIN = pygame.Rect(18, 40, 210, 176)     # bounding box of the window opening
GROUND = 200                            # street level, in drawing pixels
SKY_TOP, SKY_LOW, SKY_GLOW = (6, 8, 22), (34, 26, 46), (78, 50, 44)
FAR_BLDG, MID_BLDG = (24, 28, 46), (11, 13, 22)
WARM, COOL = [(236, 198, 120), (250, 214, 150), (226, 170, 96)], [(190, 214, 250), (170, 200, 240)]
NEON = [(255, 70, 150), (60, 230, 230), (255, 150, 40), (140, 120, 255)]
INTERIOR, INTERIOR_EDGE, INTERIOR_LIT = (18, 18, 22), (34, 34, 40), (70, 56, 38)
HAZE = np.array([168, 176, 190], np.float32)
CELL = 3                                # fog grid cell size, in drawing pixels


def window_polygon():
    """The glass opening: slanted front pillar on the left, B-pillar on the right."""
    pts = [(18, 216), (20, 190)]
    for a in np.linspace(math.pi, 1.5 * math.pi, 8):            # rounded top-front corner
        pts.append((62 + 26 * math.cos(a), 66 + 26 * math.sin(a)))
    pts += [(150, 40), (228, 42), (228, 216)]
    return pts


class Scene(BaseScene):
    TITLE = "Foggy car window"
    PARAMS = [
        Param("speed", 60, 0, 300, 5, "Driving speed", help="0 = stopped at a light."),
        Param("regrow_time", 14, 1, 60, 0.5, "Fog return time", help="Seconds for a wiped patch to fog over."),
        Param("creep", 0.6, 0, 3, 0.05, "Fog creep", help="How much fog spreads in from foggy areas."),
        Param("fog_max", 0.96, 0.3, 1, 0.01, "Fog thickness"),
        Param("haze", 0.5, 0, 1, 0.01, "Fog brightness"),
        Param("brush", 26, 6, 80, 1, "Finger size", help="In screen pixels."),
        Param("wipe", 0.85, 0.1, 1, 0.05, "Wipe strength"),
        Param("drips", 0.6, 0, 4, 0.05, "Drips from wipes"),
        Param("ambient_drips", 0.15, 0, 2, 0.05, "Random drips"),
        Param("lamp_light", 1.0, 0, 2, 0.05, "Lamp light on interior"),
    ]

    # ------------------------------------------------------------------ setup
    def setup(self):
        self.rng = rng = np.random.default_rng(12)
        self.low = pygame.Surface((LW, LH))
        self.view = pygame.Surface((LW, LH))
        self._build_city()
        self._build_frame()
        self._build_mirror()

        self.gw, self.gh = WIN.w // CELL + 1, WIN.h // CELL + 1
        self.fog = np.full((self.gw, self.gh), float(self.p.fog_max), np.float32)
        nz = ValueNoise2D(seed=8)
        gx, gy = np.meshgrid(np.arange(self.gw), np.arange(self.gh), indexing="ij")
        self.regrow_jit = (0.55 + 0.9 * nz(gx / 7.0, gy / 7.0)).astype(np.float32)   # patchy
        self.speckle = (0.9 + 0.2 * rng.random((self.gw, self.gh))).astype(np.float32)[..., None]   # texture
        self.fog_surf = pygame.Surface((self.gw, self.gh), pygame.SRCALPHA)
        self.off = np.zeros(4)                 # scroll offsets per layer
        self.finger = None
        self.prev = None
        self.drops = []                        # [x, y, vy, stuck_time, life]
        self.t = 0.0

    def _build_city(self):
        rng = self.rng
        self.sky = pygame.Surface((LW, LH))
        for y in range(LH):
            t = min(1.0, y / GROUND)
            c = lerp_color(SKY_TOP, SKY_LOW, t ** 1.6)
            if t > 0.7:
                c = lerp_color(c, SKY_GLOW, (t - 0.7) / 0.3 * 0.7)
            pygame.draw.line(self.sky, c, (0, y), (LW, y))

        def buildings(tile_w, hmin, hmax, wmin, wmax, color, win_step, win_size, lit, neon=0.0):
            tile = pygame.Surface((tile_w, LH), pygame.SRCALPHA)
            x = 0
            while x < tile_w:
                bw = int(rng.uniform(wmin, wmax))
                bh = int(rng.uniform(hmin, hmax))
                top = GROUND - bh
                col = tuple(max(0, min(255, c + int(rng.uniform(-4, 4)))) for c in color)
                pygame.draw.rect(tile, col, (x, top, bw, bh + 2))
                if rng.random() < 0.3:                              # rooftop detail
                    pygame.draw.rect(tile, col, (x + bw // 3, top - 4, max(2, bw // 5), 4))
                for wy in range(top + 3, GROUND - 3, win_step):
                    for wx in range(x + 2, x + bw - win_size, win_step):
                        if rng.random() < lit:
                            wc = WARM[int(rng.integers(3))] if rng.random() < 0.8 else COOL[int(rng.integers(2))]
                            dim = rng.uniform(0.55, 1.0)
                            wc = tuple(int(c * dim) for c in wc)
                            pygame.draw.rect(tile, wc, (wx, wy, win_size, win_size))
                if neon and rng.random() < neon and bw > 18:
                    nc = NEON[int(rng.integers(len(NEON)))]
                    ny = int(top + rng.uniform(8, min(40, bh - 8)))
                    nw = int(min(bw - 6, rng.uniform(10, 22)))
                    glow = pygame.Surface((nw + 12, 12), pygame.SRCALPHA)
                    pygame.draw.rect(glow, (*nc, 60), (0, 0, nw + 12, 12), border_radius=5)
                    tile.blit(glow, (x + 3 - 6, ny - 5))
                    pygame.draw.rect(tile, nc, (x + 3, ny, nw, 3))
                x += bw + int(rng.uniform(0, 4))
            return tile

        tw = LW * 2
        self.far = buildings(tw, 30, 110, 12, 40, FAR_BLDG, 3, 1, 0.22)
        self.mid = buildings(tw, 60, 165, 24, 58, MID_BLDG, 5, 2, 0.32, neon=0.35)

        # street lamps: poles (normal blit) and glows (added on top)
        self.poles = pygame.Surface((tw, LH), pygame.SRCALPHA)
        self.glows = pygame.Surface((tw, LH))
        self.lamp_x = []
        for x in range(30, tw, 120):
            px = x + int(rng.uniform(-8, 8))
            self.lamp_x.append(px)
            pygame.draw.line(self.poles, (14, 14, 18), (px, GROUND + 14), (px, 96), 3)
            pygame.draw.line(self.poles, (14, 14, 18), (px, 98), (px - 14, 94), 2)
            for r in range(30, 0, -2):                              # soft additive glow
                k = (1 - r / 30) ** 2
                pygame.draw.circle(self.glows, (int(120 * k), int(90 * k), int(50 * k)), (px - 15, 98), r)
            pygame.draw.circle(self.glows, (255, 226, 170), (px - 15, 98), 3)
        # street band with a curb highlight
        self.street = pygame.Surface((LW, LH - GROUND), pygame.SRCALPHA)
        self.street.fill((14, 14, 18))
        pygame.draw.line(self.street, (44, 42, 48), (0, 2), (LW, 2))
        self.tw = tw

    def _build_frame(self):
        """Car interior around the window, drawn dark and lit versions."""
        poly = window_polygon()
        self.win_poly = poly

        def paint(base, edge):
            f = pygame.Surface((LW, LH), pygame.SRCALPHA)
            f.fill(base)
            pygame.draw.polygon(f, (0, 0, 0, 0), poly)                  # cut out the glass
            pygame.draw.polygon(f, edge, poly, 3)                       # rubber seal
            pygame.draw.rect(f, lerp_color(base, edge, 0.6), (0, 236, LW, 14))   # armrest top
            pygame.draw.line(f, lerp_color(edge, (90, 90, 96), 0.5), (0, 236), (LW, 236), 1)
            pygame.draw.rect(f, lerp_color(base, edge, 0.4), (150, 262, 56, 16), border_radius=6)  # handle recess
            pygame.draw.line(f, edge, (156, 270), (200, 270), 3)
            pygame.draw.line(f, edge, (0, 226), (LW, 226), 1)           # window sill line
            for y in range(290, LH, 6):                                 # speaker grille
                pygame.draw.line(f, lerp_color(base, (0, 0, 0), 0.3), (30, y), (110, y), 1)
            return f

        self.frame = paint(INTERIOR, INTERIOR_EDGE)
        self.frame_lit = paint(INTERIOR_LIT, lerp_color(INTERIOR_LIT, (160, 140, 110), 0.5))
        self.mask = pygame.Surface((LW, LH), pygame.SRCALPHA)           # glass-only mask
        pygame.draw.polygon(self.mask, (255, 255, 255, 255), poly)
        # faint diagonal reflections on the glass
        self.sheen = pygame.Surface((LW, LH), pygame.SRCALPHA)
        for i, a in enumerate((14, 9)):
            x0 = 70 + i * 70
            pygame.draw.polygon(self.sheen, (255, 255, 255, a), [(x0, 40), (x0 + 26, 40), (x0 - 60, 216), (x0 - 86, 216)])
        self.sheen.blit(self.mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

    def _build_mirror(self):
        """Side mirror outside the glass at the front corner: painted housing, mirror glass."""
        self.mirror_rect = pygame.Rect(20, 150, 74, 52)
        r = self.mirror_rect
        body, shade, shine = (58, 64, 80), (34, 38, 48), (92, 100, 120)
        h = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(h, shade, (0, 4, r.w, r.h - 4), border_radius=16)        # underside in shadow
        pygame.draw.rect(h, body, (1, 0, r.w - 2, r.h - 8), border_radius=16)
        pygame.draw.line(h, shine, (14, 3), (r.w - 14, 3), 2)                    # paint highlight
        self.mirror_house = h
        self.glass_rect = pygame.Rect(6, 7, r.w - 12, r.h - 19)
        self.glass_mask = pygame.Surface(self.glass_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(self.glass_mask, (255, 255, 255, 255), (0, 0, *self.glass_rect.size), border_radius=11)

    PREVIEW_AFTER = 20

    def preview(self, step):
        """Wipe a zigzag for the gallery image."""
        for _ in range(90):
            self.update(step)
        pts = [(0.2, 0.3), (0.8, 0.3), (0.25, 0.45), (0.8, 0.52), (0.12, 0.6)]
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
        # water pushed to the edge of the wipe gathers into drops
        moved = math.hypot(x1 - x0, y1 - y0)
        if p.drips > 0 and self.rng.random() < p.drips * min(1.0, moved / 10) * 0.6:
            a = self.rng.uniform(0.15, math.pi - 0.15)                 # lower half of the finger
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
        for i, k in enumerate((0.12, 0.4, 1.0, 1.0)):
            self.off[i] = (self.off[i] + p.speed * k * dt) % self.tw

        if self.finger is not None:
            self._wipe()

        # fog returns: patchy regrowth plus creep from foggy neighbours
        f = self.fog
        fmax = p.fog_max
        f += (fmax - f) * np.clip(dt / p.regrow_time * self.regrow_jit * 2.2, 0, 1)
        if p.creep > 0:
            nb = f.copy()
            nb[1:-1, 1:-1] = (f[2:, 1:-1] + f[:-2, 1:-1] + f[1:-1, 2:] + f[1:-1, :-2]) * 0.25
            f += np.maximum(nb - f, 0) * min(1.0, p.creep * dt * 3)
        np.clip(f, 0, fmax, out=f)

        # drops run down, stick, and clear a thin trail
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
    def _city(self, surf):
        surf.blit(self.sky, (0, 0))
        for layer, i in ((self.far, 0), (self.mid, 1), (self.poles, 2)):
            x0 = self.off[i] - self.tw
            surf.blit(layer, (x0, 0))
            surf.blit(layer, (x0 + self.tw, 0))
        x0 = self.off[3] - self.tw
        surf.blit(self.glows, (x0, 0), special_flags=pygame.BLEND_RGB_ADD)
        surf.blit(self.glows, (x0 + self.tw, 0), special_flags=pygame.BLEND_RGB_ADD)
        surf.blit(self.street, (0, GROUND))

    def _mirror(self, view):
        r = self.mirror_rect
        # the glass shows the street behind: a flipped slice of the view
        slice_ = view.subsurface(pygame.Rect(90, 100, 110, 110)).copy()
        img = pygame.transform.scale(pygame.transform.flip(slice_, True, False), self.glass_rect.size)
        glass = pygame.Surface(self.glass_rect.size, pygame.SRCALPHA)
        glass.blit(img, (0, 0))
        glass.fill((24, 26, 34, 0), special_flags=pygame.BLEND_RGB_ADD)          # silvered: never pitch black
        glass.blit(self.glass_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        pygame.draw.polygon(view, (30, 34, 42), [(22, 216), (34, 216), (52, 196), (40, 194)])   # mount
        view.blit(self.mirror_house, r.topleft)
        view.blit(glass, (r.x + self.glass_rect.x, r.y + self.glass_rect.y))

    def draw(self, surf):
        p = self.p
        view = self.view
        self._city(view)
        self._mirror(view)

        # fog: blurred, brightened copy of the window view, with density as alpha
        win = view.subsurface(WIN)
        tiny = pygame.transform.smoothscale(win, (max(2, self.gw // 4), max(2, self.gh // 4)))
        small = pygame.transform.smoothscale(tiny, (self.gw, self.gh))     # heavy blur: lights bloom
        rgb = pygame.surfarray.array3d(small).astype(np.float32)
        rgb = (rgb * 1.5 * (1 - p.haze * 0.55) + HAZE * p.haze * 0.55 + 6) * self.speckle   # glowing, milky
        pygame.surfarray.blit_array(self.fog_surf, np.clip(rgb, 0, 255).astype(np.uint8))
        alpha = pygame.surfarray.pixels_alpha(self.fog_surf)
        alpha[:] = np.clip(self.fog * 255, 0, 255).astype(np.uint8)
        del alpha
        fog_big = pygame.transform.smoothscale(self.fog_surf, (self.gw * CELL, self.gh * CELL))

        low = self.low
        low.blit(view, (0, 0))
        low.blit(fog_big, WIN.topleft, area=pygame.Rect(0, 0, WIN.w, WIN.h))
        for x, y, vy, stuck, life in self.drops:                        # droplets
            low.set_at((int(x), int(y)), (226, 232, 240))
            low.set_at((int(x), int(y) - 1), (150, 160, 175))
        low.blit(self.sheen, (0, 0))

        # interior, brightened as a street lamp passes the window
        low.blit(self.frame, (0, 0))
        if p.lamp_light > 0:
            centre = WIN.centerx
            near = min(abs(((lx - 15 + self.off[3] - self.tw) % self.tw) - centre) for lx in self.lamp_x)
            k = max(0.0, 1 - near / 110) ** 2 * min(1.0, p.speed / 20) * p.lamp_light
            if k > 0.01:
                self.frame_lit.set_alpha(int(min(1.0, k) * 140))
                low.blit(self.frame_lit, (0, 0))

        surf.blit(pygame.transform.scale(low, (self.w, self.h)), (0, 0))
