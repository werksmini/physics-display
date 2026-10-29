"""A flock of birds wheeling over a dusk sky (boids).

Craig Reynolds' boids: every bird follows three local rules about the
neighbours it can see, and flocking emerges with no leader.
- Separation: steer away from birds that are too close.
- Alignment: match the average heading of nearby birds.
- Cohesion: drift toward the centre of nearby birds.
Birds also steer back from the screen edges and keep their speed between a
minimum and a maximum. All birds are updated at once with NumPy (every pair
of birds is compared each step).

Touch: by default your finger is a hawk and the flock scatters from it. Set
Touch mode to 1 and it becomes food the flock swarms toward.
"""
import math

import numpy as np
import pygame

from playground.noise import lerp_color
from playground.scene import BaseScene, Param

SKY_TOP, SKY_MID, SKY_LOW = (38, 52, 92), (122, 104, 132), (236, 160, 112)
HILLS, HILLS_FAR = (24, 26, 36), (60, 56, 76)
BIRD = (22, 22, 30)


class Scene(BaseScene):
    TITLE = "Flocking birds"
    PREVIEW_TOUCH = (0.5, 0.4)
    PREVIEW_AFTER = 40
    PARAMS = [
        Param("visual_range", 75, 10, 200, 1, "Visual range", help="How far a bird can see its neighbours (px)."),
        Param("separation", 1.0, 0, 5, 0.05, "Separation"),
        Param("personal_space", 13, 2, 60, 1, "Personal space", help="Closer than this counts as too close (px)."),
        Param("alignment", 2.0, 0, 5, 0.05, "Alignment"),
        Param("cohesion", 1.4, 0, 5, 0.05, "Cohesion"),
        Param("max_speed", 170, 20, 400, 5, "Max speed"),
        Param("min_speed", 70, 0, 300, 5, "Min speed"),
        Param("edge_margin", 70, 0, 200, 5, "Edge margin"),
        Param("touch_mode", 0, 0, 1, 1, "Touch mode", help="0 = hawk (scatter), 1 = food (swarm)."),
        Param("touch_strength", 1.0, 0, 4, 0.05, "Touch strength"),
        Param("touch_range", 120, 20, 300, 5, "Touch range"),
        Param("bird_size", 7, 2, 20, 0.5, "Bird size"),
        Param("bird_count", 180, 10, 400, 10, "Birds", reset=True),
    ]

    def setup(self):
        rng = np.random.default_rng(5)
        n = int(self.p.bird_count)
        self.pos = np.stack([rng.uniform(0, self.w, n), rng.uniform(0, self.h * 0.7, n)], 1).astype(np.float32)
        ang = rng.uniform(0, 2 * math.pi, n)
        self.vel = (np.stack([np.cos(ang), np.sin(ang)], 1) * 100).astype(np.float32)
        self.phase = rng.uniform(0, 2 * math.pi, n)
        self.finger = None

        # dusk sky with layered hill silhouettes along the bottom
        self.bg = pygame.Surface((self.w, self.h))
        for y in range(self.h):
            t = y / self.h
            c = lerp_color(SKY_TOP, SKY_MID, t / 0.55) if t < 0.55 else lerp_color(SKY_MID, SKY_LOW, (t - 0.55) / 0.45)
            pygame.draw.line(self.bg, c, (0, y), (self.w, y))
        for color, base, amp, f in ((HILLS_FAR, 0.86, 26, 0.011), (HILLS, 0.92, 22, 0.017)):
            pts = [(x, self.h * base - amp * math.sin(x * f + base * 9) - amp * 0.5 * math.sin(x * f * 2.7))
                   for x in range(0, self.w + 8, 8)]
            pygame.draw.polygon(self.bg, color, pts + [(self.w, self.h), (0, self.h)])

    def touch(self, kind, x, y):
        self.finger = None if kind == "up" else np.array([x, y], dtype=np.float32)

    def update(self, dt):
        p = self.p
        pos, vel = self.pos, self.vel
        diff = pos[None, :, :] - pos[:, None, :]              # [i, j] = j - i
        d2 = (diff ** 2).sum(-1)
        np.fill_diagonal(d2, np.inf)
        seen = d2 < p.visual_range ** 2
        close = d2 < p.personal_space ** 2
        count = seen.sum(1, keepdims=True)
        has = count > 0
        count = np.maximum(count, 1)

        sep = -(diff * close[..., None]).sum(1)                 # away from too-close birds
        ali = (seen @ vel) / count - vel                        # toward neighbours' average velocity
        coh = (seen @ pos) / count - pos                        # toward neighbours' centre
        steer = (p.separation * 2.5 * sep
                 + p.alignment * 0.6 * ali * has
                 + p.cohesion * 0.5 * coh * has)

        # edges: turn back smoothly inside a margin
        m, turn = p.edge_margin, 260.0
        steer[:, 0] += np.where(pos[:, 0] < m, turn, 0) - np.where(pos[:, 0] > self.w - m, turn, 0)
        steer[:, 1] += np.where(pos[:, 1] < m, turn, 0) - np.where(pos[:, 1] > self.h * 0.85 - m, turn, 0)

        if self.finger is not None:
            away = pos - self.finger
            dist = np.sqrt((away ** 2).sum(1, keepdims=True)) + 1e-3
            fall = np.clip(1 - dist / p.touch_range, 0, 1)
            sign = 1.0 if p.touch_mode < 0.5 else -0.6
            steer += sign * p.touch_strength * 1400 * fall * away / dist

        vel += steer * dt
        speed = np.sqrt((vel ** 2).sum(1, keepdims=True)) + 1e-6
        lo, hi = min(p.min_speed, p.max_speed), p.max_speed
        vel *= np.clip(speed, lo, hi) / speed
        pos += vel * dt
        np.clip(pos[:, 0], -20, self.w + 20, out=pos[:, 0])
        np.clip(pos[:, 1], -20, self.h + 20, out=pos[:, 1])
        self.phase += dt * (6 + speed[:, 0] / 25)               # faster birds flap faster

    def draw(self, surf):
        surf.blit(self.bg, (0, 0))
        s = self.p.bird_size
        speed = np.sqrt((self.vel ** 2).sum(1)) + 1e-6
        dx, dy = self.vel[:, 0] / speed, self.vel[:, 1] / speed
        flap = 0.55 + 0.45 * np.sin(self.phase)
        px, py = -dy, dx
        bx, by = self.pos[:, 0], self.pos[:, 1]
        backx, backy = bx - dx * s * 0.7, by - dy * s * 0.7
        lx, ly = backx + px * s * flap, backy + py * s * flap - s * 0.25 * (1 - flap)
        rx, ry = backx - px * s * flap, backy - py * s * flap - s * 0.25 * (1 - flap)
        lines = pygame.draw.lines
        for pts in zip(zip(lx.tolist(), ly.tolist()), zip(bx.tolist(), by.tolist()), zip(rx.tolist(), ry.tolist())):
            lines(surf, BIRD, False, pts, 2)
