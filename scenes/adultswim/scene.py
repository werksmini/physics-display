"""Adult swim: the sunlit pool, a little closer in, with swimmers.

You're the swimmer in the yellow cap, treading water. Tap anywhere in the
water and you swim there (slow, head-up breaststroke), then tread again.
Other swimmers drift in from the edges of the screen (left, right, below):
someone swims up to the wall and back, someone floats on their back, someone
hangs on a pool noodle, someone just passes through. Then they drift off.

Same water as "Sunlit pool": tiles, lane line, caustic nets, sun glints. In
the top corner is the curved edge of the pool, with stone coping and deck.

How it's built (three layers):

1. Water surface: the sunlit pool's gentle wind waves, plus a small wave
   simulation (a grid of heights, one cell per 5 screen pixels, the wave
   equation). Swimmers poke it as they move: hands on each stroke, a bow wave
   at the head, little sculling ripples while treading. Ripples spread, bounce
   off the pool wall and fade away at the screen edges (the pool carries on
   out of view). Slopes go to the GPU as a texture.
2. Bodies under the water: drawn each frame with simple capsules into a
   half-resolution image, also a texture.
3. The shader, per pixel: the sunlit pool's floor, refraction, caustics and
   glints, plus the bodies (bent by the surface, dappled by caustics), their
   sun shadows on the floor, and the coping and deck around the curved edge.

Heads are above the water, so they're drawn crisp on top, unbent.
"""
import math
import random

import numpy as np
import pygame

from playground.scene import BaseScene, Param

CELL = 5                                    # wave cell size in pixels
BODY_SCALE = 0.5                            # body texture resolution vs screen
COPING = 0.30                               # stone edge width, metres

SKIN = [(236, 196, 166), (208, 160, 120), (170, 118, 82), (122, 82, 56), (226, 178, 150), (96, 64, 44)]
SUITS = [(28, 40, 86), (20, 20, 24), (120, 30, 46), (24, 104, 110), (70, 46, 96), (160, 60, 40)]
CAPS = [(240, 240, 236), (232, 150, 176), (150, 196, 228), (210, 120, 200), (120, 190, 150)]
HAIR = [(200, 200, 204), (236, 236, 232), (90, 60, 40), (30, 26, 24), (150, 120, 90)]
YOU_CAP = (246, 206, 60)
NOODLES = [(240, 90, 150), (110, 220, 120), (250, 200, 60), (90, 170, 240)]

