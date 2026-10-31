"""Lunar Lander: set the module down gently on a pad.

On-screen controls: rotate left / right with your left thumb, THRUST with your right.
Land upright (within 10 degrees), slowly (under 12 ft/s down, 8 ft/s sideways),
on a flat pad. Pads marked x2 / x3 score more. Each level the gravity gets a
little stronger and the fuel a little shorter.

Physics is hand-rolled: gravity plus thrust along the ship's nose, integrated at a
fixed 60 Hz. 1 canvas pixel = 1 ft.
"""
import math
import random

import pygame
import pygame.gfxdraw

from playground.ui import Controls, Button, HoldButton, font

W, H = 800, 360
SAFE_VY, SAFE_VX, SAFE_ANGLE = 12.0, 8.0, 10.0      # ft/s, ft/s, degrees
ROT_SPEED = 110.0                                    # degrees/s
LEGS = [(-9, 9), (9, 9)]                             # foot positions in ship coordinates
HULL = [(-7, -6), (7, -6), (8, 5), (-8, 5)]


SHIP_SCALE = 1.5                                     # ship drawn this many px per ship unit
FOOT = 9 * SHIP_SCALE                                # centre to feet, px


def rot(pts, ang, at, k=SHIP_SCALE):
    c, s = math.cos(math.radians(ang)) * k, math.sin(math.radians(ang)) * k
    return [(at[0] + x * c - y * s, at[1] + x * s + y * c) for x, y in pts]


