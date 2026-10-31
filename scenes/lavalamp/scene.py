"""Lava Lamp: warm wax rises, cools, and sinks, in a glowing glass rocket.

Touch the glass to warm the wax near your finger (it swells and lifts off) and
drag to stir it. Tap the lamp's base to switch it off (the wax cools, slumps and
the glow fades) and tap again to switch it back on.

How it works:
- Physics (CPU, a handful of blobs): each blob has a temperature. The bulb in
  the base heats whatever is near the bottom; everything slowly cools, faster
  near the top. Warm wax is lighter than the liquid, so it rises; cool wax
  sinks. Thick liquid (drag) keeps it all slow. Blobs swell a little when warm.
- Drawing (GPU, one fragment shader): the blobs are "metaballs". Every pixel
  adds up r^2 / distance^2 from each blob, plus a puddle of wax on the bottom;
  where the sum passes 1 it's wax. Because the field adds up, blobs that come
  close join smoothly and pull apart in a neck, just like the real thing.
  Thick wax is darker and richer, thin edges glow, and everything is lit from
  the bulb below. The glass gets bright streaks and darker edges, and the lamp
  throws a soft glow on the wall and the table.
"""
import math
import random

from playground.scene import BaseScene, Param

N = 9                                   # blobs (each is one shader uniform)
CX, TOP, BOT = 240.0, 150.0, 500.0      # glass: centre line, top and bottom (pixels)
PALETTES = ("Classic", "Sunset", "Arctic", "Slime")
WAX = [(1.0, 0.24, 0.10), (1.0, 0.55, 0.12), (0.93, 0.95, 1.0), (0.72, 1.0, 0.25)]
LIQUID = [(1.0, 0.72, 0.22), (0.42, 0.10, 0.40), (0.10, 0.30, 0.78), (0.08, 0.42, 0.40)]


def half_width(y):
    """Half the width of the glass at height y (a tapered rocket, widest low down)."""
    t = min(1.0, max(0.0, (y - TOP) / (BOT - TOP)))
    s = min(1.0, max(0.0, (t - 0.86) / 0.14))
    return 48.0 + 62.0 * t ** 0.75 - 18.0 * s * s * (3 - 2 * s)


