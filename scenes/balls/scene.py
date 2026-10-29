"""Rigid-body balls in a box; tap to blast them apart.

Uses pymunk (Chipmunk2D). A tap pushes nearby balls outward and spawns a new
one under your finger."""
import random

import pygame
import pymunk

from playground.scene import BaseScene, Param

COLORS = [(255, 107, 107), (255, 209, 102), (6, 214, 160),
          (17, 138, 178), (199, 125, 255)]


class Scene(BaseScene):
    TITLE = "Bouncing balls"
    PREVIEW_TOUCH = (0.5, 0.97)            # blast from the floor for the preview image
    PREVIEW_AFTER = 25                     # ...and capture mid-flight
    PARAMS = [
        Param("gravity", 900, -1500, 2000, 10, "Gravity", help="Negative falls upward."),
        Param("elasticity", 0.85, 0, 1.0, 0.01, "Bounciness"),
        Param("friction", 0.5, 0, 1.5, 0.05, "Friction"),
        Param("blast_radius", 120, 20, 400, 5, "Blast radius"),
        Param("blast_strength", 900, 0, 3000, 25, "Blast strength"),
        Param("max_balls", 40, 1, 150, 1, "Max balls"),
        Param("min_size", 12, 4, 60, 1, "Smallest ball"),
        Param("max_size", 26, 4, 80, 1, "Largest ball"),
        Param("start_balls", 12, 0, 100, 1, "Balls at start", reset=True),
    ]

    def setup(self):
        self.space = pymunk.Space()
        self.walls = []
        t = 10
        for a, b in (((0, 0), (self.w, 0)), ((self.w, 0), (self.w, self.h)),
                     ((self.w, self.h), (0, self.h)), ((0, self.h), (0, 0))):
            seg = pymunk.Segment(self.space.static_body, a, b, t)
            self.space.add(seg)
            self.walls.append(seg)
        self.balls = []
        for _ in range(int(self.p.start_balls)):
            self.add_ball((random.uniform(40, self.w - 40), random.uniform(40, self.h / 2)))

    def add_ball(self, pos):
        lo, hi = sorted((int(self.p.min_size), int(self.p.max_size)))
        r = random.randint(lo, hi)
        mass = r * 0.1
        body = pymunk.Body(mass, pymunk.moment_for_circle(mass, 0, r))
        body.position = pos
        shape = pymunk.Circle(body, r)
        shape.color = random.choice(COLORS)
        self.space.add(body, shape)
        self.balls.append(shape)
        while len(self.balls) > int(self.p.max_balls):
            old = self.balls.pop(0)
            self.space.remove(old.body, old)

    def touch(self, kind, x, y):
        if kind != "down":
            return
        p = pymunk.Vec2d(x, y)
        for s in self.balls:
            delta = s.body.position - p
            d = delta.length
            if 0 < d < self.p.blast_radius:
                k = (1 - d / self.p.blast_radius) * self.p.blast_strength * s.body.mass
                s.body.apply_impulse_at_world_point(delta.normalized() * k, s.body.position)
        self.add_ball((x, y))

    def update(self, dt):
        p = self.p
        self.space.gravity = (0, p.gravity)
        for s in self.walls + self.balls:          # live-tunable surface properties
            s.elasticity, s.friction = p.elasticity, p.friction
        for _ in range(2):
            self.space.step(dt / 2)

    def draw(self, surf):
        surf.fill((20, 22, 30))
        for s in self.balls:
            x, y = s.body.position
            pygame.draw.circle(surf, s.color, (int(x), int(y)), int(s.radius))
