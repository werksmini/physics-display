"""A foggy car window on a damp day in mountain farm country: wipe it to see out.

Landscape. You're in the passenger seat of a small classic 1970s sedan with a
black interior, looking out the passenger door from a slightly raised eye
height. Framed like a photo taken in a BMW 2002: a thin sliver of windshield
at the left with the wiper sweeping, a thick black A-pillar running up into a
black headliner, the triangular vent window with a chrome divider, the big
side window, a rectangular chrome mirror just past the divider whose
reflection streams with the scenery, and a black pleated door panel with a
chrome lock button, an angled door pull and a window crank.

Outside, every layer moves at its own speed (parallax), slowest far away:
low clouds, two ranges of hazy mountains with mist at their feet, a wooded
hill line, a sunflower field, a harvested straw field with windrows, and the
wet road edge rushing past. Damp and muted, with light drizzle.

Fog on the glass: a coarse density map. A heavily blurred, whitened copy of
the view is laid over the clear view with the density as its transparency.
Your finger wipes it away with soft edges; it grows back patchily and creeps
in from foggy areas, and droplets gather at wipe edges and run down.
"""
import math

import numpy as np
import pygame

from playground.noise import ValueNoise2D, lerp_color
from playground.scene import BaseScene, Param

LW, LH = 320, 240                       # drawing resolution (scaled 2x to 640x480)
WIN = pygame.Rect(44, 20, 276, 160)     # bounding box of the side glass (vent + main)
CELL = 3
TILE = LW * 2
HORIZON = 112                           # foot of the mountains, in drawing pixels

SKY_TOP, SKY_LOW = (168, 175, 184), (198, 202, 206)
CLOUD, CLOUD_SHADE = (214, 216, 220), (162, 168, 178)
MOUNTAIN_FAR, MOUNTAIN_NEAR = (152, 166, 182), (118, 136, 156)
MIST = (210, 214, 218)
HILLS, HILLS_DARK = (74, 94, 88), (56, 74, 70)
SUN_STEM, SUN_HEAD, SUN_HEAD_DARK = (78, 98, 58), (196, 166, 64), (150, 120, 50)
STRAW, STRAW_DARK, STRAW_LIGHT = (172, 148, 102), (138, 116, 80), (198, 176, 128)
ROAD, ROAD_WET, VERGE = (92, 94, 98), (120, 124, 130), (88, 96, 64)
HAZE = np.array([224, 228, 232], np.float32)

BLACK, BLACK_HI, BLACK_RIB = (20, 20, 22), (44, 44, 48), (34, 34, 38)
CHROME, CHROME_DARK, CHROME_LIGHT = (186, 192, 202), (98, 104, 116), (240, 244, 250)


def panes():
    windshield = [(0, 44), (26, 34), (16, 164), (0, 164)]
    vent = [(48, 176), (96, 40), (104, 38), (105, 176)]
    main = [(112, 176), (112, 36), (320, 20), (320, 176)]
    a_pillar = [(8, 200), (40, 200), (100, 32), (100, 14), (60, 10)]
    divider = (108, 36, 176)
    return windshield, vent, main, a_pillar, divider


