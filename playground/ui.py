"""On-screen controls for touch games: buttons, hold buttons, sliders and a thumbstick.

Everything works in canvas pixels and is multi-touch: each finger that lands on a
control belongs to that control until it lifts, so you can hold THRUST with one
thumb while steering with the other.

    self.ui = Controls()
    self.fire = self.ui.add(Button((20, 300, 90, 44), "FIRE", on_tap=self.shoot))
    self.gas = self.ui.add(HoldButton((680, 260, 100, 80), "THRUST"))
    self.zoom = self.ui.add(Slider((300, 320, 200, 28), 0.5, 2.0, 1.0, "Zoom"))
    self.stick = self.ui.add(Stick((90, 270), 50))

    def fingers(self, fingers):           # {finger id: (x, y)}, every frame
        free = self.ui.feed(fingers)      # fingers not on a control, for the game itself
    def update(self, dt):
        if self.gas.held: ...
        dx, dy = self.stick.vec           # each -1..1
    def draw(self, surf):
        ...
        self.ui.draw(surf)                # controls on top

Controls only know about fingers (not "down"/"up" events), so give them the runner's
`fingers()` call. In a laptop window the mouse is finger 0.
"""
import math

import pygame

INK = (245, 245, 240)
FACE = (20, 22, 28, 150)
FACE_DOWN = (255, 255, 255, 80)
EDGE_COLOR = (255, 255, 255, 110)

_fonts = {}


def font(size, bold=True):
    """A display font (Fredoka from playground/fonts), cached by size."""
    key = (size, bold)
    if key not in _fonts:
        from pathlib import Path
        path = Path(__file__).resolve().parent / "fonts" / "Fredoka-SemiBold.ttf"
        try:
            _fonts[key] = pygame.font.Font(str(path), size)
        except (FileNotFoundError, OSError):
            _fonts[key] = pygame.font.Font(None, int(size * 1.3))
    return _fonts[key]


def rounded(surf, color, rect, radius, width=0):
    """Rounded rect that respects alpha in color (pygame.draw ignores it on opaque surfaces)."""
    rect = pygame.Rect(rect)
    if len(color) == 4 and color[3] < 255:
        tmp = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(tmp, color, tmp.get_rect(), width, border_radius=radius)
        surf.blit(tmp, rect.topleft)
    else:
        pygame.draw.rect(surf, color[:3], rect, width, border_radius=radius)


class Control:
    def __init__(self, rect):
        self.rect = pygame.Rect(rect)
        self.owners = set()              # finger ids on this control
        self.visible = True
        self.enabled = True

    def hit(self, x, y):
        return self.rect.inflate(12, 12).collidepoint(x, y)     # a little forgiving

    # called by Controls
    def press(self, fid, x, y):
        pass

    def drag(self, fid, x, y):
        pass

    def release(self, fid, x, y):
        pass

    def tick(self, dt):
        pass

    def draw(self, surf):
        pass


