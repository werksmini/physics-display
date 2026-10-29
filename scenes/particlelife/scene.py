"""Particle life: coloured particles that chase and flee each other by type.

Each particle has a type (a colour). A random table says how much each type
is attracted to (positive) or repelled by (negative) every other type,
including its own. From those few numbers, cells, worms, chasers and orbiting
clusters emerge. Every particle also pushes away from anything very close,
so they don't collapse into a point.

The force between two particles, at distance d within the interaction range:
  - closer than Beta x range: repel (keeps particles apart)
  - further out: attract or repel by the table value, strongest in the middle
    of the range and fading to zero at its edge
The world wraps around: leaving one edge brings you back on the other.

Touch: drag to stir particles along with your finger; tap to scatter them.
Change Seed in the panel for a new random rule table (a whole new 'world').
"""
import colorsys

import numpy as np
import pygame

from playground.scene import BaseScene, Param


class Scene(BaseScene):
    TITLE = "Particle life"
    PREVIEW_AFTER = 480                    # let the creatures form first
    PARAMS = [
        Param("seed", 14, 0, 999, 1, "Seed", reset=True, help="A different seed = a different rule table."),
        Param("types", 5, 2, 8, 1, "Types", reset=True),
        Param("count", 320, 40, 900, 10, "Particles", reset=True),
        Param("radius", 95, 10, 200, 1, "Interaction range", help="In screen pixels."),
        Param("beta", 0.3, 0.05, 0.9, 0.01, "Beta", help="Fraction of the range where particles repel."),
        Param("force", 1.2, 0, 4, 0.05, "Force"),
        Param("friction", 0.06, 0.01, 1, 0.01, "Friction", help="Velocity half-life in seconds (smaller = more friction)."),
        Param("trail", 0.75, 0, 0.97, 0.01, "Trails", help="0 = no trails, 0.95 = long glowing trails."),
        Param("dot_size", 2, 1, 4, 1, "Dot size"),
        Param("touch_range", 90, 20, 300, 5, "Touch range"),
        Param("pixel_size", 2, 1, 4, 1, "Pixel size", reset=True),
    ]

    def setup(self):
        p = self.p
        rng = np.random.default_rng(int(p.seed))
        self.px = int(p.pixel_size)
        self.lw, self.lh = self.w // self.px, self.h // self.px
        k, n = int(p.types), int(p.count)
        self.table = rng.uniform(-1, 1, (k, k)).astype(np.float32)
        self.kind = rng.integers(0, k, n)
        self.pos = np.stack([rng.uniform(0, self.w, n), rng.uniform(0, self.h, n)], 1).astype(np.float32)
        self.vel = np.zeros((n, 2), np.float32)
        hues = np.linspace(0, 1, k, endpoint=False) + 0.03
        self.colors = np.array([[int(c * 255) for c in colorsys.hsv_to_rgb(h, 0.65, 1.0)] for h in hues],
                               np.float32)[self.kind]
        self.img = np.zeros((self.lw, self.lh, 3), np.float32)
        self.low = pygame.Surface((self.lw, self.lh))
        self.finger = None
        self.finger_v = np.zeros(2, np.float32)
        self.burst = None

    def touch(self, kind, x, y):
        pos = np.array([x, y], np.float32)
        if kind == "down":
            self.finger, self.finger_v, self.burst = pos, np.zeros(2, np.float32), pos
        elif kind == "move" and self.finger is not None:
            self.finger_v = 0.5 * self.finger_v + 0.5 * (pos - self.finger) * 60
            self.finger = pos
        elif kind == "up":
            self.finger = None

    def update(self, dt):
        p = self.p
        pos, vel = self.pos, self.vel
        W, H, R = self.w, self.h, p.radius
        # cheap pass over every pair: wrapped offsets and squared distance
        dx = pos[None, :, 0] - pos[:, None, 0]                    # [i, j] = j - i
        dy = pos[None, :, 1] - pos[:, None, 1]
        dx -= W * (dx > W / 2)
        dx += W * (dx < -W / 2)
        dy -= H * (dy > H / 2)
        dy += H * (dy < -H / 2)
        d2 = dx * dx + dy * dy
        near = d2 < R * R
        np.fill_diagonal(near, False)
        i, j = np.nonzero(near)                                   # only pairs within range
        ddx, ddy = dx[i, j], dy[i, j]
        d = np.sqrt(d2[i, j]) + 1e-6
        r = d / R
        beta = p.beta
        a = self.table[self.kind[i], self.kind[j]]
        f = np.where(r < beta, r / beta - 1, a * (1 - np.abs(2 * r - 1 - beta) / (1 - beta)))
        k = R * p.force * 10 / d * f
        n = len(pos)
        acc = np.stack([np.bincount(i, ddx * k, n), np.bincount(i, ddy * k, n)], 1).astype(np.float32)

        if self.finger is not None:
            off = pos - self.finger
            dist = np.sqrt((off ** 2).sum(1, keepdims=True)) + 1e-3
            fall = np.clip(1 - dist / p.touch_range, 0, 1)
            acc += fall * self.finger_v * 8
        if self.burst is not None:                                # tap: scatter outward
            off = pos - self.burst
            dist = np.sqrt((off ** 2).sum(1, keepdims=True)) + 1e-3
            vel += np.clip(1 - dist / p.touch_range, 0, 1) * off / dist * 400
            self.burst = None

        vel *= 0.5 ** (dt / p.friction)
        vel += acc * dt
        pos += vel * dt
        pos[:, 0] %= W
        pos[:, 1] %= H

    def draw(self, surf):
        p = self.p
        img = self.img
        img *= p.trail
        x = (self.pos[:, 0] / self.px).astype(np.int32) % self.lw
        y = (self.pos[:, 1] / self.px).astype(np.int32) % self.lh
        size = int(p.dot_size)
        for ox in range(size):
            for oy in range(size):
                img[(x + ox) % self.lw, (y + oy) % self.lh] = self.colors
        pygame.surfarray.blit_array(self.low, img.astype(np.uint8))
        if self.px == 1:
            surf.blit(self.low, (0, 0))
        else:
            surf.blit(pygame.transform.scale(self.low, (self.lw * self.px, self.lh * self.px)), (0, 0))
