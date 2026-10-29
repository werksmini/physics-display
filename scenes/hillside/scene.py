"""A painted lakeside hillside: tall grass and pink plumes in the summer wind.

An original scene in a hand-painted animation style: deep blue sky with
cumulus clouds, a lake, a far shore with trees and a few houses, and a
grassy hill in the foreground.

Like hand-drawn animation, almost everything is a painted backdrop drawn
once; only the wind-touched things move:
- Clouds drift slowly across the sky and the lake glints.
- Grass blades are tapered, outlined shapes. Each bends as a damped spring
  under the ambient wind (steady breeze + noise gusts rolling across).
- Pink plumes have a stem spring and a head spring: the heavy head lags the
  stem, so plumes whip and settle after gusts.
- Touch makes a local breeze around your finger that pushes the grass away
  from it. Drag to move the breeze; it fades out after you let go.
"""
import math

import numpy as np
import pygame

from playground.noise import ValueNoise2D, lerp_color
from playground.scene import BaseScene, Param
from playground.shapes import blade_shapes

SKY_TOP, SKY_LOW = (30, 90, 178), (122, 174, 216)
CLOUD, CLOUD_SHADE, CLOUD_DEEP = (250, 250, 252), (206, 216, 232), (176, 190, 214)
SHORE, SHORE_LIGHT = (92, 146, 82), (132, 178, 96)
TREE_DARK, TREE = (26, 66, 44), (44, 98, 60)
WALL, ROOF, ROOF_DARK = (232, 214, 180), (188, 94, 62), (150, 70, 50)
LAKE, LAKE_LIGHT, LAKE_DARK, GLINT = (66, 118, 172), (100, 152, 198), (50, 96, 150), (200, 222, 238)
HILL_TOP, HILL_LOW, HILL_LINE = (126, 188, 90), (62, 136, 64), (52, 110, 58)
BLADES = [(64, 150, 74), (92, 170, 84), (124, 190, 96), (48, 124, 64), (150, 200, 112)]
OUTLINE = (28, 70, 42)
STEM = (64, 116, 62)
PLUME, PLUME_LIGHT, PLUME_MID, PLUME_DARK = (232, 116, 128), (250, 182, 180), (214, 92, 112), (170, 66, 90)
FLOWER, FLOWER_CORE, WHITE_FLOWER = (246, 228, 168), (226, 182, 96), (250, 250, 244)

HORIZON = 250          # sky/lake boundary (design px, 480x640 layout)
K = 6                  # points along each blade's centreline


