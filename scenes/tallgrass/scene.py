"""A stand of tall grass seen from above and to the side; run your finger through it.

The camera looks down at the grass at an angle, as if you were standing next
to it. Far blades sit higher on the screen and are shorter; near blades are
taller and their roots run off the bottom edge.

- Each blade's tip is a 2D spring on the ground plane (left/right and
  toward/away from you). Its 3D shape is projected to the screen: bending
  sideways moves the tip left/right, bending toward you moves it down the
  screen and shortens how tall it looks.
- Ambient breeze: noise gusts roll across the stand, mostly left to right,
  with a little toward/away swirl.
- Your finger is a hand moving through the grass: blades whose upper part is
  near it are pushed away, and dragging pulls them along with the motion.
  Let go and they spring back with a wobble.
- Some blades carry grain heads. They're heavier, so they lag and sway more
  slowly.
"""
import math

import numpy as np
import pygame

from playground.noise import ValueNoise2D, lerp_color
from playground.scene import BaseScene, Param

PALETTES = [  # far ground, near ground, haze, blade base, blade tip, grain, grain light
    ((132, 128, 88), (46, 52, 30), (176, 170, 124),
     (64, 98, 48), (176, 190, 104), (214, 178, 108), (240, 214, 150)),       # late summer
    ((96, 120, 76), (30, 48, 28), (150, 172, 122),
     (40, 96, 46), (132, 196, 92), (198, 196, 120), (228, 228, 160)),        # early summer
    ((118, 92, 84), (40, 34, 38), (196, 144, 116),
     (78, 82, 58), (222, 168, 108), (232, 150, 96), (252, 200, 140)),        # evening
]
SAMPLES = np.array([0.0, 0.38, 0.72, 1.0])
WIND_FORCE = 3.2


