"""Adult swim: a quiet community pool at dusk, seen from above.

You're the swimmer in the yellow cap, treading water. Tap anywhere in the
pool and you swim there (slow, head-up breaststroke), then tread water again.
Other swimmers wander in down the ladders: someone swims a few lazy lengths,
someone floats on their back, someone hangs on a pool noodle. After a while
they climb out and leave.

How it's built (three layers):

1. Water surface: a small wave simulation (a grid of heights, one cell per
   5 screen pixels, the classic "wave equation" update). Swimmers poke it as
   they move: hands on each stroke, a soft bow wave at the head, little
   sculling ripples while treading. Ripples spread, bounce off the walls and
   cross each other. The heights and their slopes go to the GPU as a texture.
2. Bodies under the water: drawn each frame with simple shapes (capsules for
   torso, arms and legs) into a half-resolution image, also a texture.
3. The shader, per pixel: bends the view of the tiles and the bodies by the
   surface slope (refraction), adds the bodies' soft shadows on the floor, the
   glow of the underwater lights, the water's colour, the dusk sky reflected
   at the surface and glints of the deck lamp on the ripples.

Heads are above the water, so they're drawn crisp on top, unbent. The deck,
coping and ladders are painted once into an overlay with the pool cut out.
"""
import math
import random

import numpy as np
import pygame

from playground.scene import BaseScene, Param

PXM = 55.0                                  # screen pixels per metre
CELL = 5                                    # wave cell size in pixels
POOL = (34, 46, 446, 594)                   # pool rectangle on screen (x0, y0, x1, y1)
PW, PH = (POOL[2] - POOL[0]) / PXM, (POOL[3] - POOL[1]) / PXM     # pool size in metres
BODY_SCALE = 0.5                            # body texture resolution vs screen
LADDERS = [((PW - 0.25, 1.15), math.pi), ((0.25, PH - 1.3), 0.0)]   # inside the wall, facing out
FOOT = 0.3048

SKIN = [(236, 196, 166), (208, 160, 120), (170, 118, 82), (122, 82, 56), (226, 178, 150), (96, 64, 44)]
SUITS = [(28, 40, 86), (20, 20, 24), (120, 30, 46), (24, 104, 110), (70, 46, 96), (160, 60, 40)]
CAPS = [(240, 240, 236), (232, 150, 176), (150, 196, 228), (210, 120, 200), (120, 190, 150)]
HAIR = [(200, 200, 204), (236, 236, 232), (90, 60, 40), (30, 26, 24), (150, 120, 90)]
YOU_CAP = (246, 206, 60)
NOODLES = [(240, 90, 150), (110, 220, 120), (250, 200, 60), (90, 170, 240)]

