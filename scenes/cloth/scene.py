"""Laundry Day: a striped sheet pegged on a clothesline in a meadow at golden hour.

The low sun is behind the sheet, so it glows where the light comes through. A
gusty breeze makes it billow. Grab it and pull; let go and it swings back.
Double-tap the sky or grass to unpeg it (it blows off and drops onto the
grass), and double-tap again to hang a fresh one. Switch "Setup" to drop a
cloth over a ball instead.

The cloth is a grid of particles joined by distance constraints (Verlet
integration, the method from Thomas Jakobsen's Hitman cloth):

- each particle remembers where it was last step; its velocity is simply
  (now - before), so moving a particle by hand gives it velocity for free
- gravity and the breeze (which pushes on the face of the cloth) move the
  particles, then the constraints are relaxed a few times: every neighbour
  pair is nudged back toward its rest distance. Straight neighbours keep the
  cloth from stretching, diagonal ones stop it shearing, and pairs two apart
  give it a little stiffness to fold
- pegged particles don't move; the grass and the ball push particles out,
  with friction so the cloth grips

All of this is numpy on whole slices of the grid at once, so it costs the same
few dozen array operations whatever the cloth size. The shape is uploaded as a
fresh mesh each frame and drawn on the GPU: both sides lit, the pattern woven
per pixel, and light passing through the fabric when the sun is behind it.

Touch: drag the cloth to pull that spot (a finger each, up to three); drag
empty space to orbit the camera, pinch to zoom.
"""
import math

import numpy as np
import pygame

from playground.mat import look_at, perspective
from playground.scene import BaseScene, Param

FOV = 45.0
TARGET = np.array([0.0, 1.45, 0.0])
LIGHT = np.array([0.22, -0.26, 0.94]) / np.linalg.norm([0.22, -0.26, 0.94])   # low sun, behind the line
BALL_C = np.array([0.0, 0.75, 0.0])
BALL_R = 0.75
POST_X = 1.55                     # the two clothesline posts
LINE_TOP = 2.82                   # where the line is tied on
SAG = 0.13                        # how far the line sags in the middle
SETUPS = ("Clothesline", "Over a ball")
PATTERNS = ("Stripes", "Gingham", "Plain linen")
HAZE = (0.96, 0.80, 0.62)

SKY_FS = """
uniform vec2 u_sun;        // sun on screen (uv)
uniform float u_horizon;   // horizon height on screen (uv.y)
uniform float u_yaw;
uniform float u_time;
uniform float u_aspect;
varying vec2 uv;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0)), f.x), f.y);
}
void main() {
    float h = u_horizon - uv.y;                                   // height above the horizon
    vec3 col = mix(vec3(1.0, 0.80, 0.58), vec3(0.42, 0.60, 0.86), smoothstep(0.0, 0.55, h));
    col = mix(col, vec3(1.0, 0.68, 0.46), smoothstep(0.08, 0.0, h) * 0.5);
    // soft clouds drifting by
    vec2 cp = vec2(uv.x * 2.2 - u_yaw * 0.6 + u_time * 0.008, h * 9.0);
    float c = noise(cp * vec2(1.0, 1.6)) * 0.65 + noise(cp * 2.3 + 4.0) * 0.35;
    c = smoothstep(0.52, 0.80, c) * smoothstep(0.02, 0.12, h) * (1.0 - smoothstep(0.35, 0.6, h));
    col = mix(col, vec3(1.0, 0.90, 0.80), c * 0.55);
    // the sun and its glow
    float d = length((uv - u_sun) * vec2(u_aspect, 1.0));
    col += vec3(1.0, 0.72, 0.40) * (exp(-d * d * 30.0) * 0.55 + exp(-d * 5.0) * 0.18);
    col = mix(col, vec3(1.0, 0.97, 0.86), smoothstep(0.042, 0.034, d));
    // two rows of hazy hills on the horizon
    float x = uv.x - u_yaw * 0.28;
    float far = u_horizon - 0.030 - 0.018 * sin(x * 7.0 + 1.0) - 0.010 * sin(x * 17.0 + 2.0);
    col = mix(col, mix(vec3(0.78, 0.66, 0.62), vec3(1.0, 0.80, 0.58), 0.35), step(far, uv.y));
    float x2 = uv.x - u_yaw * 0.45;
    float near = u_horizon - 0.012 - 0.012 * sin(x2 * 5.0 + 4.0) - 0.006 * sin(x2 * 23.0);
    col = mix(col, vec3(0.56, 0.56, 0.42), step(near, uv.y));
    col += (hash(gl_FragCoord.xy + fract(u_time) * 61.0) - 0.5) / 96.0;
    gl_FragColor = vec4(col, 1.0);
}"""

