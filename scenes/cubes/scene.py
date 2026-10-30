"""Cubes: turn a cube in space with your fingers, set it down, watch it fall.

A real 3D scene on the GPU: a grey studio with a grid floor fading into haze,
lit cubes with softly bevelled edges, and shadows on the floor.

The screen is too small to touch the cube itself, so the controls are
indirect, like a laptop trackpad: gestures anywhere steer the active cube.
- 1 finger drag: tumble it (trackball: drag right, it spins right).
- 2 fingers: move it around; twist to roll it; pinch to push it away,
  spread to pull it closer.
- 3 fingers: tumble it too.
- Lift your fingers: it stays where you left it, so you can adjust in steps.
- Double-tap: set it down (it falls with gravity). A quick two-finger flick
  throws it instead.
- Tap a cube on the floor: pick it back up.
With no active cube (while the last one lands), dragging orbits the camera
and pinching zooms.

Physics: each cube is a rigid body (position, velocity, rotation, spin).
Contacts are found by checking each cube's corners against the floor, and
corner and edge points against other cubes; each contact gets an impulse (a
push at that point) that stops it sinking in, with a little bounce and
friction. Because the push lands off-centre, it also changes the spin, which
is what makes cubes tumble and settle onto a face. Cubes that stop moving
go to sleep until something knocks them.
"""
import colorsys
import math

import numpy as np
import pygame

from playground.mat import axis_angle, look_at, model, orthonormalize, perspective
from playground.scene import BaseScene, Param

CORNERS = np.array([[x, y, z] for x in (-.5, .5) for y in (-.5, .5) for z in (-.5, .5)])


def _edge_points():
    """The midpoints of all 12 edges: with the corners, these
    catch cubes meeting edge-to-edge, where no corner pokes into the other cube."""
    pts = []
    for i in range(8):
        for j in range(i + 1, 8):
            if np.sum(CORNERS[i] != CORNERS[j]) == 1:
                for t in (0.5,):
                    pts.append(CORNERS[i] + (CORNERS[j] - CORNERS[i]) * t)
    return np.array(pts)


SAMPLES = np.vstack([CORNERS, _edge_points()])     # 8 corners + 12 edge midpoints
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
        self.state = "held"                 # held (active, kinematic) | free | sleep
        self.still = 0.0
        self.touching = False
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


def reorthonormalize(R):
    """Cheap clean-up of rounding drift (Gram-Schmidt on the columns)."""
    x = R[:, 0] / np.linalg.norm(R[:, 0])
    y = R[:, 1] - x * (x @ R[:, 1])
    y /= np.linalg.norm(y)
    return np.column_stack([x, y, np.cross(x, y)])