FRAG = """
uniform sampler2D u_wave;   // r, g: slope x, y   b: height
uniform sampler2D u_body;   // swimmers under the water (rgba)
uniform vec4 u_pool;        // pool rectangle in pixels
uniform vec4 u_look;        // refraction, pool lights, sky glow, deck lamp glints
uniform vec4 u_misc;        // time, px per metre, screen w, screen h
varying vec2 uv;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }

float caustic(vec2 q, float t) {
    vec2 a = q * 3.0;
    float c = 0.0;
    for (int i = 0; i < 2; i++) {
        float fi = float(i);
        a += vec2(sin(a.y * 1.3 + t * 0.35 + fi * 1.7), cos(a.x * 1.1 - t * 0.27 + fi * 2.3)) * 0.75;
        c += 1.0 / (1.0 + 30.0 * abs(sin(a.x) * sin(a.y)));
    }
    return c * 0.5;
}

vec3 lights(vec2 m, vec2 size) {
    // two lamps in the long walls toward the deep end, one in the shallow end wall
    vec2 l1 = vec2(0.0, size.y * 0.66), l2 = vec2(size.x, size.y * 0.66), l3 = vec2(size.x * 0.5, 0.0);
    float g = exp(-dot(m - l1, m - l1) * 0.16) + exp(-dot(m - l2, m - l2) * 0.16)
            + 0.6 * exp(-dot(m - l3, m - l3) * 0.22);
    return vec3(0.75, 0.95, 1.0) * g;
}

void main() {
    float t = u_misc.x, pxm = u_misc.y;
    vec2 px = uv * u_misc.zw;
    vec2 size = (u_pool.zw - u_pool.xy) / pxm;           // pool in metres
    vec2 puv = (px - u_pool.xy) / (u_pool.zw - u_pool.xy);
    vec2 m = puv * size;                                  // metres from the shallow-end corner

    // ---- surface slope: the simulated ripples plus a whisper of breeze
    vec4 wv = texture2D(u_wave, puv);
    vec2 g = (wv.rg - 0.5) * 0.65;
    g += vec2(cos(dot(m, vec2(2.1, 0.7)) + t * 0.9), cos(dot(m, vec2(-0.6, 2.6)) + t * 0.7)) * 0.012;
    vec3 n = normalize(vec3(-g, 1.0));

    // ---- depth: 0.9 m at the shallow end to 1.8 m at the deep end
    float depth = mix(0.9, 1.8, smoothstep(0.35, 0.8, puv.y));

    // ---- the tiled floor, seen through the bent surface
    vec2 q = m + n.xy * 0.35 * depth * u_look.x;
    vec2 f = fract(q / 0.12);
    float grout = smoothstep(0.0, 0.07, f.x) * smoothstep(1.0, 0.93, f.x)
                * smoothstep(0.0, 0.07, f.y) * smoothstep(1.0, 0.93, f.y);
    vec3 tile = vec3(0.70, 0.86, 0.90) * (0.94 + 0.06 * hash(floor(q / 0.12)));
    vec3 floorc = mix(vec3(0.52, 0.66, 0.70), tile, grout);
    float lx = min(abs(q.x - size.x * 0.33), abs(q.x - size.x * 0.67));
    float lane = smoothstep(0.11, 0.09, lx) * step(0.9, q.y) * step(q.y, size.y - 0.9);
    floorc = mix(floorc, vec3(0.07, 0.12, 0.30), lane);
    float edge = min(min(q.x, size.x - q.x), min(q.y, size.y - q.y));
    floorc *= 0.72 + 0.28 * smoothstep(0.0, 0.5, edge);  // the walls shade the floor beside them

    // swimmers' soft shadows on the floor (the deck lamp is up and to the left)
    float sh = texture2D(u_body, puv + n.xy * 0.02 + vec2(0.018, 0.02) * depth).a;
    vec3 glow = lights(q, size) * u_look.y;
    float amb = 0.22 + 0.08 * u_look.z;
    vec3 col = floorc * (amb * (1.0 - 0.35 * sh) + glow * (1.0 - 0.5 * sh) * 1.5);
    col += floorc * caustic(q + n.xy * 0.3, t) * (0.06 + 0.18 * length(glow)) * u_look.y;

    // water between floor and eye: blue-green, deeper = darker
    vec3 water = vec3(0.05, 0.30, 0.40) * (0.55 + 0.6 * length(glow)) + vec3(0.0, 0.04, 0.08) * u_look.z;
    col = mix(col, water, clamp(0.32 + depth * 0.22, 0.0, 0.85));

    // ---- swimmers, nearer the surface: bent less, tinted less
    vec4 b = texture2D(u_body, puv + n.xy * 0.018 * u_look.x);
    vec3 bc = b.rgb * (0.62 + 0.10 * u_look.z + 0.7 * lights(m, size) * u_look.y);
    bc = mix(bc, water * 1.3, 0.22);
    col = mix(col, bc, b.a);

    // ---- the surface: dusk sky in the reflection, deck-lamp glints on ripples
    float fres = 0.03 + 0.45 * pow(1.0 - n.z, 2.0);
    vec3 sky = mix(vec3(0.20, 0.24, 0.42), vec3(0.62, 0.46, 0.52), clamp(n.y * 4.0 + 0.4, 0.0, 1.0));
    col = mix(col, sky * u_look.z, fres);
    vec3 V = vec3(0.0, 0.0, 1.0);
    vec3 L = normalize(vec3(-0.55, -0.62, 0.56));
    float spec = pow(max(dot(n, normalize(L + V)), 0.0), 900.0) * 1.1 * u_look.w;
    col += vec3(1.0, 0.86, 0.62) * spec;

    // lamp housings in the walls
    vec2 lp1 = vec2(0.04, size.y * 0.66), lp2 = vec2(size.x - 0.04, size.y * 0.66), lp3 = vec2(size.x * 0.5, 0.04);
    float lamp = smoothstep(0.13, 0.05, length((m - lp1) * vec2(1.6, 1.0))) + smoothstep(0.13, 0.05, length((m - lp2) * vec2(1.6, 1.0)))
               + smoothstep(0.11, 0.04, length((m - lp3) * vec2(1.0, 1.6)));
    col = mix(col, vec3(0.92, 1.0, 1.0), lamp * clamp(u_look.y, 0.0, 1.0));

    col += (hash(gl_FragCoord.xy + fract(t) * 61.0) - 0.5) / 72.0;     // dither
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
        self.alpha = 1.0 if you else 0.0
        self.plan = []                  # queue of things to do (others)
        self.timer = 0.0
        self.leaving = False
        self.gone = False
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
        Param("lights", 1.0, 0, 2, 0.05, "Pool lights"),
        Param("dusk", 1.0, 0, 2, 0.05, "Dusk sky"),
        Param("glints", 1.0, 0, 3, 0.05, "Lamp glints"),
        Param("refraction", 1.0, 0, 3, 0.05, "Refraction"),
    ]

    # ------------------------------------------------------------------ setup
    def setup(self):
        gl = self.gl
        self.prog = gl.program(FRAG)
        self.rng = random.Random()
        self.gw = (POOL[2] - POOL[0]) // CELL
        self.gh = (POOL[3] - POOL[1]) // CELL
        self.hgt = np.zeros((self.gh, self.gw), np.float32)
        self.vel = np.zeros_like(self.hgt)
        self.pad = np.zeros((self.gh + 2, self.gw + 2), np.float32)
        self.wbuf = np.full((self.gh, self.gw, 4), 128, np.uint8)
        self.wbuf[..., 3] = 255
        self.wave_tex = gl.texture(self.gw, self.gh, self.wbuf.tobytes())
        bw = int((POOL[2] - POOL[0]) * BODY_SCALE)
        bh = int((POOL[3] - POOL[1]) * BODY_SCALE)
        self.body = pygame.Surface((bw, bh), pygame.SRCALPHA)
        self.body_tex = gl.texture(bw, bh)
        self.bpm = PXM * BODY_SCALE                     # body-texture pixels per metre
        k = np.exp(-np.linspace(-1.6, 1.6, 5) ** 2)
        self.kernel = (k[:, None] * k[None, :]).astype(np.float32)
        self.deck_tex = gl.surface_texture(self._paint_deck(), "adultswim_deck")
        self.font = pygame.font.Font(None, 24)
        self.t = 0.0
        self.you = Swimmer(PW * 0.5, PH * 0.45, -math.pi / 2, you=True, rng=self.rng)
        self.swimmers = [self.you]
        self.next_arrival = 4.0
        self.marker = None                              # (x, y, time) of your last tap
        first = self._arrive(0, already_in=True)
        first.x, first.y = PW * 0.25, PH * 0.75
        self.taps = {}

    # ------------------------------------------------------------- the deck
    def _paint_deck(self):
        w, h = self.w, self.h
        rng = np.random.default_rng(7)
        yy, xx = np.mgrid[0:h, 0:w]
        noise = rng.normal(0, 1, (h, w))
        base = np.array([108, 100, 92], float)
        lamp = np.exp(-((xx + 60) ** 2 + (yy + 40) ** 2) / (2 * 320.0 ** 2))   # deck lamp, upper left
        cool = np.array([0.62, 0.66, 0.80])
        warm = np.array([1.12, 0.98, 0.80])
        light = cool[None, None] + (warm - cool)[None, None] * lamp[..., None]
        img = (base[None, None] * light * (1 + noise[..., None] * 0.035)).clip(0, 255)
        surf = pygame.surfarray.make_surface(img.transpose(1, 0, 2).astype(np.uint8)).convert_alpha()
        x0, y0, x1, y1 = POOL
        cop = 9
        stone = (176, 168, 156)
        pygame.draw.rect(surf, stone, (x0 - cop, y0 - cop, x1 - x0 + 2 * cop, y1 - y0 + 2 * cop), border_radius=6)
        for x in range(x0 - cop, x1 + cop, 22):                              # coping joints
            pygame.draw.line(surf, (150, 142, 132), (x, y0 - cop), (x, y0 - 1))
            pygame.draw.line(surf, (150, 142, 132), (x, y1), (x, y1 + cop))
        for y in range(y0 - cop, y1 + cop, 22):
            pygame.draw.line(surf, (150, 142, 132), (x0 - cop, y), (x0 - 1, y))
            pygame.draw.line(surf, (150, 142, 132), (x1, y), (x1 + cop, y))
        dim = pygame.Surface((w, h), pygame.SRCALPHA)                          # dusk on the coping too
        dim.fill((40, 50, 90, 70))
        surf.blit(dim, (0, 0))
        small = pygame.font.Font(None, 17)
        ink = (34, 52, 104)
        for text, pos in (("3 FT", (x0 + 30, y0 - 26)), ("3 FT", (x1 - 62, y0 - 26)),
                          ("5 FT", (x0 + 30, y1 + 14)), ("5 FT", (x1 - 62, y1 + 14)),
                          ("NO DIVING", (w // 2 - 34, y0 - 26))):
            surf.blit(small.render(text, True, ink), pos)
        # a striped towel and some flip-flops
        towel = pygame.Surface((70, 26), pygame.SRCALPHA)
        for i in range(0, 70, 10):
            pygame.draw.rect(towel, (172, 76, 70) if (i // 10) % 2 else (210, 196, 170), (i, 0, 10, 26))
        towel = pygame.transform.rotate(towel, 8)
        towel.fill((150, 150, 170, 255), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(towel, (w // 2 - 40, h - 40))
        for dx, ang in ((0, 12), (12, -6)):
            ff = pygame.Surface((10, 22), pygame.SRCALPHA)
            pygame.draw.ellipse(ff, (60, 120, 170), ff.get_rect())
            surf.blit(pygame.transform.rotate(ff, ang), (w // 2 + 70 + dx, h - 38))
        # cut the pool out
        pygame.draw.rect(surf, (0, 0, 0, 0), (x0, y0, x1 - x0, y1 - y0))
        # ladders: rails curving from the deck into the water, rungs dim beneath
        for (lx, ly), face in LADDERS:
            sx = x0 + lx * PXM
            sy = y0 + ly * PXM
            wall = x1 if face == math.pi else x0
            out = 1 if face == math.pi else -1
            for dy in (-14, 14):
                yy0 = sy + dy
                pygame.draw.line(surf, (60, 64, 72), (wall + out * 16, yy0 + 2), (wall - out * 12, yy0 + 2), 4)
                pygame.draw.line(surf, (214, 220, 228), (wall + out * 16, yy0), (wall - out * 12, yy0), 3)
                pygame.draw.circle(surf, (230, 234, 240), (wall + out * 16, yy0), 3)
            for k in range(3):
                rx = wall - out * (5 + k * 7)
                pygame.draw.line(surf, (200, 214, 220, 70 - k * 18), (rx, sy - 13), (rx, sy + 13), 3)
        return surf

    # ------------------------------------------------------------- swimmers
    def _arrive(self, n_others, already_in=False):
        (lx, ly), face = self.rng.choice(LADDERS)
        s = Swimmer(lx, ly, face + math.pi, rng=self.rng)
        s.mode = "tread"
        s.alpha = 1.0 if already_in else 0.0
        kind = self.rng.choice(["laps", "laps", "float", "float", "noodle", "chat"])
        if already_in:
            kind = "float"
        if kind == "noodle":
            s.mode = "noodle"
        s.plan = self._plan(kind, s)
        self.swimmers.append(s)
        return s

    def _plan(self, kind, s):
        r = self.rng
        lane = r.choice([PW * 0.17, PW * 0.5, PW * 0.83])
        if kind == "laps":
            ends = []
            for i in range(r.randint(2, 4)):
                ends.append(("swim", (lane + r.uniform(-0.2, 0.2), 0.8 if i % 2 == 0 else PH - 0.8)))
                ends.append(("rest", r.uniform(2, 6)))
            return [("swim", (lane, PH * 0.5))] + ends + [("leave", None)]
        if kind == "float":
            return [("swim", (r.uniform(1.2, PW - 1.2), r.uniform(1.5, PH - 1.5))),
                    ("float", r.uniform(35, 80)), ("leave", None)]
        if kind == "noodle":
            return [("drift", r.uniform(40, 90)), ("leave", None)]
        # chat: drift over to someone and tread nearby
        return [("chat", r.uniform(25, 50)), ("leave", None)]

    def _next_task(self, s):
        if not s.plan:
            s.leaving = True
            return
        kind, arg = s.plan.pop(0)
        s.task = kind
        s.timer = arg if isinstance(arg, (int, float)) else 0.0
        if kind == "swim":
            s.target = arg
            s.mode = "breast"
        elif kind == "rest":
            s.mode, s.target = "tread", None
        elif kind == "float":
            s.mode, s.target = "float", None
        elif kind == "drift":
            s.mode, s.target = "noodle", None
        elif kind == "chat":
            friend = min((o for o in self.swimmers if o is not s and not o.leaving),
                         key=lambda o: (o.x - s.x) ** 2 + (o.y - s.y) ** 2, default=None)
            if friend:
                s.target = (friend.x + self.rng.uniform(-1, 1), friend.y + self.rng.uniform(-1, 1))
                s.mode = "breast"
                s.plan.insert(0, ("rest", s.timer))
                s.task = "swim"
        elif kind == "leave":
            (lx, ly), _ = min(LADDERS, key=lambda L: (L[0][0] - s.x) ** 2 + (L[0][1] - s.y) ** 2)
            s.target = (lx, ly)
            s.mode = "breast"
            s.leaving = True

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
        mx = min(PW - 0.4, max(0.4, (x - POOL[0]) / PXM))
        my = min(PH - 0.4, max(0.4, (y - POOL[1]) / PXM))
        self.you.target = (mx, my)
        self.you.mode = "breast"
        self.marker = (mx, my, self.t)

    # ------------------------------------------------------------- update
    def update(self, dt):
        self.t += dt
        p = self.p
        others = [s for s in self.swimmers if not s.you]
        self.next_arrival -= dt * p.busy
        if self.next_arrival <= 0:
            if len(others) < int(p.others):
                self._arrive(len(others))
            self.next_arrival = self.rng.uniform(14, 40)
        for s in self.swimmers:
            self._move(s, dt)
        self._separate()
        self.swimmers = [s for s in self.swimmers if not s.gone]
        self._waves(dt)

    def _move(self, s, dt):
        p = self.p
        if not s.you:
            if s.alpha < 1 and not s.leaving:
                s.alpha = min(1.0, s.alpha + dt * 0.5)     # climbing down the ladder
                if s.alpha < 1:
                    s.phase = (s.phase + dt * 0.4) % 1
                    return
                self._next_task(s)
            elif s.leaving and s.target is None:
                s.alpha -= dt * 0.5                         # climbing out
                if s.alpha <= 0:
                    s.gone = True
                return
            elif s.target is None and s.timer > 0:
                s.timer -= dt
                if s.timer <= 0:
                    self._next_task(s)
            elif s.target is None and not s.leaving and s.alpha >= 1 and not getattr(s, "task", None):
                self._next_task(s)
        pace = p.pace * s.pace
        if s.mode == "breast" and s.target is not None:
            tx, ty = s.target
            dx, dy = tx - s.x, ty - s.y
            dist = math.hypot(dx, dy)
            want = math.atan2(dy, dx)
            turn = angle_to(s.a, want)
            s.a += max(-1.0, min(1.0, turn)) * dt * 1.4
            period = 2.3 / pace
            s.phase = (s.phase + dt / period) % 1
            ph = s.phase
            surge = 0.35 + 1.25 * math.exp(-(((ph - 0.6) % 1.0) * 3.2))   # glide after the kick
            v = 0.5 * pace * surge * max(0.25, math.cos(turn) if abs(turn) < 1.5 else 0.25)
            v *= min(1.0, dist / 0.8 + 0.25)
            s.speed = v
            fx, fy = s.f
            s.x += fx * v * dt
            s.y += fy * v * dt
            if dist < 0.3:
                s.target = None
                s.speed = 0.0
                s.mode = "tread"
                if not s.you:
                    if s.leaving:
                        s.target = None
                    else:
                        self._next_task(s)
            # splashes: hands as they sweep out, a little bow wave at the head
            if 0.05 < ph < 0.3 and self.t - s.last_splash > 0.12:
                sx, sy = -fy, fx
                for side in (-1, 1):
                    self._poke(s.x + fx * 0.35 + sx * side * 0.4, s.y + fy * 0.35 + sy * side * 0.4, 0.55)
                s.last_splash = self.t
            self._poke(s.x + fx * 0.25, s.y + fy * 0.25, 0.10 * v)
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
        s.x = min(PW - 0.25, max(0.25, s.x))
        s.y = min(PH - 0.25, max(0.25, s.y))

    def _separate(self):
        sw = [s for s in self.swimmers if s.alpha > 0.3]
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
        cx = int(x * PXM / CELL)
        cy = int(y * PXM / CELL)
        if not (2 <= cx < self.gw - 2 and 2 <= cy < self.gh - 2):
            return
        self.vel[cy - 2:cy + 3, cx - 2:cx + 3] -= self.kernel * amount * 0.6 * self.p.ripple

    def _waves(self, dt):
        p = self.p
        h, v, pad = self.hgt, self.vel, self.pad
        c = 0.045 * p.ripple_speed ** 2
        damp = math.exp(-dt * 0.55 * p.ripple_fade)
        pad[1:-1, 1:-1] = h                                  # walls reflect: copy the edge outward
        pad[0, 1:-1] = h[0]
        pad[-1, 1:-1] = h[-1]
        pad[1:-1, 0] = h[:, 0]
        pad[1:-1, -1] = h[:, -1]
        lap = pad[:-2, 1:-1] + pad[2:, 1:-1] + pad[1:-1, :-2] + pad[1:-1, 2:] - 4 * h
        v += lap * c
        v *= damp
        h += v
        h -= h.mean()                                         # keep the water level

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
        return surf

    def _head_tex(self, gl, s):
        """A crisp head (cap or hair, the face toward the heading), cached per 16 directions."""
        kind, col = s.head
        on_back = s.mode == "float"
        d = int(round((s.a % (2 * math.pi)) / (2 * math.pi) * 16)) % 16
        key = f"head_{kind}_{col}_{s.skin}_{on_back}_{d}"
        cache = self.__dict__.setdefault("_heads", {})
        if key in cache:
            return cache[key]
        S, R = 4, 24                                         # draw 4x then shrink; 24 px canvas
        D = R * S
        big = pygame.Surface((D, D), pygame.SRCALPHA)
        c = D // 2
        r = 0.115 * PXM * S
        ang = d / 16 * 2 * math.pi
        fx, fy = math.cos(ang), math.sin(ang)
        pygame.draw.circle(big, (255, 255, 255, 40), (c, c), int(r * 1.55))              # water ring
        pygame.draw.circle(big, (10, 30, 50, 60), (c + S * 2, c + S * 2), int(r * 1.1))   # shadow
        if on_back:
            pygame.draw.circle(big, s.skin, (c, c), int(r))                                # face up
            hc = HAIR[0] if kind == "cap" else col
            pygame.draw.circle(big, col if kind == "cap" else hc, (int(c - fx * r * 0.55), int(c - fy * r * 0.55)), int(r * 0.75))
            pygame.draw.circle(big, s.skin, (int(c + fx * r * 0.25), int(c + fy * r * 0.25)), int(r * 0.72))
        else:
            pygame.draw.circle(big, s.skin, (int(c + fx * r * 0.18), int(c + fy * r * 0.18)), int(r * 0.95))
            pygame.draw.circle(big, col, (int(c - fx * r * 0.12), int(c - fy * r * 0.12)), int(r * 0.97))
        hl = (int(c - r * 0.35), int(c - r * 0.4))
        pygame.draw.circle(big, (255, 255, 255, 120), hl, int(r * 0.28))                  # wet shine
        small = pygame.transform.smoothscale(big, (R, R))
        cache[key] = gl.surface_texture(small, key)
        return cache[key]

    def draw_gl(self, gl):
        p = self.p
        h = self.hgt
        gy, gx = np.gradient(h)
        wb = self.wbuf
        wb[..., 0] = np.clip(128 + gx * 600, 0, 255)
        wb[..., 1] = np.clip(128 + gy * 600, 0, 255)
        wb[..., 2] = np.clip(128 + h * 300, 0, 255)
        self.wave_tex.update(wb.tobytes())
        self.body_tex.update(pygame.image.tobytes(self._draw_bodies(), "RGBA"))

        gl.screen()
        pr = self.prog
        pr.use()
        self.wave_tex.bind(0)
        self.body_tex.bind(1)
        pr.set_int("u_wave", 0)
        pr.set_int("u_body", 1)
        pr.set("u_pool", *POOL)
        pr.set("u_look", p.refraction, p.lights, p.dusk, p.glints)
        pr.set("u_misc", self.t % 500.0, PXM, self.w, self.h)
        gl.draw_quad()
        gl.blit_at(self.deck_tex, 0, 0)

        if self.marker:                                      # where you tapped: a soft ring that fades
            mx, my, t0 = self.marker
            age = self.t - t0
            if age < 1.6 and self.you.target is not None:
                if not hasattr(self, "_ring"):
                    ring = pygame.Surface((40, 40), pygame.SRCALPHA)
                    pygame.draw.circle(ring, (255, 250, 220, 150), (20, 20), 14, 2)
                    self._ring = gl.surface_texture(ring, "adultswim_ring")
                gl.blit_at(self._ring, POOL[0] + mx * PXM - 20, POOL[1] + my * PXM - 20,
                           alpha=max(0.0, 1 - age / 1.6))
        for s in self.swimmers:
            if s.alpha <= 0:
                continue
            tex = self._head_tex(gl, s)
            fx, fy = s.f
            if s.mode == "breast":
                off = 0.36
            elif s.mode == "float":
                off = 0.40
            else:
                off = 0.0
            bob = 0.02 * math.sin(s.phase * 4 * math.pi) if s.mode in ("tread", "noodle") else 0.0
            hx = POOL[0] + (s.x + fx * off) * PXM - tex.w / 2
            hy = POOL[1] + (s.y + fy * off + bob) * PXM - tex.h / 2
            gl.blit_at(tex, hx, hy, alpha=s.alpha)

        if self.t < 8 and not self.taps:
            if not hasattr(self, "_hint"):
                im = self.font.render("tap the water to swim there", True, (40, 40, 52))
                hint = pygame.Surface((im.get_width() + 20, 28), pygame.SRCALPHA)
                pygame.draw.rect(hint, (255, 255, 255, 160), hint.get_rect(), border_radius=10)
                hint.blit(im, im.get_rect(center=(hint.get_width() // 2, 14)))
                self._hint = gl.surface_texture(hint, "adultswim_hint")
            gl.blit_at(self._hint, (self.w - self._hint.w) // 2, self.h - 80, alpha=min(1.0, 8 - self.t))

    # ------------------------------------------------------------- preview
    def preview(self, step):
        self.rng.seed(5)
        for _ in range(60):
            self.update(step)
        self._go(300, 200)
        for _ in range(150):
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