FRAG = """
uniform sampler2D u_wave;   // r, g: slope x, y from the wave simulation
uniform sampler2D u_body;   // swimmers under the water (rgba)
uniform float u_time;
uniform vec4 u_a;           // ambient wave, ripple strength, caustics, refraction
uniform vec4 u_b;           // tile size, depth tint, glints, px per metre
uniform vec4 u_edge;        // the deck: a disc in the corner (centre x, y, radius in metres), coping width
uniform vec4 u_misc;        // screen w, h (px), lane x, lane end y (metres)
varying vec2 uv;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }

float wave(vec2 p, vec2 d, float k, float w, float a, float ph, inout vec2 g) {
    float x = dot(d, p) * k + u_time * w + ph;
    g += d * (a * k * cos(x));
    return a * sin(x);
}

float caustic(vec2 q) {
    vec2 a = q * 3.6;
    float c = 0.0;
    for (int i = 0; i < 3; i++) {
        float fi = float(i);
        a += vec2(sin(a.y * 1.3 + u_time * 0.7 + fi * 1.7),
                  cos(a.x * 1.1 - u_time * 0.5 + fi * 2.3)) * 0.75;
        c += 1.0 / (1.0 + 34.0 * abs(sin(a.x) * sin(a.y)));
    }
    return c / 3.0;
}

void main() {
    vec2 px = uv * u_misc.xy;
    vec2 p = px / u_b.w;                                   // metres
    float d = length(p - u_edge.xy) - u_edge.z;            // >0 in the water, metres from the wall
    vec3 L = normalize(vec3(0.35, -0.45, 0.82));           // toward the sun (up and to the right)

    if (d < 0.0) {
        // ---- coping and deck, in the sun
        vec2 rel = p - u_edge.xy;
        float along = atan(rel.y, rel.x) * u_edge.z;
        float c = -d / u_edge.w;                            // 0 at the water, 1 at the deck side
        vec3 col;
        if (c < 1.0) {
            float round = sqrt(max(0.0, 1.0 - pow(1.0 - c * 1.6, 2.0)));       // bullnose profile
            col = vec3(0.86, 0.83, 0.77) * (0.80 + 0.22 * round) * (0.95 + 0.06 * hash(floor(p * 60.0)));
            float joint = abs(fract(along / 0.6) - 0.5) * 0.6;
            col *= 1.0 - 0.18 * (1.0 - smoothstep(0.0, 0.012, joint));
            col *= 1.0 - 0.25 * smoothstep(0.85, 1.0, c);                        // the joint to the deck
        } else {
            vec2 g2 = floor(px / 2.0);
            col = vec3(0.80, 0.76, 0.69) * (0.92 + 0.10 * hash(g2) + 0.05 * hash(floor(p * 3.0)));
            col *= 0.96 + 0.04 * sin(p.x * 1.3 + p.y * 0.7);
        }
        col *= 1.0 - 0.12 * smoothstep(0.02, 0.0, d + 0.0);                       // edge of the stone
        col += (hash(gl_FragCoord.xy + fract(u_time) * 61.0) - 0.5) / 64.0;
        gl_FragColor = vec4(col, 1.0);
        return;
    }

    // ---- height slope: ambient wind waves plus the simulated ripples
    vec2 g = vec2(0.0);
    float amb = u_a.x * 0.004;
    wave(p, normalize(vec2(1.0, 0.35)), 9.0, 1.7, amb, 0.0, g);
    wave(p, normalize(vec2(-0.4, 1.0)), 13.0, 2.1, amb * 0.7, 1.3, g);
    wave(p, normalize(vec2(0.8, -0.6)), 21.0, 2.9, amb * 0.4, 2.1, g);
    wave(p, normalize(vec2(-1.0, -0.2)), 31.0, 3.7, amb * 0.25, 0.4, g);
    vec4 wv = texture2D(u_wave, uv);
    g += (wv.rg - 0.5) * 0.30 * u_a.y;
    vec3 n = normalize(vec3(-g * 1.6, 1.0));

    // ---- refracted tile floor (exactly the sunlit pool's)
    vec2 q = p + n.xy * 0.22 * u_a.w;
    float ts = u_b.x;
    vec2 cell = floor(q / ts);
    vec2 f = fract(q / ts);
    float grout = smoothstep(0.0, 0.045, f.x) * smoothstep(1.0, 0.955, f.x)
                * smoothstep(0.0, 0.045, f.y) * smoothstep(1.0, 0.955, f.y);
    vec3 tile = vec3(0.80, 0.93, 0.95) * (0.94 + 0.08 * hash(cell));
    vec3 floorc = mix(vec3(0.60, 0.74, 0.78), tile, grout);
    float lane = smoothstep(0.13, 0.11, abs(q.x - u_misc.z)) * step(u_misc.w, q.y);
    float tee = smoothstep(0.13, 0.11, abs(q.y - u_misc.w)) * smoothstep(0.42, 0.40, abs(q.x - u_misc.z));
    floorc = mix(floorc, vec3(0.08, 0.16, 0.36), max(lane, tee));
    floorc *= 0.80 + 0.20 * smoothstep(0.0, 0.35, d);       // the wall shades the floor beside it

    // ---- swimmers' sun shadows on the floor (sun up-right, so shadows fall down-left)
    vec2 suv = uv + n.xy * 0.01 + vec2(0.38, -0.49) / (u_misc.xy / u_b.w);
    vec2 bt = 2.0 / u_misc.xy;                               // one body-texture texel
    float sh = 0.5 * (texture2D(u_body, suv + bt * vec2(1.2, 0.4)).a + texture2D(u_body, suv - bt * vec2(0.4, 1.2)).a);

    // ---- caustic light on the floor
    float c = caustic(q + n.xy * 0.15) * u_a.z;
    vec3 col = floorc * (0.62 + 1.15 * c * (1.0 - 0.7 * sh)) * (1.0 - 0.38 * sh);

    // ---- water: depth tint
    vec3 water = vec3(0.30, 0.72, 0.82);
    col = mix(col, col * water * 1.25, u_b.y);

    // ---- swimmers, nearer the surface: bent less, dappled by the light, lightly tinted
    vec2 buv = uv + n.xy * 0.012 * u_a.w;                    // 4 taps: soft edges, like seen through water
    vec4 b = 0.25 * (texture2D(u_body, buv + bt * vec2(0.6, 0.2)) + texture2D(u_body, buv - bt * vec2(0.6, 0.2))
                   + texture2D(u_body, buv + bt * vec2(-0.2, 0.6)) + texture2D(u_body, buv - bt * vec2(-0.2, 0.6)));
    if (b.a > 0.01) {
        b.rgb *= 0.92 / b.a;                                   // undo the fade to black at the edges
        vec3 bc = b.rgb * (0.78 + 0.55 * caustic(p * 1.3 + n.xy * 0.1) * u_a.z);
        bc = mix(bc, bc * water * 1.3, 0.55 * u_b.y);
        col = mix(col, bc, b.a);
    }

    // ---- surface: sky reflection, sun glints
    vec3 H = normalize(L + vec3(0.0, 0.0, 1.0));
    float spec = pow(max(dot(n, H), 0.0), 900.0) * 2.5 * u_b.z;
    float fres = 0.04 + 0.5 * pow(1.0 - n.z, 3.0);
    col = mix(col, vec3(0.80, 0.90, 1.0), fres) + vec3(1.0, 0.97, 0.9) * spec;
    col *= 1.0 - 0.22 * smoothstep(0.10, 0.0, d);           // the coping's lip shades the water under it

    col += (hash(gl_FragCoord.xy + fract(u_time) * 61.0) - 0.5) / 64.0;   // dither
    gl_FragColor = vec4(col, 1.0);
}
"""


