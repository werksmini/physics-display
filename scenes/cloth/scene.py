"""Cloth: a gingham tablecloth that drops onto a ball. Grab it and pull it around.

The cloth is a grid of particles joined by distance constraints (Verlet
integration, the method from Thomas Jakobsen's Hitman cloth):

- each particle remembers where it was last step; its velocity is simply
  (now - before), so moving a particle by hand gives it velocity for free
- gravity and a gusty breeze push the particles, then the constraints are
  relaxed a few times: every neighbour pair is nudged back toward its rest
  distance. Straight neighbours keep the cloth from stretching, diagonal ones
  stop it shearing, and pairs two apart give it a little stiffness to fold
- the ball and the floor push particles out, with friction so the cloth grips

All of this is numpy on whole slices of the grid at once (every horizontal
pair in one go, and so on), so it costs the same few dozen array operations
whatever the cloth size. The shape is uploaded as a fresh mesh each frame and
drawn on the GPU, with both sides lit and a woven gingham pattern.

Touch: drag the cloth to pull that point (a finger each, up to three);
drag empty space to orbit the camera, pinch to zoom; double-tap empty space
to drop a fresh cloth.
"""
import math

import numpy as np
import pygame

from playground.mat import look_at, perspective
from playground.scene import BaseScene, Param

FOV = 45.0
TARGET = np.array([0.0, 0.7, 0.0])
LIGHT = np.array([0.35, -1.0, -0.30]) / np.linalg.norm([0.35, -1.0, -0.30])
BALL_C = np.array([0.0, 0.75, 0.0])
BALL_R = 0.75

BG_FS = """
varying vec2 uv;
void main() {
    vec3 top = vec3(0.74, 0.73, 0.70), low = vec3(0.63, 0.62, 0.60);
    gl_FragColor = vec4(mix(top, low, smoothstep(0.0, 0.62, uv.y)), 1.0);
}"""

FLOOR_VS = """
attribute vec3 a_pos;
uniform mat4 u_viewproj;
varying vec3 v_world;
void main() { v_world = a_pos; gl_Position = u_viewproj * vec4(a_pos, 1.0); }"""

FLOOR_FS = """
uniform vec3 u_eye;
uniform vec3 u_fog;
varying vec3 v_world;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
void main() {
    float d = length(v_world - u_eye);
    vec2 p = v_world.xz;
    // pale wooden boards
    float board = floor(p.x / 0.32);
    float grain = sin(p.y * 9.0 + hash(vec2(board, 1.0)) * 40.0 + sin(p.x * 30.0) * 0.6) * 0.5 + 0.5;
    vec3 col = vec3(0.66, 0.58, 0.48) * (0.90 + 0.12 * hash(vec2(board, 3.0)) + 0.05 * grain);
    float seam = abs(fract(p.x / 0.32) - 0.5) * 0.32;
    col *= 1.0 - 0.25 * (1.0 - smoothstep(0.0, 0.006 + d * 0.0015, 0.16 - seam));
    col *= 1.0 + 0.12 * exp(-dot(p, p) * 0.08);
    col = mix(col, u_fog, clamp(1.0 - exp(-d * 0.07), 0.0, 1.0));
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
uniform vec4 u_cloth;      // checks across, red, green, blue
varying vec3 v_normal;
varying vec3 v_world;
varying vec2 v_uv;
void main() {
    vec3 n = normalize(v_normal);
    vec3 V = normalize(u_eye - v_world);
    if (dot(n, V) < 0.0) n = -n;                       // both sides of the cloth are lit
    // gingham: stripes one way plus stripes the other; where they cross is darkest
    vec2 g = step(0.5, fract(v_uv * u_cloth.x));
    float k = (g.x + g.y) * 0.5;
    vec3 red = u_cloth.yzw;
    vec3 base = mix(vec3(0.95, 0.93, 0.89), red, k * k * 0.85 + k * 0.15);
    vec2 w = fract(v_uv * u_cloth.x * 14.0);            // fine weave
    base *= 0.93 + 0.07 * abs(w.x - w.y);
    float diff = dot(n, -u_light);
    float wrap = max((diff + 0.35) / 1.35, 0.0);        // soft fabric light
    float sky = 0.5 + 0.5 * n.y;
    vec3 H = normalize(-u_light + V);
    float sheen = pow(max(dot(n, H), 0.0), 12.0) * 0.10;
    vec3 col = base * (0.22 + 0.20 * sky + 0.68 * wrap) + vec3(sheen);
    gl_FragColor = vec4(col, 1.0);
}"""