class Button(Control):
    """Taps: on_tap() runs when a finger lifts while still over the button."""

    def __init__(self, rect, label, on_tap=None, color=None):
        super().__init__(rect)
        self.label, self.on_tap, self.color = label, on_tap, color
        self.inside = False

    def press(self, fid, x, y):
        self.inside = True

    def drag(self, fid, x, y):
        self.inside = self.hit(x, y)

    def release(self, fid, x, y):
        if self.inside and self.on_tap:
            self.on_tap()
        self.inside = False

    @property
    def down(self):
        return bool(self.owners) and self.inside

    def draw(self, surf):
        r = self.rect
        face = FACE_DOWN if self.down else (self.color + (170,) if self.color else FACE)
        rounded(surf, face, r, min(14, r.h // 3))
        rounded(surf, EDGE_COLOR, r, min(14, r.h // 3), 2)
        if self.label:
            img = font(max(12, min(26, r.h // 2))).render(self.label, True, INK)
            surf.blit(img, img.get_rect(center=r.center))


class HoldButton(Button):
    """`.held` is True while any finger is on it (thrust, brake, fire-while-held).
    With hold_secs set, `on_hold()` runs once after holding that long (a ring fills
    meanwhile) - handy for "hold to quit" so it can't happen by accident."""

    def __init__(self, rect, label, color=None, hold_secs=0.0, on_hold=None):
        super().__init__(rect, label, None, color)
        self.hold_secs, self.on_hold = hold_secs, on_hold
        self.t = 0.0

    @property
    def held(self):
        return bool(self.owners)

    def press(self, fid, x, y):
        self.inside = True

    def drag(self, fid, x, y):
        pass                                 # sliding off doesn't let go: thumbs wander

    def release(self, fid, x, y):
        if not self.owners - {fid}:
            self.t = 0.0

    def tick(self, dt):
        if self.held and self.hold_secs:
            before = self.t
            self.t += dt
            if before < self.hold_secs <= self.t and self.on_hold:
                self.on_hold()

    @property
    def progress(self):
        return min(1.0, self.t / self.hold_secs) if self.hold_secs else 0.0

    def draw(self, surf):
        r = self.rect
        face = FACE_DOWN if self.held else (self.color + (170,) if self.color else FACE)
        rounded(surf, face, r, min(14, r.h // 3))
        rounded(surf, EDGE_COLOR, r, min(14, r.h // 3), 2)
        if self.hold_secs and self.t > 0:
            rad = max(r.w, r.h) // 2 + 6
            box = pygame.Rect(0, 0, rad * 2, rad * 2)
            box.center = r.center
            pygame.draw.arc(surf, INK, box, math.pi / 2, math.pi / 2 + 2 * math.pi * self.progress, 3)
        if self.label:
            img = font(max(12, min(26, r.h // 2))).render(self.label, True, INK)
            surf.blit(img, img.get_rect(center=r.center))


class Slider(Control):
    """Horizontal slider; drag anywhere on it. `.value` between lo and hi."""

    def __init__(self, rect, lo, hi, value, label="", on_change=None, fmt="{:.1f}"):
        super().__init__(rect)
        self.lo, self.hi, self.value = lo, hi, value
        self.label, self.on_change, self.fmt = label, on_change, fmt

    def _set_from(self, x):
        t = (x - self.rect.x) / max(1, self.rect.w)
        v = self.lo + max(0.0, min(1.0, t)) * (self.hi - self.lo)
        if v != self.value:
            self.value = v
            if self.on_change:
                self.on_change(v)

    def press(self, fid, x, y):
        self._set_from(x)

    def drag(self, fid, x, y):
        self._set_from(x)

    def draw(self, surf):
        r = self.rect
        rounded(surf, FACE, r, r.h // 2)
        t = (self.value - self.lo) / ((self.hi - self.lo) or 1)
        fill = pygame.Rect(r.x, r.y, max(r.h, int(r.w * t)), r.h)
        rounded(surf, FACE_DOWN, fill, r.h // 2)
        rounded(surf, EDGE_COLOR, r, r.h // 2, 2)
        knob = (r.x + int(r.w * t), r.centery)
        pygame.draw.circle(surf, INK, knob, r.h // 2 + 3)
        text = f"{self.label}  {self.fmt.format(self.value)}" if self.label else self.fmt.format(self.value)
        img = font(max(11, r.h // 2)).render(text, True, INK)
        surf.blit(img, img.get_rect(midbottom=(r.centerx, r.y - 2)))


class Stick(Control):
    """Virtual thumbstick. `.vec` is (x, y), each -1..1, (0, 0) when let go.
    floating=True: the stick re-centres wherever your thumb lands inside its area."""

    def __init__(self, center, radius, floating=True):
        cx, cy = center
        super().__init__((cx - radius * 2, cy - radius * 2, radius * 4, radius * 4))
        self.home = (cx, cy)
        self.center = (cx, cy)
        self.radius = radius
        self.floating = floating
        self.knob = (cx, cy)

    @property
    def vec(self):
        return ((self.knob[0] - self.center[0]) / self.radius,
                (self.knob[1] - self.center[1]) / self.radius)

    def press(self, fid, x, y):
        if self.floating:
            self.center = (x, y)
        self.drag(fid, x, y)

    def drag(self, fid, x, y):
        dx, dy = x - self.center[0], y - self.center[1]
        d = math.hypot(dx, dy)
        if d > self.radius:
            dx, dy = dx / d * self.radius, dy / d * self.radius
        self.knob = (self.center[0] + dx, self.center[1] + dy)

    def release(self, fid, x, y):
        self.center = self.knob = self.home

    def draw(self, surf):
        c = [int(v) for v in self.center]
        ring = pygame.Surface((self.radius * 2 + 8,) * 2, pygame.SRCALPHA)
        rc = (self.radius + 4,) * 2
        pygame.draw.circle(ring, FACE, rc, self.radius + 2)
        pygame.draw.circle(ring, EDGE_COLOR, rc, self.radius + 2, 2)
        surf.blit(ring, (c[0] - rc[0], c[1] - rc[1]))
        pygame.draw.circle(surf, INK if self.owners else (200, 200, 200),
                           [int(v) for v in self.knob], max(8, self.radius // 2))


class Controls:
    """Owns a set of controls and hands each finger to the control it landed on."""

    def __init__(self):
        self.items = []
        self.owner = {}                  # finger id -> control (or None: belongs to the game)
        self.last = {}                   # finger id -> last position

    def add(self, control):
        self.items.append(control)
        return control

    def feed(self, fingers):
        """Call every frame with {finger id: (x, y)}. Returns the fingers that aren't
        on a control, for the game to use."""
        free = {}
        for fid, (x, y) in fingers.items():
            if fid not in self.owner:                     # a new finger: who gets it?
                hit = None
                for c in reversed(self.items):            # topmost first
                    if c.visible and c.enabled and c.hit(x, y):
                        hit = c
                        break
                self.owner[fid] = hit
                if hit:
                    hit.owners.add(fid)
                    hit.press(fid, x, y)
            elif self.owner[fid] and self.last.get(fid) != (x, y):
                self.owner[fid].drag(fid, x, y)
            if self.owner[fid] is None:
                free[fid] = (x, y)
            self.last[fid] = (x, y)
        for fid in [f for f in self.owner if f not in fingers]:    # lifted
            c = self.owner.pop(fid)
            x, y = self.last.pop(fid, (0, 0))
            if c:
                c.release(fid, x, y)
                c.owners.discard(fid)
        return free

    def tick(self, dt):
        for c in self.items:
            c.tick(dt)

    def draw(self, surf):
        for c in self.items:
            if c.visible:
                c.draw(surf)
