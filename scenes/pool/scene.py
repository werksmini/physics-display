"""A sunlit swimming pool seen from above; touch the water to make ripples.

The first GPU scene: everything is computed per pixel in a fragment shader,
every frame, on the Pi's graphics chip.

For each pixel:
1. Water height: a few gentle wind waves (sums of sines) plus the ripple rings
   from your touches. Each ripple is a ring travelling outward, a short train
   of waves that fades with time and distance.
2. Surface normal: the slope of that height, worked out exactly (the
   derivative of each sine), so it costs no extra samples.
3. Refraction: the tile floor is looked up at a point shifted by the slope,
   which is what makes the grout lines waver.
4. Caustics: sunlight focused by the waves into bright, shifting nets on the
   floor. An animated, warped pattern, plus extra brightness where ripples
   curve the surface.
5. Light: water tint by depth, sun glints where the surface faces the sun
   (specular highlight), a faint sky reflection, and a little dither so the
   panel's 18-bit colour doesn't band.

Ripples are passed to the shader as a small array (position, age, strength).
"""
import math
import time

from playground.scene import BaseScene, Param

MAX_RIPPLES = 8

FRAG = """
uniform float u_time;
uniform vec4 u_ripples[%(n)d];   // x, y (world metres), age (s), strength
uniform vec4 u_a;                // ambient wave, ripple strength, caustics, refraction
uniform vec4 u_b;                // tile size, depth tint, glints, world height (m)
uniform vec4 u_c;                // ripple speed, ripple decay, ripple wavenumber, aspect
varying vec2 uv;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }

// one directional wave: adds slope to g, returns height
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
    float aspect = u_c.w;
    vec2 p = vec2(uv.x * aspect, uv.y) * u_b.w;            // world position in metres

    // --- height slope from ambient waves
    vec2 g = vec2(0.0);
    float amb = u_a.x * 0.004;
    wave(p, normalize(vec2(1.0, 0.35)), 9.0, 1.7, amb, 0.0, g);
    wave(p, normalize(vec2(-0.4, 1.0)), 13.0, 2.1, amb * 0.7, 1.3, g);
    wave(p, normalize(vec2(0.8, -0.6)), 21.0, 2.9, amb * 0.4, 2.1, g);
    wave(p, normalize(vec2(-1.0, -0.2)), 31.0, 3.7, amb * 0.25, 0.4, g);

    // --- ripples from touches
    float curv = 0.0;
    float k = u_c.z;
    for (int i = 0; i < %(n)d; i++) {
        vec4 r = u_ripples[i];
        if (r.w <= 0.0) continue;
        vec2 d = p - r.xy;
        float dist = length(d) + 1e-4;
        float front = u_c.x * r.z;
        float behind = front - dist;                       // >0 inside the ring
        float env = smoothstep(-0.05, 0.03, behind) * exp(-behind * 2.2)
                  * exp(-r.z * u_c.y) / (1.0 + dist * 0.8);
        float a = r.w * u_a.y * 0.008 * env;
        float ph = k * behind;
        g += (d / dist) * (a * k * cos(ph));
        curv += a * k * k * sin(ph);
    }

    vec3 n = normalize(vec3(-g * 1.6, 1.0));

    // --- refracted tile floor
    vec2 q = p + n.xy * 0.22 * u_a.w;
    float ts = u_b.x;
    vec2 cell = floor(q / ts);
    vec2 f = fract(q / ts);
    float grout = smoothstep(0.0, 0.045, f.x) * smoothstep(1.0, 0.955, f.x)
                * smoothstep(0.0, 0.045, f.y) * smoothstep(1.0, 0.955, f.y);
    vec3 tile = vec3(0.80, 0.93, 0.95) * (0.94 + 0.08 * hash(cell));
    vec3 floorc = mix(vec3(0.60, 0.74, 0.78), tile, grout);
    float lane = smoothstep(0.13, 0.11, abs(q.x - 1.15)) * step(0.45, q.y);   // dark lane line
    float tee = smoothstep(0.13, 0.11, abs(q.y - 0.45)) * smoothstep(0.42, 0.40, abs(q.x - 1.15));
    floorc = mix(floorc, vec3(0.08, 0.16, 0.36), max(lane, tee));

    // --- caustic light on the floor
    float c = caustic(q + n.xy * 0.15) * u_a.z + max(curv * 0.05, 0.0) * u_a.z;
    vec3 col = floorc * (0.62 + 1.15 * c);

    // --- water: depth tint, sky reflection, sun glints
    vec3 water = vec3(0.30, 0.72, 0.82);
    col = mix(col, col * water * 1.25, u_b.y);
    vec3 L = normalize(vec3(0.35, -0.45, 0.82));
    vec3 H = normalize(L + vec3(0.0, 0.0, 1.0));
    float spec = pow(max(dot(n, H), 0.0), 900.0) * 2.5 * u_b.z;
    float fres = 0.04 + 0.5 * pow(1.0 - n.z, 3.0);
    col = mix(col, vec3(0.80, 0.90, 1.0), fres) + vec3(1.0, 0.97, 0.9) * spec;

    col += (hash(gl_FragCoord.xy + fract(u_time) * 61.0) - 0.5) / 64.0;   // dither
    gl_FragColor = vec4(col, 1.0);
}
""" % {"n": MAX_RIPPLES}