class Game:
    TITLE = "Lunar Lander"
    COLOR = (70, 60, 110)
    SMOOTH = False                        # crisp pixels suit the vector look
    # headless screenshot: burn, tilt right, burn again
    DEMO_TOUCHES = [(10, 70, 1, 730, 300, 730, 300), (60, 80, 2, 125, 315, 125, 315),
                    (100, 140, 3, 730, 300, 730, 300)]

    @staticmethod
    def icon(surf):
        w, h = surf.get_size()
        surf.fill((8, 8, 20))
        rnd = random.Random(3)
        for _ in range(30):
            surf.set_at((rnd.randrange(w), rnd.randrange(h // 2)), (200, 200, 220))
        pts = [(0, h * .8), (w * .25, h * .6), (w * .45, h * .75), (w * .65, h * .75), (w * .8, h * .5), (w, h * .7), (w, h), (0, h)]
        pygame.draw.polygon(surf, (90, 90, 105), pts)
        pygame.draw.line(surf, (255, 220, 120), (w * .45, h * .75), (w * .65, h * .75), 3)
        ship = rot(HULL, 15, (w * .5, h * .35), 1.6)
        pygame.draw.polygon(surf, (235, 235, 240), [(x * 1, y) for x, y in ship])
        pygame.draw.polygon(surf, (255, 170, 60), rot([(-3, 6), (3, 6), (0, 16)], 15, (w * .5, h * .35), 1.6))

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.level = 1
        self.total = 0
        rnd = random.Random(7)
        self.stars = [(rnd.randrange(W), rnd.randrange(H), rnd.choice((90, 140, 220))) for _ in range(110)]
        self.ui = Controls()
        self.left = self.ui.add(HoldButton((22, 280, 70, 66), ""))
        self.right = self.ui.add(HoldButton((100, 280, 70, 66), ""))
        self.thrust = self.ui.add(HoldButton((660, 252, 120, 94), "THRUST", color=(150, 70, 30)))
        self.next_btn = self.ui.add(Button((W // 2 - 85, 196, 170, 46), "Next", on_tap=self.advance))
        self.particles = []
        self.new_level()

    # -------------------------------------------------------------- level setup
    def new_level(self):
        rnd = random.Random()
        self.gravity = 14.0 + 2.0 * (self.level - 1)              # ft/s^2
        self.power = 34.0 + 1.0 * (self.level - 1)                # thrust, ft/s^2
        self.fuel_max = max(5.0, 14.0 - 1.0 * (self.level - 1))   # seconds of burn
        self.fuel = self.fuel_max
        self.terrain, self.pads = self._terrain(rnd)
        self.pos = [rnd.uniform(220, 580), 40.0]
        self.vel = [rnd.uniform(-25, 25), 0.0]
        self.angle = 0.0                                          # degrees, 0 = upright
        self.state = "flying"                                     # flying / landed / crashed
        self.message = ""
        self.next_btn.visible = self.next_btn.enabled = False
        self.burning = False

    def _terrain(self, rnd):
        """A jagged ridge line with two or three flat pads (wider = easier, x1)."""
        widths = {1: 70, 2: 52, 3: 38}
        mult = [1, 2, 3] if self.level > 1 else [1, 2]
        slots = sorted(rnd.sample(range(190, 600, 70), len(mult)))
        pads = []
        for x, m in zip(slots, rnd.sample(mult, len(mult))):
            pw = max(26, widths[m] - 3 * (self.level - 1))
            pads.append([x, x + pw, rnd.uniform(235, 315), m])
        pts = []
        x = 0.0
        y = rnd.uniform(240, 320)
        while x <= W:
            pad = next((p for p in pads if p[0] - 4 <= x <= p[1]), None)
            if pad:
                pts += [(pad[0], pad[2]), (pad[1], pad[2])]
                x, y = pad[1] + rnd.uniform(14, 24), pad[2]
                continue
            nxt = next((p for p in pads if p[0] > x), None)
            y += rnd.uniform(-28, 28)
            if nxt and nxt[0] - x < 30:
                y = (y + nxt[2]) / 2
            y = max(170, min(340, y))
            pts.append((x, y))
            x += rnd.uniform(14, 30)
        pts.append((W, max(170, min(340, y))))
        pts.sort()
        return pts, pads

    def ground(self, x):
        t = self.terrain
        for (x0, y0), (x1, y1) in zip(t, t[1:]):
            if x0 <= x <= x1:
                return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
        return t[-1][1]

    def advance(self):
        if self.state == "landed":
            self.level += 1
        else:
            self.level, self.total = 1, 0
        self.new_level()

    # -------------------------------------------------------------- input
    def fingers(self, fingers):
        self.ui.feed(fingers)

    # -------------------------------------------------------------- update
    def update(self, dt):
        self.ui.tick(dt)
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += self.gravity * dt
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0 and p[1] < H + 10]
        if self.state != "flying":
            return
        if self.left.held:
            self.angle -= ROT_SPEED * dt
        if self.right.held:
            self.angle += ROT_SPEED * dt
        self.angle = max(-90.0, min(90.0, self.angle))
        self.burning = self.thrust.held and self.fuel > 0
        ax, ay = 0.0, self.gravity
        if self.burning:
            a = math.radians(self.angle)
            ax += math.sin(a) * self.power
            ay -= math.cos(a) * self.power
            self.fuel = max(0.0, self.fuel - dt)
            nx, ny = rot([(random.uniform(-2, 2), 9)], self.angle, self.pos)[0]
            self.particles.append([nx, ny, self.vel[0] - math.sin(a) * 90 + random.uniform(-15, 15),
                                   self.vel[1] + math.cos(a) * 90 + random.uniform(-10, 10), 0.35,
                                   (255, random.randint(140, 220), 60)])
        self.vel[0] += ax * dt
        self.vel[1] += ay * dt
        self.pos[0] += self.vel[0] * dt
        self.pos[1] += self.vel[1] * dt
        if self.pos[0] < 0:                    # wrap around the sides, like the arcade
            self.pos[0] += W
        elif self.pos[0] > W:
            self.pos[0] -= W
        self._touchdown()

    def _touchdown(self):
        feet = rot(LEGS, self.angle, self.pos)
        hull = rot(HULL, self.angle, self.pos)
        if not any(y >= self.ground(x) for x, y in feet + hull):
            return
        pad = next((p for p in self.pads if p[0] <= feet[0][0] and feet[1][0] <= p[1]), None)
        vx, vy = self.vel
        ok = (pad and abs(self.angle) <= SAFE_ANGLE and vy <= SAFE_VY and abs(vx) <= SAFE_VX
              and not any(y > self.ground(x) + 2 for x, y in hull))
        if ok:
            self.state = "landed"
            self.pos[1] = pad[2] - FOOT
            score = int((50 + 100 * self.fuel / self.fuel_max) * pad[3])
            self.total += score
            self.message = f"Landed! +{score}"
            self.next_btn.label = "Next level"
        else:
            self.state = "crashed"
            why = ("missed the pad" if not pad else
                   "too fast" if vy > SAFE_VY or abs(vx) > SAFE_VX else "not upright")
            self.message = f"Crashed: {why}"
            self.next_btn.label = "Try again"
            for _ in range(70):
                a = random.uniform(0, math.tau)
                s = random.uniform(20, 120)
                self.particles.append([self.pos[0], self.pos[1], math.cos(a) * s, math.sin(a) * s - 40,
                                       random.uniform(0.5, 1.4), random.choice(((255, 200, 80), (255, 120, 40), (220, 220, 230)))])
        self.vel = [0.0, 0.0]
        self.burning = False
        self.next_btn.visible = self.next_btn.enabled = True

    # -------------------------------------------------------------- drawing
    def draw(self, surf):
        surf.fill((6, 6, 16))
        for x, y, b in self.stars:
            surf.set_at((x, y), (b, b, b + 20))
        poly = self.terrain + [(W, H), (0, H)]
        pygame.draw.polygon(surf, (70, 70, 84), poly)
        pygame.draw.lines(surf, (170, 170, 185), False, self.terrain, 2)
        for x0, x1, y, m in self.pads:
            pygame.draw.line(surf, (255, 214, 110), (x0, y), (x1, y), 3)
            tag = font(13).render(f"x{m}", True, (255, 214, 110))
            surf.blit(tag, tag.get_rect(midtop=((x0 + x1) / 2, y + 5)))
        for x, y, vx, vy, life, c in self.particles:
            r = 2 if life > 0.3 else 1
            pygame.draw.circle(surf, c, (int(x), int(y)), r)
        if self.state != "crashed":
            self._ship(surf)
        self._hud(surf)
        self.ui.draw(surf)
        self._arrow(surf, self.left.rect, -1)
        self._arrow(surf, self.right.rect, 1)
        if self.message:
            good = self.state == "landed"
            img = font(34).render(self.message, True, (140, 235, 150) if good else (255, 130, 110))
            surf.blit(img, img.get_rect(center=(W // 2, 160)))

    def _ship(self, surf):
        p, a = self.pos, self.angle
        if self.burning:
            L = random.uniform(12, 20)
            pygame.draw.polygon(surf, (255, 170, 60), rot([(-4, 6), (4, 6), (0, 6 + L)], a, p))
            pygame.draw.polygon(surf, (255, 240, 180), rot([(-2, 6), (2, 6), (0, 6 + L * .55)], a, p))
        for (fx, fy) in LEGS:                                     # legs
            pygame.draw.aaline(surf, (200, 200, 210), rot([(fx * .6, 4)], a, p)[0], rot([(fx, fy)], a, p)[0])
        pygame.draw.polygon(surf, (225, 225, 232), rot(HULL, a, p))
        pygame.draw.polygon(surf, (120, 200, 255), rot([(-3, -4), (3, -4), (3, 0), (-3, 0)], a, p))  # window
        top = rot([(0, -10)], a, p)[0]
        pygame.draw.circle(surf, (225, 225, 232), (int(top[0]), int(top[1])), int(4 * SHIP_SCALE))

    def _arrow(self, surf, r, d):
        cx, cy = r.center
        pts = [(cx + 14 * d, cy), (cx - 10 * d, cy - 14), (cx - 10 * d, cy + 14)]
        pygame.gfxdraw.aapolygon(surf, pts, (245, 245, 240))
        pygame.gfxdraw.filled_polygon(surf, pts, (245, 245, 240))

    def _hud(self, surf):
        alt = max(0, int(self.ground(self.pos[0]) - self.pos[1] - FOOT))
        vx, vy = self.vel
        f = font(15)
        def stat(label, value, ok, x):
            img = f.render(f"{label} {value}", True, (150, 235, 160) if ok else (240, 240, 240))
            surf.blit(img, (x, 8))
        stat("ALT", f"{alt} ft", True, 14)
        stat("H", f"{vx:+.0f} ft/s", abs(vx) <= SAFE_VX, 104)
        stat("V", f"{vy:+.0f} ft/s", vy <= SAFE_VY, 200)
        stat("TILT", f"{self.angle:+.0f}°", abs(self.angle) <= SAFE_ANGLE, 296)
        lv = f.render(f"LEVEL {self.level}   SCORE {self.total}", True, (240, 240, 240))
        surf.blit(lv, lv.get_rect(topright=(W - 14, 8)))
        bar = pygame.Rect(W - 200, 30, 186, 8)                    # fuel
        pygame.draw.rect(surf, (60, 60, 70), bar, border_radius=4)
        k = self.fuel / self.fuel_max
        fill = bar.copy()
        fill.w = max(0, int(bar.w * k))
        pygame.draw.rect(surf, (255, 190, 70) if k > 0.25 else (255, 90, 70), fill, border_radius=4)
        lab = font(11).render("FUEL", True, (200, 200, 210))
        surf.blit(lab, lab.get_rect(midright=(bar.x - 6, bar.centery)))