class Scene(BaseScene):
    TITLE = "Foggy car window"
    LANDSCAPE = True
    PARAMS = [
        Param("speed", 60, 0, 250, 5, "Driving speed", help="0 = parked."),
        Param("regrow_time", 14, 1, 60, 0.5, "Fog return time", help="Seconds for a wiped patch to fog over."),
        Param("creep", 0.6, 0, 3, 0.05, "Fog creep"),
        Param("fog_max", 0.95, 0.3, 1, 0.01, "Fog thickness"),
        Param("haze", 0.6, 0, 1, 0.01, "Fog brightness"),
        Param("brush", 26, 6, 80, 1, "Finger size", help="In screen pixels."),
        Param("wipe", 0.85, 0.1, 1, 0.05, "Wipe strength"),
        Param("drips", 0.6, 0, 4, 0.05, "Drips from wipes"),
        Param("ambient_drips", 0.15, 0, 2, 0.05, "Random drips"),
        Param("drizzle", 1.0, 0, 3, 0.05, "Drizzle"),
        Param("wiper_speed", 0.7, 0, 2, 0.05, "Wiper speed", help="Sweeps per second; 0 = off."),
    ]
    PREVIEW_AFTER = 20

    # ------------------------------------------------------------------ setup
    def setup(self):
        self.rng = rng = np.random.default_rng(21)
        self.low = pygame.Surface((LW, LH))
        self.view = pygame.Surface((LW, LH))
        self._build_land()
        self._build_car()

        self.gw, self.gh = WIN.w // CELL + 1, WIN.h // CELL + 1
        self.fog = np.full((self.gw, self.gh), float(self.p.fog_max), np.float32)
        nz = ValueNoise2D(seed=8)
        gx, gy = np.meshgrid(np.arange(self.gw), np.arange(self.gh), indexing="ij")
        self.regrow_jit = (0.55 + 0.9 * nz(gx / 7.0, gy / 7.0)).astype(np.float32)
        self.speckle = (0.9 + 0.2 * rng.random((self.gw, self.gh))).astype(np.float32)[..., None]
        self.fog_surf = pygame.Surface((self.gw, self.gh), pygame.SRCALPHA)
        self.off = np.zeros(len(self.layers))
        self.finger = None
        self.prev = None
        self.drops = []
        self.rain = rng.uniform(0, 1, (70, 2)) * [LW, LH]
        self.ws_drops = []
        self.wiper_phase = 0.0
        self.t = 0.0

    def _build_land(self):
        rng = self.rng
        self.sky = pygame.Surface((LW, LH))
        for y in range(LH):
            pygame.draw.line(self.sky, lerp_color(SKY_TOP, SKY_LOW, min(1, y / HORIZON)), (0, y), (LW, y))

        def tile():
            return pygame.Surface((TILE, LH), pygame.SRCALPHA)

        def ridge(x, base, amps):
            return base - sum(a * math.sin(2 * math.pi * x / TILE * k + ph) for a, k, ph in amps)

        # low clouds: soft lumpy masses with darker undersides, blurred
        clouds = tile()
        clouds.fill((*CLOUD, 0))
        for _ in range(26):
            cx, cy, cw = rng.uniform(0, TILE), rng.uniform(26, 84), rng.uniform(40, 110)
            for _ in range(10):
                x, y, r = cx + rng.uniform(-cw / 2, cw / 2), cy + rng.uniform(-6, 6), rng.uniform(8, 18)
                pygame.draw.circle(clouds, (*CLOUD_SHADE, 255), (x % TILE, y + r * 0.4), r)
                pygame.draw.circle(clouds, (*CLOUD, 255), (x % TILE, y), r * 0.85)
        small = pygame.transform.smoothscale(clouds, (TILE // 6, LH // 6))
        self.clouds = pygame.transform.smoothscale(small, (TILE, LH))
        self.clouds.set_alpha(190)

        # two mountain ranges, hazy, with mist at their feet
        m_far, m_near = tile(), tile()
        far = [(x, ridge(x, 82, [(14, 2, 0.3), (7, 5, 1.1), (3, 11, 2.0)])) for x in range(0, TILE + 4, 4)]
        near = [(x, ridge(x, 98, [(10, 3, 1.7), (6, 7, 0.4), (2, 15, 0.9)])) for x in range(0, TILE + 4, 4)]
        pygame.draw.polygon(m_far, MOUNTAIN_FAR, far + [(TILE, HORIZON + 4), (0, HORIZON + 4)])
        pygame.draw.polygon(m_near, MOUNTAIN_NEAR, near + [(TILE, HORIZON + 4), (0, HORIZON + 4)])
        for y in range(HORIZON - 16, HORIZON + 4):                  # mist pooling at the mountain feet
            a = int(150 * (y - (HORIZON - 16)) / 20)
            pygame.draw.line(m_near, (*MIST, a), (0, y), (TILE, y))
        self.m_far, self.m_near = m_far, m_near

        # wooded hill line
        hills = tile()
        line = [(x, ridge(x, HORIZON + 2, [(3, 4, 0.2), (1.5, 13, 1.0)])) for x in range(0, TILE + 2, 2)]
        pygame.draw.polygon(hills, HILLS, line + [(TILE, HORIZON + 14), (0, HORIZON + 14)])
        for _ in range(500):
            x = rng.uniform(0, TILE)
            y = ridge(x, HORIZON + 2, [(3, 4, 0.2), (1.5, 13, 1.0)]) + rng.uniform(0, 10)
            pygame.draw.circle(hills, HILLS_DARK if rng.random() < 0.6 else lerp_color(HILLS, MIST, 0.15), (x, y), rng.uniform(1, 2.5))
        self.hills = hills

        # sunflower field
        sun = tile()
        top, bot = HORIZON + 10, HORIZON + 24
        pygame.draw.rect(sun, SUN_STEM, (0, top, TILE, bot - top))
        for row in range(5):
            y = top + 1 + row * 2.6
            step = 2.0 + row * 0.6
            for x in np.arange(rng.uniform(0, step), TILE, step):
                c = SUN_HEAD if rng.random() < 0.75 else SUN_HEAD_DARK
                r = 0.8 + row * 0.25
                pygame.draw.circle(sun, c, (x + rng.uniform(-0.6, 0.6), y), r)
        self.sun = sun

        # harvested straw field with windrows
        straw = tile()
        f_top, f_bot = HORIZON + 24, 168
        pygame.draw.rect(straw, STRAW, (0, f_top, TILE, f_bot - f_top))
        for _ in range(2400):
            y = f_top + (f_bot - f_top) * rng.random() ** 0.8
            t = (y - f_top) / (f_bot - f_top)
            x = rng.uniform(0, TILE)
            ln = 2 + 10 * t
            c = STRAW_DARK if rng.random() < 0.5 else STRAW_LIGHT
            pygame.draw.line(straw, c, (x, y), (x + ln, y + rng.uniform(-0.5, 0.5)), 1 if t < 0.6 else 2)
        for k in range(4):                                          # windrows: darker bands, wider toward you
            y = f_top + 4 + k * k * 2.6
            for x in range(0, TILE, 2):
                h = 1 + k * 0.8 + math.sin(x * 0.3 + k) * 0.6
                pygame.draw.line(straw, STRAW_DARK, (x, y), (x, y + h))
        self.straw = straw

        # wet road edge and verge, nearest and fastest
        road = tile()
        pygame.draw.rect(road, VERGE, (0, 166, TILE, 4))
        pygame.draw.rect(road, ROAD, (0, 170, TILE, LH - 170))
        for _ in range(500):
            x, y = rng.uniform(0, TILE), rng.uniform(166, 170)
            pygame.draw.line(road, lerp_color(VERGE, STRAW, rng.random()), (x, y), (x + rng.uniform(1, 4), y - rng.uniform(0, 5)))
        for _ in range(200):
            x, y = rng.uniform(0, TILE), rng.uniform(171, 182)
            pygame.draw.line(road, ROAD_WET, (x, y), (x + rng.uniform(6, 20), y))
        self.road = road

        # layer, speed factor (fraction of driving speed), sorted far to near
        layers = [(self.clouds, 0.015), (self.m_far, 0.03), (self.m_near, 0.06), (self.hills, 0.14),
                  (self.sun, 0.32), (self.straw, 0.6), (self.road, 1.4)]
        # crop each layer to the band it actually covers, so blending only touches that strip
        self.layers = []
        for surf, k in layers:
            box = surf.get_bounding_rect()
            band = pygame.Rect(0, box.y, TILE, box.h)
            self.layers.append((surf.subsurface(band).copy(), k, box.y))

        # the little view through the windshield sliver: sky and hazy mountains
        ahead = pygame.Surface((LW, LH), pygame.SRCALPHA)
        for y in range(LH):
            pygame.draw.line(ahead, lerp_color(SKY_TOP, SKY_LOW, min(1, y / 120)), (0, y), (LW, y))
        pygame.draw.polygon(ahead, MOUNTAIN_FAR, [(0, 110), (14, 98), (30, 106), (30, 170), (0, 170)])
        pygame.draw.rect(ahead, ROAD, (0, 140, 40, 40))
        self.ahead = ahead

    def _build_car(self):
        windshield, vent, main, a_pillar, (dx, dtop, dbot) = panes()
        rng = self.rng
        f = pygame.Surface((LW, LH), pygame.SRCALPHA)
        f.fill(BLACK)
        for _ in range(900):                                        # perforated headliner texture
            x, y = rng.uniform(60, LW), rng.uniform(0, 26)
            f.set_at((int(x), int(y)), BLACK_RIB)
        # door: smooth padded top, then horizontal pleats
        pygame.draw.rect(f, BLACK, (0, 180, LW, LH - 180))
        pygame.draw.line(f, BLACK_HI, (0, 182), (LW, 182), 1)
        for y in range(206, LH, 7):
            pygame.draw.line(f, BLACK_RIB, (60, y), (LW, y), 1)
            pygame.draw.line(f, (12, 12, 14), (60, y + 1), (LW, y + 1), 1)
        pygame.draw.line(f, BLACK_HI, (120, 198), (LW, 196), 1)     # pleat panel top seam
        # chrome lock button, angled door pull, window crank
        pygame.draw.circle(f, CHROME_DARK, (96, 194), 6)
        pygame.draw.circle(f, CHROME, (96, 194), 4)
        pygame.draw.circle(f, CHROME_LIGHT, (95, 193), 1)
        pygame.draw.line(f, (10, 10, 12), (176, 204), (200, 240), 9)
        pygame.draw.line(f, BLACK_HI, (174, 204), (198, 240), 2)
        pygame.draw.circle(f, CHROME, (176, 202), 4)
        pygame.draw.line(f, CHROME_DARK, (74, 218), (64, 232), 3)
        pygame.draw.circle(f, CHROME, (74, 218), 4)
        pygame.draw.circle(f, (14, 14, 16), (62, 234), 5)
        # cut out the glass
        for poly in (windshield, vent, main):
            pygame.draw.polygon(f, (0, 0, 0, 0), poly)
        # chrome channels: along the main window top, the divider, and the sill
        pygame.draw.line(f, CHROME_DARK, (112, 35), (320, 19), 3)
        pygame.draw.line(f, CHROME, (112, 35), (320, 19), 1)
        pygame.draw.line(f, CHROME_DARK, (dx - 3, dtop), (dx - 3, dbot), 2)
        pygame.draw.rect(f, CHROME_DARK, (dx - 1, dtop, 5, dbot - dtop))
        pygame.draw.line(f, CHROME, (dx, dtop), (dx, dbot), 2)
        pygame.draw.line(f, CHROME_LIGHT, (dx + 3, dtop), (dx + 3, dbot), 1)
        pygame.draw.line(f, CHROME_DARK, (44, 177), (LW, 177), 3)
        pygame.draw.line(f, CHROME_LIGHT, (44, 177), (LW, 176), 1)
        # A-pillar: thick, black, a soft highlight along its edge
        pygame.draw.polygon(f, BLACK, a_pillar)
        pygame.draw.line(f, BLACK_HI, (40, 200), (100, 32), 2)
        pygame.draw.line(f, BLACK_HI, (8, 200), (60, 10), 1)
        # dash corner at the lower left
        pygame.draw.polygon(f, (16, 16, 18), [(0, 164), (22, 164), (30, 240), (0, 240)])
        pygame.draw.line(f, BLACK_HI, (0, 165), (22, 165), 1)
        self.frame = f

        self.side_mask = pygame.Surface((LW, LH), pygame.SRCALPHA)
        for poly in (vent, main):
            pygame.draw.polygon(self.side_mask, (255, 255, 255, 255), poly)
        self.ws_mask = pygame.Surface((LW, LH), pygame.SRCALPHA)
        pygame.draw.polygon(self.ws_mask, (255, 255, 255, 255), windshield)
        self.sheen = pygame.Surface((LW, LH), pygame.SRCALPHA)
        for i, a in enumerate((10, 7)):
            x0 = 200 + i * 80
            pygame.draw.polygon(self.sheen, (255, 255, 255, a), [(x0, 24), (x0 + 30, 22), (x0 - 50, 176), (x0 - 80, 176)])
        self.sheen.blit(self.side_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

        # rectangular chrome mirror just past the divider
        mr = pygame.Rect(0, 0, 40, 30)
        m = pygame.Surface((mr.w, mr.h + 10), pygame.SRCALPHA)
        pygame.draw.rect(m, CHROME_DARK, (8, mr.h - 2, 6, 12))                      # arm down to the door
        pygame.draw.rect(m, CHROME_DARK, mr, border_radius=5)
        pygame.draw.rect(m, CHROME, mr.inflate(-2, -2), border_radius=4)
        pygame.draw.line(m, CHROME_LIGHT, (4, 2), (mr.w - 5, 2), 1)
        self.mirror = m
        self.mirror_glass = pygame.Rect(3, 3, mr.w - 6, mr.h - 6)
        self.mirror_pos = (116, 138)

    # ------------------------------------------------------------- preview
    def preview(self, step):
        for _ in range(90):
            self.update(step)
        pts = [(0.3, 0.2), (0.92, 0.18), (0.4, 0.4), (0.92, 0.5), (0.25, 0.64)]
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
        for i, (_, k, _y) in enumerate(self.layers):
            self.off[i] = (self.off[i] + (p.speed * k + (4 if i == 0 else 0)) * dt) % TILE   # clouds also drift
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
            self._spawn_drop(self.rng.uniform(WIN.x + 30, WIN.right - 10), self.rng.uniform(WIN.y + 20, WIN.y + 60))
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
            if d[4] > 0 and d[1] < WIN.bottom - 4:
                alive.append(d)
        self.drops = alive

        # drizzle outside; drops collect on the windshield and the wiper clears them
        self.rain[:, 0] += (30 + p.speed * 0.5) * dt
        self.rain[:, 1] += 150 * dt
        self.rain %= [LW, LH]
        if p.drizzle > 0 and self.rng.random() < p.drizzle * 10 * dt and len(self.ws_drops) < 40:
            self.ws_drops.append((self.rng.uniform(0, 26), self.rng.uniform(38, 162)))
        self.wiper_phase = (self.wiper_phase + p.wiper_speed * dt) % 1.0
        if p.wiper_speed > 0:
            ang = self._wiper_angle()
            self.ws_drops = [(x, y) for x, y in self.ws_drops
                             if abs(math.atan2(178 - y, 40 - x) - ang) > 0.12]

    def _wiper_angle(self):
        """Angle of the wiper arm from its pivot below the windshield (radians)."""
        u = self.wiper_phase
        return 2.05 + 0.9 * math.sin(u * 2 * math.pi) ** 2           # sweeps up into view and back

    # ------------------------------------------------------------------- draw
    def _land(self, surf):
        surf.blit(self.sky, (0, 0))
        for i, (layer, _, y) in enumerate(self.layers):
            x0 = self.off[i] - TILE
            surf.blit(layer, (x0, y))
            surf.blit(layer, (x0 + TILE, y))
        if self.p.drizzle > 0:
            n = int(min(len(self.rain), 25 * self.p.drizzle))
            for x, y in self.rain[:n].tolist():
                pygame.draw.line(surf, (220, 224, 230), (x, y), (x + 2, y + 6))

    def _windshield(self, low):
        ws = self.ahead.copy()
        for x, y in self.ws_drops:
            ws.set_at((int(x), int(y)), (226, 230, 236))
        if self.p.wiper_speed > 0:
            a = self._wiper_angle()
            px, py = 40, 178
            ex, ey = px + math.cos(a) * 160, py - math.sin(a) * 160
            pygame.draw.line(ws, (14, 14, 16), (px, py), (ex, ey), 2)              # arm
            bx, by = px + math.cos(a) * 60, py - math.sin(a) * 60
            pygame.draw.line(ws, (30, 30, 34), (bx, by), (ex, ey), 3)              # blade
        ws.blit(self.ws_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        low.blit(ws, (0, 0), area=pygame.Rect(0, 0, 30, 170))

    def _mirror(self, view):
        g = self.mirror_glass
        # the mirror looks back along the car: a flipped slice of the passing fields and hills
        slice_ = view.subsurface(pygame.Rect(160, 96, 80, 60)).copy()
        img = pygame.transform.scale(pygame.transform.flip(slice_, True, False), g.size)
        m = self.mirror.copy()
        m.blit(img, g.topleft)
        view.blit(m, self.mirror_pos)

    def draw(self, surf):
        p = self.p
        view = self.view
        self._land(view)
        self._mirror(view)

        win = view.subsurface(WIN)
        tiny = pygame.transform.smoothscale(win, (max(2, self.gw // 4), max(2, self.gh // 4)))
        small = pygame.transform.smoothscale(tiny, (self.gw, self.gh))
        rgb = pygame.surfarray.array3d(small).astype(np.float32)
        rgb = (rgb * (1 - p.haze * 0.7) + HAZE * p.haze * 0.7 + 6) * self.speckle
        pygame.surfarray.blit_array(self.fog_surf, np.clip(rgb, 0, 255).astype(np.uint8))
        alpha = pygame.surfarray.pixels_alpha(self.fog_surf)
        alpha[:] = np.clip(self.fog * 255, 0, 255).astype(np.uint8)
        del alpha
        fog_big = pygame.transform.smoothscale(self.fog_surf, (self.gw * CELL, self.gh * CELL))

        low = self.low
        low.blit(view, (0, 0))
        low.blit(fog_big, WIN.topleft, area=pygame.Rect(0, 0, WIN.w, WIN.h))
        for x, y, vy, stuck, life in self.drops:
            low.set_at((int(x), int(y)), (238, 240, 244))
            low.set_at((int(x), int(y) - 1), (160, 166, 176))
        low.blit(self.sheen, (0, 0))
        self._windshield(low)
        low.blit(self.frame, (0, 0))
        surf.blit(pygame.transform.scale(low, (self.w, self.h)), (0, 0))
