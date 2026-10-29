"""Ink in water: stir coloured ink through a fluid with your finger.

A real (if coarse) fluid simulation, the "stable fluids" method from Jos
Stam's 1999 paper, on a grid much smaller than the screen and smoothed up.
Each step:
1. Forces: your finger pushes the water and drops in ink.
2. Vorticity confinement: a nudge that keeps small swirls spinning instead
   of smearing out.
3. Advection: velocity carries itself along. Each cell looks backwards along
   the flow and takes the value it finds there, which is what keeps this
   stable at any time step.
4. Projection: water can't be squashed, so a pressure field is solved with
   a few relaxation passes and its gradient removed, leaving swirling flow.
5. The ink is carried by the flow the same way, and slowly fades.

Touch: drag to stir; each new touch picks the next ink colour. When nobody
touches it, a slow drifting emitter keeps adding a little ink (Idle ink).
"""
import colorsys
import math

import numpy as np
import pygame

from playground.scene import BaseScene, Param

WATER = np.array([6, 10, 22], np.float32)


def sample(f, x, y):
    """Bilinear sample of grid f (gw, gh) at float coordinates x, y."""
    gw, gh = f.shape
    x = np.clip(x, 0, gw - 1.001)
    y = np.clip(y, 0, gh - 1.001)
    x0, y0 = x.astype(np.int32), y.astype(np.int32)
    fx, fy = x - x0, y - y0
    a, b = f[x0, y0], f[x0 + 1, y0]
    c, d = f[x0, y0 + 1], f[x0 + 1, y0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


class Scene(BaseScene):
    TITLE = "Ink in water"
    PREVIEW_AFTER = 30
    PARAMS = [
        Param("stir_strength", 1.0, 0, 4, 0.05, "Stir strength"),
        Param("ink_amount", 1.0, 0, 3, 0.05, "Ink amount"),
        Param("brush", 40, 8, 140, 2, "Brush size", help="In screen pixels."),
        Param("swirl", 1.5, 0, 6, 0.1, "Swirliness", help="Vorticity confinement: keeps small eddies alive."),
        Param("fade", 0.25, 0, 2, 0.01, "Ink fade", help="How fast ink disappears (per second)."),
        Param("drag", 0.15, 0, 2, 0.01, "Water drag", help="How fast motion dies down."),
        Param("idle_ink", 0.6, 0, 2, 0.05, "Idle ink", help="A slow emitter when nobody is touching."),
        Param("quality", 20, 4, 60, 1, "Pressure passes", help="More = more accurate swirls, slower."),
        Param("grid", 60, 24, 120, 2, "Grid width", reset=True, help="Simulation cells across. Higher = finer, slower."),
        Param("smooth", 1, 0, 1, 1, "Smooth scaling"),
    ]

    def setup(self):
        self.gw = int(self.p.grid)
        self.gh = int(round(self.gw * self.h / self.w))
        shape = (self.gw, self.gh)
        self.u = np.zeros(shape, np.float32)         # velocity, cells per second
        self.v = np.zeros(shape, np.float32)
        self.dye = np.zeros((3,) + shape, np.float32)
        self.pres = np.zeros(shape, np.float32)
        gx, gy = np.meshgrid(np.arange(self.gw, dtype=np.float32), np.arange(self.gh, dtype=np.float32), indexing="ij")
        self.gx, self.gy = gx, gy
        self.cell = self.w / self.gw                  # screen px per cell
        self.finger = None
        self.prev = None
        self.hue = 0.55
        self.color = self._next_color()
        self.t = 0.0
        self.low = pygame.Surface(shape)

    def _next_color(self):
        self.hue = (self.hue + 0.17) % 1.0
        return np.array(colorsys.hsv_to_rgb(self.hue, 0.8, 1.0), np.float32)

    def preview(self, step):
        """Scripted strokes for the gallery image."""
        for pts in (((0.15, 0.3), (0.8, 0.35), (0.55, 0.7)),):
            (x0, y0) = pts[0]
            self.touch("down", x0 * self.w, y0 * self.h)
            for (x1, y1) in pts[1:]:
                for i in range(1, 31):
                    f = i / 30
                    self.touch("move", (x0 + (x1 - x0) * f) * self.w, (y0 + (y1 - y0) * f) * self.h)
                    self.update(step)
                x0, y0 = x1, y1
            self.touch("up", 0, 0)
            for _ in range(20):
                self.update(step)

    # ------------------------------------------------------------------ input
    def touch(self, kind, x, y):
        pt = np.array([x, y], np.float32) / self.cell
        if kind == "down":
            self.color = self._next_color()
            self.finger = self.prev = pt
        elif kind == "move" and self.finger is not None:
            self.finger = pt
        elif kind == "up":
            self.finger = self.prev = None

    def _splat(self, pos, vel, color, amount, radius):
        r2 = radius * radius
        g = np.exp(-((self.gx - pos[0]) ** 2 + (self.gy - pos[1]) ** 2) / r2)
        self.u += g * vel[0]
        self.v += g * vel[1]
        self.dye += g[None] * (color[:, None, None] * amount)

    # ----------------------------------------------------------------- update
    def update(self, dt):
        p = self.p
        self.t += dt
        radius = p.brush / self.cell * 0.5
        if self.finger is not None:
            vel = (self.finger - self.prev) / dt * 0.35 * p.stir_strength
            self._splat(self.finger, vel, self.color, 0.35 * p.ink_amount, radius)
            self.prev = self.finger.copy()
        elif p.idle_ink > 0:                           # slow drifting emitter
            a = self.t * 0.35
            pos = np.array([self.gw * (0.5 + 0.32 * math.sin(a)), self.gh * (0.62 + 0.2 * math.sin(a * 1.7))], np.float32)
            vel = np.array([math.cos(a * 1.3), -math.sin(a * 0.9) - 0.4], np.float32) * self.gw * 0.25
            hue = (self.t * 0.03) % 1
            col = np.array(colorsys.hsv_to_rgb(hue, 0.75, 1.0), np.float32)
            self._splat(pos, vel * p.idle_ink * dt * 8, col, 0.05 * p.idle_ink, radius * 0.7)

        u, v = self.u, self.v
        # vorticity confinement
        if p.swirl > 0:
            curl = np.zeros_like(u)
            curl[1:-1, 1:-1] = (v[2:, 1:-1] - v[:-2, 1:-1] - u[1:-1, 2:] + u[1:-1, :-2]) * 0.5
            ac = np.abs(curl)
            nx = np.zeros_like(u); ny = np.zeros_like(u)
            nx[1:-1, 1:-1] = (ac[2:, 1:-1] - ac[:-2, 1:-1]) * 0.5
            ny[1:-1, 1:-1] = (ac[1:-1, 2:] - ac[1:-1, :-2]) * 0.5
            ln = np.sqrt(nx * nx + ny * ny) + 1e-5
            u += (ny / ln) * curl * p.swirl * dt * 10
            v -= (nx / ln) * curl * p.swirl * dt * 10

        # advect velocity (semi-Lagrangian: look backwards along the flow)
        bx, by = self.gx - u * dt, self.gy - v * dt
        u, v = sample(u, bx, by), sample(v, bx, by)
        damp = math.exp(-p.drag * dt)
        u *= damp; v *= damp

        # walls
        u[0, :] = u[-1, :] = 0
        v[:, 0] = v[:, -1] = 0

        # pressure projection (Jacobi relaxation)
        div = np.zeros_like(u)
        div[1:-1, 1:-1] = (u[2:, 1:-1] - u[:-2, 1:-1] + v[1:-1, 2:] - v[1:-1, :-2]) * 0.5
        pr = self.pres * 0.8                                       # warm start from last frame
        for _ in range(int(p.quality)):
            pr[1:-1, 1:-1] = (pr[2:, 1:-1] + pr[:-2, 1:-1] + pr[1:-1, 2:] + pr[1:-1, :-2] - div[1:-1, 1:-1]) * 0.25
            pr[0, :], pr[-1, :], pr[:, 0], pr[:, -1] = pr[1, :], pr[-2, :], pr[:, 1], pr[:, -2]
        self.pres = pr
        u[1:-1, 1:-1] -= (pr[2:, 1:-1] - pr[:-2, 1:-1]) * 0.5
        v[1:-1, 1:-1] -= (pr[1:-1, 2:] - pr[1:-1, :-2]) * 0.5
        self.u, self.v = u, v

        # advect ink along the new flow, and fade it
        bx, by = self.gx - u * dt, self.gy - v * dt
        fade = math.exp(-p.fade * dt)
        for c in range(3):
            self.dye[c] = sample(self.dye[c], bx, by) * fade
        d = self.dye                                               # soften ink pooled on the walls
        d[:, 0, :], d[:, -1, :] = d[:, 1, :] * 0.9, d[:, -2, :] * 0.9
        d[:, :, 0], d[:, :, -1] = d[:, :, 1] * 0.9, d[:, :, -2] * 0.9

    # ------------------------------------------------------------------- draw
    def draw(self, surf):
        ink = np.clip(self.dye, 0, 1.2)
        # ink glows over dark water; dense ink saturates gently
        rgb = WATER[:, None, None] + (1 - np.exp(-ink * 1.6)) * 255
        img = np.clip(rgb, 0, 255).astype(np.uint8).transpose(1, 2, 0)
        pygame.surfarray.blit_array(self.low, img)
        scale = pygame.transform.smoothscale if self.p.smooth else pygame.transform.scale
        surf.blit(scale(self.low, (self.w, self.h)), (0, 0))
