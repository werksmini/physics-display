"""Pin art: the desk toy with a bed of metal pins. Press and shapes rise out of it.

Like pressing your hand into the back of the board: the pins under your fingers
slide out toward you and stay there. Hold to press deeper, drag to draw a
groove, use several fingers at once. Double-tap to tip the board up so the pins
slide back, row by row.

Drawing (all in one fragment shader): we look at the board slightly from above,
so a pin pushed out by h appears lower on screen by h * parallax, with its
shaft running back up to its hole. For each pixel the shader checks the pin in
its own cell and the few pins above it whose heads or shafts could reach down
this far, and keeps the one nearest the viewer (the most pushed out). Pin
heights live in a small texture, one texel per pin, updated each frame.

Each head is shaded as a polished steel dome: a reflected sky / dark-room
gradient, a sharp highlight, and a shadow when the pins up and to the left
stick out further (the light comes from the upper left).
"""
import math

import numpy as np

from playground.scene import BaseScene, Param

FRAG = """
uniform sampler2D u_h;
uniform vec4 u_grid;     // spacing (px), cols, rows, parallax (px)
uniform vec4 u_look;     // head radius (fraction of spacing), shine, rows to search, time
uniform vec4 u_frame;    // screen w, h, grid offset x, y
varying vec2 uv;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }

float H(vec2 c) {
    if (c.x < 0.0 || c.y < 0.0 || c.x >= u_grid.y || c.y >= u_grid.z) return 0.0;
    return texture2D(u_h, (c + 0.5) / u_grid.yz).r;
}

void main() {
    vec2 px = uv * u_frame.xy;
    float s = u_grid.x, P = u_grid.w;
    vec2 off = u_frame.zw;
    vec2 q = (px - off) / s;
    float ci = floor(q.x);
    float r = s * u_look.x;
    float sw = s * 0.085;                       // shaft half-width

    float best = -1.0;                          // height of the nearest pin found
    float kind = 0.0;                           // 1 head, 2 shaft
    vec2 local = vec2(0.0);
    vec2 cell = vec2(0.0);
    float edge = 1.0;
    for (int k = 0; k < 8; k++) {
        if (float(k) > u_look.z) break;
        vec2 c = vec2(ci, floor(q.y) - float(k));
        if (c.y < 0.0) break;
        float h = H(c);
        if (h <= best) continue;
        vec2 base = (c + 0.5) * s + off;
        vec2 head = base + vec2(0.0, h * P);
        vec2 d = px - head;
        float dl = length(d);
        if (dl < r) {
            best = h; kind = 1.0; local = d / r; cell = c;
            edge = smoothstep(r, r - 0.9, dl);
        } else if (abs(px.x - base.x) < sw && px.y > base.y && px.y < head.y) {
            best = h; kind = 2.0; local = vec2((px.x - base.x) / sw, 0.0); cell = c;
        }
    }

    // the board: dark felt-black plastic with a hole under every pin
    vec2 own = vec2(ci, floor(q.y));
    vec2 hc = (own + 0.5) * s + off;
    float hole = smoothstep(s * 0.24, s * 0.18, length(px - hc));
    float boardShade = clamp(1.0 - 0.9 * max(H(own + vec2(-1.0, -1.0)), H(own + vec2(0.0, -1.0))), 0.35, 1.0);
    vec3 board = vec3(0.075, 0.078, 0.085) * (0.92 + 0.12 * hash(floor(px / 2.0)));
    board = mix(board, vec3(0.02), hole * 0.85) * boardShade;
    vec3 col = board;

    vec3 L = normalize(vec3(-0.55, -0.65, 0.75));        // light from the upper left, toward us
    if (kind > 0.5) {
        // shadow from taller neighbours up and to the left
        float hn = max(H(cell + vec2(-1.0, -1.0)), max(H(cell + vec2(0.0, -1.0)), H(cell + vec2(-1.0, 0.0))));
        float sh = 1.0 - clamp((hn - best) * 2.6, 0.0, 0.55);
        vec3 n;
        if (kind < 1.5) {
            float z = sqrt(max(0.0, 1.0 - dot(local, local)));
            n = normalize(vec3(local * 0.95, z));
        } else {
            n = normalize(vec3(local.x, 0.0, sqrt(max(0.0, 1.0 - local.x * local.x))));
        }
        vec3 R = 2.0 * n.z * n - vec3(0.0, 0.0, 1.0);    // reflected view ray
        float sky = smoothstep(0.35, -0.75, R.y);         // room light above, dark below
        vec3 env = mix(vec3(0.16, 0.165, 0.18), vec3(0.95, 0.96, 1.0), sky);
        env += vec3(0.25) * smoothstep(0.55, 0.95, -R.x * 0.7 - R.y * 0.7);   // window to the upper left
        float spec = pow(max(dot(R, L), 0.0), 70.0) * 1.6 * u_look.y;
        float diff = max(dot(n, L), 0.0);
        vec3 steel = vec3(0.70, 0.72, 0.76);
        vec3 pin = steel * (0.22 + 0.60 * diff) * 0.55 + env * 0.62 * u_look.y + vec3(spec);
        if (kind > 1.5) pin *= 0.85;                      // shafts are thin and partly shaded
        pin *= sh * (0.80 + 0.35 * best);                 // nearer pins catch more light
        col = mix(col, pin, kind < 1.5 ? edge : 1.0);
    }

    col += (hash(gl_FragCoord.xy + fract(u_look.w) * 31.0) - 0.5) / 80.0;   // dither
    gl_FragColor = vec4(col, 1.0);
}
"""


