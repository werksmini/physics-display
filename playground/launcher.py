"""The home screen: a scrolling grid of vignettes. Tap one to open it.

Shown at startup (when run.py is given no scene) and whenever you hold the top
edge of the screen. The runner builds it like any scene, under the name "home";
when a tile is tapped it sets `self.launch` to that scene's name and the runner
switches to it.

On the GPU it draws a slow, dim water shimmer behind the tiles; without the GPU
it falls back to a plain gradient.
"""
import math

import pygame

from playground.loader import scene_dir
from playground.scene import BaseScene

HOME = "home"
PAD = 16
HEADER = 78
LABEL = 34

BG_FS = """
uniform float u_time;
uniform vec2 u_size;
varying vec2 uv;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
void main() {
    vec2 p = uv * u_size / 160.0;
    vec2 a = p * 2.2;
    float c = 0.0;
    for (int i = 0; i < 2; i++) {
        float fi = float(i);
        a += vec2(sin(a.y * 1.3 + u_time * 0.25 + fi * 1.7), cos(a.x * 1.1 - u_time * 0.18 + fi * 2.3)) * 0.75;
        c += 1.0 / (1.0 + 30.0 * abs(sin(a.x) * sin(a.y)));
    }
    vec3 top = vec3(0.07, 0.16, 0.20), low = vec3(0.03, 0.07, 0.10);
    vec3 col = mix(top, low, uv.y) + vec3(0.10, 0.22, 0.24) * c * 0.22;
    col += (hash(gl_FragCoord.xy + fract(u_time) * 61.0) - 0.5) / 80.0;
    gl_FragColor = vec4(col, 1.0);
}
"""


def short_title(title):
    """'Sunlit pool (GPU)' -> 'Sunlit pool'."""
    return title.split(" (")[0]