FLOOR_VS = """
attribute vec3 a_pos;
uniform mat4 u_viewproj;
varying vec3 v_world;
void main() { v_world = a_pos; gl_Position = u_viewproj * vec4(a_pos, 1.0); }"""

GRASS_FS = """
uniform vec3 u_eye;
uniform vec3 u_fog;
varying vec3 v_world;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0)), f.x), f.y);
}
void main() {
    float d = length(v_world - u_eye);
    vec2 p = v_world.xz;
    float patch = noise(p * 0.35) * 0.6 + noise(p * 1.3) * 0.4;
    vec3 col = mix(vec3(0.24, 0.38, 0.12), vec3(0.58, 0.62, 0.26), patch);          // green into straw
    col *= 0.88 + 0.22 * noise(p * 9.0) * clamp(1.0 - d / 8.0, 0.0, 1.0);          // blades up close
    col *= vec3(1.08, 0.98, 0.86);                                                 // warm evening light
    col = mix(col, u_fog, clamp(1.0 - exp(-d * 0.045), 0.0, 1.0));
    col += (hash(gl_FragCoord.xy) - 0.5) / 96.0;
    gl_FragColor = vec4(col, 1.0);
}"""

LIT_VS = """
attribute vec3 a_pos;
attribute vec3 a_normal;
attribute vec2 a_uv;
uniform mat4 u_viewproj;
varying vec3 v_normal;
varying vec3 v_world;
varying vec2 v_uv;
void main() {
    v_world = a_pos;
    v_normal = a_normal;
    v_uv = a_uv;
    gl_Position = u_viewproj * vec4(a_pos, 1.0);
}"""

CLOTH_FS = """
uniform vec3 u_light;
uniform vec3 u_eye;
uniform vec4 u_cloth;      // pattern, repeats across, -, -
varying vec3 v_normal;
varying vec3 v_world;
varying vec2 v_uv;
void main() {
    vec3 n = normalize(v_normal);
    vec3 V = normalize(u_eye - v_world);
    if (dot(n, V) < 0.0) n = -n;                       // both sides of the cloth are lit
    vec3 base;
    vec2 q = v_uv * u_cloth.y;
    if (u_cloth.x < 0.5) {                             // pale sheet with pairs of blue stripes
        float s = fract(v_uv.x * u_cloth.y);
        float stripe = smoothstep(0.08, 0.06, abs(s - 0.15)) + smoothstep(0.03, 0.02, abs(s - 0.27));
        base = mix(vec3(0.97, 0.95, 0.90), vec3(0.36, 0.52, 0.80), clamp(stripe, 0.0, 1.0) * 0.85);
    } else if (u_cloth.x < 1.5) {                      // red gingham
        vec2 g = step(0.5, fract(q));
        float k = (g.x + g.y) * 0.5;
        base = mix(vec3(0.95, 0.93, 0.89), vec3(0.78, 0.13, 0.14), k * k * 0.85 + k * 0.15);
    } else {
        base = vec3(0.93, 0.89, 0.80);                 // plain linen
    }
    vec2 w = fract(v_uv * 160.0);                      // fine weave
    base *= 0.94 + 0.06 * abs(w.x - w.y);
    float facing = dot(n, -u_light);                   // > 0: this side faces the sun
    float wrap = max((facing + 0.35) / 1.35, 0.0);
    float through = max(-facing, 0.0);                 // sun behind the cloth: light comes through
    vec3 H = normalize(-u_light + V);
    float sheen = pow(max(dot(n, H), 0.0), 12.0) * 0.08;
    vec3 sky = vec3(0.55, 0.62, 0.78) * (0.5 + 0.5 * n.y);
    vec3 col = base * (0.42 * sky + vec3(1.0, 0.82, 0.62) * 0.80 * wrap)
             + base * vec3(1.0, 0.86, 0.64) * through * (0.55 + 0.75 * through) + vec3(sheen);
    gl_FragColor = vec4(col, 1.0);
}"""