class Scene(BaseScene):
    TITLE = "Pin art (GPU)"
    GPU = True
    PARAMS = [
        Param("finger", 30, 10, 70, 1, "Fingertip size", help="Pixels. Bigger = a broader press."),
        Param("press", 0.55, 0.1, 1, 0.01, "Press depth", help="How far a quick touch pushes the pins out."),
        Param("deepen", 0.6, 0, 2, 0.05, "Hold to deepen", help="How fast holding still pushes further."),
        Param("parallax", 26, 0, 40, 1, "Pin length", help="Pixels a fully pushed pin sticks out on screen."),
        Param("shine", 1.0, 0, 2, 0.05, "Polish"),
        Param("spacing", 10, 7, 20, 1, "Pin spacing", reset=True, help="Pixels between pins."),
        Param("fall", 1.0, 0.2, 3, 0.05, "Reset speed", help="How fast pins slide back after a double-tap."),
    ]

    def setup(self):
        s = int(self.p.spacing)
        self.cols = self.w // s
        self.rows = self.h // s + 1
        self.off = ((self.w - self.cols * s) / 2, (self.h - (self.rows - 1) * s) / 2 - s * 0.5)
        self.hgt = np.zeros((self.rows, self.cols), np.float32)
        self.vel = np.zeros_like(self.hgt)            # used while pins slide back
        self.delay = np.zeros_like(self.hgt)
        self.reset_t = None
        gx, gy = np.meshgrid(np.arange(self.cols), np.arange(self.rows))
        self.cx = (gx + 0.5) * s + self.off[0]
        self.cy = (gy + 0.5) * s + self.off[1]
        self.prog = self.gl.program(FRAG)
        self.tex = self.gl.texture(self.cols, self.rows, None, smooth=False)
        self.buf = np.zeros((self.rows, self.cols, 4), np.uint8)
        self.buf[..., 3] = 255
        self.dirty = True
        self.t = 0.0
        self.held = {}                                 # finger id -> [x, y, seconds held still]
        self.last_tap = (-9.0, 0.0, 0.0)
        self.touch_start = {}

    # ------------------------------------------------------------- input
    def fingers(self, fingers):
        for k in list(self.held):
            if k not in fingers:                        # lifted: was it a quick tap?
                t0, x0, y0 = self.touch_start.pop(k, (0, 0, 0))
                x, y, _ = self.held.pop(k)
                if self.t - t0 < 0.25 and math.hypot(x - x0, y - y0) < 12:
                    lt, lx, ly = self.last_tap
                    if self.t - lt < 0.4 and math.hypot(x - lx, y - ly) < 60:
                        self._tip()
                        self.last_tap = (-9.0, 0.0, 0.0)
                    else:
                        self.last_tap = (self.t, x, y)
        for k, (x, y) in fingers.items():
            if k not in self.held:
                self.held[k] = [x, y, 0.0]
                self.touch_start[k] = (self.t, x, y)
            else:
                h = self.held[k]
                if math.hypot(x - h[0], y - h[1]) > 3:
                    h[2] *= 0.7                         # moving: deepening eases off
                h[0], h[1] = x, y

    def _tip(self):
        """Tip the board up: pins slide back, top rows first."""
        self.reset_t = self.t
        rng = np.random.default_rng()
        rows = np.arange(self.rows)[:, None] / self.rows
        self.delay = (rows * 0.6 + rng.uniform(0, 0.12, self.hgt.shape)).astype(np.float32) / self.p.fall
        self.vel[:] = 0

    # ------------------------------------------------------------- update
    def update(self, dt):
        self.t += dt
        p = self.p
        if self.reset_t is not None:                    # sliding back
            age = self.t - self.reset_t
            going = (age > self.delay) & (self.hgt > 0)
            self.vel[going] += 6.0 * p.fall * dt
            self.hgt[going] -= self.vel[going] * dt
            np.maximum(self.hgt, 0, out=self.hgt)
            self.dirty = True
            if not (self.hgt > 0).any():
                self.reset_t = None
            return
        if not self.held:
            return
        R = p.finger
        lift = p.parallax * 0.55                        # press slightly above the fingertip so
        for h in self.held.values():                    # the risen heads land under it
            h[2] += dt
            x, y, still = h
            depth = min(1.0, p.press + p.deepen * max(0.0, still - 0.15) * 0.5)
            yy = y - lift * depth
            r0, r1 = max(0, int((yy - R - self.off[1]) / p.spacing) - 1), int((yy + R - self.off[1]) / p.spacing) + 2
            c0, c1 = max(0, int((x - R - self.off[0]) / p.spacing) - 1), int((x + R - self.off[0]) / p.spacing) + 2
            if r1 <= 0 or c1 <= 0:
                continue
            dx = self.cx[r0:r1, c0:c1] - x
            dy = self.cy[r0:r1, c0:c1] - yy
            d2 = (dx * dx + dy * dy) / (R * R)
            target = depth * np.sqrt(np.clip(1.0 - d2, 0, 1))      # a rounded fingertip
            cur = self.hgt[r0:r1, c0:c1]
            np.maximum(cur, cur + (target - cur) * min(1.0, dt * 18), out=cur)
            self.dirty = True

    # ------------------------------------------------------------- draw
    def draw_gl(self, gl):
        p = self.p
        if self.dirty:
            self.buf[..., 0] = np.clip(self.hgt * 255, 0, 255).astype(np.uint8)
            self.tex.update(self.buf.tobytes())
            self.dirty = False
        gl.screen()
        pr = self.prog
        pr.use()
        self.tex.bind(0)
        pr.set_int("u_h", 0)
        s = float(p.spacing)
        r = 0.44
        reach = math.ceil((p.parallax + r * s) / s)
        pr.set("u_grid", s, self.cols, self.rows, p.parallax)
        pr.set("u_look", r, p.shine, min(7, reach), self.t % 100.0)
        pr.set("u_frame", self.w, self.h, self.off[0], self.off[1])
        gl.draw_quad()

    # ------------------------------------------------------------- preview
    def preview(self, step):
        """A hand pressed into the board: palm, then each finger drawn from tip to knuckle."""
        vals = self.p._c.values
        R0 = vals["finger"]

        def stroke(a, b, size, n=14):
            vals["finger"] = size
            for j in range(n + 1):
                f = j / n
                self.fingers({1: (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)})
                self.update(step)
            self.fingers({})
            self.update(step)

        stroke((235, 440), (240, 470), 78, 30)                    # palm
        for tip, base in (((118, 330), (165, 420)), ((168, 190), (200, 340)), ((235, 160), (238, 330)),
                          ((300, 185), (282, 335)), ((352, 255), (318, 360))):
            stroke(tip, base, 26)
        vals["finger"] = R0
        for _ in range(5):
            self.update(step)

    PREVIEW_AFTER = 0
