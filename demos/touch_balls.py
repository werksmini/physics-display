"""Touch physics demo: balls bounce in a box; tapping blasts nearby balls
outward and spawns a new one where you tapped.

Run on the Pi (fullscreen on the panel):   python3 demos/touch_balls.py
Run on a laptop (window, mouse = touch):  python3 demos/touch_balls.py --window
"""
import argparse
import random

import pygame
import pymunk

from touchinput import TouchScreen

W, H = 480, 640          # panel resolution (portrait)
FPS = 60
PHYSICS_STEPS = 2        # substeps per frame for stability
MAX_BALLS = 40
BLAST_RADIUS = 120
BLAST_STRENGTH = 900

COLORS = [(255, 107, 107), (255, 209, 102), (6, 214, 160),
          (17, 138, 178), (199, 125, 255)]


def make_walls(space, w, h):
    thickness = 10
    pts = [((0, 0), (w, 0)), ((w, 0), (w, h)), ((w, h), (0, h)), ((0, h), (0, 0))]
    for a, b in pts:
        seg = pymunk.Segment(space.static_body, a, b, thickness)
        seg.elasticity = 0.85
        seg.friction = 0.4
        space.add(seg)


def add_ball(space, pos, balls):
    radius = random.randint(12, 26)
    mass = radius * 0.1
    body = pymunk.Body(mass, pymunk.moment_for_circle(mass, 0, radius))
    body.position = pos
    shape = pymunk.Circle(body, radius)
    shape.elasticity = 0.85
    shape.friction = 0.5
    shape.color = random.choice(COLORS)
    space.add(body, shape)
    balls.append(shape)
    if len(balls) > MAX_BALLS:          # drop the oldest
        old = balls.pop(0)
        space.remove(old.body, old)


def blast(balls, pos):
    p = pymunk.Vec2d(*pos)
    for s in balls:
        delta = s.body.position - p
        dist = delta.length
        if 0 < dist < BLAST_RADIUS:
            falloff = 1 - dist / BLAST_RADIUS
            s.body.apply_impulse_at_world_point(
                delta.normalized() * BLAST_STRENGTH * falloff * s.body.mass,
                s.body.position)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", action="store_true", help="run in a window")
    args = ap.parse_args()

    pygame.init()
    if args.window:
        screen = pygame.display.set_mode((W, H))
    else:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.mouse.set_visible(False)
    w, h = screen.get_size()
    pygame.display.set_caption("touch balls")
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 22)

    space = pymunk.Space()
    space.gravity = (0, 900)
    make_walls(space, w, h)
    balls = []
    for _ in range(12):
        add_ball(space, (random.uniform(40, w - 40), random.uniform(40, h / 2)), balls)

    # On the Pi, read the touchscreen directly (handles its scale quirk).
    # On a laptop this is None and mouse/touch come through pygame instead.
    touch = None if args.window else TouchScreen.open(w, h)

    running = True
    while running:
        taps = touch.taps() if touch else []
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN and e.key in (pygame.K_ESCAPE, pygame.K_q):
                running = False
            elif touch:
                continue                               # ignore pygame's copy of touches
            elif e.type == pygame.FINGERDOWN:          # touch (normalized 0..1)
                taps.append((e.x * w, e.y * h))
            elif e.type == pygame.MOUSEBUTTONDOWN and not getattr(e, "touch", False):
                taps.append(e.pos)                     # mouse
        for tap in taps:
            blast(balls, tap)
            add_ball(space, tap, balls)

        dt = 1.0 / FPS
        for _ in range(PHYSICS_STEPS):
            space.step(dt / PHYSICS_STEPS)

        screen.fill((20, 22, 30))
        for s in balls:
            x, y = s.body.position
            pygame.draw.circle(screen, s.color, (int(x), int(y)), int(s.radius))
        screen.blit(font.render(f"{clock.get_fps():4.0f} fps  {len(balls)} balls",
                                True, (140, 140, 160)), (8, 8))
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()