SOLID_FS = """
uniform vec3 u_light;
uniform vec3 u_eye;
uniform vec3 u_color;
varying vec3 v_normal;
varying vec3 v_world;
varying vec2 v_uv;
void main() {
    vec3 n = normalize(v_normal);
    vec3 V = normalize(u_eye - v_world);
    float diff = max(dot(n, -u_light), 0.0);
    vec3 H = normalize(-u_light + V);
    float spec = pow(max(dot(n, H), 0.0), 30.0) * 0.2;
    float sky = 0.5 + 0.5 * n.y;
    float rim = pow(1.0 - max(dot(n, V), 0.0), 3.0) * max(dot(V, u_light), 0.0);   // backlit edges glow
    gl_FragColor = vec4(u_color * (0.60 * sky * vec3(0.72, 0.78, 0.92) + 0.85 * diff * vec3(1.0, 0.82, 0.62))
                        + vec3(1.0, 0.78, 0.5) * rim * 0.6 + vec3(spec), 1.0);
}"""

SHADOW_VS = """
attribute vec3 a_pos;
uniform mat4 u_mvp;
void main() { gl_Position = u_mvp * vec4(a_pos, 1.0); }"""

SHADOW_FS = """
uniform float u_alpha;
void main() { gl_FragColor = vec4(0.10, 0.10, 0.18, u_alpha); }"""


def sphere_mesh(c, r, nu=28, nv=16):
    out = []
    for i in range(nv):
        for j in range(nu):
            quad = []
            for di, dj in ((0, 0), (1, 0), (1, 1), (0, 1)):
                th = math.pi * (i + di) / nv
                ph = 2 * math.pi * (j + dj) / nu
                n = (math.sin(th) * math.cos(ph), math.cos(th), math.sin(th) * math.sin(ph))
                quad.append([c[0] + r * n[0], c[1] + r * n[1], c[2] + r * n[2], *n, 0.0, 0.0])
            for k in (0, 1, 2, 0, 2, 3):
                out += quad[k]
    return out


