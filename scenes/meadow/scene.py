"""A meadow seen from directly above.

Each blade is a tiny 1x2-pixel stub at rest. Wind pushes its tip sideways, so
from above it stretches into a streak pointing downwind; a spring pulls it back.

Wind at each blade is the sum of three things:
- Global wind: touch sets it. It blows from the centre of the screen toward
  your finger (any direction, 360 degrees); further from centre = stronger.
  Let go and it eases back to the idle wind.
- Ambient swirl: a slowly changing flow field (noise gives an angle and a
  strength everywhere), so the field is never perfectly still.
- Breezes: local puffs that appear, drift across in their own direction,
  and fade, pushing the blades they pass over.

Rendering is fully vectorised: every blade is sampled at a few points from
root to tip and written straight into a pixel array, so thousands of blades
stay cheap.
"""
import math

import numpy as np
import pygame

from playground.noise import ValueNoise2D
from playground.scene import BaseScene, Param

PALETTES = [  # (ground, ground variation, blade root, blade tip)
    ((34, 56, 30), (52, 80, 40), (44, 92, 42), (168, 214, 104)),     # summer
    ((30, 34, 46), (48, 46, 60), (48, 74, 70), (226, 176, 120)),     # dusk
    ((46, 58, 66), (70, 84, 92), (110, 140, 140), (232, 244, 246)),  # frost
]
REST = np.array([0.0, -1.0])       # a resting blade leans one pixel 'up': 1x2 px
WIND_FORCE = 3.5                   # full touch wind bends a blade to ~3/4 stretch,
                                   # leaving headroom for breezes to show
EDGE = 8                           # blades beyond the screen edge fill in when blown inward


