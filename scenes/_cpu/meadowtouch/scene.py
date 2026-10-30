"""A meadow seen from directly above that you can run your hand through.

Same field as "Meadow from above": each blade is a tiny 1x2-pixel stub at
rest, and anything pushing its tip stretches it into a streak; a spring pulls
it back. But here your finger doesn't steer the wind. It touches the grass:

- Press: blades around your finger are pushed outward, flattening a ring
  around it, like a hand pressed into the lawn.
- Drag: blades near your finger are also swept along the way you're moving,
  so you comb a path through the field.
- Memory: pushed blades stay bent for a while and slowly stand back up
  (Recovery time), so your strokes leave trails that heal.

The ambient weather keeps going underneath, on its own:
- Steady wind: a gentle constant breeze (Idle wind, Idle wind direction).
- Ambient swirl: a slowly changing flow field, so the field is never still.
- Breezes: local puffs that appear, drift across and fade.

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
    TITLE = "Meadow, hands in the grass"
    PARAMS = [
        Param("hand_size", 55, 10, 200, 1, "Hand size", help="Radius your finger reaches, in screen pixels."),
        Param("press", 4.0, 0, 12, 0.1, "Press strength", help="How hard blades are pushed outward."),
        Param("sweep", 1.0, 0, 4, 0.05, "Sweep strength", help="How much blades follow a moving finger."),
        Param("memory", 0.8, 0, 1, 0.05, "Trail depth", help="How bent blades stay after your finger passes."),
        Param("recovery", 7.0, 0.3, 30, 0.1, "Recovery time", help="Seconds for flattened blades to stand back up."),
        Param("idle_wind", 0.3, 0, 3, 0.05, "Idle wind", help="Steady background breeze."),
        Param("idle_direction", 135, 0, 360, 5, "Idle wind direction",
              help="Degrees: 0 blows toward the top, 90 toward the right."),
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
        self.t = 0.0
        self.breezes = []          # each: [x, y, dx, dy, age, life]

        # touch state
        self.bend = np.zeros((n, 2))                         # lasting bend left by your hand
        self.finger = None                                   # screen px
        self.finger_v = np.zeros(2)                          # screen px / second
        self.screen_pos = self.base * self.px                # blade roots in screen px

    def _idle_vec(self):
        a = math.radians(self.p.idle_direction)
        return np.array([math.sin(a), -math.cos(a)]) * self.p.idle_wind

    # ------------------------------------------------------------------ input
    def touch(self, kind, x, y):
        pos = np.array([x, y], float)
        if kind == "down":
            self.finger, self.finger_v = pos, np.zeros(2)
        elif kind == "move" and self.finger is not None:
            self.finger_v = 0.5 * self.finger_v + 0.5 * (pos - self.finger) * 60
            self.finger = pos
        elif kind == "up":
            self.finger = None

    def preview(self, step):
        """Comb an S-curve through the field for the gallery image."""
        for _ in range(60):
            self.update(step)
        pts = [(0.2, 0.15), (0.75, 0.3), (0.3, 0.55), (0.8, 0.8)]
        self.touch("down", pts[0][0] * self.w, pts[0][1] * self.h)
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            for i in range(1, 31):
                f = i / 30
                self.touch("move", (x0 + (x1 - x0) * f) * self.w, (y0 + (y1 - y0) * f) * self.h)
                self.update(step)
        self.touch("up", 0, 0)

    PREVIEW_AFTER = 15

    def _hand(self, dt):
        """Push from the finger: outward press + sweep along the drag direction."""
        p = self.p
        d = self.screen_pos - self.finger
        dist = np.sqrt((d ** 2).sum(1)) + 1e-6
        r = p.hand_size
        near = dist < r
        force = np.zeros_like(d)
        if not near.any():
            return force
        dn, distn = d[near], dist[near]
        fall = (1 - distn / r)[:, None]
        outward = dn / distn[:, None]
        sweep = self.finger_v / max(r, 1)                    # drag speed in hand-widths per second
        f = outward * p.press * fall * 4 + sweep[None, :] * p.sweep * fall * 2.5
        force[near] = f
        # leave a lasting bend in the direction the blade was pushed
        mag = np.sqrt((f ** 2).sum(1, keepdims=True)) + 1e-6
        target = f / mag * np.minimum(1.0, mag / 6) * p.memory
        grab = np.minimum(1.0, fall * 12 * dt)
        self.bend[near] += (target - self.bend[near]) * grab
        self.finger_v *= 0.85                                # held still: sweep fades
        return force

    # ----------------------------------------------------------------- update
    def update(self, dt):
        p = self.p
        self.t += dt
        bx, by = self.screen_pos[:, 0], self.screen_pos[:, 1]
        local = np.broadcast_to(self._idle_vec(), self.base.shape).copy()

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

        hand = self._hand(dt) if self.finger is not None else 0.0
        self.bend *= math.exp(-dt / p.recovery)                 # flattened blades stand back up

        # tip springs (semi-implicit Euler), 2D; rest point shifted by the lasting bend
        k = (p.stiffness * self.k_jit)[:, None]
        acc = local * WIND_FORCE + hand * WIND_FORCE - k * (self.off - self.bend) - p.damping * self.vel
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

        surf.fill((0, 0, 0))
        surf.blit(pygame.transform.scale(self.low, (self.lw * self.px, self.lh * self.px)), (0, 0))