def box(c, size, along=None):
    """A box (36 vertices: position, normal, uv). `along`: optional (p0, p1) to stretch it between."""
    out = []
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    faces = [((1, 0, 0), [(hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz), (hx, -hy, hz)]),
             ((-1, 0, 0), [(-hx, -hy, hz), (-hx, hy, hz), (-hx, hy, -hz), (-hx, -hy, -hz)]),
             ((0, 1, 0), [(-hx, hy, -hz), (-hx, hy, hz), (hx, hy, hz), (hx, hy, -hz)]),
             ((0, -1, 0), [(-hx, -hy, hz), (-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz)]),
             ((0, 0, 1), [(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]),
             ((0, 0, -1), [(hx, -hy, -hz), (-hx, -hy, -hz), (-hx, hy, -hz), (hx, hy, -hz)])]
    R = np.eye(3)
    if along is not None:                            # rotate the box's x axis onto p0 -> p1
        p0, p1 = np.array(along[0]), np.array(along[1])
        d = p1 - p0
        a = math.atan2(d[1], d[0])
        R = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
        c = (p0 + p1) / 2
    for n, quad in faces:
        n = R @ n
        pts = [np.asarray(c) + R @ np.array(v) for v in quad]
        for k in (0, 1, 2, 0, 2, 3):
            out += [*pts[k], *n, 0.0, 0.0]
    return out


def line_y(x):
    """Height of the clothesline at x: it sags in the middle."""
    return LINE_TOP - SAG * (1.0 - (x / POST_X) ** 2)


class Scene(BaseScene):
    TITLE = "Laundry Day"
    BRAND = dict(name="Laundry Day", font="Pacifico", size=60, tilt=-3,
                 fill=((255, 255, 255), (255, 236, 210)), outline=(196, 84, 70), outline_width=6,
                 tagline="a breezy afternoon on the line", art="clothesline", art_y=58)
    GPU = True
    PARAMS = [
        Param("setup", 0, 0, 0, 1, choices=SETUPS, label="Setup", reset=True),
        Param("pattern", 0, 0, 0, 1, choices=PATTERNS, label="Pattern"),
        Param("wind", 1.0, 0, 4, 0.05, "Breeze"),
        Param("stiffness", 0.5, 0, 1, 0.05, "Fold stiffness", help="0 = silk, 1 = canvas."),
        Param("friction", 0.6, 0, 1, 0.05, "Grip", help="How much the cloth sticks to the grass and ball."),
        Param("gravity", 9.8, 1, 20, 0.1, "Gravity"),
        Param("iterations", 6, 2, 14, 1, "Solver passes", help="More = less stretchy, slower."),
        Param("pegs", 5, 2, 12, 1, "Clothespins", reset=True),
        Param("detail", 24, 12, 36, 1, "Cloth detail", reset=True, help="Particles along each edge."),
        Param("repeats", 7, 2, 16, 1, "Pattern repeats"),
    ]

    # ------------------------------------------------------------------ setup
    def setup(self):
        gl = self.gl
        attribs = ("a_pos", "a_normal", "a_uv")
        self.sky = gl.program(SKY_FS)
        self.floor_prog = gl.program(GRASS_FS, FLOOR_VS)
        self.cloth_prog = gl.program(CLOTH_FS, LIT_VS, attribs=attribs)
        self.solid_prog = gl.program(SOLID_FS, LIT_VS, attribs=attribs)
        self.shadow_prog = gl.program(SHADOW_FS, SHADOW_VS, attribs=attribs)
        S = 60.0
        self.floor_mesh = gl.mesh([-S, 0, -S, S, 0, -S, S, 0, S, -S, 0, -S, S, 0, S, -S, 0, S], (3,))
        self.line_mode = int(self.p.setup) == 0
        self.has_ball = not self.line_mode
        self.ball_mesh = gl.mesh(sphere_mesh(BALL_C, BALL_R * 0.985), (3, 3, 2)) if self.has_ball else None

        n = self.n = int(self.p.detail)
        self.size = 2.4 if self.line_mode else 2.6
        self.rest = self.size / (n - 1)
        u = np.linspace(0, 1, n)
        uu, vv = np.meshgrid(u, u)
        self.uv = np.stack([uu, vv], -1).reshape(-1, 2).astype(np.float32)
        tris = []
        for i in range(n - 1):
            for j in range(n - 1):
                a, b, c, d = i * n + j, i * n + j + 1, (i + 1) * n + j, (i + 1) * n + j + 1
                tris += [a, c, b, b, c, d]
        self.idx = np.array(tris, np.int32)
        self.cloth_mesh = gl.mesh(np.zeros(8 * 3), (3, 3, 2))
        self.peg_cols = np.unique(np.round(np.linspace(0, n - 1, int(self.p.pegs))).astype(int))
        if self.line_mode:                                 # posts, the line and the pegs
            posts = []
            for x in (-POST_X, POST_X):
                posts += box((x, LINE_TOP / 2 + 0.02, 0), (0.09, LINE_TOP + 0.08, 0.09))
                posts += box((x, LINE_TOP + 0.02, 0), (0.05, 0.05, 0.32))      # little crossbar
            self.posts_mesh = gl.mesh(posts, (3, 3, 2))
            xs = np.linspace(-POST_X, POST_X, 25)
            line = []
            for a, b in zip(xs[:-1], xs[1:]):
                line += box(None, (abs(b - a) * 1.02 / math.cos(math.atan2(line_y(b) - line_y(a), b - a)), 0.014, 0.014),
                            along=((a, line_y(a), 0), (b, line_y(b), 0)))
            self.line_mesh = gl.mesh(line, (3, 3, 2))
            pegs = []
            for j in self.peg_cols:
                x = -self.size / 2 + j * self.rest
                pegs += box((x, line_y(x) - 0.015, 0), (0.028, 0.10, 0.045))
            self.pegs_mesh = gl.mesh(pegs, (3, 3, 2))
        self.t = 0.0
        if self.line_mode:
            self.yaw, self.pitch, self.dist = 0.38, 0.10, 6.4
        else:
            self.yaw, self.pitch, self.dist = 0.5, 0.30, 6.2
        self.grabs = {}             # finger id -> [particle indices, offsets, depth]
        self.prev = {}
        self.gesture = None
        self.last_tap = (-9.0, 0.0, 0.0)
        self.font = pygame.font.Font(None, 24)
        self._camera()
        self._drop()

    def _drop(self):
        """A fresh cloth: hung on the line, or flat above the ball."""
        n, s = self.n, self.size
        rng = np.random.default_rng()
        g = np.linspace(-s / 2, s / 2, n)
        if self.line_mode:
            X, R = np.meshgrid(g, np.arange(n) * self.rest)
            Y = line_y(X) - 0.03 - R
            Z = rng.normal(0, 0.01, X.shape)
            self.pegged = True
        else:
            X, Z = np.meshgrid(g, g)
            tilt = rng.uniform(-0.08, 0.08)
            Y = 2.6 + X * tilt + Z * 0.08
            X = X + rng.uniform(-0.06, 0.06)
            self.pegged = False
        P = np.stack([X, Y, Z], -1).astype(np.float64)
        self.P = P
        self.Q = P.copy()                             # where each particle was last step
        self.W0 = np.ones((n, n, 1))                  # inverse mass at rest (0 = pegged)
        if self.line_mode:
            self.W0[0, self.peg_cols] = 0.0
        self.W = self.W0.copy()                       # ... and right now (0 = pegged or held)
        self.grabs.clear()

    def _unpeg(self):
        self.pegged = False
        self.W0[:] = 1.0
        self.W[:] = 1.0
        for patch, _, _ in self.grabs.values():
            self.W.reshape(-1, 1)[patch] = 0.0

    def _camera(self):
        cp = math.cos(self.pitch)
        self.eye = TARGET + self.dist * np.array([cp * math.sin(self.yaw), math.sin(self.pitch), cp * math.cos(self.yaw)])
        self.view = look_at(self.eye, TARGET)
        self.proj = perspective(FOV, self.w / self.h, 0.3, 80.0)
        self.viewproj = self.proj @ self.view
        self.inv_vp = np.linalg.inv(self.viewproj)
        self.right, self.up, self.fwd = self.view[0, :3], self.view[1, :3], -self.view[2, :3]

    def _ray(self, x, y):
        nx, ny = 2 * x / self.w - 1, 1 - 2 * y / self.h
        a = self.inv_vp @ [nx, ny, -1, 1]
        b = self.inv_vp @ [nx, ny, 1, 1]
        a, b = a[:3] / a[3], b[:3] / b[3]
        d = b - a
        return a, d / np.linalg.norm(d)

    def _screen_points(self):
        P = self.P.reshape(-1, 3)
        c = np.c_[P, np.ones(len(P))] @ self.viewproj.T
        return np.c_[(c[:, 0] / c[:, 3] + 1) / 2 * self.w, (1 - c[:, 1] / c[:, 3]) / 2 * self.h], c[:, 3]

    # ------------------------------------------------------------- touch
    def fingers(self, fingers):
        ids, prev_ids = set(fingers), set(self.prev)
        for k in prev_ids - ids:                              # lifted: let go of the cloth
            g = self.grabs.pop(k, None)
            if g is not None:
                self.W.reshape(-1, 1)[g[0]] = self.W0.reshape(-1, 1)[g[0]]   # back to pegged / free
        if not prev_ids and ids:
            x, y = next(iter(fingers.values()))
            self.gesture = {"t0": self.t, "start": (x, y), "moved": 0.0, "n": len(ids), "grab": False}
        for k in ids - prev_ids:                              # new finger: on the cloth?
            x, y = fingers[k]
            sp, depth = self._screen_points()
            d2 = ((sp - (x, y)) ** 2).sum(1)
            taken = set()
            for g in self.grabs.values():
                taken.update(g[0].tolist())
            order = np.argsort(d2)[:6]
            i = next((int(i) for i in order if int(i) not in taken), None)
            if i is not None and d2[i] < 45 ** 2:
                # pinch a small patch (the point and its neighbours), like fingers grabbing fabric
                n = self.n
                r, c = divmod(i, n)
                patch = np.array([rr * n + cc for rr in range(max(0, r - 1), min(n, r + 2))
                                  for cc in range(max(0, c - 1), min(n, c + 2))
                                  if rr * n + cc not in taken and abs(rr - r) + abs(cc - c) <= 1])
                P = self.P.reshape(-1, 3)
                self.grabs[k] = [patch, P[patch] - P[i], float(np.dot(P[i] - self.eye, self.fwd))]
                self.W.reshape(-1, 1)[patch] = 0.0
                if self.gesture:
                    self.gesture["grab"] = True
        if self.gesture:
            self.gesture["n"] = max(self.gesture["n"], len(ids))
        if prev_ids and not ids:
            self._end_gesture()
        # drag held points; free fingers move the camera
        free = [k for k in ids & prev_ids if k not in self.grabs]
        P = self.P.reshape(-1, 3)
        for k, (patch, offs, depth) in self.grabs.items():
            o, d = self._ray(*fingers[k])
            p = o + d * ((depth - np.dot(o - self.eye, self.fwd)) / max(np.dot(d, self.fwd), 1e-3))
            p[1] = max(p[1], 0.03)
            q = p + offs
            q[:, 1] = np.maximum(q[:, 1], 0.01)
            P[patch] = q
        if free and ids == prev_ids:
            moved = [np.subtract(fingers[k], self.prev[k]) for k in free]
            dc = np.mean(moved, 0)
            if self.gesture:
                self.gesture["moved"] += math.hypot(*dc)
            if not self.grabs:
                if len(free) == 1:
                    self.yaw -= dc[0] * 0.008
                    self.pitch = min(1.35, max(0.08, self.pitch + dc[1] * 0.006))
                elif len(free) >= 2:
                    a, b = free[:2]
                    d0 = math.dist(self.prev[a], self.prev[b])
                    d1 = math.dist(fingers[a], fingers[b])
                    if d0 > 10:
                        self.dist = min(14, max(3, self.dist * d0 / d1))
                self._camera()
        elif self.gesture and ids == prev_ids and self.grabs:
            self.gesture["moved"] += 20
        self.prev = dict(fingers)

    def _end_gesture(self):
        g, self.gesture = self.gesture, None
        if not g or g["grab"] or g["n"] > 1:
            return
        if self.t - g["t0"] < 0.3 and g["moved"] < 14:
            x, y = g["start"]
            t, lx, ly = self.last_tap
            if self.t - t < 0.4 and math.hypot(x - lx, y - ly) < 70:
                self.last_tap = (-9.0, 0.0, 0.0)
                if self.line_mode and self.pegged:
                    self._unpeg()                          # off it blows
                else:
                    self._drop()
            else:
                self.last_tap = (self.t, x, y)

    # ------------------------------------------------------------- physics
    def update(self, dt):
        self.t += dt
        p = self.p
        h = dt
        P, Q, W = self.P, self.Q, self.W
        # wind: a gusty breeze that pushes on the face of the cloth, mostly toward you
        nrm = self.nrm = self._normals()
        gust = p.wind * (0.55 + 0.45 * math.sin(self.t * 0.9) * math.sin(self.t * 0.37 + 1.0))
        wdir = np.array([0.35 * math.sin(self.t * 0.13), 0.05, 1.0])
        wdir /= np.linalg.norm(wdir)
        strength = 5.0 if self.line_mode else 1.5
        push = (nrm @ wdir)[..., None] * nrm * gust * strength
        acc = push + np.array([0.0, -p.gravity, 0.0])
        vel = (P - Q) * 0.995
        Q[:] = P
        P += (vel + acc * h * h) * W                      # pegged and held points don't move on their own
        self._relax(int(p.iterations))
        self._collide()

    def _relax(self, iters):
        """Pull every neighbour pair back toward its rest length (Jacobi, all pairs at once)."""
        P, W, L = self.P, self.W, self.rest
        bend = self.p.stiffness
        pairs = [((slice(None), slice(0, -1)), (slice(None), slice(1, None)), L, 1.0),            # across
                 ((slice(0, -1), slice(None)), (slice(1, None), slice(None)), L, 1.0),            # down
                 ((slice(0, -1), slice(0, -1)), (slice(1, None), slice(1, None)), L * 1.41421, 0.7),
                 ((slice(0, -1), slice(1, None)), (slice(1, None), slice(0, -1)), L * 1.41421, 0.7)]
        if bend > 0:
            pairs += [((slice(None), slice(0, -2)), (slice(None), slice(2, None)), 2 * L, 0.5 * bend),
                      ((slice(0, -2), slice(None)), (slice(2, None), slice(None)), 2 * L, 0.5 * bend)]
        wts = []
        for a, b, rest, k in pairs:
            wa, wb = W[a], W[b]
            s = wa + wb
            s[s == 0] = 1.0
            wts.append((a, b, rest, k * wa / s, k * wb / s))
        delta = np.empty_like(P)
        for _ in range(iters):
            delta[:] = 0
            for a, b, rest, fa, fb in wts:
                d = P[b] - P[a]
                dist = np.sqrt((d * d).sum(-1, keepdims=True)) + 1e-9
                c = d * (1.0 - rest / dist)
                delta[a] += c * fa
                delta[b] -= c * fb
            P += delta * 0.42                             # under-relaxed: each point has up to 12 pairs

    def _collide(self):
        P, Q = self.P, self.Q
        fr = self.p.friction
        if self.has_ball:
            d = P - BALL_C
            dist = np.sqrt((d * d).sum(-1, keepdims=True)) + 1e-9
            r = BALL_R + 0.02
            inside = (dist < r)
            if inside.any():
                fix = BALL_C + d / dist * r
                P[:] = np.where(inside, fix, P)
                m = inside * fr                            # friction: lose some sliding speed
                Q[:] = Q + (P - Q) * m * 0.9
        low = P[..., 1:2] < 0.01
        if low.any():
            P[..., 1] = np.maximum(P[..., 1], 0.01)
            m = low * fr
            Q[:] = Q + (P - Q) * m * 0.6

    def _normals(self):
        P = self.P
        du = np.gradient(P, axis=1)
        dv = np.gradient(P, axis=0)
        n = np.cross(dv, du)
        return n / (np.linalg.norm(n, axis=-1, keepdims=True) + 1e-9)

    # ------------------------------------------------------------- draw
    def _screen(self, p):
        c = self.viewproj @ [*p, 1.0]
        return (c[0] / c[3] + 1) / 2, (1 - c[1] / c[3]) / 2

    def draw_gl(self, gl):
        nrm = self._normals()                              # after this frame's moves
        verts = np.concatenate([self.P.reshape(-1, 3), nrm.reshape(-1, 3), self.uv], 1).astype(np.float32)
        self.cloth_mesh.update(verts[self.idx])

        gl.clear_3d(*HAZE)
        gl.depth(False)
        sk = self.sky
        sk.use()
        sun = self._screen(self.eye - LIGHT * 60.0)
        fx, fz = self.fwd[0], self.fwd[2]
        k = 400.0 / max(1e-6, math.hypot(fx, fz))
        hz = self._screen((self.eye[0] + fx * k, 0.0, self.eye[2] + fz * k))[1]
        sk.set("u_sun", *sun)
        sk.set("u_horizon", hz)
        sk.set("u_yaw", self.yaw)
        sk.set("u_time", self.t % 1000.0)
        sk.set("u_aspect", self.w / self.h)
        gl.draw_quad()

        gl.depth(True)
        fp = self.floor_prog
        fp.use()
        fp.set_mat4("u_viewproj", self.viewproj)
        fp.set("u_eye", *self.eye)
        fp.set("u_fog", *HAZE)
        self.floor_mesh.draw()

        lx, ly, lz = LIGHT                                 # long evening shadows on the grass
        flatten = np.array([[1, -lx / ly, 0, 0], [0, 0, 0, 0.004], [0, -lz / ly, 1, 0], [0, 0, 0, 1]])
        gl.blend(True)
        gl.depth(True, write=False)
        gl.stencil_once(True)
        sp = self.shadow_prog
        sp.use()
        sp.set("u_alpha", 0.28)
        sp.set_mat4("u_mvp", self.viewproj @ flatten)
        for m in (self.ball_mesh, getattr(self, "posts_mesh", None), self.cloth_mesh):
            if m:
                m.draw()
        gl.stencil_once(False)
        gl.blend(False)

        gl.depth(True, write=True)
        so = self.solid_prog
        so.use()
        so.set_mat4("u_viewproj", self.viewproj)
        so.set("u_light", *LIGHT)
        so.set("u_eye", *self.eye)
        if self.ball_mesh:
            so.set("u_color", 0.30, 0.42, 0.55)
            self.ball_mesh.draw()
        if self.line_mode:
            so.set("u_color", 0.46, 0.34, 0.24)
            self.posts_mesh.draw()
            so.set("u_color", 0.92, 0.90, 0.84)
            self.line_mesh.draw()
            if self.pegged:
                so.set("u_color", 0.80, 0.64, 0.44)
                self.pegs_mesh.draw()
        cp = self.cloth_prog
        cp.use()
        cp.set_mat4("u_viewproj", self.viewproj)
        cp.set("u_light", *LIGHT)
        cp.set("u_eye", *self.eye)
        cp.set("u_cloth", self.p.pattern, self.p.repeats, 0.0, 0.0)
        self.cloth_mesh.draw()
        gl.depth(False)

        if self.t < 7 and not self.prev:
            if not hasattr(self, "_hint"):
                lines = ["drag the sheet to pull it (up to 3 fingers)",
                         "drag the sky: look around   double-tap: unpeg / rehang" if self.line_mode else
                         "drag elsewhere: orbit   double-tap: new cloth"]
                imgs = [self.font.render(s, True, (60, 44, 34)) for s in lines]
                hint = pygame.Surface((max(i.get_width() for i in imgs) + 20, 52), pygame.SRCALPHA)
                pygame.draw.rect(hint, (255, 248, 236, 180), hint.get_rect(), border_radius=10)
                for k, im in enumerate(imgs):
                    hint.blit(im, im.get_rect(center=(hint.get_width() // 2, 15 + k * 22)))
                self._hint = gl.surface_texture(hint, "cloth_hint")
            gl.blit_at(self._hint, (self.w - self._hint.w) // 2, self.h - 70, alpha=min(1.0, 7 - self.t))

    # ------------------------------------------------------------- preview
    def preview(self, step):
        for _ in range(240):
            self.update(step)
        self.t = 99

    PREVIEW_AFTER = 0