FRAG = """
uniform vec4 u_blobs[%(n)d];   // x, y, radius (px), temperature
uniform vec4 u_lamp;           // centre x, glass top, glass bottom, power (0..1)
uniform vec4 u_misc;           // time, screen w, screen h, glow
uniform vec3 u_wax;
uniform vec3 u_liquid;
varying vec2 uv;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }

float halfWidth(float y) {
    float t = clamp((y - u_lamp.y) / (u_lamp.z - u_lamp.y), 0.0, 1.0);
    return 48.0 + 62.0 * pow(t, 0.75) - 18.0 * smoothstep(0.86, 1.0, t);
}

vec3 metal(float nx, float lit) {                   // a brushed, rounded metal surface
    float shade = 0.22 + 0.55 * (1.0 - nx * nx) + 0.5 * exp(-pow((nx + 0.45) / 0.12, 2.0));
    return vec3(0.42, 0.40, 0.44) * shade + vec3(1.0, 0.6, 0.35) * lit * 0.25;
}

void main() {
    vec2 px = uv * u_misc.yz;
    float cx = u_lamp.x, top = u_lamp.y, bot = u_lamp.z, power = u_lamp.w;
    float glow = u_misc.w * power;
    float dx = px.x - cx;

    // ---- the room: a dark wall, lit by the lamp; a table top below
    float lampD = length(vec2(dx * 0.9, (px.y - (top + bot) * 0.5) * 0.55));
    vec3 col = mix(vec3(0.07, 0.06, 0.08), vec3(0.03, 0.03, 0.05), uv.y);
    col += u_wax * glow * 0.32 * exp(-lampD / 120.0) + u_liquid * glow * 0.10 * exp(-lampD / 220.0);
    if (px.y > 600.0) {                                   // table, catching the glow
        float k = (px.y - 600.0) / 40.0;
        col = vec3(0.16, 0.10, 0.07) * (0.7 + 0.3 * hash(vec2(floor(px.x / 3.0), 7.0)));
        col += u_wax * glow * 0.35 * exp(-abs(dx) / 90.0) * (1.0 - k * 0.5);
    }

    // ---- cap (top) and base (bottom): metal cones
    if (px.y > top - 58.0 && px.y < top) {
        float hw = mix(30.0, 50.0, (px.y - (top - 58.0)) / 58.0);
        if (abs(dx) < hw) col = metal(dx / hw, glow * 0.5);
    }
    if (px.y >= bot && px.y < 604.0) {
        float k = (px.y - bot) / (604.0 - bot);
        float hw = mix(90.0, 122.0, k);
        if (abs(dx) < hw) {
            col = metal(dx / hw, glow * (1.0 - k));
            col *= 1.0 - 0.35 * smoothstep(0.0, 0.05, k) * smoothstep(0.12, 0.07, k);   // a ring
        }
    }

    // ---- the glass and everything inside it
    float hw = halfWidth(px.y);
    if (px.y > top && px.y < bot && abs(dx) < hw) {
        float nx = dx / hw;
        float bulb = exp(-(bot - px.y) / 170.0);          // light from the bulb below
        vec3 liquid = u_liquid * (0.18 + 0.30 * glow + 0.85 * bulb * glow);

        // metaball field
        float f = 0.0;
        for (int i = 0; i < %(n)d; i++) {
            vec4 b = u_blobs[i];
            vec2 d = px - b.xy;
            f += b.z * b.z / (dot(d, d) + 1.0);
        }
        vec2 pd = vec2(dx / 2.4, px.y - (bot + 22.0));      // the puddle on the bottom
        f += 46.0 * 46.0 / (dot(pd, pd) + 1.0);

        float wax = smoothstep(0.92, 1.08, f);
        float thick = smoothstep(1.0, 2.4, f);
        vec3 w = u_wax * (0.30 + 0.35 * glow + 0.80 * bulb * glow);
        w = mix(w * 1.18 + vec3(0.07) * glow, w, thick);          // thin edges glow a little brighter
        col = mix(liquid, w, wax);

        // glass: bright streaks, darker toward the edges
        col *= 0.55 + 0.45 * (1.0 - pow(abs(nx), 4.0));
        col += vec3(1.0) * 0.30 * exp(-pow((nx + 0.58) / 0.06, 2.0));
        col += vec3(1.0) * 0.10 * exp(-pow((nx - 0.62) / 0.10, 2.0));
    }

    col += (hash(gl_FragCoord.xy + fract(u_misc.x) * 61.0) - 0.5) / 72.0;   // dither
    gl_FragColor = vec4(col, 1.0);
}
""" % {"n": N}


class Blob:
    def __init__(self, rng):
        self.x = CX + rng.uniform(-40, 40)
        self.y = rng.uniform(TOP + 60, BOT - 40)
        self.vx = self.vy = 0.0
        self.r0 = rng.uniform(17, 30)
        self.temp = rng.uniform(0.3, 0.75)