class Launcher(BaseScene):
    TITLE = "Home"
    PARAMS = []

    def __init__(self, w, h, params, gl=None, scenes=None, last=None):
        self.scenes = dict(scenes or {})          # {name: title}, in menu order
        self.last = last
        super().__init__(w, h, params, gl)

    def setup(self):
        self.t = 0.0
        self.scroll = 0.0
        self.vel = 0.0
        self.launch = None
        self.press = None                         # (x, y, time, scroll at press)
        self.dragging = False
        self.pressed_tile = None
        self.flash = None                         # (name, time) tile tapped, launching shortly
        cols = 2
        self.tw = (self.w - PAD * (cols + 1)) // cols
        self.th = self.tw                         # square crop of each preview
        self.tiles = []                           # (name, rect in content coords)
        for i, name in enumerate(self.scenes):
            r, c = divmod(i, cols)
            x = PAD + c * (self.tw + PAD)
            y = HEADER + r * (self.th + LABEL + PAD)
            self.tiles.append((name, pygame.Rect(x, y, self.tw, self.th + LABEL)))
        rows = math.ceil(len(self.tiles) / cols)
        self.content_h = max(self.h, HEADER + rows * (self.th + LABEL + PAD) + PAD)
        self.content = self._paint()
        self.bg = self.gl.program(BG_FS) if self.gl else None
        self.tex = self.gl.surface_texture(self.content, "launcher_content") if self.gl else None
        self.hl = None

    # ------------------------------------------------------------- painting
    def _paint(self):
        surf = pygame.Surface((self.w, self.content_h), pygame.SRCALPHA)
        title = pygame.font.Font(None, 46).render("Vignettes", True, (236, 240, 238))
        sub = pygame.font.Font(None, 22).render("tap to open   ·   hold the top edge to come back",
                                                True, (150, 172, 176))
        surf.blit(title, (PAD + 2, 22))
        surf.blit(sub, (PAD + 3, 54))
        font = pygame.font.Font(None, 26)
        for name, rect in self.tiles:
            card = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(card, (255, 255, 255, 26), card.get_rect(), border_radius=12)
            img = self._preview(name)
            if img:
                mask = pygame.Surface((self.tw, self.th), pygame.SRCALPHA)
                pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=12)
                img = img.convert_alpha() if pygame.display.get_surface() else img
                pic = pygame.Surface((self.tw, self.th), pygame.SRCALPHA)
                pic.blit(img, (0, 0))
                pic.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
                card.blit(pic, (0, 0))
            label = font.render(short_title(self.scenes[name]), True, (232, 238, 236))
            card.blit(label, (10, self.th + (LABEL - label.get_height()) // 2 + 1))
            if name == self.last:                         # where you were last time
                pygame.draw.circle(card, (246, 206, 60), (rect.w - 14, self.th + LABEL // 2), 5)
            surf.blit(card, rect.topleft)
        return surf

    def _preview(self, name):
        path = scene_dir(name) / "preview.png"
        try:
            img = pygame.image.load(str(path))
        except (pygame.error, FileNotFoundError):
            return None
        w, h = img.get_size()
        k = self.tw / w                                    # fill the width, crop the middle
        img = pygame.transform.smoothscale(img, (self.tw, max(self.th, int(h * k))))
        top = (img.get_height() - self.th) // 2
        return img.subsurface((0, top, self.tw, self.th)).copy()

    # ------------------------------------------------------------- input
    def _tile_at(self, x, y):
        cy = y + self.scroll
        for name, rect in self.tiles:
            if rect.collidepoint(x, cy):
                return name, rect
        return None

    def touch(self, kind, x, y):
        if kind == "down":
            self.press = (x, y, self.t, self.scroll)
            self.dragging = False
            self.vel = 0.0
            hit = self._tile_at(x, y)
            self.pressed_tile = hit[0] if hit else None
            self.last_y = y
        elif kind == "move" and self.press:
            if abs(y - self.press[1]) > 12 or abs(x - self.press[0]) > 12:
                self.dragging = True
                self.pressed_tile = None
            if self.dragging:
                dy = y - self.last_y
                self.scroll = self._clamp(self.scroll - dy)
                self.vel = -dy * 60 * 0.6 + self.vel * 0.4
            self.last_y = y
        elif kind == "up" and self.press:
            if not self.dragging and self.t - self.press[2] < 0.6:
                hit = self._tile_at(x, y)
                if hit and self.flash is None:
                    self.flash = (hit[0], self.t)
            self.press = None
            self.pressed_tile = None

    def _clamp(self, s):
        return max(0.0, min(self.content_h - self.h, s))

    def update(self, dt):
        self.t += dt
        if self.press is None and abs(self.vel) > 1:          # coast after a flick
            self.scroll = self._clamp(self.scroll + self.vel * dt)
            self.vel *= math.exp(-dt * 4)
        if self.flash and self.t - self.flash[1] > 0.18:
            self.launch = self.flash[0]

    # ------------------------------------------------------------- drawing
    def _highlight_rect(self):
        name = self.flash[0] if self.flash else self.pressed_tile
        if not name:
            return None
        rect = dict(self.tiles)[name]
        return rect.move(0, -round(self.scroll))

    def draw_gl(self, gl):
        self.bg.use()
        self.bg.set("u_time", self.t % 1000.0)
        self.bg.set("u_size", self.w, self.h)
        gl.draw_quad()
        gl.blit_at(self.tex, 0, -round(self.scroll))
        r = self._highlight_rect()
        if r:
            if self.hl is None:
                s = pygame.Surface((self.tw, self.th + LABEL), pygame.SRCALPHA)
                pygame.draw.rect(s, (255, 255, 255, 70), s.get_rect(), border_radius=12)
                pygame.draw.rect(s, (255, 255, 255, 200), s.get_rect(), 3, border_radius=12)
                self.hl = gl.surface_texture(s, "launcher_hl")
            gl.blit_at(self.hl, r.x, r.y)

    def draw(self, surf):
        if not hasattr(self, "_bg"):
            self._bg = pygame.Surface((self.w, self.h))
            for y in range(self.h):
                k = y / self.h
                self._bg.fill((int(18 - 10 * k), int(41 - 23 * k), int(51 - 25 * k)), (0, y, self.w, 1))
        surf.blit(self._bg, (0, 0))
        surf.blit(self.content, (0, -round(self.scroll)))
        r = self._highlight_rect()
        if r:
            pygame.draw.rect(surf, (255, 255, 255), r, 3, border_radius=12)
