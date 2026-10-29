"""Low-resolution field of grass blowing in the wind.

How it works (see the "How real-time physics & animation work" deep dive):
- Each blade is a damped spring: an angle that wind pushes and stiffness pulls
  back upright. Integrated with semi-implicit Euler.
- Wind = a steady value (breeze, or what your finger sets) plus gusts from a
  2D noise field that drifts across the field, so gusts roll through.
- Touch: where you touch left/right of centre sets wind direction and strength.
  Let go and it eases back to the breeze.
- Everything is drawn on a small surface and scaled up for chunky pixels.
"""
import numpy as np
import pygame

from playground.scene import BaseScene, Param


class ValueNoise2D:
    """Smooth random values over 2D space (vectorised value noise)."""

    def __init__(self, seed=0, size=256):
        self.g = np.random.default_rng(seed).random((size, size)).astype(np.float32)
        self.m = size - 1

    def __call__(self, u, v):
        iu, iv = np.floor(u).astype(np.int64), np.floor(v).astype(np.int64)
        fu, fv = u - iu, v - iv
        su, sv = fu * fu * (3 - 2 * fu), fv * fv * (3 - 2 * fv)    # smoothstep
        iu0, iv0, iu1, iv1 = iu & self.m, iv & self.m, (iu + 1) & self.m, (iv + 1) & self.m
        a, b = self.g[iv0, iu0], self.g[iv0, iu1]
        c, d = self.g[iv1, iu0], self.g[iv1, iu1]
        return a + (b - a) * su + (c - a) * sv + (a - b - c + d) * su * sv