class Scene(BaseScene):
    TITLE = "Lava Lamp"
    BRAND = dict(name="Lava Lamp", font="Shrikhand", size=62, tilt=3,
                 fill=((255, 200, 70), (255, 70, 120)), outline=(70, 20, 80), outline_width=6,
                 tagline="warm it up and watch", art="lava", art_y=118)
    GPU = True
    PARAMS = [
        Param("palette", 0, 0, 0, 1, choices=PALETTES, label="Colours"),
        Param("heat", 1.0, 0, 3, 0.05, "Bulb heat", help="Hotter = more wax rising at once."),
        Param("thickness", 1.0, 0.3, 3, 0.05, "Liquid thickness", help="Higher = slower, lazier blobs."),
        Param("size", 1.0, 0.6, 1.5, 0.05, "Blob size"),
        Param("glow", 1.0, 0, 2, 0.05, "Glow"),
        Param("touch_heat", 1.0, 0, 3, 0.05, "Finger warmth"),
    ]

    def setup(self):
        self.prog = self.gl.program(FRAG)
        self.rng = random.Random()
        self.blobs = [Blob(self.rng) for _ in range(N)]
        self.t = 0.0
        self.on = True
        self.power = 1.0
        self.fingers_now = {}
        self.prev = {}
        self.downs = {}

    # ------------------------------------------------------------- input
    def fingers(self, fingers):
        for k in list(self.downs):
            if k not in fingers:                       # a tap on the base switches the lamp
                t0, x0, y0, moved = self.downs.pop(k)
                if self.t - t0 < 0.35 and moved < 15 and BOT < y0 < 604 and abs(x0 - CX) < 122:
                    self.on = not self.on
        for k, (x, y) in fingers.items():
            if k in self.downs:
                t0, x0, y0, moved = self.downs[k]
                self.downs[k] = (t0, x0, y0, max(moved, math.hypot(x - x0, y - y0)))
            else:
                self.downs[k] = (self.t, x, y, 0.0)
        self.prev, self.fingers_now = self.fingers_now, dict(fingers)

    # ------------------------------------------------------------- physics
    def update(self, dt):
        self.t += dt
        p = self.p
        target = 1.0 if self.on else 0.0
        self.power += (target - self.power) * min(1.0, dt * (1.5 if self.on else 0.6))
        heat = p.heat * self.power
        drag = math.exp(-dt * 1.6 * p.thickness)
        for b in self.blobs:
            # heat from the bulb below, cooling everywhere (faster near the top)
            # (big blobs warm and cool more slowly, which keeps them out of step with each other)
            near_bulb = math.exp(-(BOT - b.y) / 55.0)
            near_cap = math.exp(-(b.y - TOP) / 45.0)
            slow = 24.0 / b.r0
            b.temp += dt * slow * (0.7 * heat * near_bulb - 0.025 - 0.30 * near_cap)
            for x, y in self.fingers_now.values():         # a finger on the glass warms the wax near it
                if TOP < y < BOT + 12 and abs(x - CX) < half_width(min(y, BOT)):
                    d2 = (x - b.x) ** 2 + (y - b.y) ** 2
                    b.temp += dt * 1.2 * p.touch_heat * math.exp(-d2 / (2 * 55.0 ** 2))
            b.temp = min(1.0, max(0.0, b.temp))
            # warm wax is lighter than the liquid: it rises; cool wax sinks
            b.vy += (-(b.temp - 0.5) * 120.0) * dt / p.thickness
            b.vx += math.sin(self.t * 0.3 + b.r0) * 2.0 * dt   # faint currents
            b.vx *= drag
            b.vy *= drag
        # stirring: dragging a finger nudges the wax along
        for k, (x, y) in self.fingers_now.items():
            if k in self.prev and TOP < y < BOT:
                px, py = self.prev[k]
                for b in self.blobs:
                    w = math.exp(-((x - b.x) ** 2 + (y - b.y) ** 2) / (2 * 45.0 ** 2))
                    b.vx += (x - px) * w * 3.0
                    b.vy += (y - py) * w * 3.0
        # blobs give way to each other a little (they still merge visually)
        for i, a in enumerate(self.blobs):
            for b in self.blobs[i + 1:]:
                dx, dy = b.x - a.x, b.y - a.y
                d = math.hypot(dx, dy) + 1e-3
                need = 0.55 * (a.r0 + b.r0)
                if d < need:
                    push = (need - d) * 0.5 * dt * 6
                    a.vx -= dx / d * push
                    a.vy -= dy / d * push
                    b.vx += dx / d * push
                    b.vy += dy / d * push
        for b in self.blobs:
            b.x += b.vx * dt
            b.y += b.vy * dt
            r = self._radius(b)
            lo, hi = TOP + r * 0.6, BOT + 6.0             # resting on the bottom sinks into the puddle
            if b.y < lo:
                b.y, b.vy = lo, abs(b.vy) * 0.2
            if b.y > hi:
                b.y, b.vy = hi, -abs(b.vy) * 0.2
            lim = max(4.0, half_width(b.y) - r * 0.7)
            if abs(b.x - CX) > lim:
                b.x = CX + math.copysign(lim, b.x - CX)
                b.vx *= -0.3

    def _radius(self, b):
        return b.r0 * self.p.size * (0.82 + 0.34 * b.temp)

    # ------------------------------------------------------------- draw
    def draw_gl(self, gl):
        p = self.p
        gl.screen()
        pr = self.prog
        pr.use()
        flat = []
        for b in self.blobs:
            flat += [b.x, b.y, self._radius(b), b.temp]
        pr.set_vec4_array("u_blobs", flat)
        pr.set("u_lamp", CX, TOP, BOT, self.power)
        pr.set("u_misc", self.t % 1000.0, self.w, self.h, p.glow)
        k = int(p.palette)
        pr.set("u_wax", *WAX[k])
        pr.set("u_liquid", *LIQUID[k])
        gl.draw_quad()

    def preview(self, step):
        self.rng.seed(4)
        for _ in range(60 * 25):
            self.update(step)

    PREVIEW_AFTER = 0
