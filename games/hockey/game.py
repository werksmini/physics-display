"""Air Hockey: two players, one at each end of the screen.

Each player's finger anywhere in their half drives their mallet (the first finger
that lands there; the mallet follows it). The puck is a pymunk body; mallets are
kinematic bodies whose velocity is set to chase the finger, so a fast swipe hits
hard. First to 7 wins; tap the screen to play again.
"""
import math
import random

import pygame
import pygame.gfxdraw
import pymunk

from playground.ui import Controls, Button, font, text

W, H = 800, 360
RINK = pygame.Rect(30, 18, 740, 324)     # playing surface, inside the rails
GOAL = 110                               # goal mouth height
PUCK_R, MALLET_R = 13, 22
MAX_PUCK = 1100                          # px/s, stops tunnelling through rails
WIN = 7
BLUE, RED = (60, 140, 255), (235, 70, 70)


def aa_disc(surf, color, center, r):
    x, y = int(center[0]), int(center[1])
    pygame.gfxdraw.filled_circle(surf, x, y, int(r), color)
    pygame.gfxdraw.aacircle(surf, x, y, int(r), color)


class Game:
    TITLE = "Air Hockey"
    COLOR = (40, 90, 160)
    # headless screenshot: each player swipes once
    DEMO_TOUCHES = [(0, 90, 1, 120, 260, 330, 170), (40, 120, 2, 680, 90, 560, 200)]

    @staticmethod
    def icon(surf):
        w, h = surf.get_size()
        surf.fill((228, 238, 246))
        pygame.draw.line(surf, (220, 60, 60), (w // 2, 0), (w // 2, h), 3)
        pygame.draw.circle(surf, (120, 160, 220), (w // 2, h // 2), h // 4, 2)
        aa_disc(surf, BLUE, (w * 0.2, h * 0.55), 16)
        aa_disc(surf, RED, (w * 0.8, h * 0.4), 16)
        aa_disc(surf, (25, 25, 30), (w * 0.58, h * 0.6), 9)

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.score = [0, 0]                       # left (blue), right (red)
        self.winner = None
        self.flash = 0.0
        self.ui = Controls()
        self.again = self.ui.add(Button((W // 2 - 80, H // 2 + 40, 160, 46), "Play again",
                                        on_tap=self.restart))
        self.again.visible = self.again.enabled = False
        self.bg = self._table()
        self._scores = {}
        self._build_space()
        self.serve(random.choice((0, 1)))

    # -------------------------------------------------------------- physics
    def _build_space(self):
        self.space = pymunk.Space()
        self.space.damping = 0.985                # air cushion: the puck glides, slowly
        sb = self.space.static_body
        l, r, t, b = RINK.left, RINK.right, RINK.top, RINK.bottom
        gy0, gy1 = H / 2 - GOAL / 2, H / 2 + GOAL / 2
        rails = [((l, t), (r, t)), ((l, b), (r, b)),
                 ((l, t), (l, gy0)), ((l, gy1), (l, b)),
                 ((r, t), (r, gy0)), ((r, gy1), (r, b))]
        for a, c in rails:
            s = pymunk.Segment(sb, a, c, 4)
            s.elasticity, s.friction = 0.92, 0.0
            self.space.add(s)
        # the back of each goal, so the puck stops in the net
        for x in (l - 26, r + 26):
            s = pymunk.Segment(sb, (x, gy0), (x, gy1), 4)
            s.elasticity, s.friction = 0.2, 0.5
            self.space.add(s)
        for x in ((l - 26, l), (r, r + 26)):
            for y in (gy0, gy1):
                s = pymunk.Segment(sb, (x[0], y), (x[1], y), 4)
                s.elasticity = 0.5
                self.space.add(s)

        self.puck = pymunk.Body(1, pymunk.moment_for_circle(1, 0, PUCK_R))
        ps = pymunk.Circle(self.puck, PUCK_R)
        ps.elasticity, ps.friction = 0.95, 0.0
        self.space.add(self.puck, ps)

        self.mallets = []
        for side in (0, 1):
            m = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
            m.position = self._home(side)
            s = pymunk.Circle(m, MALLET_R)
            s.elasticity, s.friction = 1.0, 0.0
            self.space.add(m, s)
            self.mallets.append(m)
        self.target = [self._home(0), self._home(1)]
        self.finger = [None, None]                # which finger drives each mallet

    def _home(self, side):
        return (RINK.left + 70, H / 2) if side == 0 else (RINK.right - 70, H / 2)

    def serve(self, side):
        """Puck rests on the side of the player who was scored on."""
        x = RINK.centerx - 120 if side == 0 else RINK.centerx + 120
        self.puck.position = (x, H / 2)
        self.puck.velocity = (0, 0)
        self.puck.angular_velocity = 0

    def restart(self):
        self.score = [0, 0]
        self.winner = None
        self.again.visible = self.again.enabled = False
        self.serve(random.choice((0, 1)))

    # -------------------------------------------------------------- input
    def fingers(self, fingers):
        free = self.ui.feed(fingers)
        for side in (0, 1):
            if self.finger[side] not in free:
                self.finger[side] = None
        for fid, (x, y) in free.items():
            side = 0 if x < W / 2 else 1
            if self.finger[side] is None and fid not in self.finger:
                self.finger[side] = fid
        for side in (0, 1):
            fid = self.finger[side]
            if fid is not None:
                self.target[side] = free[fid]

    def _clamp(self, side, x, y):
        top, bot = RINK.top + MALLET_R, RINK.bottom - MALLET_R
        if side == 0:
            x = max(RINK.left + MALLET_R, min(W / 2 - MALLET_R, x))
        else:
            x = max(W / 2 + MALLET_R, min(RINK.right - MALLET_R, x))
        return x, max(top, min(bot, y))

    # -------------------------------------------------------------- update
    def update(self, dt):
        self.ui.tick(dt)
        self.flash = max(0.0, self.flash - dt)
        if self.winner is not None:
            return
        for side, m in enumerate(self.mallets):
            tx, ty = self._clamp(side, *self.target[side])
            vx, vy = (tx - m.position.x) / dt, (ty - m.position.y) / dt       # catch up in one frame
            sp = math.hypot(vx, vy)
            if sp > 1600:                                                   # but not teleport-fast
                vx, vy = vx / sp * 1600, vy / sp * 1600
            m.velocity = (vx, vy)
        sub = 4
        for _ in range(sub):
            h = dt / sub
            self.space.step(h)
            for side, m in enumerate(self.mallets):                         # stay in own half
                m.position = self._clamp(side, *m.position)
            v = self.puck.velocity
            if v.length > MAX_PUCK:
                self.puck.velocity = v * (MAX_PUCK / v.length)
        x = self.puck.position.x                  # most of the puck over the goal line
        if x < RINK.left - 4:
            self._goal(1)
        elif x > RINK.right + 4:
            self._goal(0)
        # a puck stuck dead in the middle of nowhere gets a nudge
        if self.puck.velocity.length < 4 and abs(self.puck.position.x - W / 2) < PUCK_R + 2:
            self.puck.apply_impulse_at_local_point((random.choice((-40, 40)), 0))

    def _goal(self, scorer):
        self.score[scorer] += 1
        self.flash = 0.8
        self.flash_side = scorer
        if self.score[scorer] >= WIN:
            self.winner = scorer
            self.again.visible = self.again.enabled = True
            self.puck.velocity = (0, 0)
        else:
            self.serve(1 - scorer)

    # -------------------------------------------------------------- drawing
    def _table(self):
        bg = pygame.Surface((W, H))
        bg.fill((24, 28, 36))                                     # floor
        pygame.draw.rect(bg, (70, 76, 90), RINK.inflate(24, 24), border_radius=26)  # rail
        pygame.draw.rect(bg, (232, 240, 247), RINK, border_radius=18)               # ice
        for x in range(RINK.left + 8, RINK.right, 16):            # air holes
            for y in range(RINK.top + 8, RINK.bottom, 16):
                bg.set_at((x, y), (205, 215, 226))
        cx, cy = RINK.center
        pygame.draw.line(bg, (225, 70, 70), (cx, RINK.top), (cx, RINK.bottom), 3)
        pygame.draw.circle(bg, (110, 150, 215), (cx, cy), 52, 3)
        pygame.draw.circle(bg, (110, 150, 215), (cx, cy), 6)
        for side, x in ((0, RINK.left), (1, RINK.right)):
            crease = pygame.Rect(0, 0, 150, 150)
            crease.center = (x, cy)
            pygame.draw.arc(bg, BLUE if side == 0 else RED, crease,
                            -math.pi / 2 if side == 0 else math.pi / 2,
                            math.pi / 2 if side == 0 else 3 * math.pi / 2, 3)
            gy0 = cy - GOAL // 2
            gx = x - 30 if side == 0 else x + 4
            pygame.draw.rect(bg, (16, 18, 24), (gx, gy0, 26, GOAL), border_radius=5)
            pygame.draw.line(bg, BLUE if side == 0 else RED, (x, gy0), (x, gy0 + GOAL), 4)
        return bg

    def _mallet(self, surf, pos, color):
        x, y = pos
        aa_disc(surf, (0, 0, 0, 60), (x + 3, y + 4), MALLET_R)                 # shadow
        aa_disc(surf, tuple(int(c * 0.7) for c in color), (x, y), MALLET_R)
        aa_disc(surf, color, (x, y), MALLET_R - 4)
        aa_disc(surf, tuple(int(c * 0.75) for c in color), (x, y), 10)         # handle
        aa_disc(surf, tuple(min(255, c + 70) for c in color), (x - 3, y - 3), 5)

    def _score_text(self, surf, n, side):
        """Each score faces its own player (rotated toward their end)."""
        key = (n, side)
        if key not in self._scores:
            img = text(34, str(n), BLUE if side == 0 else RED)
            self._scores[key] = pygame.transform.rotate(img, -90 if side == 0 else 90)
        img = self._scores[key]
        x = RINK.centerx - 40 - img.get_width() if side == 0 else RINK.centerx + 40
        surf.blit(img, (x, RINK.top + 10))

    def draw(self, surf):
        surf.blit(self.bg, (0, 0))
        self._score_text(surf, self.score[0], 0)
        self._score_text(surf, self.score[1], 1)
        p = self.puck.position
        aa_disc(surf, (0, 0, 0, 50), (p.x + 2, p.y + 3), PUCK_R)
        aa_disc(surf, (22, 22, 26), p, PUCK_R)
        pygame.gfxdraw.aacircle(surf, int(p.x), int(p.y), PUCK_R - 4, (70, 70, 80))
        self._mallet(surf, self.mallets[0].position, BLUE)
        self._mallet(surf, self.mallets[1].position, RED)
        if self.flash > 0:
            glow = pygame.Surface((W // 2, H), pygame.SRCALPHA)
            c = BLUE if self.flash_side == 0 else RED
            glow.fill(c + (int(90 * self.flash / 0.8),))
            surf.blit(glow, (0 if self.flash_side == 0 else W // 2, 0))
        if self.winner is not None:
            shade = pygame.Surface((W, H), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 140))
            surf.blit(shade, (0, 0))
            who = "Blue wins!" if self.winner == 0 else "Red wins!"
            img = text(48, who, BLUE if self.winner == 0 else RED)
            surf.blit(img, img.get_rect(center=(W // 2, H // 2 - 20)))
        self.ui.draw(surf)
