"""A barley field in the wind, seen from eye level; run your finger through it.

Based on a photo of a barley field in France: soft blue sky with fair-weather
clouds, a field going hazy and golden toward the horizon and greener up close,
long bristly awns, and taller green wild grasses in front.

- Backdrop (drawn once): sky, distant field painted with slanted awn strokes
  and softened with a little blur for depth of field.
- Wind waves: a noise field drifts across the far field and brightens it in
  moving bands, like gusts combing the barley.
- Barley stalks: each tip is a 2D spring on the ground plane (left/right and
  toward/away), projected to the screen for a low camera. Heads nod downwind
  under their weight; near heads get long awns.
- Foreground: tall green blades, drooping grass spikelets and purple flower
  spikes, each a bending spring.
- Touch is a hand moving through the field: stalks and blades near your
  finger are pushed aside, and dragging sweeps them along.
"""
import math

import numpy as np
import pygame

from playground.noise import ValueNoise2D, lerp_color
from playground.scene import BaseScene, Param
from playground.shapes import blade_shapes, tapered_polygon

SKY_TOP, SKY_LOW = (110, 160, 218), (196, 216, 236)
FIELD_FAR, FIELD_MID, FIELD_NEAR = (214, 182, 122), (200, 160, 92), (150, 150, 74)
AWN_STROKES = [(226, 196, 136), (196, 154, 86), (178, 140, 76), (170, 168, 96), (210, 190, 120)]
STALK_FAR, STALK_NEAR = (186, 166, 104), (122, 146, 62)
HEAD_FAR, HEAD_NEAR, HEAD_LIGHT, HEAD_SHADE = (206, 186, 110), (168, 196, 86), (226, 236, 156), (112, 138, 54)
AWN_FAR, AWN_NEAR = (214, 190, 132), (204, 188, 124)
GREENS = [(44, 104, 42), (62, 128, 52), (84, 150, 64), (52, 116, 48), (98, 160, 74)]
SPIKELET = (150, 160, 100)
PURPLE, PURPLE_DARK = (150, 126, 168), (112, 90, 132)
SAMPLES = np.array([0.0, 0.4, 0.75, 1.0])
WIND_FORCE = 3.0


