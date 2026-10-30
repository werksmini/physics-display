"""Cubes: pick up a cube with your fingers, spin it like in a CAD program, let it fall.

A real 3D scene on the GPU: a grey studio with a grid floor fading into haze,
lit cubes with softly bevelled edges, and shadows on the floor.

Gestures (on a cube):
- 1 finger: pick it up and tumble it (trackball: drag right spins it right).
- 2 fingers: carry it. Move them together to move it; twist to roll it;
  pinch to push it away, spread to pull it closer.
- 3 fingers: tumble it while it stays where it is.
- Let go: it falls with gravity, keeping the spin and throw you gave it,
  bounces, tumbles and settles. Then the next cube is presented.
On empty space: 1 finger orbits the camera, 2 fingers pinch to zoom.

Physics: each cube is a rigid body (position, velocity, rotation, spin).
Contacts are found by checking each cube's 8 corners against the floor and
against other cubes; each contact gets an impulse (a push at that corner) that
stops it sinking in, with a little bounce and friction. Because the push lands
at a corner, it also changes the spin, which is what makes cubes tumble
realistically. Cubes that stop moving go to sleep until something hits them.
"""
import colorsys
import math

import numpy as np
import pygame

from playground.mat import axis_angle, look_at, model, orthonormalize, perspective
from playground.scene import BaseScene, Param

CORNERS = np.array([[x, y, z] for x in (-.5, .5) for y in (-.5, .5) for z in (-.5, .5)])


def _edge_points():
    """Points along all 12 edges (quarter, half, three-quarter): with the corners, these
    catch cubes meeting edge-to-edge, where no corner pokes into the other cube."""
    pts = []
    for i in range(8):
        for j in range(i + 1, 8):
            if np.sum(CORNERS[i] != CORNERS[j]) == 1:
                for t in (0.25, 0.5, 0.75):
                    pts.append(CORNERS[i] + (CORNERS[j] - CORNERS[i]) * t)
    return np.array(pts)


SAMPLES = np.vstack([CORNERS, _edge_points()])     # 8 corners + 36 edge points
INV_I = 6.0                     # inverse inertia of a unit cube of mass 1 (I = m s^2 / 6)
FOV = 45.0
TARGET = np.array([0.0, 0.9, 0.0])
PRESENT_AT = np.array([0.0, 2.5, 0.0])
MAX_CUBES = 14
LIGHT = np.array([0.30, -1.0, -0.35]) / np.linalg.norm([0.30, -1.0, -0.35])
BASE_COLORS = [(0.86, 0.24, 0.22), (0.27, 0.72, 0.32), (0.22, 0.42, 0.86),
               (0.93, 0.76, 0.22), (0.80, 0.30, 0.74), (0.24, 0.74, 0.80)]

BG_FS = """
varying vec2 uv;
void main() {
    vec3 top = vec3(0.70, 0.71, 0.73), low = vec3(0.60, 0.61, 0.63);
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
    float w = 0.012 + d * 0.0025;                                 // lines stay ~1px wide far away
    vec2 g = abs(fract(p + 0.5) - 0.5);
    float line = 1.0 - smoothstep(0.0, w, min(g.x, g.y));
    vec2 g2 = abs(fract(p * 4.0 + 0.5) - 0.5) / 4.0;
    float fine = (1.0 - smoothstep(0.0, w * 0.6, min(g2.x, g2.y))) * clamp(1.0 - d / 9.0, 0.0, 1.0);
    vec3 col = vec3(0.58) - vec3(0.09) * line - vec3(0.035) * fine;
    col *= 1.0 + 0.10 * exp(-dot(p, p) * 0.05);                   // soft pool of light in the middle
    col = mix(col, u_fog, clamp(1.0 - exp(-d * 0.07), 0.0, 1.0));  // haze into the distance
    col += (hash(gl_FragCoord.xy) - 0.5) / 96.0;
    gl_FragColor = vec4(col, 1.0);
}"""

CUBE_VS = """
attribute vec3 a_pos;
attribute vec3 a_normal;
attribute float a_face;
uniform mat4 u_model;
uniform mat4 u_viewproj;
uniform vec3 u_colors[6];
varying vec3 v_normal;
varying vec3 v_world;
varying vec3 v_local;
varying vec3 v_color;
void main() {
    vec4 w = u_model * vec4(a_pos, 1.0);
    v_world = w.xyz;
    v_normal = (u_model * vec4(a_normal, 0.0)).xyz;
    v_local = a_pos;
    v_color = u_colors[int(a_face + 0.5)];
    gl_Position = u_viewproj * w;
}"""