def lerp(a, b, f):
    return a + (b - a) * f


def angle_to(a, b):
    return (b - a + math.pi) % (2 * math.pi) - math.pi


class Swimmer:
    def __init__(self, x, y, heading, you=False, rng=random):
        self.x, self.y, self.a = x, y, heading
        self.you = you
        self.mode = "tread"             # tread, breast, float, noodle
        self.phase = rng.random()
        self.speed = 0.0
        self.target = None
        self.alpha = 1.0
        self.plan = []                  # queue of things to do (others)
        self.task = None
        self.timer = 0.0
        self.leaving = False
        self.gone = False
        self.noodler = False
        self.skin = SKIN[0] if you else rng.choice(SKIN)
        self.suit = SUITS[0] if you else rng.choice(SUITS)
        if you:
            self.head = ("cap", YOU_CAP)
        elif rng.random() < 0.55:
            self.head = ("cap", rng.choice(CAPS))
        else:
            self.head = ("hair", rng.choice(HAIR))
        self.noodle = rng.choice(NOODLES)
        self.pace = rng.uniform(0.85, 1.1)
        self.last_splash = 0.0
        self.id = id(self)

    @property
    def f(self):
        return math.cos(self.a), math.sin(self.a)


class Scene(BaseScene):
    TITLE = "Adult swim (GPU)"
    GPU = True
    PARAMS = [
        Param("others", 3, 0, 6, 1, "Other swimmers", help="Most at once."),
        Param("busy", 1.0, 0.2, 3, 0.05, "Comings and goings", help="Higher = people arrive more often."),
        Param("pace", 1.0, 0.4, 2.5, 0.05, "Swim pace"),
        Param("ripple", 1.0, 0, 3, 0.05, "Ripple strength"),
        Param("ripple_speed", 1.0, 0.4, 2, 0.05, "Ripple speed"),
        Param("ripple_fade", 1.0, 0.2, 3, 0.05, "Ripple fade"),
        Param("ambient", 1.0, 0, 4, 0.05, "Wind on the water"),
        Param("caustics", 1.0, 0, 3, 0.05, "Caustics"),
        Param("refraction", 1.0, 0, 3, 0.05, "Refraction"),
        Param("glints", 1.0, 0, 3, 0.05, "Sun glints"),
        Param("depth", 0.55, 0, 1, 0.01, "Water depth tint"),
        Param("tile_size", 0.16, 0.05, 0.5, 0.01, "Tile size", help="Metres."),
        Param("render_scale", 1.0, 0.25, 1.0, 0.05, "Render scale", reset=True,
              help="Draw the water smaller and scale it up: faster on the Pi, a little softer."),
        Param("view", 6.7, 4, 12, 0.1, "View height", reset=True,
              help="Metres of pool from top to bottom of the screen. Smaller = closer."),
    ]

    # ------------------------------------------------------------------ setup
    def setup(self):
        gl = self.gl
        self.prog = gl.program(FRAG)
        sc = self.p.render_scale
        self.target = gl.target(max(16, int(self.w * sc)), max(16, int(self.h * sc))) if sc < 0.99 else None
        self.rng = random.Random()
        self.pxm = self.h / self.p.view                  # pixels per metre
        self.SW, self.SH = self.w / self.pxm, self.h / self.pxm
        # the deck: a rounded corner in the top left; the pool curves around it and carries on
        # off the left, right and bottom of the screen
        self.edge_c = np.array([-0.5, -0.5])
        R = self.edge_r = 2.6
        self.lane_x = 1.15                              # where the sunlit pool's lane line is
        self.lane_end = self._wall_y(self.lane_x) + 0.45

        self.gw, self.gh = self.w // CELL, self.h // CELL
        self.hgt = np.zeros((self.gh, self.gw), np.float32)
        self.vel = np.zeros_like(self.hgt)
        self.pad = np.zeros((self.gh + 2, self.gw + 2), np.float32)
        cy, cx = (np.mgrid[0:self.gh, 0:self.gw] + 0.5) * CELL / self.pxm
        inside = (np.hypot(cx - self.edge_c[0], cy - self.edge_c[1]) > R).astype(np.float32)
        ey, ex = np.mgrid[0:self.gh, 0:self.gw]
        border = np.minimum(np.minimum(ex, self.gw - 1 - ex), np.minimum(ey, self.gh - 1 - ey))
        sponge = 1.0 - 0.10 * np.clip(1.0 - border / 10.0, 0, 1) ** 2      # ripples fade off-screen
        self.mask = inside
        self.sponge = (sponge * inside).astype(np.float32)
        self.wbuf = np.full((self.gh, self.gw, 4), 128, np.uint8)
        self.wbuf[..., 3] = 255
        self.wave_tex = gl.texture(self.gw, self.gh, self.wbuf.tobytes())
        bw, bh = int(self.w * BODY_SCALE), int(self.h * BODY_SCALE)
        self.body = pygame.Surface((bw, bh), pygame.SRCALPHA)
        self.body_tex = gl.texture(bw, bh)
        self.bpm = self.pxm * BODY_SCALE                 # body-texture pixels per metre
        k = np.exp(-np.linspace(-1.6, 1.6, 5) ** 2)
        self.kernel = (k[:, None] * k[None, :]).astype(np.float32)
        self.font = pygame.font.Font(None, 24)
        self.t = 0.0
        self.you = Swimmer(self.SW * 0.55, self.SH * 0.58, -math.pi / 2, you=True, rng=self.rng)
        self.swimmers = [self.you]
        self.next_arrival = 5.0
        first = Swimmer(self.SW * 0.24, self.SH * 0.80, 0.4, rng=self.rng)
        first.plan = [("float", self.rng.uniform(30, 50)), ("leave", None)]
        self.swimmers.append(first)
        self.taps = {}

    def _wall_y(self, x):
        """y of the pool wall above x (metres); off the top of the screen past the deck."""
        dx = x - self.edge_c[0]
        if abs(dx) >= self.edge_r:
            return -3.0
        return self.edge_c[1] + math.sqrt(self.edge_r ** 2 - dx * dx)

    def _in_pool(self, x, y, margin):
        return math.hypot(x - self.edge_c[0], y - self.edge_c[1]) > self.edge_r + margin

    def _offscreen(self, s, m=1.0):
        return s.x < -m or s.x > self.SW + m or s.y > self.SH + m

    def _side_point(self, side=None):
        """A point just off the left, right or bottom of the screen."""
        r = self.rng
        side = side or r.choice(["left", "right", "bottom", "bottom"])
        if side == "left":
            return side, (-1.4, r.uniform(self.edge_c[1] + self.edge_r + 0.9, self.SH - 0.6))
        if side == "right":
            return side, (self.SW + 1.4, r.uniform(0.7, self.SH - 0.6))
        return side, (r.uniform(0.6, self.SW - 0.6), self.SH + 1.4)

    def _spot(self, margin=0.9):
        """A random spot in the visible water."""
        for _ in range(30):
            x = self.rng.uniform(margin, self.SW - margin)
            y = self.rng.uniform(margin, self.SH - margin)
            if self._in_pool(x, y, 0.8):
                return x, y
        return self.SW * 0.6, self.SH * 0.6

    # ------------------------------------------------------------- swimmers
    def _arrive(self):
        r = self.rng
        kind = r.choice(["laps", "laps", "cross", "float", "float", "noodle", "chat", "wall"])
        if kind == "laps":
            x = self.lane_x + r.choice([-0.5, 0.5])
            start = (x, self.SH + 1.4)
            plan = [("swim", (x, self._wall_y(x) + 0.55)), ("rest", r.uniform(2, 7)),
                    ("swim", (x + r.uniform(-0.2, 0.2), self.SH + 1.4))]
        else:
            side, start = self._side_point()
            if kind == "cross":
                other = {"left": "right", "right": "left"}.get(side, r.choice(["left", "right"]))
                plan = [("swim", self._spot(1.2)), ("swim", self._side_point(other)[1])]
            elif kind == "float":
                plan = [("swim", self._spot()), ("float", r.uniform(30, 70)), ("leave", None)]
            elif kind == "noodle":
                plan = [("swim", self._spot()), ("drift", r.uniform(35, 80)), ("leave", None)]
            elif kind == "wall":
                x = r.uniform(0.5, self.edge_c[0] + self.edge_r - 0.3)
                plan = [("swim", (x, self._wall_y(x) + 0.45)), ("rest", r.uniform(25, 55)), ("leave", None)]
            else:
                plan = [("chat", r.uniform(25, 50)), ("leave", None)]
        s = Swimmer(*start, 0.0, rng=r)
        s.a = math.atan2(self.SH * 0.5 - start[1], self.SW * 0.5 - start[0])
        s.noodler = kind == "noodle"
        s.plan = plan
        self._next_task(s)
        self.swimmers.append(s)
        return s

    def _next_task(self, s):
        if not s.plan:
            s.plan = [("leave", None)]
        kind, arg = s.plan.pop(0)
        s.task = kind
        s.timer = arg if isinstance(arg, (int, float)) else 0.0
        s.target = None
        if kind == "swim":
            s.target = arg
            s.mode = "noodle" if s.noodler else "breast"
        elif kind == "rest":
            s.mode = "noodle" if s.noodler else "tread"
        elif kind == "float":
            s.mode = "float"
        elif kind == "drift":
            s.mode = "noodle"
        elif kind == "chat":
            friend = min((o for o in self.swimmers if o is not s and not o.leaving),
                         key=lambda o: (o.x - s.x) ** 2 + (o.y - s.y) ** 2, default=None)
            fx, fy = (friend.x, friend.y) if friend else self._spot()
            tx = min(self.SW - 0.6, max(0.6, fx + self.rng.uniform(-1.1, 1.1)))
            ty = min(self.SH - 0.6, max(0.6, fy + self.rng.uniform(-1.1, 1.1)))
            s.target = (tx, ty)
            s.mode = "breast"
            s.plan.insert(0, ("rest", s.timer))
            s.task = "swim"
        elif kind == "leave":
            s.leaving = True
            s.target = self._side_point()[1]
            s.mode = "noodle" if s.noodler else "breast"

    # ------------------------------------------------------------- input
    def fingers(self, fingers):
        for k in list(self.taps):
            if k not in fingers:
                t0, x, y, moved = self.taps.pop(k)
                if self.t - t0 < 0.5 and moved < 25:
                    self._go(x, y)
        for k, (x, y) in fingers.items():
            if k in self.taps:
                t0, x0, y0, moved = self.taps[k]
                self.taps[k] = (t0, x0, y0, max(moved, math.hypot(x - x0, y - y0)))
            else:
                self.taps[k] = (self.t, x, y, 0.0)

    def _go(self, x, y):
        mx = min(self.SW - 0.4, max(0.4, x / self.pxm))
        my = min(self.SH - 0.4, max(0.4, y / self.pxm))
        if not self._in_pool(mx, my, 0.45):                  # tapped the deck: the nearest water instead
            dx, dy = mx - self.edge_c[0], my - self.edge_c[1]
            k = (self.edge_r + 0.5) / max(math.hypot(dx, dy), 1e-6)
            mx, my = self.edge_c[0] + dx * k, self.edge_c[1] + dy * k
        self.you.target = (mx, my)
        self.you.mode = "breast"
        self._poke(mx, my, 0.35)                              # a little plip where you tapped

    # ------------------------------------------------------------- update
    def update(self, dt):
        self.t += dt
        p = self.p
        others = [s for s in self.swimmers if not s.you]
        self.next_arrival -= dt * p.busy
        if self.next_arrival <= 0:
            if len(others) < int(p.others):
                self._arrive()
            self.next_arrival = self.rng.uniform(12, 35)
        for s in self.swimmers:
            self._move(s, dt)
        self._separate()
        self.swimmers = [s for s in self.swimmers if not s.gone]
        self._waves(dt)

    def _move(self, s, dt):
        p = self.p
        if not s.you and s.target is None:
            s.timer -= dt
            if s.timer <= 0:
                self._next_task(s)
        pace = p.pace * s.pace
        if s.target is not None and s.mode in ("breast", "noodle"):
            tx, ty = s.target
            dx, dy = tx - s.x, ty - s.y
            dist = math.hypot(dx, dy)
            turn = angle_to(s.a, math.atan2(dy, dx))
            s.a += max(-1.0, min(1.0, turn)) * dt * 1.4
            fx, fy = s.f
            if s.mode == "breast":
                s.phase = (s.phase + dt * pace / 2.3) % 1
                ph = s.phase
                surge = 0.35 + 1.25 * math.exp(-(((ph - 0.6) % 1.0) * 3.2))   # glide after the kick
                v = 0.5 * pace * surge
                if 0.05 < ph < 0.3 and self.t - s.last_splash > 0.12:      # hands sweeping out
                    sx, sy = -fy, fx
                    for side in (-1, 1):
                        self._poke(s.x + fx * 0.35 + sx * side * 0.4, s.y + fy * 0.35 + sy * side * 0.4, 0.5)
                    s.last_splash = self.t
            else:                                                           # kicking along on a noodle
                s.phase = (s.phase + dt * 0.35) % 1
                v = 0.16 * pace
                if self.t - s.last_splash > 0.8:
                    self._poke(s.x - fx * 0.5, s.y - fy * 0.5, 0.2)
                    s.last_splash = self.t
            v *= max(0.25, math.cos(turn)) * min(1.0, dist / 0.8 + 0.25)
            s.speed = v
            s.x += fx * v * dt
            s.y += fy * v * dt
            self._poke(s.x + fx * 0.25, s.y + fy * 0.25, 0.10 * v)         # soft bow wave
            arrived = dist < 0.3 or (s.leaving and self._offscreen(s))
            if not s.you and self._offscreen(s, 1.2) and (s.leaving or s.task == "swim" and
                                                              not self._on_screen_pt(s.target)):
                s.gone = True
            elif arrived:
                s.target = None
                s.speed = 0.0
                if s.you:
                    s.mode = "tread"
                elif s.leaving:
                    s.gone = True
                else:
                    self._next_task(s)
        else:
            s.speed = 0.0
            rate = {"tread": 0.55, "noodle": 0.35, "float": 0.18}.get(s.mode, 0.5)
            s.phase = (s.phase + dt * rate) % 1
            if s.mode == "float":                           # drift slowly, turn lazily
                s.a += math.sin(self.t * 0.05 + s.id % 7) * dt * 0.05
                fx, fy = s.f
                s.x += fx * 0.03 * dt
                s.y += fy * 0.03 * dt
                if self.t - s.last_splash > 2.8:
                    self._poke(s.x - fx * 0.9, s.y - fy * 0.9, 0.25)
                    s.last_splash = self.t
            elif s.mode == "noodle":
                s.x += math.sin(self.t * 0.07 + s.id % 5) * 0.03 * dt
                s.y += math.cos(self.t * 0.05 + s.id % 3) * 0.03 * dt
                if self.t - s.last_splash > 1.6:
                    self._poke(s.x, s.y, 0.15)
                    s.last_splash = self.t
            else:                                           # treading: little sculling ripples
                if self.t - s.last_splash > 0.9:
                    fx, fy = s.f
                    side = 1 if (self.t * 1.1) % 2 < 1 else -1
                    self._poke(s.x - fy * side * 0.45, s.y + fx * side * 0.45, 0.22)
                    self._poke(s.x, s.y, 0.12)
                    s.last_splash = self.t
        self._keep_in(s)

    def _on_screen_pt(self, pt):
        return pt is not None and 0 <= pt[0] <= self.SW and pt[1] <= self.SH

    def _keep_in(self, s):
        dx, dy = s.x - self.edge_c[0], s.y - self.edge_c[1]
        d = max(math.hypot(dx, dy), 1e-6)
        lim = self.edge_r + 0.32
        if d < lim:                                         # stay off the wall
            s.x, s.y = self.edge_c[0] + dx / d * lim, self.edge_c[1] + dy / d * lim
        s.y = max(0.3, s.y)
        if s.you:
            s.x = min(self.SW - 0.3, max(0.3, s.x))
            s.y = min(self.SH - 0.3, s.y)

    def _separate(self):
        sw = self.swimmers
        for i, a in enumerate(sw):
            for b in sw[i + 1:]:
                dx, dy = b.x - a.x, b.y - a.y
                d = math.hypot(dx, dy)
                need = 1.0 if "float" in (a.mode, b.mode) else 0.8
                if 1e-6 < d < need:
                    push = (need - d) * 0.05
                    a.x -= dx / d * push
                    a.y -= dy / d * push
                    b.x += dx / d * push
                    b.y += dy / d * push

    # ------------------------------------------------------------- waves
    def _poke(self, x, y, amount):
        cx = int(x * self.pxm / CELL)
        cy = int(y * self.pxm / CELL)
        if not (2 <= cx < self.gw - 2 and 2 <= cy < self.gh - 2):
            return
        self.vel[cy - 2:cy + 3, cx - 2:cx + 3] -= self.kernel * amount * 0.6 * self.p.ripple

    def _waves(self, dt):
        p = self.p
        h, v, pad = self.hgt, self.vel, self.pad
        c = 0.045 * p.ripple_speed ** 2
        damp = math.exp(-dt * 0.55 * p.ripple_fade)
        pad[1:-1, 1:-1] = h
        pad[0, 1:-1] = h[0]
        pad[-1, 1:-1] = h[-1]
        pad[1:-1, 0] = h[:, 0]
        pad[1:-1, -1] = h[:, -1]
        lap = pad[:-2, 1:-1] + pad[2:, 1:-1] + pad[1:-1, :-2] + pad[1:-1, 2:] - 4 * h
        v += lap * c
        v *= self.sponge                                     # the wall (masked) reflects; screen edges absorb
        v *= damp
        h += v
        h *= self.mask
        h -= h.mean() * self.mask                            # keep the water level

    # ------------------------------------------------------------- drawing
    def _draw_bodies(self):
        surf = self.body
        surf.fill((0, 0, 0, 0))
        B = self.bpm
        for s in sorted(self.swimmers, key=lambda s: s.you):
            if s.alpha <= 0:
                continue
            a = int(235 * s.alpha)
            fx, fy = s.f
            sx, sy = -fy, fx

            def P(fw, sd, _s=s):
                return ((_s.x + fx * fw + sx * sd) * B, (_s.y + fy * fw + sy * sd) * B)

            def limb(p0, p1, r, col):
                cap(surf, col + (a,), p0, p1, r * B)

            skin, suit = s.skin, s.suit
            deep = tuple(int(c * 0.7) for c in skin)
            ph = s.phase * 2 * math.pi
            if s.mode == "breast":
                f = s.phase
                if f < 0.35:                                   # pull: hands sweep out and in
                    k = f / 0.35
                    ang, reach = lerp(0.15, 1.35, k), lerp(0.62, 0.38, k)
                elif f < 0.55:                                 # recover: hands meet under the chin, shoot forward
                    k = (f - 0.35) / 0.2
                    ang, reach = lerp(1.35, 0.1, k), lerp(0.38, 0.62, k)
                else:
                    ang, reach = 0.12, 0.64
                kick = max(0.0, math.sin(min(1.0, max(0.0, (f - 0.38) / 0.24)) * math.pi))
                for side in (-1, 1):                           # legs: frog kick
                    hip = P(-0.42, side * 0.09)
                    knee = P(-0.70 + 0.18 * kick, side * (0.12 + 0.30 * kick))
                    foot = P(-1.02 + 0.30 * kick, side * (0.10 + 0.20 * kick))
                    limb(hip, knee, 0.075, deep)
                    limb(knee, foot, 0.06, deep)
                limb(P(0.12, 0), P(-0.42, 0), 0.17, suit)       # torso
                for side in (-1, 1):
                    sh = P(0.12, side * 0.17)
                    hand = P(0.12 + reach * math.cos(ang), side * (0.17 + reach * math.sin(ang)))
                    elbow = ((sh[0] + hand[0]) / 2 + sx * side * 0.06 * B, (sh[1] + hand[1]) / 2 + sy * side * 0.06 * B)
                    limb(sh, elbow, 0.065, skin)
                    limb(elbow, hand, 0.055, skin)
                limb(P(0.2, 0), P(0.3, 0), 0.09, skin)           # neck, just under the head
            elif s.mode == "float":                            # on the back, arms and legs out like a star
                for side in (-1, 1):
                    limb(P(-0.42, side * 0.09), P(-1.05, side * (0.32 + 0.03 * math.sin(ph))), 0.07, deep)
                limb(P(0.12, 0), P(-0.42, 0), 0.17, suit)
                for side in (-1, 1):
                    sc = 0.05 * math.sin(ph * 2 + side)
                    limb(P(0.12, side * 0.17), P(0.05 + sc, side * 0.78), 0.06, skin)
                limb(P(0.2, 0), P(0.3, 0), 0.09, skin)
            else:                                              # upright: tread water / noodle
                slow = 0.6 if s.mode == "noodle" else 1.0
                for side in (-1, 1):                           # legs below, eggbeater circles
                    kx = 0.10 * math.cos(ph * 2 + side * 1.4) * slow
                    ky = 0.10 * math.sin(ph * 2 + side * 1.4) * slow
                    limb(P(-0.05, side * 0.1), P(-0.05 + kx, side * (0.32 + ky)), 0.08, deep)
                limb(P(0.0, -0.21), P(0.0, 0.21), 0.14, suit)   # shoulders and chest
                for side in (-1, 1):
                    if s.mode == "noodle":
                        hand = P(0.32, side * 0.5)
                    else:
                        sc = math.sin(ph * 2 + (0 if side > 0 else math.pi))
                        hand = P(0.18 + 0.16 * sc, side * (0.5 + 0.08 * sc))
                    limb(P(0.0, side * 0.2), hand, 0.06, skin)
                if s.mode == "noodle":
                    limb(P(0.28, -0.85), P(0.28, 0.85), 0.07, s.noodle)
        for s in self.swimmers:                            # heads too, so they cast shadows
            hx, hy = self._head_pos(s)
            pygame.draw.circle(surf, s.skin + (235,), (hx * B, hy * B), 0.11 * B)
        return surf

    def _head_tex(self, gl, s):
        """A crisp head (cap or hair, the face toward the heading), cached per 16 directions."""
        kind, col = s.head
        on_back = s.mode == "float"
        d = int(round((s.a % (2 * math.pi)) / (2 * math.pi) * 16)) % 16
        key = f"head_{kind}_{col}_{s.skin}_{on_back}_{d}_{int(self.pxm)}"
        cache = self.__dict__.setdefault("_heads", {})
        if key in cache:
            return cache[key]
        r1 = 0.115 * self.pxm
        R = int(r1 * 3.4) + 4                                # canvas size in px
        S = 4                                                # draw 4x then shrink
        D = R * S
        big = pygame.Surface((D, D), pygame.SRCALPHA)
        c = D // 2
        r = r1 * S
        ang = d / 16 * 2 * math.pi
        fx, fy = math.cos(ang), math.sin(ang)
        pygame.draw.circle(big, (255, 255, 255, 34), (c, c), int(r * 1.6))               # water ring
        pygame.draw.circle(big, (255, 255, 255, 60), (c, c), int(r * 1.25), max(1, S))
        if on_back:
            pygame.draw.circle(big, s.skin, (c, c), int(r))                                # face up
            hc = col if kind == "cap" else col
            pygame.draw.circle(big, hc, (int(c - fx * r * 0.55), int(c - fy * r * 0.55)), int(r * 0.75))
            pygame.draw.circle(big, s.skin, (int(c + fx * r * 0.25), int(c + fy * r * 0.25)), int(r * 0.72))
        else:
            pygame.draw.circle(big, s.skin, (int(c + fx * r * 0.18), int(c + fy * r * 0.18)), int(r * 0.95))
            pygame.draw.circle(big, col, (int(c - fx * r * 0.12), int(c - fy * r * 0.12)), int(r * 0.97))
        pygame.draw.circle(big, (255, 255, 255, 140), (int(c + r * 0.3), int(c - r * 0.38)), int(r * 0.26))   # sun shine
        small = pygame.transform.smoothscale(big, (R, R))
        cache[key] = gl.surface_texture(small, key)
        return cache[key]

    def _head_pos(self, s):
        fx, fy = s.f
        off = {"breast": 0.36, "float": 0.40}.get(s.mode, 0.0)
        bob = 0.02 * math.sin(s.phase * 4 * math.pi) if s.mode in ("tread", "noodle") else 0.0
        return s.x + fx * off, s.y + fy * off + bob

    def draw_gl(self, gl):
        p = self.p
        h = self.hgt
        gy, gx = np.gradient(h)
        wb = self.wbuf
        wb[..., 0] = np.clip(128 + gx * 600, 0, 255)
        wb[..., 1] = np.clip(128 + gy * 600, 0, 255)
        self.wave_tex.update(wb.tobytes())
        self.body_tex.update(pygame.image.tobytes(self._draw_bodies(), "RGBA"))

        if self.target:
            self.target.bind()
        else:
            gl.screen()
        pr = self.prog
        pr.use()
        self.wave_tex.bind(0)
        self.body_tex.bind(1)
        pr.set_int("u_wave", 0)
        pr.set_int("u_body", 1)
        pr.set("u_time", self.t % 1000.0)
        pr.set("u_a", p.ambient, p.ripple, p.caustics, p.refraction)
        pr.set("u_b", p.tile_size, p.depth, p.glints, self.pxm)
        pr.set("u_edge", self.edge_c[0], self.edge_c[1], self.edge_r, COPING)
        pr.set("u_misc", self.w, self.h, self.lane_x, self.lane_end)
        gl.draw_quad()
        if self.target:
            gl.screen()
            gl.blit(self.target.tex)

        for s in self.swimmers:
            tex = self._head_tex(gl, s)
            hx, hy = self._head_pos(s)
            gl.blit_at(tex, hx * self.pxm - tex.w / 2, hy * self.pxm - tex.h / 2)

        if self.t < 8 and not self.taps:
            if not hasattr(self, "_hint"):
                im = self.font.render("tap the water to swim there", True, (40, 40, 52))
                hint = pygame.Surface((im.get_width() + 20, 28), pygame.SRCALPHA)
                pygame.draw.rect(hint, (255, 255, 255, 170), hint.get_rect(), border_radius=10)
                hint.blit(im, im.get_rect(center=(hint.get_width() // 2, 14)))
                self._hint = gl.surface_texture(hint, "adultswim_hint")
            gl.blit_at(self._hint, (self.w - self._hint.w) // 2, self.h - 60, alpha=min(1.0, 8 - self.t))

    # ------------------------------------------------------------- preview
    def preview(self, step):
        self.rng.seed(5)
        for _ in range(60):
            self.update(step)
        self._go(330, 300)
        self.next_arrival = 0
        for _ in range(240):
            self.update(step)
        self.next_arrival = 0
        for _ in range(200):
            self.update(step)
        self.t = max(self.t, 20)

    PREVIEW_AFTER = 0


def cap(surf, col, p0, p1, r):
    """A capsule (rounded line) from p0 to p1 with radius r."""
    r = max(1.0, r)
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    d = math.hypot(dx, dy)
    if d > 0.5:
        nx, ny = -dy / d * r, dx / d * r
        pygame.draw.polygon(surf, col, [(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)])
    pygame.draw.circle(surf, col, (x0, y0), r)
    pygame.draw.circle(surf, col, (x1, y1), r)