class Scene(BaseScene):
    TITLE = "Barley field"
    PREVIEW_TOUCH = (0.45, 0.62)
    PARAMS = [
        Param("breeze", 0.7, -3, 3, 0.05, "Breeze", help="Steady wind; negative blows left."),
        Param("gust_strength", 1.4, 0, 4, 0.05, "Gust strength"),
        Param("gust_size", 110, 15, 300, 5, "Gust size", help="In screen pixels."),
        Param("gust_speed", 60, 0, 250, 5, "Gust speed"),
        Param("wave_strength", 0.8, 0, 2, 0.05, "Wind waves", help="Light bands rolling across the far field."),
        Param("hand_size", 80, 15, 220, 5, "Hand size", help="Reach of your finger, in screen pixels."),
        Param("hand_push", 40, 0, 120, 1, "Hand push"),
        Param("hand_drag", 0.6, 0, 3, 0.05, "Hand drag"),
        Param("stiffness", 11, 2, 50, 0.5, "Stalk stiffness"),
        Param("damping", 1.8, 0, 10, 0.1, "Stalk damping", help="Low = stalks wobble after you let go."),
        Param("head_weight", 1.8, 1, 4, 0.1, "Head weight", help="Heavier heads nod more and lag."),
        Param("cloud_speed", 5, 0, 40, 1, "Cloud speed"),
        Param("stalk_count", 240, 60, 800, 10, "Barley stalks", reset=True),
        Param("stalk_height", 380, 80, 560, 10, "Stalk height", reset=True,
              help="Length of the nearest stalks, in screen pixels."),
        Param("foreground", 16, 0, 60, 1, "Foreground grasses", reset=True),
        Param("view_angle", 16, 5, 45, 1, "View angle", reset=True,
              help="Degrees the camera looks down: low = eye level."),
        Param("horizon", 0.30, 0.15, 0.5, 0.01, "Horizon height", reset=True),
        Param("pixel_size", 2, 1, 4, 1, "Pixel size", reset=True),
    ]

    # ------------------------------------------------------------------ setup
    def setup(self):
        p = self.p
        self.px = int(p.pixel_size)
        self.s = 1.0 / self.px
        self.lw, self.lh = self.w // self.px, self.h // self.px
        self.low = pygame.Surface((self.lw, self.lh))
        e = math.radians(p.view_angle)
        self.cos_e, self.sin_e = math.cos(e), math.sin(e)
        self.hy = int(self.lh * p.horizon)
        rng = self.rng = np.random.default_rng(29)
        self._build_backdrop()
        self._build_clouds()

        # barley stalks: back to front
        n = int(p.stalk_count)
        y0, y1 = self.hy + 2, self.lh * 1.15
        self.ry = y0 + (y1 - y0) * np.sort(rng.random(n)) ** 1.25    # more rows far away
        self.rx = rng.uniform(-12, self.lw + 12, n)
        d = (self.ry - y0) / (y1 - y0)
        self.depth = d
        self.L = (p.stalk_height / self.px) * (0.12 + 0.88 * d ** 1.15) * rng.uniform(0.8, 1.1, n)
        self.rest = np.stack([rng.normal(0.12, 0.1, n), rng.normal(0, 0.08, n)], 1)
        self.b = self.rest.copy()
        self.v = np.zeros((n, 2))
        self.k_jit = rng.uniform(0.8, 1.2, n)
        self.tier = np.where(d > 0.72, 2, np.where(d > 0.32, 1, 0)).tolist()   # detail by distance
        self.awns = np.where(d > 0.72, 4, np.where(d > 0.32, 2, 0)).tolist()
        self.width = np.where(d > 0.7, 2, 1)
        self.stalk_col = [lerp_color(STALK_FAR, STALK_NEAR, x) for x in d]
        self.head_col = [lerp_color(HEAD_FAR, HEAD_NEAR, x) for x in d]
        self.awn_col = [lerp_color(AWN_FAR, AWN_NEAR, x) for x in d]
        self.awn_spread = rng.uniform(0.25, 0.45, n).tolist()
        self.head_len = (self.L * (0.14 + 0.08 * d)).tolist()
        self.width_l = self.width.tolist()

        # foreground: green blades, spikelet stems and purple spikes
        s = self.s
        m = int(p.foreground)
        kinds = (["blade"] * m + ["spikelet"] * (2 if m else 0) + ["purple"] * (3 if m else 0))
        k = len(kinds)
        fx = rng.uniform(-20, 500, k)
        for i, kind in enumerate(kinds):            # accents roughly where the photo has them
            if kind == "spikelet":
                fx[i] = rng.uniform(10, 140)
            elif kind == "purple":
                fx[i] = rng.uniform(380, 470)
        self.fg_kind = kinds
        self.fg = dict(x=fx * s, y=rng.uniform(650, 720, k) * s,
                       L=np.array([rng.uniform(300, 560) if kd == "blade" else rng.uniform(420, 600)
                                   for kd in kinds]) * s,
                       a0=rng.normal(0.05, 0.22, k), curve=rng.normal(0.3, 0.3, k),
                       w=rng.uniform(5, 11, k) * s, th=np.zeros(k), om=np.zeros(k),
                       k=rng.uniform(0.8, 1.2, k))
        self.fg_col = [GREENS[i] for i in rng.integers(0, len(GREENS), k)]
        self.fg_rand = [rng.uniform(-1, 1, 12).tolist() for _ in range(k)]

        # wind state
        self.n1, self.n2, self.nwave = ValueNoise2D(seed=31), ValueNoise2D(seed=32), ValueNoise2D(seed=33)
        self.drift = 0.0
        self.t = 0.0
        self.finger = None
        self.finger_v = np.zeros(2)
        # wind-wave overlay grid (coarse, scaled up each frame)
        self.gw, self.gh = max(8, self.lw // 4), max(6, (self.lh - self.hy) // 4)
        gx, gy = np.meshgrid(np.arange(self.gw), np.arange(self.gh), indexing="ij")
        self.wave_v = gy / self.gh                                   # 0 horizon .. 1 bottom
        self.wave_gx = gx

    def _build_backdrop(self):
        lw, lh, hy, rng, s = self.lw, self.lh, self.hy, self.rng, self.s
        self.sky = pygame.Surface((lw, hy + 4))
        for y in range(hy + 4):
            pygame.draw.line(self.sky, lerp_color(SKY_TOP, SKY_LOW, (y / max(1, hy)) ** 1.3), (0, y), (lw, y))

        field = pygame.Surface((lw, lh - hy + 6))
        fh = field.get_height()
        for y in range(6, fh):
            t = (y - 6) / (fh - 6)
            c = lerp_color(FIELD_FAR, FIELD_MID, min(1, t * 2.2)) if t < 0.45 else \
                lerp_color(FIELD_MID, FIELD_NEAR, (t - 0.45) / 0.55)
            pygame.draw.line(field, c, (0, y), (lw, y))
        # awn strokes slanting downwind, bigger toward the viewer
        for _ in range(int(lw * fh * 0.9)):
            y = 6 + (fh - 6) * rng.random() ** 1.1
            t = (y - 6) / (fh - 6)
            x = rng.uniform(-5, lw + 5)
            ln = (1.5 + 9 * t ** 1.4) * rng.uniform(0.6, 1.4)
            a = rng.normal(1.05, 0.25)                                # mostly sideways, a bit up
            c = AWN_STROKES[int(rng.integers(len(AWN_STROKES)))]
            if t > 0.55 and rng.random() < 0.35:
                c = lerp_color(c, (150, 170, 90), rng.uniform(0.3, 0.7))
            pygame.draw.line(field, c, (x, y), (x + math.sin(a) * ln, y - math.cos(a) * ln))
        # depth of field: blur the far third by scaling down and back up
        band = int(fh * 0.35)
        far = field.subsurface((0, 0, lw, band)).copy()
        far = pygame.transform.smoothscale(far, (max(1, lw // 2), max(1, band // 2)))
        far = pygame.transform.smoothscale(far, (lw, band))
        field.blit(far, (0, 0))
        self.field = field.subsurface((0, 6, lw, fh - 6)).copy()
        self.field_y = hy
        # soft, ragged top edge where the field meets the sky (thin alpha strip)
        edge = pygame.Surface((lw, 8), pygame.SRCALPHA)
        for _ in range(lw * 2):
            x = rng.uniform(0, lw)
            ln = rng.uniform(1, 5)
            a = rng.normal(0.6, 0.4)
            c = lerp_color(FIELD_FAR, SKY_LOW, rng.uniform(0.0, 0.35))
            pygame.draw.line(edge, (*c, 200), (x, 8), (x + math.sin(a) * ln, 8 - math.cos(a) * ln))
        self.edge = edge

    def _build_clouds(self):
        lw, hy, rng = self.lw, self.hy, self.rng
        self.clouds = []
        for _ in range(6):
            cw = int(rng.uniform(0.28, 0.6) * lw)
            ch = int(cw * rng.uniform(0.2, 0.32)) + 4
            pad = 10
            surf = pygame.Surface((cw + 2 * pad, ch + 2 * pad), pygame.SRCALPHA)
            surf.fill((246, 248, 252, 0))          # transparent white, so soft edges don't go grey
            puffs = []
            for _ in range(int(cw / 4) + 4):
                fx = rng.uniform(0.08, 0.92)
                r = (rng.uniform(0.06, 0.16) * cw * (0.4 + math.sin(fx * math.pi))) + 2
                y = ch * 0.72 - r * rng.uniform(0.0, 0.7)
                puffs.append((fx * cw + pad, y + pad, r))
            for x, y, r in puffs:
                pygame.draw.circle(surf, (214, 224, 238, 255), (x, y + r * 0.3), r)    # soft grey underside
            for x, y, r in puffs:
                pygame.draw.circle(surf, (252, 252, 252, 255), (x - r * 0.1, y - r * 0.12), r * 0.85)
            small = pygame.transform.smoothscale(surf, (max(1, surf.get_width() // 4), max(1, surf.get_height() // 4)))
            surf = pygame.transform.smoothscale(small, surf.get_size())
            surf.set_alpha(int(rng.uniform(170, 235)))
            y = rng.uniform(-pad, max(1, hy * 0.8 - ch))
            self.clouds.append([rng.uniform(-cw, lw), y, surf])

    # ------------------------------------------------------------------ input
    def touch(self, kind, x, y):
        pos = np.array([x, y]) / self.px
        if kind == "down":
            self.finger, self.finger_v = pos, np.zeros(2)
        elif kind == "move" and self.finger is not None:
            self.finger_v = 0.6 * self.finger_v + 0.4 * (pos - self.finger) * 60
            self.finger = pos
        elif kind == "up":
            self.finger = None

    # ---------------------------------------------------------------- shapes
    def _points(self):
        b = self.b
        mag2 = np.minimum(0.9, (b ** 2).sum(1))
        up = self.L * self.cos_e * np.sqrt(1 - mag2)
        bend = SAMPLES ** 1.8
        xs = self.rx[:, None] + (b[:, 0] * self.L)[:, None] * bend[None, :]
        ys = (self.ry[:, None] - up[:, None] * SAMPLES[None, :]
              + (b[:, 1] * self.L * self.sin_e)[:, None] * bend[None, :])
        return xs, ys

    def _wind(self, sx, sy):
        """Ambient wind at screen-pixel points: (wx, wz)."""
        p = self.p
        d = 1.0 if p.breeze >= 0 else -1.0
        u = (sx - self.drift) / p.gust_size
        v = sy / p.gust_size * 0.8 + self.t * 0.2
        wx = p.breeze + p.gust_strength * (self.n1(u, v) - 0.35) * d
        wz = 0.3 * p.gust_strength * (self.n2(u * 0.7 + 50, v) - 0.5)
        return wx, wz

    def _hand(self, xs, ys, scale_z=True):
        """Push from the finger for points (n, k): returns (fx, fz) per item."""
        p = self.p
        ddx, ddy = xs - self.finger[0], ys - self.finger[1]
        dist = np.hypot(ddx, ddy)
        j = dist.argmin(1)
        rows = np.arange(len(j))
        dx, dy, d = ddx[rows, j], ddy[rows, j], dist[rows, j] + 1e-6
        r = p.hand_size / self.px
        fall = np.clip(1 - d / r, 0, 1) ** 2
        zs = 1 / max(self.sin_e, 0.3) if scale_z else 1.0
        fx = fall * (p.hand_push * dx / d + p.hand_drag * 30 * self.finger_v[0] / max(r, 1))
        fz = fall * (p.hand_push * dy / d * zs + p.hand_drag * 30 * self.finger_v[1] * zs / max(r, 1))
        return fx, fz

    # ----------------------------------------------------------------- update
    def update(self, dt):
        p = self.p
        self.t += dt
        self.drift += p.gust_speed * dt * (1 if p.breeze >= 0 else -1)
        for c in self.clouds:
            c[0] += p.cloud_speed * self.s * dt
            if c[0] > self.lw + 5:
                c[0] = -c[2].get_width() - 5

        # barley
        wx, wz = self._wind(self.rx * self.px, self.ry * self.px)
        force = np.stack([wx, wz], 1) * WIND_FORCE
        if self.finger is not None:
            xs, ys = self._points()
            fx, fz = self._hand(xs[:, 1:], ys[:, 1:])
            force[:, 0] += fx
            force[:, 1] += fz
        inv_m = 1.0 / (1 + (p.head_weight - 1) * 0.6)
        k = (p.stiffness * self.k_jit)[:, None]
        acc = (force - k * (self.b - self.rest) - p.damping * self.v) * inv_m
        self.v += acc * dt
        self.b += self.v * dt
        mag = np.hypot(self.b[:, 0], self.b[:, 1])
        over = mag > 0.92
        if over.any():
            self.b[over] *= (0.92 / mag[over])[:, None]
            self.v[over] *= 0.5

        # foreground springs (side view: horizontal force only)
        g = self.fg
        if len(g["x"]):
            mx = g["x"] + np.sin(g["a0"]) * g["L"] * 0.6
            my = g["y"] - np.cos(g["a0"]) * g["L"] * 0.6
            w, _ = self._wind(mx * self.px, my * self.px)
            f = w * 2.2
            if self.finger is not None:
                xs, ys, _ = blade_shapes(g["x"], g["y"], g["L"], g["a0"], g["curve"], g["th"], 4)
                hx, _ = self._hand(xs[:, 2:], ys[:, 2:], scale_z=False)
                f = f + hx * 0.12
            acc = f * np.cos(g["a0"] + g["th"]) - p.stiffness * 0.8 * g["k"] * g["th"] - p.damping * g["om"]
            g["om"] += acc * dt
            g["th"] += g["om"] * dt
            np.clip(g["th"], -1.3, 1.3, out=g["th"])

    # ------------------------------------------------------------------- draw
    def draw(self, surf):
        low, p = self.low, self.p
        low.blit(self.sky, (0, 0))
        for cx, cy, cs in self.clouds:
            low.blit(cs, (cx, cy))
        low.blit(self.field, (0, self.field_y))
        low.blit(self.edge, (0, self.hy - 8))
        if p.wave_strength > 0:
            self._waves(low)

        xs, ys = self._points()
        X, Y = xs.tolist(), ys.tolist()
        bx_all = self.b[:, 0].tolist()
        droop = 0.175 * p.head_weight
        line, lines = pygame.draw.line, pygame.draw.lines
        tiers, awns, spread, hlen, widths = self.tier, self.awns, self.awn_spread, self.head_len, self.width_l
        scol, hcol, acol = self.stalk_col, self.head_col, self.awn_col
        for i in range(len(X)):
            x, y = X[i], Y[i]
            tier, w = tiers[i], widths[i]
            if tier:                                       # far stalks: the field texture covers them
                lines(low, scol[i], False, ((x[0], y[0]), (x[1], y[1]), (x[2], y[2]), (x[3], y[3])), w)
            # head: continues from the tip, nodding downwind and down under its weight
            tx, ty = x[3] - x[2], y[3] - y[2]
            tl = math.hypot(tx, ty) + 1e-6
            hx = tx / tl + bx_all[i] * 0.6
            hy = ty / tl + droop
            hl = math.hypot(hx, hy) + 1e-6
            hx, hy = hx / hl, hy / hl
            L = hlen[i]
            ex, ey = x[3] + hx * L, y[3] + hy * L
            hw = w + tier + (1 if tier == 2 else 0)
            line(low, hcol[i], (x[3], y[3]), (ex, ey), max(1, hw))
            if tier == 2:                                  # braided kernels on near heads
                line(low, HEAD_SHADE, (x[3] + hy * hw * 0.5, y[3] - hx * hw * 0.5),
                     (ex + hy * hw * 0.3, ey - hx * hw * 0.3))           # shaded side
                for f in (0.22, 0.5, 0.78):
                    kx, ky = x[3] + hx * L * f, y[3] + hy * L * f
                    line(low, HEAD_LIGHT, (kx - hy * hw * 0.6, ky + hx * hw * 0.6),
                         (kx + hx * L * 0.12, ky + hy * L * 0.12))
            na = awns[i]
            if na:
                ax, ay = -hy, hx
                sp = spread[i]
                aw = L * 1.15
                col = acol[i]
                for a in range(na):
                    f = (a + 0.5) / na
                    bx, by = x[3] + hx * L * f, y[3] + hy * L * f
                    side = sp if a % 2 else -sp
                    line(low, col, (bx, by), (bx + (hx + ax * side) * aw, by + (hy + ay * side) * aw))

        self._foreground(low)
        surf.fill((0, 0, 0))
        if self.px == 1:
            surf.blit(low, (0, 0))
        else:
            surf.blit(pygame.transform.scale(low, (self.lw * self.px, self.lh * self.px)), (0, 0))

    def _waves(self, low):
        """Moving light bands on the far field (computed coarse, scaled up, added)."""
        self.frame = getattr(self, "frame", 0) + 1
        if self.frame % 2 and getattr(self, "wave_surf", None) is not None:
            low.blit(self.wave_surf, (0, self.hy), special_flags=pygame.BLEND_RGB_ADD)
            return
        p = self.p
        v = self.wave_v
        persp = 0.4 + 1.6 * v                                         # bands widen toward you
        u = (self.wave_gx * 4 * self.px - self.drift * 1.2) / (p.gust_size * 1.6) / persp
        n = self.nwave(u, v * 3.0 + self.t * 0.1)
        b = np.clip((n - 0.55) * 3.0, 0, 1) * (1 - v) ** 0.7 * p.wave_strength
        arr = np.stack([b * 46, b * 40, b * 26], -1).astype(np.uint8)
        small = pygame.surfarray.make_surface(arr)
        self.wave_surf = pygame.transform.smoothscale(small, (self.lw, self.lh - self.hy))
        low.blit(self.wave_surf, (0, self.hy), special_flags=pygame.BLEND_RGB_ADD)

    def _foreground(self, low):
        g = self.fg
        if not len(g["x"]):
            return
        s = self.s
        xs, ys, ang = blade_shapes(g["x"], g["y"], g["L"], g["a0"], g["curve"], g["th"])
        taper = (1 - np.linspace(0, 1, xs.shape[1])) ** 0.7
        for i, kind in enumerate(self.fg_kind):
            if kind == "blade":
                pygame.draw.polygon(low, self.fg_col[i], tapered_polygon(xs[i], ys[i], ang[i], g["w"][i] * taper))
                continue
            pts = list(zip(xs[i].tolist(), ys[i].tolist()))
            pygame.draw.lines(low, (70, 120, 56), False, pts, max(1, int(1.5 * s)))
            tx, ty = pts[-1]
            r = self.fg_rand[i]
            a = ang[i][-1]
            if kind == "spikelet":                      # small spikelets dangling from the top
                for j in range(6):
                    f = j / 6
                    bx = xs[i][-3] + (tx - xs[i][-3]) * f
                    by = ys[i][-3] + (ty - ys[i][-3]) * f
                    swing = g["th"][i] * 0.6 + (0.5 if j % 2 else -0.5)
                    ln = (32 + 6 * r[j]) * s
                    ex, ey = bx + math.sin(swing) * ln, by + math.cos(swing) * ln
                    pygame.draw.line(low, (90, 120, 60), (bx, by), (ex, ey), 1)        # thin hanging stalk
                    mx, my = bx + (ex - bx) * 0.55, by + (ey - by) * 0.55
                    pygame.draw.line(low, SPIKELET, (mx, my), (ex, ey), max(2, int(4 * s)))  # the spikelet
            else:                                       # purple flower spike: clusters up the stem
                for j in range(9):
                    f = 0.5 + 0.5 * j / 8
                    k = min(len(pts) - 2, int(f * (len(pts) - 1)))
                    bx, by = pts[k]
                    nx, ny = pts[k + 1]
                    bx, by = bx + (nx - bx) * (f * (len(pts) - 1) - k), by + (ny - by) * (f * (len(pts) - 1) - k)
                    off = 7 * r[j] * s
                    rad = (8 - j * 0.6) * s + 1
                    pygame.draw.ellipse(low, PURPLE_DARK, (bx + off - rad, by - rad * 0.7, rad * 2, rad * 1.4))
                    pygame.draw.ellipse(low, PURPLE, (bx + off - rad * 0.7, by - rad * 0.8, rad * 1.4, rad * 1.1))