CUBE_FS = """
uniform vec3 u_light;
uniform vec3 u_eye;
uniform float u_glow;
varying vec3 v_normal;
varying vec3 v_world;
varying vec3 v_local;
varying vec3 v_color;
void main() {
    vec3 n = normalize(v_normal);
    float diff = max(dot(n, -u_light), 0.0);
    vec3 a = abs(v_local) * 2.0;                                  // 1.0 at the cube's surface
    float mx = max(a.x, max(a.y, a.z)), mn = min(a.x, min(a.y, a.z));
    float mid = a.x + a.y + a.z - mx - mn;
    float edge = smoothstep(0.86, 0.985, mid);                     // near an edge: soft bevel
    vec3 base = v_color * (1.0 - 0.30 * edge) + vec3(0.10) * smoothstep(0.975, 1.0, mid);
    vec3 V = normalize(u_eye - v_world);
    vec3 H = normalize(-u_light + V);
    float spec = pow(max(dot(n, H), 0.0), 48.0) * 0.32;
    float sky = 0.5 + 0.5 * n.y;
    vec3 col = base * (0.26 + 0.22 * sky + 0.62 * diff) + vec3(spec) + base * u_glow * 0.22;
    gl_FragColor = vec4(col, 1.0);
}"""

SHADOW_VS = """
attribute vec3 a_pos;
uniform mat4 u_mvp;
void main() { gl_Position = u_mvp * vec4(a_pos, 1.0); }"""

SHADOW_FS = """
uniform float u_alpha;
void main() { gl_FragColor = vec4(0.02, 0.02, 0.06, u_alpha); }"""


def cube_mesh():
    """36 vertices: position, normal, face index (0..5)."""
    faces = [((1, 0, 0), (0, 1, 0), (0, 0, 1)), ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
             ((0, 1, 0), (0, 0, 1), (1, 0, 0)), ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
             ((0, 0, 1), (1, 0, 0), (0, 1, 0)), ((0, 0, -1), (0, 1, 0), (1, 0, 0))]
    out = []
    for f, (n, u, v) in enumerate(faces):
        n, u, v = (np.array(x, float) for x in (n, u, v))
        if np.dot(np.cross(u, v), n) < 0:
            u, v = v, u                                         # counter-clockwise seen from outside
        c = n * 0.5
        quad = [c - u * .5 - v * .5, c + u * .5 - v * .5, c + u * .5 + v * .5, c - u * .5 + v * .5]
        for i in (0, 1, 2, 0, 2, 3):
            out.extend([*quad[i], *n, float(f)])
    return out


class Cube:
    def __init__(self, idx, pos, rot):
        self.pos, self.R = np.array(pos, float), np.array(rot, float)
        self.vel, self.w = np.zeros(3), np.zeros(3)
        self.state = "presented"            # presented | held | free | sleep
        self.still = 0.0
        self.age = 0.0
        hue_shift = (idx * 0.09) % 1.0
        cols = BASE_COLORS[idx % 6:] + BASE_COLORS[:idx % 6]
        self.colors = []
        for c in cols:
            h, l, s = colorsys.rgb_to_hls(*c)
            self.colors.extend(colorsys.hls_to_rgb((h + hue_shift) % 1.0, l, s))

    def corners(self):
        return self.pos + CORNERS @ self.R.T

    def samples(self):
        return self.pos + SAMPLES @ self.R.T