class Scene(BaseScene):
    TITLE = "Tall grass, up close"
    PREVIEW_TOUCH = (0.5, 0.45)
    PARAMS = [
        Param("breeze", 0.5, -3, 3, 0.05, "Breeze", help="Steady wind; negative blows left."),
        Param("gust_strength", 1.4, 0, 4, 0.05, "Gust strength"),
        Param("gust_size", 90, 15, 300, 5, "Gust size", help="In screen pixels."),
        Param("gust_speed", 45, 0, 200, 5, "Gust speed"),
        Param("hand_size", 70, 15, 200, 5, "Hand size", help="Reach of your finger, in screen pixels."),
        Param("hand_push", 40, 0, 120, 1, "Hand push", help="How hard blades are pushed aside."),
        Param("hand_drag", 0.6, 0, 3, 0.05, "Hand drag", help="How much blades follow a moving finger."),
        Param("stiffness", 12, 2, 50, 0.5, "Blade stiffness"),
        Param("damping", 1.8, 0, 10, 0.1, "Blade damping", help="Low = blades wobble after you let go."),
        Param("grain_weight", 1.8, 1, 4, 0.1, "Grain weight", help="Heavier heads lag and droop more."),
        Param("grain_fraction", 0.45, 0, 1, 0.05, "Blades with grain", reset=True),
        Param("blade_count", 320, 60, 900, 10, "Blade count", reset=True),
        Param("blade_height", 300, 80, 500, 10, "Blade height", reset=True,
              help="Length of the nearest blades, in screen pixels."),
        Param("view_angle", 50, 25, 75, 1, "View angle", reset=True,
              help="Degrees the camera looks down: low = from the side, high = from above."),
        Param("pixel_size", 2, 1, 6, 1, "Pixel size", reset=True),
        Param("palette", 0, 0, 2, 1, "Palette", reset=True, help="0 late summer, 1 early summer, 2 evening."),
    ]

    # ------------------------------------------------------------------ setup
    def setup(self):
        p = self.p
        self.px = int(p.pixel_size)
        self.lw, self.lh = self.w // self.px, self.h // self.px
        self.low = pygame.Surface((self.lw, self.lh))
        e = math.radians(p.view_angle)
        self.cos_e, self.sin_e = math.cos(e), math.sin(e)
        far_g, near_g, haze, base_c, tip_c, grain_c, grain_l = PALETTES[int(p.palette)]
        self.grain_c, self.grain_l = grain_c, grain_l
        rng = np.random.default_rng(17)

        n = int(p.blade_count)
        y0, y1 = self.lh * 0.24, self.lh * 1.12            # far root row .. near (off-screen)
        self.ry = np.sort(rng.uniform(y0, y1, n))          # back-to-front draw order
        self.rx = rng.uniform(-10, self.lw + 10, n)
        depth = (self.ry - y0) / (y1 - y0)                  # 0 far .. 1 near
        self.depth = depth
        self.L = (p.blade_height / self.px) * (0.32 + 0.68 * depth) * rng.uniform(0.7, 1.05, n)
        self.rest = np.stack([rng.normal(0, 0.12, n), rng.normal(0, 0.10, n)], 1)
        self.b = self.rest.copy()                           # tip offset (fraction of length)
        self.v = np.zeros((n, 2))
        self.has_grain = rng.random(n) < p.grain_fraction
        self.k_jit = rng.uniform(0.8, 1.2, n) * np.where(self.has_grain, 0.75, 1.0)
        self.width = np.where(depth > 0.62, 2, 1)

        # colours: far blades fade toward the haze colour
        self.col_lo, self.col_hi = [], []
        for d, j in zip(depth, rng.uniform(-12, 12, n)):
            fade = (1 - d) * 0.45
            lo = lerp_color(lerp_color(base_c, tip_c, 0.15), haze, fade)
            hi = lerp_color(tip_c, haze, fade)
            self.col_lo.append(tuple(max(0, min(255, c + j)) for c in lo))
            self.col_hi.append(tuple(max(0, min(255, c + j)) for c in hi))

        # background: hazy distance at the top, darker ground toward you
        self.bg = pygame.Surface((self.lw, self.lh))
        tex = ValueNoise2D(seed=9)
        for y in range(self.lh):                            # one continuous gradient
            if y < y0:
                row = lerp_color(haze, far_g, y / max(1, y0))
            else:
                row = lerp_color(far_g, near_g, min(1.0, (y - y0) / (self.lh - y0)))
            pygame.draw.line(self.bg, row, (0, y), (self.lw, y))
        speck = pygame.PixelArray(self.bg)
        for _ in range(self.lw * self.lh // 6):
            x, y = int(rng.integers(self.lw)), int(rng.integers(int(y0 * 0.6), self.lh))
            c = self.bg.get_at((x, y))
            k = 0.82 + 0.3 * float(tex(x / 6.0, y / 6.0))
            speck[x, y] = (min(255, int(c.r * k)), min(255, int(c.g * k)), min(255, int(c.b * k)))
        del speck

        self.n1, self.n2 = ValueNoise2D(seed=31), ValueNoise2D(seed=32)
        self.drift = 0.0
        self.t = 0.0
        self.finger = None                                  # low-res coords while touching
        self.finger_v = np.zeros(2)
        self.tips = None                                    # cached screen points per blade

    # ------------------------------------------------------------------ input
    def touch(self, kind, x, y):
        pos = np.array([x / self.px, y / self.px])
        if kind == "down":
            self.finger, self.finger_v = pos, np.zeros(2)
        elif kind == "move" and self.finger is not None:
            self.finger_v = 0.6 * self.finger_v + 0.4 * (pos - self.finger) * 60   # px / second
            self.finger = pos
        elif kind == "up":
            self.finger = None

    # ---------------------------------------------------------------- shapes
    def _points(self):
        """Screen-space polyline points for every blade: arrays (n, 4) for x and y."""
        b = self.b
        mag2 = np.minimum(0.9, (b ** 2).sum(1))
        up = self.L * self.cos_e * np.sqrt(1 - mag2)       # how tall it looks
        bend = SAMPLES ** 1.8
        xs = self.rx[:, None] + (b[:, 0] * self.L)[:, None] * bend[None, :]
        ys = (self.ry[:, None] - up[:, None] * SAMPLES[None, :]
              + (b[:, 1] * self.L * self.sin_e)[:, None] * bend[None, :])
        return xs, ys

    # ----------------------------------------------------------------- update
    def update(self, dt):
        p = self.p
        self.t += dt
        self.drift += p.gust_speed * dt * (1 if p.breeze >= 0 else -1)
        sx, sy = self.rx * self.px, self.ry * self.px
        u = (sx - self.drift) / p.gust_size
        v = sy / p.gust_size * 0.8 + self.t * 0.2
        wx = p.breeze + p.gust_strength * (self.n1(u, v) - 0.35) * (1 if p.breeze >= 0 else -1)
        wz = 0.35 * p.gust_strength * (self.n2(u * 0.7 + 50, v) - 0.5)
        force = np.stack([wx, wz], 1) * WIND_FORCE

        if self.finger is not None:
            xs, ys = self._points()
            # nearest of the blade's upper sample points to the finger
            ddx, ddy = xs[:, 1:] - self.finger[0], ys[:, 1:] - self.finger[1]
            dist = np.hypot(ddx, ddy)
            j = dist.argmin(1)
            rows = np.arange(len(j))
            dx, dy, d = ddx[rows, j], ddy[rows, j], dist[rows, j] + 1e-6
            r = p.hand_size / self.px
            fall = np.clip(1 - d / r, 0, 1) ** 2
            # push away on the ground plane (screen y -> depth), plus drag along
            away = np.stack([dx / d, dy / d / max(self.sin_e, 0.3)], 1)
            drag = np.array([self.finger_v[0], self.finger_v[1] / max(self.sin_e, 0.3)]) / max(r, 1)
            force += fall[:, None] * (p.hand_push * away + p.hand_drag * 30 * drag[None, :])
            self.finger_v *= 0.9                           # finger held still: drag fades

        inv_m = np.where(self.has_grain, 1 / p.grain_weight, 1.0)[:, None]
        k = (p.stiffness * self.k_jit)[:, None]
        acc = (force - k * (self.b - self.rest) - p.damping * self.v) * inv_m
        self.v += acc * dt
        self.b += self.v * dt
        mag = np.hypot(self.b[:, 0], self.b[:, 1])
        over = mag > 0.92
        if over.any():
            self.b[over] *= (0.92 / mag[over])[:, None]
            self.v[over] *= 0.5

    # ------------------------------------------------------------------- draw
    def draw(self, surf):
        low = self.low
        low.blit(self.bg, (0, 0))
        xs, ys = self._points()
        droop = 0.6 * self.p.grain_weight
        lines, line = pygame.draw.lines, pygame.draw.line
        X, Y = xs.tolist(), ys.tolist()
        for i in range(len(X)):
            x, y, w = X[i], Y[i], int(self.width[i])
            lines(low, self.col_lo[i], False, ((x[0], y[0]), (x[1], y[1]), (x[2], y[2])), w)
            line(low, self.col_hi[i], (x[2], y[2]), (x[3], y[3]), w)
            if self.has_grain[i]:
                tx, ty = x[3] - x[2], y[3] - y[2]
                tl = math.hypot(tx, ty) + 1e-6
                hx, hy = tx / tl, ty / tl + droop * 0.35       # heads droop under their weight
                hl = math.hypot(hx, hy) + 1e-6
                L = self.L[i] * 0.13
                ex, ey = x[3] + hx / hl * L, y[3] + hy / hl * L
                mx, my = x[3] + (ex - x[3]) * 0.55, y[3] + (ey - y[3]) * 0.55
                line(low, self.grain_c, (x[3], y[3]), (mx, my), w + 1)     # plump base
                line(low, self.grain_c, (mx, my), (ex, ey), w)             # tapering tip
                px_, py_ = -hy / hl, hx / hl                               # side, for spikelets
                for f in (0.25, 0.6):
                    gx, gy = x[3] + (ex - x[3]) * f, y[3] + (ey - y[3]) * f
                    low.set_at((int(gx + px_ * (w + 0.6)), int(gy + py_ * (w + 0.6))), self.grain_l)
        surf.fill((0, 0, 0))
        surf.blit(pygame.transform.scale(low, (self.lw * self.px, self.lh * self.px)), (0, 0))