class Scene(BaseScene):
    TITLE = "Lakeside hillside"
    PREVIEW_TOUCH = (0.35, 0.8)
    PARAMS = [
        Param("breeze", 0.6, -3, 3, 0.05, "Breeze", help="Ambient wind; negative blows left."),
        Param("gust_strength", 1.3, 0, 4, 0.05, "Gust strength"),
        Param("gust_size", 140, 20, 400, 5, "Gust size", help="In screen pixels."),
        Param("gust_speed", 70, 0, 250, 5, "Gust speed"),
        Param("touch_strength", 3.0, 0, 8, 0.1, "Touch breeze strength"),
        Param("touch_radius", 120, 20, 300, 5, "Touch breeze size", help="In screen pixels."),
        Param("touch_fade", 1.5, 0.2, 6, 0.1, "Touch breeze fade", help="How quickly it dies after you let go."),
        Param("stiffness", 9, 2, 40, 0.5, "Grass stiffness"),
        Param("damping", 2.2, 0, 10, 0.1, "Grass damping"),
        Param("plume_lag", 1.0, 0, 3, 0.05, "Plume head lag", help="How much plume heads trail their stems."),
        Param("cloud_speed", 6, 0, 60, 1, "Cloud speed"),
        Param("glints", 1, 0, 1, 1, "Lake glints"),
        Param("blade_count", 70, 10, 160, 5, "Foreground blades", reset=True),
        Param("plume_count", 9, 0, 24, 1, "Plumes", reset=True),
        Param("pixel_size", 1, 1, 4, 1, "Pixel size", reset=True),
    ]

    # ------------------------------------------------------------------ setup
    def setup(self):
        p = self.p
        self.px = int(p.pixel_size)
        self.s = 1.0 / self.px                       # design px -> drawing px
        self.lw, self.lh = self.w // self.px, self.h // self.px
        self.low = pygame.Surface((self.lw, self.lh))
        self.rng = rng = np.random.default_rng(23)
        self._build_backdrop()
        self._build_clouds()

        s = self.s
        # mid-distance grass along the ridge of the hill
        nm = 110
        mx = rng.uniform(-5, 485, nm)
        self.mid = dict(x=mx * s, y=(self._ridge(mx) + rng.uniform(3, 16, nm)) * s,
                        L=rng.uniform(12, 30, nm) * s, a0=rng.normal(0.15, 0.25, nm),
                        curve=rng.normal(0.25, 0.3, nm), th=np.zeros(nm), om=np.zeros(nm),
                        k=rng.uniform(0.8, 1.2, nm))
        self.mid_cols = [BLADES[i] for i in rng.integers(0, len(BLADES), nm)]

        # foreground blades rooted below the bottom edge
        nf = int(p.blade_count)
        fx = rng.uniform(-30, 510, nf)
        fy = rng.uniform(610, 720, nf)
        self.fg = dict(x=fx * s, y=fy * s, L=rng.uniform(150, 330, nf) * s,
                       a0=rng.normal(0.1, 0.32, nf), curve=rng.normal(0.35, 0.35, nf),
                       w=rng.uniform(7, 15, nf) * s, th=np.zeros(nf), om=np.zeros(nf),
                       k=rng.uniform(0.75, 1.25, nf))
        self.fg_cols = [BLADES[i] for i in rng.integers(0, len(BLADES), nf)]

        # plumes: stem spring + head spring
        npl = int(p.plume_count)
        self.pl = dict(x=rng.uniform(10, 470, npl) * s, y=rng.uniform(640, 700, npl) * s,
                       L=rng.uniform(250, 400, npl) * s, a0=rng.normal(0.06, 0.12, npl),
                       curve=rng.normal(0.12, 0.08, npl), hl=rng.uniform(52, 78, npl) * s,
                       hw=rng.uniform(14, 20, npl) * s, th=np.zeros(npl), om=np.zeros(npl),
                       hth=np.zeros(npl), hom=np.zeros(npl), k=rng.uniform(0.8, 1.2, npl))

        # flower clusters on short stems
        nfl = 9
        self.fl = dict(x=rng.uniform(20, 460, nfl) * s, y=rng.uniform(560, 660, nfl) * s,
                       L=rng.uniform(70, 150, nfl) * s, a0=rng.normal(0.1, 0.2, nfl),
                       curve=rng.normal(0.2, 0.2, nfl), th=np.zeros(nfl), om=np.zeros(nfl),
                       k=rng.uniform(1.2, 1.8, nfl), white=rng.random(nfl) < 0.3)
        self.fl_dots = [[(rng.normal(0, 5), rng.normal(0, 4)) for _ in range(int(rng.integers(3, 6)))]
                        for _ in range(nfl)]

        # draw order for foreground things: back (small root y) to front
        items = [("fg", i, y) for i, y in enumerate(self.fg["y"])]
        items += [("pl", i, y - 20 * s) for i, y in enumerate(self.pl["y"])]
        items += [("fl", i, y) for i, y in enumerate(self.fl["y"])]
        self.order = [(kind, i) for kind, i, _ in sorted(items, key=lambda it: it[2])]

        # lake glints
        ng = 46
        self.gl = dict(x=rng.uniform(0, 480, ng), y=rng.uniform(HORIZON + 8, 380, ng),
                       w=rng.uniform(5, 16, ng), ph=rng.uniform(0, 2 * math.pi, ng),
                       sp=rng.uniform(1.0, 2.6, ng))

        self.noise = ValueNoise2D(seed=41)
        self.t = 0.0
        self.drift = 0.0
        self.finger = None
        self.breeze_pos = np.array([240.0, 500.0]) * s
        self.breeze_vel = np.zeros(2)
        self.breeze_amp = 0.0

    def _ridge(self, x):
        """Top edge of the near hill (design px): rises toward the right."""
        x = np.asarray(x, dtype=float)
        return 468 - 0.19 * x - 14 * np.sin(x / 70.0) - 6 * np.sin(x / 23.0 + 1.3)

    def _build_backdrop(self):
        s, rng, lw, lh = self.s, self.rng, self.lw, self.lh
        sky = pygame.Surface((lw, int(HORIZON * s) + 1))
        for y in range(sky.get_height()):
            pygame.draw.line(sky, lerp_color(SKY_TOP, SKY_LOW, (y / s / HORIZON) ** 1.4), (0, y), (lw, y))
        self.sky = sky

        land = pygame.Surface((lw, lh), pygame.SRCALPHA)
        # lake
        pygame.draw.rect(land, LAKE, (0, HORIZON * s, lw, lh))
        for _ in range(900):
            x, y = rng.uniform(0, 480), rng.uniform(HORIZON + 2, 470)
            near = (y - HORIZON) / 220
            c = LAKE_LIGHT if rng.random() < 0.55 else LAKE_DARK
            ln = rng.uniform(4, 14) * (0.6 + near)
            pygame.draw.line(land, c, (x * s, y * s), ((x + ln) * s, y * s), max(1, int(s * (1 + near))))
        # far shore: low band of land, a promontory on the left, trees and houses
        xs = np.arange(0, 481, 4)
        top = HORIZON - 7 - 3 * np.sin(xs / 37.0) - np.where(xs < 210, 9 + 5 * np.cos(xs / 50.0), 0)
        poly = [(x * s, t * s) for x, t in zip(xs, top)] + [(480 * s, (HORIZON + 4) * s), (0, (HORIZON + 4) * s)]
        pygame.draw.polygon(land, SHORE, poly)
        pygame.draw.lines(land, SHORE_LIGHT, False, [(x * s, (t + 1) * s) for x, t in zip(xs, top)], max(1, int(2 * s)))
        pygame.draw.line(land, LAKE_DARK, (0, (HORIZON + 4) * s), (lw, (HORIZON + 4) * s), max(1, int(s)))

        def ground(x):
            return float(np.interp(x, xs, top))
        for x, hgt, wid in [(30, 40, 11), (46, 34, 10), (63, 44, 12), (150, 30, 9), (330, 26, 9), (420, 22, 8)]:
            g = ground(x)
            pygame.draw.ellipse(land, TREE_DARK, ((x - wid / 2) * s, (g - hgt) * s, wid * s, (hgt + 3) * s))
        for x, r in [(84, 9), (96, 11), (182, 8), (260, 7), (372, 9), (452, 8)]:
            g = ground(x)
            pygame.draw.circle(land, TREE, (x * s, (g - r + 2) * s), r * s)
            pygame.draw.circle(land, TREE_DARK, ((x + r * 0.4) * s, (g - r + 4) * s), r * 0.7 * s)
        for x, wid in [(112, 18), (200, 14), (236, 12), (300, 16)]:
            g = ground(x) + 1
            hgt = wid * 0.55
            pygame.draw.rect(land, WALL, ((x - wid / 2) * s, (g - hgt) * s, wid * s, hgt * s))
            pygame.draw.polygon(land, ROOF, [((x - wid / 2 - 2) * s, (g - hgt) * s), ((x + wid / 2 + 2) * s, (g - hgt) * s),
                                             ((x + wid / 4) * s, (g - hgt - wid * 0.38) * s), ((x - wid / 4) * s, (g - hgt - wid * 0.38) * s)])
            pygame.draw.line(land, ROOF_DARK, ((x - wid / 2 - 2) * s, (g - hgt) * s), ((x + wid / 2 + 2) * s, (g - hgt) * s), max(1, int(s)))
        # near hill: gradient fill below the ridge, painted strokes, ridge line
        rx = np.arange(0, 481, 3)
        ridge = self._ridge(rx)
        for x, r in zip(rx, ridge):
            for y in range(int(r), 641, 3):
                c = lerp_color(HILL_TOP, HILL_LOW, min(1, (y - r) / 260))
                pygame.draw.rect(land, c, (x * s, y * s, max(1, 3 * s) + 1, max(1, 3 * s) + 1))
        for _ in range(1400):
            x = rng.uniform(0, 480)
            y = rng.uniform(self._ridge(x) + 2, 640)
            depth = min(1, (y - self._ridge(x)) / 260)
            base = lerp_color(HILL_TOP, HILL_LOW, depth)
            j = rng.uniform(-22, 22)
            c = tuple(max(0, min(255, v + j)) for v in base)
            ln = rng.uniform(3, 9) * (0.5 + depth)
            a = rng.normal(-0.3, 0.35)
            pygame.draw.line(land, c, (x * s, y * s), ((x + math.sin(a) * ln) * s, (y - math.cos(a) * ln) * s),
                             max(1, int(s * (1 + depth))))
        pygame.draw.lines(land, HILL_LINE, False, [(x * s, r * s) for x, r in zip(rx, ridge)], max(1, int(2 * s)))

        # split: a transparent band where trees rise into the sky, opaque below
        cut = int((HORIZON + 5) * s)
        top_y = int((HORIZON - 60) * s)
        self.land_band = land.subsurface((0, top_y, lw, cut - top_y)).copy()
        self.land_band_y = top_y
        self.land_rest = pygame.Surface((lw, lh - cut))
        self.land_rest.blit(land, (0, -cut))
        self.land_rest_y = cut

    def _build_clouds(self):
        s, rng = self.s, self.rng
        self.clouds = []
        for cx, cy, wid in [(60, 70, 230), (330, 120, 200), (520, 50, 170), (210, 175, 130)]:
            hgt = wid * 0.55
            surf = pygame.Surface((int((wid + 40) * s), int((hgt + 40) * s)), pygame.SRCALPHA)
            puffs = []
            for i in range(16):
                fx = rng.uniform(0.08, 0.92)
                bulge = math.sin(fx * math.pi)                     # taller in the middle
                r = rng.uniform(0.12, 0.22) * wid * (0.6 + 0.6 * bulge)
                y = hgt + 10 - r * 0.6 - bulge * hgt * rng.uniform(0.25, 0.55)
                puffs.append((fx * wid + 20, y, r))
            for x, y, r in puffs:                                  # shaded underside
                pygame.draw.circle(surf, CLOUD_DEEP, (x * s, (y + r * 0.25) * s), r * s)
            for x, y, r in puffs:
                pygame.draw.circle(surf, CLOUD_SHADE, (x * s, (y + r * 0.08) * s), r * 0.96 * s)
            for x, y, r in puffs:                                  # bright tops
                pygame.draw.circle(surf, CLOUD, ((x - r * 0.12) * s, (y - r * 0.18) * s), r * 0.8 * s)
            pygame.draw.rect(surf, (0, 0, 0, 0), (0, int((hgt + 18) * s), surf.get_width(), surf.get_height()))
            self.clouds.append([cx * s, cy * s, surf])

    # ------------------------------------------------------------------ input
    def touch(self, kind, x, y):
        pos = np.array([x, y]) / self.px
        if kind == "down":
            self.finger = pos
            self.breeze_pos = pos.copy()
            self.breeze_vel = np.zeros(2)
        elif kind == "move" and self.finger is not None:
            self.breeze_vel = 0.6 * self.breeze_vel + 0.4 * (pos - self.finger) * 60
            self.finger = pos
            self.breeze_pos = pos.copy()
        elif kind == "up":
            self.finger = None

    # ----------------------------------------------------------------- update
    def _wind(self, x, y):
        """Horizontal wind at drawing-space points x, y (arrays)."""
        p = self.p
        sx, sy = x * self.px, y * self.px
        u = (sx - self.drift) / p.gust_size
        v = sy / p.gust_size * 0.5 + self.t * 0.15
        d = 1.0 if p.breeze >= 0 else -1.0
        w = p.breeze + p.gust_strength * (self.noise(u, v) - 0.35) * d
        if self.breeze_amp > 0.01:
            dx, dy = x - self.breeze_pos[0], y - self.breeze_pos[1]
            r = p.touch_radius * self.s
            fall = np.exp(-(dx * dx + dy * dy) / (r * r))
            outward = np.tanh(dx / (r * 0.35))                     # push away from the finger
            along = np.clip(self.breeze_vel[0] / (r * 3), -1.5, 1.5)
            w = w + self.breeze_amp * p.touch_strength * fall * (outward + along)
        return w

    def _spring(self, g, wind, force, kmul=1.0):
        p = self.p
        acc = wind * force * np.cos(g["a0"] + g["th"]) - p.stiffness * kmul * g["k"] * g["th"] - p.damping * g["om"]
        g["om"] += acc * self.dt
        g["th"] += g["om"] * self.dt
        np.clip(g["th"], -1.3, 1.3, out=g["th"])
        return acc

    def update(self, dt):
        p = self.p
        self.dt = dt
        self.t += dt
        self.drift += p.gust_speed * dt * (1 if p.breeze >= 0 else -1)
        target = 1.0 if self.finger is not None else 0.0
        rate = 6.0 if target > self.breeze_amp else p.touch_fade
        self.breeze_amp += (target - self.breeze_amp) * min(1.0, rate * dt)
        self.breeze_vel *= 0.94

        for c in self.clouds:
            c[0] += p.cloud_speed * self.s * dt
            if c[0] > self.lw + 20:
                c[0] = -c[2].get_width() - 20
        self.gl["ph"] += self.gl["sp"] * dt

        for g, force in ((self.mid, 3.0), (self.fg, 2.4), (self.fl, 2.0)):
            mx = g["x"] + np.sin(g["a0"]) * g["L"] * 0.6
            my = g["y"] - np.cos(g["a0"]) * g["L"] * 0.6
            self._spring(g, self._wind(mx, my), force)

        pl = self.pl
        if len(pl["x"]):
            tx = pl["x"] + np.sin(pl["a0"]) * pl["L"]
            ty = pl["y"] - np.cos(pl["a0"]) * pl["L"]
            w = self._wind(tx, ty)
            acc_s = self._spring(pl, w, 2.2)
            # head: its own spring, kicked backwards by the stem's acceleration
            acc_h = (w * 3.5 - p.stiffness * 1.4 * pl["hth"] - p.damping * 0.6 * pl["hom"]
                     - p.plume_lag * 0.8 * acc_s)
            pl["hom"] += acc_h * dt
            pl["hth"] += pl["hom"] * dt
            np.clip(pl["hth"], -1.2, 1.2, out=pl["hth"])

    # ------------------------------------------------------------------- draw
    def draw(self, surf):
        low, s = self.low, self.s
        low.blit(self.sky, (0, 0))
        for cx, cy, cs in self.clouds:
            low.blit(cs, (cx, cy))
        low.blit(self.land_band, (0, self.land_band_y))
        low.blit(self.land_rest, (0, self.land_rest_y))

        if self.p.glints:
            g = self.gl
            vis = np.sin(g["ph"]) > 0.55
            for x, y, w in zip(g["x"][vis], g["y"][vis], g["w"][vis]):
                pygame.draw.line(low, GLINT, (x * s, y * s), ((x + w) * s, y * s), max(1, int(s * 1.5)))

        m = self.mid
        xs, ys, _ = blade_shapes(m["x"], m["y"], m["L"], m["a0"], m["curve"], m["th"], 3)
        for c, x, y in zip(self.mid_cols, xs.tolist(), ys.tolist()):
            pygame.draw.lines(low, c, False, list(zip(x, y)), max(1, int(2 * s)))

        f = self.fg
        fxs, fys, fang = blade_shapes(f["x"], f["y"], f["L"], f["a0"], f["curve"], f["th"], K)
        pl = self.pl
        if len(pl["x"]):
            pxs, pys, pang = blade_shapes(pl["x"], pl["y"], pl["L"], pl["a0"], pl["curve"], pl["th"], K)
        fl = self.fl
        lxs, lys, _ = blade_shapes(fl["x"], fl["y"], fl["L"], fl["a0"], fl["curve"], fl["th"], 3)

        t = np.linspace(0, 1, K + 1)
        taper = (1 - t) ** 0.8
        for kind, i in self.order:
            if kind == "fg":
                self._blade(low, fxs[i], fys[i], fang[i], f["w"][i] * taper, self.fg_cols[i])
            elif kind == "pl":
                self._plume(low, pxs[i], pys[i], pang[i], i)
            else:
                self._flower(low, lxs[i], lys[i], i)

        surf.fill((0, 0, 0))
        if self.px == 1:
            surf.blit(low, (0, 0))
        else:
            surf.blit(pygame.transform.scale(low, (self.lw * self.px, self.lh * self.px)), (0, 0))

    def _blade(self, low, xs, ys, ang, widths, col):
        a = np.concatenate([ang, ang[-1:]])
        nx, ny = np.cos(a) * widths / 2, np.sin(a) * widths / 2
        left = list(zip((xs + nx).tolist(), (ys + ny).tolist()))
        right = list(zip((xs - nx).tolist(), (ys - ny).tolist()))
        poly = left + right[-2::-1]
        pygame.draw.polygon(low, col, poly)
        pygame.draw.polygon(low, OUTLINE, poly, 1)

    def _plume(self, low, xs, ys, ang, i):
        s, pl = self.s, self.pl
        pygame.draw.lines(low, STEM, False, list(zip(xs.tolist(), ys.tolist())), max(1, int(2 * s)))
        # heads point a little more upright than the stem's bend, plus their own swing
        a = ang[-1] * 0.7 + pl["hth"][i] + 0.06
        hl, hw = pl["hl"][i], pl["hw"][i]
        bx, by = xs[-1], ys[-1]
        dx, dy = math.sin(a), -math.cos(a)
        nx, ny = -dy, dx

        def prof(f):          # half-width profile: swells low, tapers to a point
            return hw * 0.5 * (math.sin(min(1.0, f / 0.3) * math.pi / 2) if f < 0.3
                               else (1 - (f - 0.3) / 0.7) ** 0.85)

        core = []
        fs = (0.0, 0.12, 0.3, 0.55, 0.8, 1.0)
        for f in fs:
            core.append((bx + dx * hl * f + nx * prof(f) * 0.55, by + dy * hl * f + ny * prof(f) * 0.55))
        for f in fs[::-1]:
            core.append((bx + dx * hl * f - nx * prof(f) * 0.55, by + dy * hl * f - ny * prof(f) * 0.55))
        pygame.draw.polygon(low, PLUME, core)
        lw = max(1, int(1.5 * s))
        for j, f in enumerate(np.linspace(0.06, 0.94, 12)):     # feathers, swept back
            cx, cy = bx + dx * hl * f, by + dy * hl * f
            col = PLUME_LIGHT if j % 2 else PLUME_MID
            for side in (-1, 1):
                w = prof(f) * 1.05
                ex = cx + nx * side * w - dx * hl * 0.09
                ey = cy + ny * side * w - dy * hl * 0.09
                pygame.draw.line(low, col, (cx, cy), (ex, ey), lw)
        pygame.draw.line(low, PLUME_DARK, (bx, by), (bx + dx * hl * 0.7, by + dy * hl * 0.7), max(1, int(s)))

    def _flower(self, low, xs, ys, i):
        s = self.s
        pygame.draw.lines(low, STEM, False, list(zip(xs.tolist(), ys.tolist())), max(1, int(s * 1.5)))
        hx, hy = xs[-1], ys[-1]
        white = self.fl["white"][i]
        for ox, oy in self.fl_dots[i]:
            r = (3.5 if white else 5) * s
            pygame.draw.circle(low, WHITE_FLOWER if white else FLOWER, (hx + ox * s, hy + oy * s), r)
            if not white:
                pygame.draw.circle(low, FLOWER_CORE, (hx + ox * s + r * 0.2, hy + oy * s + r * 0.3), max(1, r * 0.35))