class Scene(BaseScene):
    TITLE = "Cubes (GPU, 3D)"
    GPU = True
    PARAMS = [
        Param("gravity", 1.0, 0.1, 3, 0.05, "Gravity"),
        Param("bounce", 0.3, 0, 0.9, 0.01, "Bounciness"),
        Param("friction", 0.6, 0, 1.5, 0.05, "Friction"),
        Param("spin_speed", 1.0, 0.2, 3, 0.05, "Spin sensitivity"),
        Param("throw", 1.0, 0, 2, 0.05, "Throw strength", help="How much of your hand's motion the cube keeps."),
        Param("max_cubes", 10, 1, MAX_CUBES, 1, "Cubes kept"),
    ]

    # ------------------------------------------------------------------ setup
    def setup(self):
        gl = self.gl
        self.bg = gl.program(BG_FS)
        self.floor_prog = gl.program(FLOOR_FS, FLOOR_VS)
        self.cube_prog = gl.program(CUBE_FS, CUBE_VS, attribs=("a_pos", "a_normal", "a_face"))
        self.shadow_prog = gl.program(SHADOW_FS, SHADOW_VS, attribs=("a_pos", "a_normal", "a_face"))
        self.cube_mesh = gl.mesh(cube_mesh(), (3, 3, 1))
        S = 40.0
        self.floor_mesh = gl.mesh([-S, 0, -S, S, 0, -S, S, 0, S, -S, 0, -S, S, 0, S, -S, 0, S], (3,))
        self.cubes = []
        self.count = 0
        self.t = 0.0
        self.yaw, self.pitch, self.dist = 0.42, 0.40, 8.5
        self.prev = {}                          # finger id -> (x, y) last frame
        self.held = None
        self.cam_drag = False
        self.release_t = None
        self.hold_v, self.hold_w = np.zeros(3), np.zeros(3)
        self.last_pos, self.last_R = None, None
        self.font = pygame.font.Font(None, 24)
        self._camera()
        self._present()

    def _present(self):
        rot = axis_angle([0.3, 1, 0.2], 0.6)
        c = Cube(self.count, PRESENT_AT + [0, 4.0, 0], rot)
        self.count += 1
        self.cubes.append(c)
        while len(self.cubes) > int(self.p.max_cubes):
            old = next((k for k in self.cubes if k.state == "sleep"), None) or self.cubes[0]
            self.cubes.remove(old)
        self.presented = c

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

    def _project(self, p):
        c = self.viewproj @ [*p, 1.0]
        return ((c[0] / c[3] + 1) / 2 * self.w, (1 - c[1] / c[3]) / 2 * self.h)

    def _pick(self, pts):
        """The cube under any of the fingers (ray hit, or close on screen)."""
        best, best_t = None, 1e9
        for (x, y) in pts:
            o, d = self._ray(x, y)
            for c in self.cubes:
                lo, ld = (o - c.pos) @ c.R, d @ c.R
                with np.errstate(divide="ignore", invalid="ignore"):
                    t1, t2 = (-0.5 - lo) / ld, (0.5 - lo) / ld
                tmin = np.nanmax(np.minimum(t1, t2))
                tmax = np.nanmin(np.maximum(t1, t2))
                if tmax >= max(tmin, 0) and tmin < best_t:
                    best, best_t = c, tmin
        if best is None:                                    # forgiving: near the cube on screen
            for (x, y) in pts:
                for c in self.cubes:
                    sx, sy = self._project(c.pos)
                    if math.hypot(sx - x, sy - y) < 48:
                        return c
        return best

    # ------------------------------------------------------------- gestures
    def fingers(self, fingers):
        ids = set(fingers)
        prev_ids = set(self.prev)
        if ids != prev_ids:
            if not prev_ids and ids:                         # gesture starts
                c = self._pick(list(fingers.values()))
                if c is not None:
                    self.held = c
                    c.state = "held"
                    c.vel[:], c.w[:] = 0, 0
                    self.hold_v[:], self.hold_w[:] = 0, 0
                    self.last_pos, self.last_R = c.pos.copy(), c.R.copy()
                    if c is self.presented:
                        self.presented = None
                else:
                    self.cam_drag = True
            elif prev_ids and not ids:                       # all fingers lifted
                if self.held is not None:
                    c = self.held
                    c.state = "free"
                    c.vel = np.clip(self.hold_v * self.p.throw, -14, 14)
                    c.w = np.clip(self.hold_w * self.p.throw, -25, 25)
                    c.still = 0.0
                    self.held = None
                    self.release_t = self.t
                self.cam_drag = False
            self.prev = dict(fingers)                        # re-baseline when fingers change
            return

        n = len(fingers)
        if n == 0:
            return
        cur = np.array([fingers[k] for k in sorted(ids)], float)
        old = np.array([self.prev[k] for k in sorted(ids)], float)
        dc = cur.mean(0) - old.mean(0)
        if self.held is not None:
            c = self.held
            if n == 2:
                depth = max(1.5, float(np.dot(c.pos - self.eye, self.fwd)))
                scale = 2 * depth * math.tan(math.radians(FOV) / 2) / self.h
                c.pos += (self.right * dc[0] - self.up * dc[1]) * scale
                a0 = math.atan2(*(old[1] - old[0])[::-1])
                a1 = math.atan2(*(cur[1] - cur[0])[::-1])
                twist = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
                c.R = axis_angle(self.fwd, twist) @ c.R
                d0, d1 = np.linalg.norm(old[1] - old[0]), np.linalg.norm(cur[1] - cur[0])
                if d0 > 10:
                    push = (d1 / d0 - 1) * depth * 1.2
                    new_depth = depth - push
                    if 2.5 < new_depth < 20:
                        c.pos -= self.fwd * push
            else:                                            # 1 or 3+ fingers: trackball
                k = 0.011 * self.p.spin_speed
                ang = math.hypot(*dc) * k
                if ang > 0:
                    c.R = axis_angle(self.up * dc[0] + self.right * dc[1], ang) @ c.R
            c.R = orthonormalize(c.R)
        elif self.cam_drag:
            if n == 1:
                self.yaw -= dc[0] * 0.008
                self.pitch = min(1.35, max(0.08, self.pitch + dc[1] * 0.006))
            elif n >= 2:
                d0, d1 = np.linalg.norm(old[1] - old[0]), np.linalg.norm(cur[1] - cur[0])
                if d0 > 10:
                    self.dist = min(18, max(4, self.dist * d0 / d1))
            self._camera()
        self.prev = dict(fingers)

    # ------------------------------------------------------------- physics
    def update(self, dt):
        self.t += dt
        p = self.p
        # presented cube: drift down into place, bob and turn slowly
        if self.presented is not None:
            c = self.presented
            c.age += dt
            c.pos += (PRESENT_AT + [0, 0.08 * math.sin(self.t * 1.6), 0] - c.pos) * min(1.0, dt * 3.0)
            c.R = orthonormalize(axis_angle([0.15, 1, 0.1], dt * 0.6) @ c.R)
        # held cube: keep it off the floor, estimate its velocity for throwing
        if self.held is not None:
            c = self.held
            c.pos[1] = max(c.pos[1], 0.9)
            v = (c.pos - self.last_pos) / dt
            dR = c.R @ self.last_R.T
            ang = math.acos(max(-1.0, min(1.0, (np.trace(dR) - 1) / 2)))
            axis = np.array([dR[2, 1] - dR[1, 2], dR[0, 2] - dR[2, 0], dR[1, 0] - dR[0, 1]])
            wv = axis / (np.linalg.norm(axis) + 1e-9) * ang / dt if ang > 1e-5 else np.zeros(3)
            self.hold_v = self.hold_v * 0.6 + v * 0.4
            self.hold_w = self.hold_w * 0.6 + wv * 0.4
            self.last_pos, self.last_R = c.pos.copy(), c.R.copy()
        # rigid bodies, 4 small steps per frame for stability
        h = dt / 4
        for _ in range(4):
            self._step(h)
        # present the next cube once the last one has landed
        if self.presented is None and self.held is None and self.release_t is not None:
            free = [c for c in self.cubes if c.state == "free"]
            if not free or self.t - self.release_t > 3.0:
                self.release_t = None
                self._present()

    def _step(self, h):
        p = self.p
        g = 9.8 * p.gravity
        free = [c for c in self.cubes if c.state == "free"]
        for c in free:
            c.vel[1] -= g * h
            c.pos += c.vel * h
            sp = np.linalg.norm(c.w)
            if sp > 1e-9:
                c.R = axis_angle(c.w / sp, sp * h) @ c.R
        for c in free:
            c.touching = False
        for _ in range(3):
            for c in free:
                touching = False
                P = c.corners()
                for i in np.nonzero(P[:, 1] < 0)[0]:          # floor
                    self._contact(c, None, P[i], np.array([0.0, 1.0, 0.0]), -P[i, 1])
                    touching = True
                for o in self.cubes:                          # other cubes
                    if o is c or np.sum((o.pos - c.pos) ** 2) > 3.1:
                        continue
                    if o.state == "free" and id(o) < id(c):
                        continue                              # free pairs handled once
                    touching |= self._cube_pair(c, o)
                c.touching = c.touching or touching or bool(np.any(P[:, 1] < 0.01))
        for c in free:
            c.R = orthonormalize(c.R) if np.random.random() < 0.1 else c.R
            damp = 1.0 - (2.0 if getattr(c, "touching", False) else 0.05) * h
            c.w *= damp
            c.vel *= 1.0 - 0.03 * h
            for k in (0, 2):                                   # invisible walls keep cubes in view
                if abs(c.pos[k]) > 6.5:
                    c.pos[k] = math.copysign(6.5, c.pos[k])
                    c.vel[k] *= -0.4
            if np.linalg.norm(c.vel) < 0.08 and np.linalg.norm(c.w) < 0.15 and getattr(c, "touching", False):
                c.still += h
                if c.still > 0.4:
                    c.state, c.vel[:], c.w[:] = "sleep", 0, 0
            else:
                c.still = 0.0

    def _cube_pair(self, a, b):
        hit = False
        for src, dst, sign in ((a, b, 1.0), (b, a, -1.0)):
            loc = (src.samples() - dst.pos) @ dst.R            # src corner/edge points in dst's frame
            inside = np.all(np.abs(loc) < 0.5, axis=1)
            if not inside.any():
                continue
            pts = loc[inside]
            pen = 0.5 - np.abs(pts)
            axis = np.argmin(pen, axis=1)
            k = int(np.bincount(axis, minlength=3).argmax())  # the face most points are pushing through
            sel = axis == k
            centre = pts[sel].mean(0)
            depth = float(pen[sel, k].max())
            n = dst.R[:, k] * math.copysign(1.0, centre[k]) * sign   # pushes a away from b
            self._contact(a, b if b.state == "free" else None, dst.pos + dst.R @ centre, n, depth, other=b)
            hit = True
        return hit

    def _contact(self, a, b, point, n, pen, other=None):
        """Impulse at a contact point: stop sinking in, bounce a little, add friction.
        b is the other free body, or None if it's static (floor, sleeping or held cube).
        Written with plain floats: numpy is slow for 3-number vectors."""
        p = self.p
        px, py, pz = float(point[0]), float(point[1]), float(point[2])
        nx, ny, nz = float(n[0]), float(n[1]), float(n[2])
        ax, ay, az = a.pos.tolist()
        rax, ray, raz = px - ax, py - ay, pz - az
        avx, avy, avz = a.vel.tolist()
        awx, awy, awz = a.w.tolist()
        vx = avx + awy * raz - awz * ray
        vy = avy + awz * rax - awx * raz
        vz = avz + awx * ray - awy * rax
        if b is not None:
            bx, by, bz = b.pos.tolist()
            rbx, rby, rbz = px - bx, py - by, pz - bz
            bvx, bvy, bvz = b.vel.tolist()
            bwx, bwy, bwz = b.w.tolist()
            vx -= bvx + bwy * rbz - bwz * rby
            vy -= bvy + bwz * rbx - bwx * rbz
            vz -= bvz + bwx * rby - bwy * rbx
            inv_b, invI_b = 1.0, INV_I
        else:
            rbx = rby = rbz = 0.0
            inv_b = invI_b = 0.0
        share = 1.0 / (1.0 + inv_b)
        push = pen * 0.6
        a.pos += (nx * push * share, ny * push * share, nz * push * share)       # push apart
        if b is not None:
            b.pos -= (nx * push * (1 - share), ny * push * (1 - share), nz * push * (1 - share))
        vn = vx * nx + vy * ny + vz * nz
        if vn >= 0:
            return

        def cross(ux, uy, uz, wx, wy, wz):
            return uy * wz - uz * wy, uz * wx - ux * wz, ux * wy - uy * wx

        def apply(jx, jy, jz):
            a.vel += (jx, jy, jz)
            cx, cy, cz = cross(rax, ray, raz, jx, jy, jz)
            a.w += (INV_I * cx, INV_I * cy, INV_I * cz)
            if b is not None:
                b.vel -= (jx * inv_b, jy * inv_b, jz * inv_b)
                cx, cy, cz = cross(rbx, rby, rbz, jx, jy, jz)
                b.w -= (invI_b * cx, invI_b * cy, invI_b * cz)

        def eff_mass(ux, uy, uz):
            c1 = cross(rax, ray, raz, ux, uy, uz)
            c2 = cross(rbx, rby, rbz, ux, uy, uz)
            return (1.0 + inv_b + INV_I * (c1[0] ** 2 + c1[1] ** 2 + c1[2] ** 2)
                    + invI_b * (c2[0] ** 2 + c2[1] ** 2 + c2[2] ** 2))

        e = p.bounce if vn < -1.0 else 0.0                    # no jitter when resting
        j = -(1 + e) * vn / eff_mass(nx, ny, nz)
        apply(nx * j, ny * j, nz * j)
        tx, ty, tz = vx - vn * nx, vy - vn * ny, vz - vn * nz
        tl = math.sqrt(tx * tx + ty * ty + tz * tz)
        if tl > 1e-6:
            tx, ty, tz = tx / tl, ty / tl, tz / tl
            jt = max(-tl / eff_mass(tx, ty, tz), -p.friction * j)
            apply(tx * jt, ty * jt, tz * jt)
        if other is not None and other.state == "sleep" and j > 0.6:
            other.state, other.still = "free", 0.0           # a hard knock wakes it up

    # ------------------------------------------------------------- drawing
    def draw_gl(self, gl):
        gl.clear_3d(0.6, 0.61, 0.63)
        gl.depth(False)
        self.bg.use()
        gl.draw_quad()

        gl.depth(True)
        fp = self.floor_prog
        fp.use()
        fp.set_mat4("u_viewproj", self.viewproj)
        fp.set("u_eye", *self.eye)
        fp.set("u_fog", 0.62, 0.63, 0.65)
        self.floor_mesh.draw()

        # shadows: each cube squashed flat onto the floor along the light direction
        lx, ly, lz = LIGHT
        flatten = np.array([[1, -lx / ly, 0, 0], [0, 0, 0, 0.004], [0, -lz / ly, 1, 0], [0, 0, 0, 1]])
        gl.blend(True)
        gl.depth(True, write=False)
        gl.stencil_once(True)
        sp = self.shadow_prog
        sp.use()
        for c in self.cubes:
            fade = min(1.0, max(0.25, 1.0 - (c.pos[1] - 0.5) / 7.0))
            sp.set("u_alpha", 0.36 * fade)
            sp.set_mat4("u_mvp", self.viewproj @ flatten @ model(c.pos, c.R))
            self.cube_mesh.draw()
        gl.stencil_once(False)
        gl.blend(False)

        gl.depth(True, write=True)
        gl.cull(True)
        cp = self.cube_prog
        cp.use()
        cp.set_mat4("u_viewproj", self.viewproj)
        cp.set("u_light", *LIGHT)
        cp.set("u_eye", *self.eye)
        for c in self.cubes:
            cp.set_mat4("u_model", model(c.pos, c.R))
            cp.set_vec3_array("u_colors", c.colors)
            cp.set("u_glow", 1.0 if c is self.held else 0.0)
            self.cube_mesh.draw()
        gl.cull(False)
        gl.depth(False)

        if self.t < 7 and not self.prev:                     # a hint for the first few seconds
            if not hasattr(self, "_hint"):
                lines = ["1 finger: spin   2: carry, twist, pinch", "3: tumble   empty space: orbit view"]
                imgs = [self.font.render(s, True, (40, 40, 46)) for s in lines]
                hint = pygame.Surface((max(i.get_width() for i in imgs) + 20, 52), pygame.SRCALPHA)
                pygame.draw.rect(hint, (255, 255, 255, 170), hint.get_rect(), border_radius=10)
                for k, im in enumerate(imgs):
                    hint.blit(im, im.get_rect(center=(hint.get_width() // 2, 15 + k * 22)))
                self._hint = gl.surface_texture(hint, "cubes_hint")
            gl.blit_at(self._hint, (self.w - self._hint.w) // 2, self.h - 70, alpha=min(1.0, 7 - self.t))

    # ------------------------------------------------------------- preview
    def preview(self, step):
        """Drop a few cubes into a pile, then present a new one."""
        rng = np.random.default_rng(3)
        self.cubes.clear()
        for i in range(5):
            c = Cube(i, [rng.uniform(-1.4, 1.4), 1.2 + i * 1.3, rng.uniform(-1.2, 0.8)],
                     axis_angle(rng.normal(size=3), rng.uniform(0, 3)))
            c.state = "free"
            c.w = rng.normal(0, 2, 3)
            self.cubes.append(c)
            for _ in range(25):
                self.update(step)
        for _ in range(240):
            self.update(step)
        self.count = 5
        self._present()

    PREVIEW_AFTER = 150