class Scene(BaseScene):
    TITLE = "Cubes (GPU, 3D)"
    GPU = True
    PARAMS = [
        Param("gravity", 1.0, 0.1, 3, 0.05, "Gravity"),
        Param("bounce", 0.3, 0, 0.9, 0.01, "Bounciness"),
        Param("friction", 0.6, 0, 1.5, 0.05, "Friction"),
        Param("spin_speed", 1.0, 0.2, 3, 0.05, "Spin sensitivity"),
        Param("move_speed", 1.0, 0.2, 3, 0.05, "Move sensitivity"),
        Param("throw", 1.0, 0, 2, 0.05, "Throw strength", help="How much of a flick the cube keeps."),
        Param("max_cubes", 8, 1, MAX_CUBES, 1, "Cubes kept"),
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
        self.active = None                      # the cube your gestures steer
        self.hover = PRESENT_AT.copy()          # where the active cube floats
        self.touched = False                    # has the active cube been moved yet?
        self.release_t = None
        self.hold_v, self.hold_w = np.zeros(3), np.zeros(3)
        self.last_pos, self.last_R = None, None
        self.gesture = None                     # info about the current touch, for taps
        self.last_tap = (-9.0, 0.0, 0.0)
        self.held = None                        # kept for drawing (glow)
        self.font = pygame.font.Font(None, 24)
        self.target = TARGET.copy()             # what the camera looks at
        self.mode = "cube"                      # "cube": gestures steer the cube; "view": the camera
        self.mode_t = -9.0                      # when the mode last changed (for the label)
        self._camera()
        self._present()

    def _present(self, cube=None):
        if cube is None:
            cube = Cube(self.count, PRESENT_AT + [0, 4.0, 0], axis_angle([0.3, 1, 0.2], 0.6))
            self.count += 1
            self.cubes.append(cube)
            while len(self.cubes) > int(self.p.max_cubes):
                old = next((k for k in self.cubes if k.state == "sleep"), None)
                if old is None:
                    break
                self.cubes.remove(old)
            self.hover = PRESENT_AT.copy()
        else:                                   # a cube picked back up from the floor
            for o in self.cubes:                # whatever rested on it starts to fall
                if o is not cube and o.state == "sleep" and np.sum((o.pos - cube.pos) ** 2) < 3.0:
                    o.state, o.still = "free", 0.0
            self.hover = np.array([cube.pos[0], max(2.2, cube.pos[1] + 1.5), cube.pos[2]])
        cube.state = "held"
        cube.vel[:], cube.w[:] = 0, 0
        self.active = self.held = cube
        self.touched = False
        self.hold_v[:], self.hold_w[:] = 0, 0
        self.last_pos, self.last_R = cube.pos.copy(), cube.R.copy()

    def _drop(self, vel=None, w=None):
        c = self.active
        if c is None:
            return
        c.state, c.still = "free", 0.0
        c.vel = np.zeros(3) if vel is None else np.clip(vel, -14, 14)
        c.w = np.zeros(3) if w is None else np.clip(w, -25, 25)
        self.active = self.held = None
        self.release_t = self.t

    # ------------------------------------------------------------- camera
    def _camera(self):
        cp = math.cos(self.pitch)
        self.eye = self.target + self.dist * np.array([cp * math.sin(self.yaw), math.sin(self.pitch), cp * math.cos(self.yaw)])
        self.view = look_at(self.eye, self.target)
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

    def _pick(self, x, y):
        """The cube under (x, y): ray hit, or close on screen."""
        o, d = self._ray(x, y)
        best, best_t = None, 1e9
        for c in self.cubes:
            lo, ld = (o - c.pos) @ c.R, d @ c.R
            with np.errstate(divide="ignore", invalid="ignore"):
                t1, t2 = (-0.5 - lo) / ld, (0.5 - lo) / ld
            tmin = np.nanmax(np.minimum(t1, t2))
            tmax = np.nanmin(np.maximum(t1, t2))
            if tmax >= max(tmin, 0) and tmin < best_t:
                best, best_t = c, tmin
        if best is None:
            for c in self.cubes:
                sx, sy = self._project(c.pos)
                if math.hypot(sx - x, sy - y) < 40:
                    return c
        return best

    # ------------------------------------------------------------- gestures
    def fingers(self, fingers):
        ids, prev_ids = set(fingers), set(self.prev)
        if ids != prev_ids:
            if not prev_ids and ids:                         # a touch starts
                x, y = next(iter(fingers.values()))
                self.gesture = {"t0": self.t, "start": (x, y), "moved": 0.0, "max_n": len(ids),
                                "button": self._on_button(x, y)}
            elif prev_ids and not ids:                       # all fingers lifted
                self._end_gesture()
            if self.gesture:
                self.gesture["max_n"] = max(self.gesture["max_n"], len(ids))
            self.prev = dict(fingers)                        # re-baseline when fingers change
            return
        n = len(fingers)
        if n == 0:
            return
        keys = sorted(ids)
        cur = np.array([fingers[k] for k in keys], float)
        old = np.array([self.prev[k] for k in keys], float)
        dc = cur.mean(0) - old.mean(0)
        if self.gesture:
            self.gesture["moved"] += math.hypot(*dc)
            if self.gesture["button"]:                       # touches on the button don't steer
                self.prev = dict(fingers)
                return
        c = self.active if self.mode == "cube" else None
        if c is not None:
            self.touched = True
            if n == 2:
                depth = max(1.5, float(np.dot(self.hover - self.eye, self.fwd)))
                scale = 2 * depth * math.tan(math.radians(FOV) / 2) / self.h * self.p.move_speed
                self.hover += (self.right * dc[0] - self.up * dc[1]) * scale
                a0 = math.atan2(old[1, 1] - old[0, 1], old[1, 0] - old[0, 0])
                a1 = math.atan2(cur[1, 1] - cur[0, 1], cur[1, 0] - cur[0, 0])
                twist = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
                c.R = axis_angle(self.fwd, twist) @ c.R
                d0, d1 = np.linalg.norm(old[1] - old[0]), np.linalg.norm(cur[1] - cur[0])
                if d0 > 10:
                    push = (d1 / d0 - 1) * depth * 1.2
                    if 3.0 < depth - push < 18:
                        self.hover -= self.fwd * push
                self.hover[1] = max(self.hover[1], 0.9)
                for k in (0, 2):
                    self.hover[k] = max(-6.0, min(6.0, self.hover[k]))
            else:                                            # 1 or 3+ fingers: trackball
                ang = math.hypot(*dc) * 0.011 * self.p.spin_speed
                if ang > 0:
                    c.R = axis_angle(self.up * dc[0] + self.right * dc[1], ang) @ c.R
            c.R = reorthonormalize(c.R)
        else:                                                # view mode (or no cube): the camera
            if n == 1:                                       # orbit
                self.yaw -= dc[0] * 0.008
                self.pitch = min(1.35, max(0.08, self.pitch + dc[1] * 0.006))
            else:                                            # pinch: zoom; slide: pan; twist: turn
                d0, d1 = np.linalg.norm(old[1] - old[0]), np.linalg.norm(cur[1] - cur[0])
                if d0 > 10:
                    self.dist = min(18, max(3, self.dist * d0 / d1))
                a0 = math.atan2(old[1, 1] - old[0, 1], old[1, 0] - old[0, 0])
                a1 = math.atan2(cur[1, 1] - cur[0, 1], cur[1, 0] - cur[0, 0])
                self.yaw -= (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
                scale = 2 * self.dist * math.tan(math.radians(FOV) / 2) / self.h
                flat_r = np.array([self.right[0], 0, self.right[2]])
                flat_f = np.array([self.fwd[0], 0, self.fwd[2]])
                flat_r /= np.linalg.norm(flat_r) + 1e-9
                flat_f /= np.linalg.norm(flat_f) + 1e-9
                self.target += (-flat_r * dc[0] + flat_f * dc[1]) * scale
                for k in (0, 2):
                    self.target[k] = max(-6.0, min(6.0, self.target[k]))
            self._camera()
        self.prev = dict(fingers)

    def _end_gesture(self):
        g, self.gesture = self.gesture, None
        if g is None:
            return
        quick = self.t - g["t0"] < 0.3 and g["moved"] < 14
        if g["button"]:
            if self.t - g["t0"] < 0.6 and g["moved"] < 30:   # tap the corner button: switch mode
                self._set_mode("view" if self.mode == "cube" else "cube")
            return
        if quick and g["max_n"] == 1:                        # a tap
            x, y = g["start"]
            t, lx, ly = self.last_tap
            if self.t - t < 0.4 and math.hypot(x - lx, y - ly) < 70:
                self.last_tap = (-9.0, 0.0, 0.0)             # double-tap: set the cube down
                self._drop()
                return
            self.last_tap = (self.t, x, y)
            c = self._pick(x, y)
            if c is not None and c is not self.active and c.state in ("sleep", "free"):
                self._drop()                                 # tap a cube on the floor: pick it up
                self._present(c)
                self._set_mode("cube")
            return
        if self.active is not None and self.mode == "cube" and g["max_n"] >= 2:      # a quick flick throws it
            if np.linalg.norm(self.hold_v) > 3.0:
                self._drop(self.hold_v * self.p.throw, self.hold_w * self.p.throw)

    # ------------------------------------------------------------- mode button
    def _button(self):
        return self.w - 34, 34, 24

    def _on_button(self, x, y):
        bx, by, r = self._button()
        return math.hypot(x - bx, y - by) < r + 18      # a generous target for a fingertip

    def _set_mode(self, mode):
        if mode != self.mode:
            self.mode, self.mode_t = mode, self.t

    def _icon(self, gl, mode):
        """A small round chip: a cube (manipulate) or orbit arrows around an eye (navigate)."""
        key = "cubes_icon_" + mode
        cache = self.__dict__.setdefault("_icons", {})
        if key in cache:
            return cache[key]
        S = 4                                            # draw big, then shrink: smooth edges
        r = self._button()[2]
        D = 2 * r * S
        big = pygame.Surface((D, D), pygame.SRCALPHA)
        c = D // 2
        pygame.draw.circle(big, (255, 255, 255, 190), (c, c), c)
        ink = (52, 54, 62, 255)
        lw = 2 * S
        if mode == "cube":                               # isometric wireframe cube
            k = 0.42 * c
            top = (c, c - k); bot = (c, c + k)
            ul = (c - 0.87 * k, c - 0.5 * k); ur = (c + 0.87 * k, c - 0.5 * k)
            ll = (c - 0.87 * k, c + 0.5 * k); lr = (c + 0.87 * k, c + 0.5 * k)
            pygame.draw.polygon(big, (214, 120, 70, 255), [(c, c), ur, top, ul])
            pygame.draw.lines(big, ink, True, [top, ur, lr, bot, ll, ul], lw)
            for q in (ul, ur, bot):
                pygame.draw.line(big, ink, (c, c), q, lw)
        else:                                            # eye inside an orbit ring with arrowheads
            rect = pygame.Rect(0, 0, 1.3 * c, 0.62 * c)
            rect.center = (c, c)
            pygame.draw.ellipse(big, ink, rect, lw)
            pygame.draw.circle(big, (70, 120, 200, 255), (c, c), int(0.17 * c))
            for sgn in (-1, 1):
                ax = c + sgn * 0.65 * c
                ay = c + sgn * 0.02 * c
                tip = (ax, ay + sgn * 0.22 * c)
                pygame.draw.polygon(big, ink, [tip, (ax - 0.16 * c, ay - sgn * 0.02 * c),
                                               (ax + 0.16 * c, ay - sgn * 0.02 * c)])
        small = pygame.transform.smoothscale(big, (2 * r, 2 * r))
        cache[key] = gl.surface_texture(small, key)
        return cache[key]

    # ------------------------------------------------------------- physics
    def update(self, dt):
        self.t += dt
        c = self.active
        if c is not None:
            if not self.touched:                             # idle: bob and turn slowly
                target = self.hover + [0, 0.08 * math.sin(self.t * 1.6), 0]
                c.R = reorthonormalize(axis_angle([0.15, 1, 0.1], dt * 0.6) @ c.R)
            else:
                target = self.hover
            c.pos += (target - c.pos) * min(1.0, dt * (12.0 if self.touched else 3.0))
            v = (c.pos - self.last_pos) / dt
            dR = c.R @ self.last_R.T
            ang = math.acos(max(-1.0, min(1.0, (np.trace(dR) - 1) / 2)))
            axis = np.array([dR[2, 1] - dR[1, 2], dR[0, 2] - dR[2, 0], dR[1, 0] - dR[0, 1]])
            wv = axis / (np.linalg.norm(axis) + 1e-9) * ang / dt if ang > 1e-5 else np.zeros(3)
            self.hold_v = self.hold_v * 0.6 + v * 0.4
            self.hold_w = self.hold_w * 0.6 + wv * 0.4
            self.last_pos, self.last_R = c.pos.copy(), c.R.copy()
        if any(k.state == "free" for k in self.cubes):
            h = dt / 2                                       # 2 small steps per frame
            for _ in range(2):
                self._step(h)
        if self.active is None and self.release_t is not None:
            if not any(k.state == "free" for k in self.cubes) or self.t - self.release_t > 3.0:
                self.release_t = None
                self._present()

    def _step(self, h):
        p = self.p
        g = 9.8 * p.gravity
        free = [c for c in self.cubes if c.state == "free"]
        for c in free:
            c.vel[1] -= g * h
            c.pos += c.vel * h
            sp = math.sqrt(float(c.w @ c.w))
            if sp > 1e-9:
                c.R = axis_angle(c.w / sp, sp * h) @ c.R
            c.touching = False
        # broad phase once per step: which cubes are close enough to touch
        pos = [k.pos.tolist() for k in self.cubes]
        pairs = []
        for i, c in enumerate(self.cubes):
            if c.state != "free":
                continue
            cx, cy, cz = pos[i]
            for j, o in enumerate(self.cubes):
                if j == i or (o.state == "free" and j < i):
                    continue
                ox, oy, oz = pos[j]
                if (ox - cx) ** 2 + (oy - cy) ** 2 + (oz - cz) ** 2 < 3.1:
                    pairs.append((c, o))
        up = np.array([0.0, 1.0, 0.0])
        for _ in range(2):                                   # 2 rounds of contact fixing
            for c in free:
                P = c.corners()
                low = P[:, 1] < 0
                if low.any():
                    for i in np.nonzero(low)[0]:            # floor
                        self._contact(c, None, P[i], up, -P[i, 1])
                    c.touching = True
                elif P[:, 1].min() < 0.01:
                    c.touching = True
            for c, o in pairs:
                if self._cube_pair(c, o):
                    c.touching = True
        for c in free:
            if np.random.random() < 0.05:
                c.R = reorthonormalize(c.R)
            c.w *= 1.0 - (2.0 if c.touching else 0.05) * h
            c.vel *= 1.0 - 0.03 * h
            for k in (0, 2):                                 # invisible walls keep cubes in view
                if abs(c.pos[k]) > 6.5:
                    c.pos[k] = math.copysign(6.5, c.pos[k])
                    c.vel[k] *= -0.4
            if c.touching and float(c.vel @ c.vel) < 0.016 and float(c.w @ c.w) < 0.07:
                c.still += h
                if c.still > 0.25:
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

        view = self.mode == "view" or self.active is None
        bx, by, r = self._button()
        gl.blit_at(self._icon(gl, "view" if view else "cube"), bx - r, by - r,
                   alpha=0.75 if self.mode == "cube" and self.active is None else 1.0)
        if self.t - self.mode_t < 1.4:                       # name the new mode briefly
            key = "cubes_label_" + self.mode
            cache = self.__dict__.setdefault("_icons", {})
            if key not in cache:
                im = self.font.render("move cube" if self.mode == "cube" else "move view", True, (40, 40, 46))
                lab = pygame.Surface((im.get_width() + 16, 26), pygame.SRCALPHA)
                pygame.draw.rect(lab, (255, 255, 255, 180), lab.get_rect(), border_radius=8)
                lab.blit(im, im.get_rect(center=(lab.get_width() // 2, 13)))
                cache[key] = gl.surface_texture(lab, key)
            tex = cache[key]
            gl.blit_at(tex, bx - r - 8 - tex.w, by - 13, alpha=min(1.0, (1.4 - (self.t - self.mode_t)) * 3))

        if self.t < 9 and not self.prev:                     # a hint for the first few seconds
            if not hasattr(self, "_hint"):
                lines = ["drag: spin   2 fingers: move, twist, pinch",
                         "double-tap: drop   corner button: move the view"]
                imgs = [self.font.render(s, True, (40, 40, 46)) for s in lines]
                hint = pygame.Surface((max(i.get_width() for i in imgs) + 20, 52), pygame.SRCALPHA)
                pygame.draw.rect(hint, (255, 255, 255, 170), hint.get_rect(), border_radius=10)
                for k, im in enumerate(imgs):
                    hint.blit(im, im.get_rect(center=(hint.get_width() // 2, 15 + k * 22)))
                self._hint = gl.surface_texture(hint, "cubes_hint")
            gl.blit_at(self._hint, (self.w - self._hint.w) // 2, self.h - 70, alpha=min(1.0, 9 - self.t))

    # ------------------------------------------------------------- preview
    def preview(self, step):
        """Drop a few cubes into a pile, then present a new one."""
        rng = np.random.default_rng(3)
        self.cubes.clear()
        self.active = self.held = None
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
        self.release_t = None
        self._present()

    PREVIEW_AFTER = 150