BALL_FS = """
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
    float spec = pow(max(dot(n, H), 0.0), 30.0) * 0.25;
    float sky = 0.5 + 0.5 * n.y;
    gl_FragColor = vec4(u_color * (0.25 + 0.22 * sky + 0.62 * diff) + vec3(spec), 1.0);
}"""

SHADOW_VS = """
attribute vec3 a_pos;
uniform mat4 u_mvp;
void main() { gl_Position = u_mvp * vec4(a_pos, 1.0); }"""

SHADOW_FS = """
uniform float u_alpha;
void main() { gl_FragColor = vec4(0.05, 0.03, 0.02, u_alpha); }"""


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


class Scene(BaseScene):
    TITLE = "Cloth (GPU)"
    GPU = True
    PARAMS = [
        Param("wind", 0.3, 0, 4, 0.05, "Breeze"),
        Param("stiffness", 0.5, 0, 1, 0.05, "Fold stiffness", help="0 = silk, 1 = canvas."),
        Param("friction", 0.6, 0, 1, 0.05, "Grip", help="How much the cloth sticks to the ball and floor."),
        Param("gravity", 9.8, 1, 20, 0.1, "Gravity"),
        Param("iterations", 6, 2, 14, 1, "Solver passes", help="More = less stretchy, slower."),
        Param("ball", 1, 0, 1, 1, "Ball", reset=True, help="1 = drape over a ball, 0 = just the floor."),
        Param("detail", 24, 12, 36, 1, "Cloth detail", reset=True, help="Particles along each edge."),
        Param("checks", 7, 2, 16, 1, "Checks across"),
    ]

    # ------------------------------------------------------------------ setup
    def setup(self):
        gl = self.gl
        self.bg = gl.program(BG_FS)
        self.floor_prog = gl.program(FLOOR_FS, FLOOR_VS)
        self.cloth_prog = gl.program(CLOTH_FS, LIT_VS, attribs=("a_pos", "a_normal", "a_uv"))
        self.ball_prog = gl.program(BALL_FS, LIT_VS, attribs=("a_pos", "a_normal", "a_uv"))
        self.shadow_prog = gl.program(SHADOW_FS, SHADOW_VS, attribs=("a_pos", "a_normal", "a_uv"))
        S = 40.0
        self.floor_mesh = gl.mesh([-S, 0, -S, S, 0, -S, S, 0, S, -S, 0, -S, S, 0, S, -S, 0, S], (3,))
        self.has_ball = bool(self.p.ball)
        self.ball_mesh = gl.mesh(sphere_mesh(BALL_C, BALL_R * 0.985), (3, 3, 2)) if self.has_ball else None

        n = self.n = int(self.p.detail)
        self.size = 2.6
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
        self.t = 0.0
        self.yaw, self.pitch, self.dist = 0.5, 0.42, 6.2
        self.grabs = {}             # finger id -> [particle index, depth]
        self.prev = {}
        self.gesture = None
        self.last_tap = (-9.0, 0.0, 0.0)
        self.font = pygame.font.Font(None, 24)
        self._camera()
        self._drop()

    def _drop(self):
        """A fresh cloth, flat and a little tilted, above the ball."""
        n, s = self.n, self.size
        rng = np.random.default_rng()
        g = np.linspace(-s / 2, s / 2, n)
        X, Z = np.meshgrid(g, g)
        tilt = rng.uniform(-0.08, 0.08)
        Y = 2.6 + X * tilt + Z * 0.08
        P = np.stack([X + rng.uniform(-0.06, 0.06), Y, Z], -1).astype(np.float64)
        self.P = P
        self.Q = P.copy()                             # where each particle was last step
        self.W = np.ones((n, n, 1))                   # inverse mass (0 = held)
        self.grabs.clear()

    # ------------------------------------------------------------- camera
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
                self.W.reshape(-1, 1)[g[0]] = 1.0       # (all the points that finger pinched)
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
                self._drop()
            else:
                self.last_tap = (self.t, x, y)

    # ------------------------------------------------------------- physics
    def update(self, dt):
        self.t += dt
        p = self.p
        h = dt
        P, Q, W = self.P, self.Q, self.W
        # wind: a gusty breeze that pushes on the face of the cloth
        nrm = self.nrm = self._normals()
        gust = p.wind * (0.6 + 0.4 * math.sin(self.t * 0.9) * math.sin(self.t * 0.37 + 1.0))
        wdir = np.array([math.cos(self.t * 0.07), 0.0, math.sin(self.t * 0.07) * 0.6 + 0.3])
        push = (nrm @ wdir)[..., None] * nrm * gust
        acc = push + np.array([0.0, -p.gravity, 0.0])
        vel = (P - Q) * 0.995
        Q[:] = P
        P += (vel + acc * h * h) * W                      # held points don't move on their own
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
    def draw_gl(self, gl):
        nrm = self._normals()                              # after this frame's moves
        verts = np.concatenate([self.P.reshape(-1, 3), nrm.reshape(-1, 3), self.uv], 1).astype(np.float32)
        self.cloth_mesh.update(verts[self.idx])

        gl.clear_3d(0.66, 0.65, 0.63)
        gl.depth(False)
        self.bg.use()
        gl.draw_quad()

        gl.depth(True)
        fp = self.floor_prog
        fp.use()
        fp.set_mat4("u_viewproj", self.viewproj)
        fp.set("u_eye", *self.eye)
        fp.set("u_fog", 0.66, 0.65, 0.63)
        self.floor_mesh.draw()

        lx, ly, lz = LIGHT                                 # shadows squashed onto the floor
        flatten = np.array([[1, -lx / ly, 0, 0], [0, 0, 0, 0.004], [0, -lz / ly, 1, 0], [0, 0, 0, 1]])
        gl.blend(True)
        gl.depth(True, write=False)
        gl.stencil_once(True)
        sp = self.shadow_prog
        sp.use()
        sp.set("u_alpha", 0.30)
        sp.set_mat4("u_mvp", self.viewproj @ flatten)
        if self.ball_mesh:
            self.ball_mesh.draw()
        self.cloth_mesh.draw()
        gl.stencil_once(False)
        gl.blend(False)

        gl.depth(True, write=True)
        if self.ball_mesh:
            bp = self.ball_prog
            bp.use()
            bp.set_mat4("u_viewproj", self.viewproj)
            bp.set("u_light", *LIGHT)
            bp.set("u_eye", *self.eye)
            bp.set("u_color", 0.30, 0.42, 0.55)
            self.ball_mesh.draw()
        cp = self.cloth_prog
        cp.use()
        cp.set_mat4("u_viewproj", self.viewproj)
        cp.set("u_light", *LIGHT)
        cp.set("u_eye", *self.eye)
        cp.set("u_cloth", self.p.checks, 0.78, 0.13, 0.14)
        self.cloth_mesh.draw()
        gl.depth(False)

        if self.t < 7 and not self.prev:
            if not hasattr(self, "_hint"):
                lines = ["drag the cloth to pull it (up to 3 fingers)",
                         "drag elsewhere: orbit   double-tap: new cloth"]
                imgs = [self.font.render(s, True, (40, 36, 34)) for s in lines]
                hint = pygame.Surface((max(i.get_width() for i in imgs) + 20, 52), pygame.SRCALPHA)
                pygame.draw.rect(hint, (255, 255, 255, 170), hint.get_rect(), border_radius=10)
                for k, im in enumerate(imgs):
                    hint.blit(im, im.get_rect(center=(hint.get_width() // 2, 15 + k * 22)))
                self._hint = gl.surface_texture(hint, "cloth_hint")
            gl.blit_at(self._hint, (self.w - self._hint.w) // 2, self.h - 70, alpha=min(1.0, 7 - self.t))

    # ------------------------------------------------------------- preview
    def preview(self, step):
        for _ in range(200):
            self.update(step)
        self.t = 99

    PREVIEW_AFTER = 0