class Scene(BaseScene):
    TITLE = "Meadow from above"
    PREVIEW_TOUCH = (0.85, 0.2)            # finger held here for the preview image
    PARAMS = [
        Param("touch_wind", 3.0, 0, 6, 0.1, "Touch wind",
              help="Wind strength at the screen edge. Direction: centre toward your finger."),
        Param("idle_wind", 0.3, 0, 3, 0.05, "Idle wind", help="Wind when nobody is touching."),
        Param("idle_direction", 135, 0, 360, 5, "Idle wind direction",
              help="Degrees: 0 blows toward the top, 90 toward the right."),
        Param("wind_response", 2.0, 0.2, 10, 0.1, "Wind response"),
        Param("ambient_strength", 0.6, 0, 3, 0.05, "Ambient swirl"),
        Param("ambient_size", 140, 20, 400, 5, "Swirl size", help="In screen pixels."),
        Param("ambient_speed", 0.15, 0, 1.5, 0.01, "Swirl speed"),
        Param("breeze_rate", 0.7, 0, 4, 0.05, "Breezes per second"),
        Param("breeze_strength", 2.2, 0, 6, 0.1, "Breeze strength"),
        Param("breeze_size", 70, 10, 250, 5, "Breeze size", help="Radius in screen pixels."),
        Param("breeze_speed", 70, 0, 300, 5, "Breeze drift speed"),
        Param("blade_length", 4.5, 1, 14, 0.5, "Blade length", help="Full stretch, in big pixels."),
        Param("stiffness", 14, 2, 60, 0.5, "Blade stiffness"),
        Param("damping", 3.0, 0, 15, 0.1, "Blade damping"),
        Param("spacing", 2.6, 1.2, 6, 0.1, "Blade spacing", reset=True, help="In big pixels."),
        Param("pixel_size", 4, 1, 8, 1, "Pixel size", reset=True),
        Param("palette", 0, 0, 2, 1, "Palette", reset=True, help="0 summer, 1 dusk, 2 frost."),
        Param("show_wind", 1, 0, 1, 1, "Show wind compass"),
    ]

    # ------------------------------------------------------------------ setup
    def setup(self):
        p = self.p
        self.px = int(p.pixel_size)
        self.lw, self.lh = self.w // self.px, self.h // self.px
        self.low = pygame.Surface((self.lw, self.lh))
        ground, ground2, root, tip = PALETTES[int(p.palette)]
        rng = np.random.default_rng(11)

        # blades on a jittered grid (positions in big-pixel units)
        sp = p.spacing
        gx, gy = np.meshgrid(np.arange(-EDGE, self.lw + EDGE, sp), np.arange(-EDGE, self.lh + EDGE, sp))
        self.base = np.stack([gx.ravel(), gy.ravel()], 1) + rng.uniform(-sp / 2, sp / 2, (gx.size, 2))
        n = len(self.base)
        self.len_jit = rng.uniform(0.6, 1.15, n)            # some blades longer than others
        self.k_jit = rng.uniform(0.8, 1.25, n)              # some stiffer
        self.off = np.zeros((n, 2))                          # tip offset (normalised)
        self.vel = np.zeros((n, 2))
        tint = rng.uniform(0.82, 1.12, (n, 1))

        # colour ramp root -> tip, sampled along each blade
        self.samples = int(math.ceil(14 * 1.2)) + 2          # enough for the longest stretch
        t = np.linspace(0, 1, self.samples)[:, None]
        ramp = np.array(root) + (np.array(tip) - np.array(root)) * t ** 1.3   # (S, 3)
        self.cols = np.clip(ramp[:, None, :] * tint[None, :, :], 0, 255).astype(np.uint8)  # (S, n, 3)
        self.t_samples = t[:, 0]

        # ground texture
        nz = ValueNoise2D(seed=5)
        xs, ys = np.meshgrid(np.arange(self.lw), np.arange(self.lh), indexing="ij")
        v = 0.65 * nz(xs / 9.0, ys / 9.0) + 0.35 * rng.random((self.lw, self.lh))
        self.bg = (np.array(ground) + (np.array(ground2) - np.array(ground)) * v[..., None]).astype(np.uint8)
        self.img = self.bg.copy()

        # wind state
        self.n_angle = ValueNoise2D(seed=21)
        self.n_mag = ValueNoise2D(seed=22)
        self.wind = self._idle_vec()
        self.target = None
        self.t = 0.0
        self.breezes = []          # each: [x, y, dx, dy, age, life]

    def _idle_vec(self):
        a = math.radians(self.p.idle_direction)
        return np.array([math.sin(a), -math.cos(a)]) * self.p.idle_wind

    # ------------------------------------------------------------------ input
    def touch(self, kind, x, y):
        if kind in ("down", "move"):
            d = np.array([x - self.w / 2, y - self.h / 2])
            dist = float(np.hypot(*d))
            reach = min(self.w, self.h) / 2
            self.target = (d / dist if dist > 1 else np.zeros(2)) * min(1.0, dist / reach) * self.p.touch_wind
        elif kind == "up":
            self.target = None

    # ----------------------------------------------------------------- update
    def update(self, dt):
        p = self.p
        self.t += dt
        target = self._idle_vec() if self.target is None else self.target
        self.wind = self.wind + (target - self.wind) * min(1.0, p.wind_response * dt)

        bx, by = self.base[:, 0] * self.px, self.base[:, 1] * self.px    # screen px
        local = np.broadcast_to(self.wind, self.base.shape).copy()

        # ambient swirl: noise gives an angle and a strength that drift over time
        if p.ambient_strength > 0:
            s, drift = p.ambient_size, self.t * p.ambient_speed
            u, v = bx / s + drift, by / s - drift * 0.7
            ang = self.n_angle(u, v) * 4 * math.pi
            mag = self.n_mag(u + 37.0, v + 11.0) * p.ambient_strength
            local[:, 0] += np.cos(ang) * mag
            local[:, 1] += np.sin(ang) * mag

        # breezes: spawn, drift, fade
        if np.random.random() < p.breeze_rate * dt:
            a = np.random.uniform(0, 2 * math.pi)
            self.breezes.append([np.random.uniform(0, self.w), np.random.uniform(0, self.h),
                                 math.cos(a), math.sin(a), 0.0, np.random.uniform(2.0, 5.0)])
        alive = []
        r2 = p.breeze_size ** 2
        for b in self.breezes:
            b[0] += b[2] * p.breeze_speed * dt
            b[1] += b[3] * p.breeze_speed * dt
            b[4] += dt
            if b[4] >= b[5]:
                continue
            env = math.sin(math.pi * b[4] / b[5])           # fade in and out
            fall = np.exp(-((bx - b[0]) ** 2 + (by - b[1]) ** 2) / r2)
            push = fall * env * p.breeze_strength
            local[:, 0] += b[2] * push
            local[:, 1] += b[3] * push
            alive.append(b)
        self.breezes = alive

        # tip springs (semi-implicit Euler), 2D
        k = (p.stiffness * self.k_jit)[:, None]
        acc = local * WIND_FORCE - k * self.off - p.damping * self.vel
        self.vel += acc * dt
        self.off += self.vel * dt
        mag = np.hypot(self.off[:, 0], self.off[:, 1])
        over = mag > 1.2
        if over.any():
            self.off[over] *= (1.2 / mag[over])[:, None]

    # ------------------------------------------------------------------- draw
    def draw(self, surf):
        img = self.img
        img[:] = self.bg
        stretch = REST + self.off * (self.p.blade_length * self.len_jit)[:, None]   # root->tip
        bx, by = self.base[:, 0], self.base[:, 1]
        length = np.hypot(stretch[:, 0], stretch[:, 1])
        steps = int(min(self.samples, max(2, math.ceil(length.max()) + 1)))
        for i, t in enumerate(np.linspace(0, 1, steps)):
            xi = np.rint(bx + stretch[:, 0] * t).astype(np.int32)
            yi = np.rint(by + stretch[:, 1] * t).astype(np.int32)
            ok = (xi >= 0) & (xi < self.lw) & (yi >= 0) & (yi < self.lh)
            ci = int(round(t * (self.samples - 1)))
            img[xi[ok], yi[ok]] = self.cols[ci][ok]           # tips drawn last, on top
        pygame.surfarray.blit_array(self.low, img)

        if self.p.show_wind:
            self._compass()

        surf.fill((0, 0, 0))
        surf.blit(pygame.transform.scale(self.low, (self.lw * self.px, self.lh * self.px)), (0, 0))

    def _compass(self):
        r = max(4, self.lw // 14)
        cx, cy = self.lw - r - 3, self.lh - r - 3
        pygame.draw.circle(self.low, (20, 24, 22), (cx, cy), r)
        pygame.draw.circle(self.low, (200, 200, 190), (cx, cy), r, 1)
        m = float(np.hypot(*self.wind))
        if m > 0.02:
            d = self.wind / m
            reach = (r - 1) * min(1.0, m / max(self.p.touch_wind, 0.1))
            pygame.draw.line(self.low, (250, 240, 210), (cx, cy),
                             (cx + d[0] * reach, cy + d[1] * reach))
        self.low.set_at((cx, cy), (255, 255, 255))