class Scene(BaseScene):
    TITLE = "Sunlit Pool"
    BRAND = dict(name="Sunlit Pool", font="Shrikhand", size=56,
                 fill=((255, 236, 120), (255, 160, 60)), outline=(150, 60, 30), outline_width=6,
                 tagline="touch the water", art="sun", art_y=70)
    GPU = True
    PARAMS = [
        Param("ambient", 1.0, 0, 4, 0.05, "Wind on the water"),
        Param("ripple", 1.0, 0, 4, 0.05, "Ripple strength"),
        Param("ripple_speed", 0.9, 0.2, 3, 0.05, "Ripple speed", help="Metres per second."),
        Param("ripple_decay", 0.45, 0.05, 3, 0.05, "Ripple fade"),
        Param("ripple_wave", 38, 10, 90, 1, "Ripple wavelength", help="Higher = tighter rings."),
        Param("caustics", 1.0, 0, 3, 0.05, "Caustics"),
        Param("refraction", 1.0, 0, 3, 0.05, "Refraction"),
        Param("glints", 1.0, 0, 3, 0.05, "Sun glints"),
        Param("depth", 0.55, 0, 1, 0.01, "Water depth tint"),
        Param("tile_size", 0.16, 0.05, 0.5, 0.01, "Tile size", help="Metres."),
        Param("view", 3.0, 1, 8, 0.1, "View height", help="Metres of pool from top to bottom of the screen."),
        Param("render_scale", 1.0, 0.25, 1.0, 0.05, "Render scale", reset=True,
              help="Render smaller and scale up: faster on the Pi, a little softer."),
    ]

    def setup(self):
        gl = self.gl
        self.prog = gl.program(FRAG)
        s = self.p.render_scale
        self.target = gl.target(max(16, int(self.w * s)), max(16, int(self.h * s))) if s < 0.99 else None
        self.ripples = []            # [x_m, y_m, t0, strength]
        self.t0 = time.perf_counter()
        self.t = 0.0
        self.last_drop = 0.0

    def _world(self, x, y):
        v = self.p.view
        return x / self.h * v, y / self.h * v

    def _add(self, x, y, strength):
        wx, wy = self._world(x, y)
        self.ripples.append([wx, wy, self.t, strength])
        self.ripples = self.ripples[-MAX_RIPPLES:]

    def touch(self, kind, x, y):
        if kind == "down":
            self._add(x, y, 1.0)
            self.last_drop = self.t
        elif kind == "move" and self.t - self.last_drop > 0.07:      # a wake behind a dragging finger
            self._add(x, y, 0.55)
            self.last_drop = self.t

    def update(self, dt):
        self.t += dt
        life = 3.0 / max(self.p.ripple_decay, 0.05) + 2
        self.ripples = [r for r in self.ripples if self.t - r[2] < life]

    def draw_gl(self, gl):
        p = self.p
        if self.target:
            self.target.bind()
        else:
            gl.screen()
        pr = self.prog
        pr.use()
        pr.set("u_time", self.t % 1000.0)
        flat = []
        for i in range(MAX_RIPPLES):
            if i < len(self.ripples):
                x, y, t0, s = self.ripples[i]
                flat += [x, y, self.t - t0, s]
            else:
                flat += [0.0, 0.0, 0.0, 0.0]
        pr.set_vec4_array("u_ripples", flat)
        pr.set("u_a", p.ambient, p.ripple, p.caustics, p.refraction)
        pr.set("u_b", p.tile_size, p.depth, p.glints, p.view)
        pr.set("u_c", p.ripple_speed, p.ripple_decay, p.ripple_wave, self.w / self.h)
        gl.draw_quad()
        if self.target:
            gl.screen()
            gl.blit(self.target.tex)

    def preview(self, step):
        for _ in range(30):
            self.update(step)
        for (x, y), delay in (((0.35, 0.3), 40), ((0.65, 0.62), 25), ((0.3, 0.78), 20)):
            self.touch("down", x * self.w, y * self.h)
            self.touch("up", x * self.w, y * self.h)
            for _ in range(delay):
                self.update(step)

    PREVIEW_AFTER = 10