def lerp(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


SKY_TOP, SKY_HORIZON = (26, 34, 70), (226, 152, 104)
GROUND = (28, 42, 26)
BLADE_FAR, BLADE_NEAR = (40, 76, 56), (122, 188, 74)
WIND_FORCE = 6.0          # how hard wind of 1.0 pushes a blade


class Scene(BaseScene):
    TITLE = "Grass in the wind"
    PARAMS = [
        Param("breeze", 0.4, -3, 3, 0.05, "Breeze",
              help="Steady wind when nobody is touching. Negative blows left."),
        Param("touch_wind", 3.0, 0, 6, 0.1, "Touch wind",
              help="Strongest wind your finger can make at the screen edge."),
        Param("wind_response", 2.0, 0.2, 10, 0.1, "Wind response",
              help="How quickly the wind follows your finger."),
        Param("gust_strength", 1.2, 0, 4, 0.05, "Gust strength"),
        Param("gust_size", 60, 10, 200, 1, "Gust size", help="Width of a gust, in screen pixels."),
        Param("gust_speed", 40, 0, 200, 1, "Gust speed", help="How fast gusts roll across."),
        Param("stiffness", 18, 2, 80, 0.5, "Blade stiffness"),
        Param("damping", 2.5, 0, 15, 0.1, "Blade damping", help="Low = wobbly, high = settles fast."),
        Param("blade_density", 1.5, 0.3, 4, 0.1, "Blade density", reset=True),
        Param("blade_height", 80, 16, 240, 1, "Blade height", reset=True,
              help="In screen pixels, for the nearest blades."),
        Param("height_variation", 0.4, 0, 0.9, 0.05, "Height variation", reset=True),
        Param("field_depth", 0.55, 0.15, 0.9, 0.05, "Field depth", reset=True,
              help="How much of the screen is grass."),
        Param("pixel_size", 4, 1, 8, 1, "Pixel size", reset=True),
        Param("show_wind", 1, 0, 1, 1, "Show wind bar"),
    ]

    def setup(self):
        p = self.p
        self.px = int(p.pixel_size)
        self.lw, self.lh = self.w // self.px, self.h // self.px
        self.low = pygame.Surface((self.lw, self.lh))
        rng = np.random.default_rng(7)

        # blades: sorted back-to-front so near blades draw over far ones
        top = int(self.lh * (1 - p.field_depth))
        n = max(20, int(p.blade_density * self.lw * 2))
        self.by = np.sort(rng.uniform(top + 2, self.lh + 2, n))
        self.bx = rng.uniform(-2, self.lw + 2, n)
        depth = (self.by - top) / (self.lh + 2 - top)               # 0 far .. 1 near
        size = (0.4 + 0.6 * depth) * (1 - p.height_variation * rng.random(n))
        self.hgt = (p.blade_height / self.px) * size
        self.kjit = rng.uniform(0.8, 1.2, n)                         # stiffness jitter
        jitter = rng.uniform(-14, 14, n)
        self.cols = [tuple(max(0, min(255, c + j)) for c in lerp(BLADE_FAR, BLADE_NEAR, d))
                     for d, j in zip(depth, jitter)]

        self.theta = np.zeros(n)                                      # blade angle (rad)
        self.omega = np.zeros(n)                                      # angular velocity
        self.noise = ValueNoise2D(seed=3)
        self.wind = p.breeze
        self.target = None                                            # set while touching
        self.drift = 0.0
        self.t = 0.0

        # pre-render sky + ground
        self.bg = pygame.Surface((self.lw, self.lh))
        horizon = max(1, top + 4)
        for y in range(self.lh):
            c = lerp(SKY_TOP, SKY_HORIZON, min(1, y / horizon)) if y < horizon else GROUND
            pygame.draw.line(self.bg, c, (0, y), (self.lw, y))

    def touch(self, kind, x, y):
        if kind in ("down", "move"):
            self.target = (x / self.w * 2 - 1) * self.p.touch_wind
        elif kind == "up":
            self.target = None

    def update(self, dt):
        p = self.p
        target = p.breeze if self.target is None else self.target
        self.wind += (target - self.wind) * min(1.0, p.wind_response * dt)
        direction = 1.0 if self.wind >= 0 else -1.0
        self.drift += p.gust_speed * dt * direction
        self.t += dt

        # gusts: noise field sampled at each blade, sliding with the wind
        u = (self.bx * self.px - self.drift) / p.gust_size
        v = self.by * self.px / p.gust_size * 0.7 + self.t * 0.15
        gust = p.gust_strength * (self.noise(u, v) - 0.35) * direction
        wind = self.wind + gust

        # damped spring per blade, semi-implicit Euler
        accel = (wind * WIND_FORCE * np.cos(self.theta)
                 - p.stiffness * self.kjit * self.theta
                 - p.damping * self.omega)
        self.omega += accel * dt
        self.theta += self.omega * dt
        np.clip(self.theta, -1.4, 1.4, out=self.theta)

    def draw(self, surf):
        low = self.low
        low.blit(self.bg, (0, 0))
        th, h = self.theta, self.hgt * 0.5
        a1, a2 = th * 0.4, th                     # lower half bends less than the tip
        x1 = self.bx + np.sin(a1) * h
        y1 = self.by - np.cos(a1) * h
        x2 = x1 + np.sin(a2) * h
        y2 = y1 - np.cos(a2) * h
        line = pygame.draw.lines
        for c, bx, by, xa, ya, xb, yb in zip(self.cols, self.bx.tolist(), self.by.tolist(),
                                             x1.tolist(), y1.tolist(), x2.tolist(), y2.tolist()):
            line(low, c, False, ((bx, by), (xa, ya), (xb, yb)))

        if self.p.show_wind:
            cx, y = self.lw // 2, max(2, self.lh // 40)
            reach = self.lw * 0.45 * self.wind / max(self.p.touch_wind, 0.1)
            pygame.draw.line(low, (240, 236, 220), (cx, y), (cx + reach, y))
            low.set_at((cx, y), (255, 255, 255))

        surf.fill((0, 0, 0))
        surf.blit(pygame.transform.scale(low, (self.lw * self.px, self.lh * self.px)), (0, 0))
