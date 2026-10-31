"""Illustrated title cards: each vignette's name, drawn like a sign, when it opens.

A scene opts in with a BRAND dict, e.g.

    BRAND = dict(name="Adult Swim", font="Pacifico", size=66,
                 fill=((255, 255, 255), (190, 236, 250)), outline=(20, 104, 150),
                 tagline="a quiet afternoon at the pool", art="waves")

- font: one of the bundled display fonts in playground/fonts (OFL-licensed)
- fill: a (top, bottom) colour gradient for the letters, or `letters`: one colour per letter
- outline / shadow: a thick outline and a soft drop shadow, like a painted sign
- art: a small illustration drawn with the card ("waves", "sun", "clothesline",
  "cubes", "pins", "lava")
- tilt: degrees, for a jaunty angle

title_card(brand) returns a transparent pygame Surface; the runner fades it in and out.
"""
import math
from pathlib import Path

import pygame

FONT_DIR = Path(__file__).parent / "fonts"
FONTS = {"Pacifico": "Pacifico.ttf", "Bungee": "Bungee.ttf", "Shrikhand": "Shrikhand.ttf",
         "Fredoka": "Fredoka-SemiBold.ttf"}
W, H = 460, 250


def font(name, size):
    try:
        return pygame.font.Font(str(FONT_DIR / FONTS.get(name, "Fredoka-SemiBold.ttf")), size)
    except (OSError, pygame.error):
        return pygame.font.Font(None, size)


def _gradient(size, top, bottom):
    w, h = size
    g = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        k = y / max(1, h - 1)
        g.fill(tuple(int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)) + (255,), (0, y, w, 1))
    return g


def _tinted(mask, color):
    s = mask.copy()
    s.fill(tuple(color[:3]) + (255,), special_flags=pygame.BLEND_RGBA_MULT)
    if len(color) > 3:
        s.fill((255, 255, 255, color[3]), special_flags=pygame.BLEND_RGBA_MULT)
    return s


def styled_text(text, f, fill=((255, 255, 255), (220, 220, 220)), letters=None,
                outline=(0, 0, 0), ow=5, shadow=(0, 0, 0, 120)):
    """Letters with a gradient (or per-letter colours), a thick outline and a drop shadow."""
    if letters:                                   # each letter its own colour
        parts, x = [], 0
        for i, ch in enumerate(text):
            img = f.render(ch, True, (255, 255, 255))
            parts.append((img, x, letters[i % len(letters)]))
            x = f.size(text[:i + 1])[0]
        mask = pygame.Surface((x, f.get_height()), pygame.SRCALPHA)
        for img, px, _ in parts:
            mask.blit(img, (px, 0))
    else:
        mask = f.render(text, True, (255, 255, 255))
    pad = ow + 8
    w, h = mask.get_width() + 2 * pad, mask.get_height() + 2 * pad
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    ring = pygame.Surface((w, h), pygame.SRCALPHA)        # the outline: the letters stamped in a circle
    for k in range(24):
        a = k / 24 * 2 * math.pi
        for r in (ow, ow * 0.5):
            ring.blit(mask, (pad + round(math.cos(a) * r), pad + round(math.sin(a) * r)))
    ring.blit(mask, (pad, pad))
    if shadow:                                    # soft drop shadow: the outline shape, blurred, offset
        sh = _tinted(ring, shadow)
        small = pygame.transform.smoothscale(sh, (max(1, w // 4), max(1, h // 4)))
        sh = pygame.transform.smoothscale(small, (w, h))
        out.blit(sh, (0, ow // 2 + 4))
    out.blit(_tinted(ring, outline), (0, 0))
    if letters:
        for img, px, col in parts:
            out.blit(_tinted(img, col), (pad + px, pad))
    else:
        body = _gradient(mask.get_size(), *fill)
        body.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        out.blit(body, (pad, pad))
    return out


# ---------------------------------------------------------------- illustrations
def _art_waves(s, c):
    cx, cy = c
    for k, (col, w) in enumerate((((120, 220, 240, 230), 5), ((255, 255, 255, 220), 4), ((70, 170, 210, 200), 4))):
        pts = [(x, cy + k * 13 + 7 * math.sin(x / 22 + k * 1.3)) for x in range(cx - 170, cx + 171, 6)]
        pygame.draw.lines(s, col, False, pts, w)
    pygame.draw.circle(s, (20, 104, 150), (cx + 150, cy - 18), 17)            # a yellow swim cap
    pygame.draw.circle(s, (246, 206, 60), (cx + 150, cy - 18), 14)
    pygame.draw.circle(s, (255, 244, 200), (cx + 145, cy - 23), 4)


def _art_sun(s, c):
    cx, cy = c
    for k in range(16):
        a = k / 16 * 2 * math.pi
        r0, r1 = 46, 70 if k % 2 == 0 else 60
        pygame.draw.line(s, (255, 196, 70, 220), (cx + math.cos(a) * r0, cy + math.sin(a) * r0),
                         (cx + math.cos(a) * r1, cy + math.sin(a) * r1), 6)
    pygame.draw.circle(s, (255, 150, 50), (cx, cy), 42)
    pygame.draw.circle(s, (255, 212, 90), (cx, cy), 36)


def _art_clothesline(s, c):
    cx, cy = c
    pts = [(x, cy + 0.0016 * (x - cx) ** 2 - 18) for x in range(cx - 190, cx + 191, 5)]
    pygame.draw.lines(s, (90, 70, 60), False, pts, 3)
    def line_y(x):
        return cy + 0.0016 * (x - cx) ** 2 - 18
    # a shirt, a sock and a towel, pegged on
    x = cx - 110
    y = line_y(x)
    shirt = [(x - 26, y), (x - 10, y), (x, y + 6), (x + 10, y), (x + 26, y), (x + 36, y + 14), (x + 24, y + 22),
             (x + 20, y + 16), (x + 20, y + 52), (x - 20, y + 52), (x - 20, y + 16), (x - 24, y + 22), (x - 36, y + 14)]
    pygame.draw.polygon(s, (120, 180, 230), shirt)
    pygame.draw.polygon(s, (60, 110, 160), shirt, 2)
    x = cx - 20
    y = line_y(x)
    pygame.draw.polygon(s, (240, 120, 110), [(x - 8, y), (x + 8, y), (x + 8, y + 30), (x + 22, y + 40), (x + 18, y + 48),
                                             (x - 6, y + 40), (x - 8, y + 34)])
    x = cx + 90
    y = line_y(x)
    pygame.draw.rect(s, (250, 238, 210), (x - 30, y, 60, 48), border_radius=3)
    for k in range(3):
        pygame.draw.line(s, (230, 170, 80), (x - 30, y + 30 + k * 6), (x + 29, y + 30 + k * 6), 2)
    for x in (cx - 128, cx - 92, cx - 20, cx + 66, cx + 114):                  # clothespins
        y = line_y(x)
        pygame.draw.rect(s, (200, 160, 110), (x - 3, y - 8, 6, 16), border_radius=2)


def _art_cubes(s, c):
    cx, cy = c

    def cube(x, y, k, col):
        top = [(x, y - k), (x + k * 0.87, y - k * 0.5), (x, y), (x - k * 0.87, y - k * 0.5)]
        left = [(x - k * 0.87, y - k * 0.5), (x, y), (x, y + k), (x - k * 0.87, y + k * 0.5)]
        right = [(x, y), (x + k * 0.87, y - k * 0.5), (x + k * 0.87, y + k * 0.5), (x, y + k)]
        for poly, f in ((left, 0.72), (right, 0.55), (top, 1.0)):
            pygame.draw.polygon(s, tuple(int(v * f) for v in col), poly)
            pygame.draw.polygon(s, (30, 30, 40), poly, 2)
    cube(cx - 120, cy + 6, 24, (220, 70, 64))
    cube(cx + 118, cy + 2, 28, (70, 120, 225))
    cube(cx + 150, cy - 30, 18, (240, 196, 60))


def _art_pins(s, c):
    cx, cy = c
    rect = pygame.Rect(0, 0, 360, 70)
    rect.center = (cx, cy)
    pygame.draw.rect(s, (30, 32, 38, 230), rect, border_radius=10)
    for j in range(5):
        for i in range(24):
            x, y = rect.x + 12 + i * 14.5, rect.y + 10 + j * 12.5
            raised = math.hypot((x - cx - 60) / 1.6, y - cy) < 26
            off = 4 if raised else 0
            pygame.draw.circle(s, (210, 214, 222) if raised else (150, 154, 162), (x, y + off), 4)


def _art_lava(s, c):
    cx, cy = c
    for (x, y, r, col) in ((cx - 150, cy - 10, 22, (255, 120, 40)), (cx - 124, cy + 14, 14, (255, 70, 90)),
                           (cx + 136, cy - 24, 18, (255, 160, 50)), (cx + 160, cy + 8, 26, (255, 90, 70)),
                           (cx + 120, cy + 20, 10, (255, 190, 80))):
        pygame.draw.circle(s, col + (230,), (x, y), r)
        pygame.draw.circle(s, (255, 240, 200, 160), (x - r // 3, y - r // 3), max(2, r // 4))


ART = {"waves": _art_waves, "sun": _art_sun, "clothesline": _art_clothesline, "cubes": _art_cubes,
       "pins": _art_pins, "lava": _art_lava}


def title_card(brand):
    """The scene's title card: illustration, title and tagline on a transparent Surface."""
    card = pygame.Surface((W, H), pygame.SRCALPHA)
    art = ART.get(brand.get("art"))
    title = styled_text(brand["name"], font(brand.get("font", "Fredoka"), brand.get("size", 60)),
                        fill=brand.get("fill", ((255, 255, 255), (220, 220, 220))),
                        letters=brand.get("letters"), outline=brand.get("outline", (30, 30, 40)),
                        ow=brand.get("outline_width", 5), shadow=brand.get("shadow", (0, 0, 0, 130)))
    tilt = brand.get("tilt", 0)
    if tilt:
        title = pygame.transform.rotozoom(title, tilt, 1.0)
    if title.get_width() > W - 10:
        k = (W - 10) / title.get_width()
        title = pygame.transform.smoothscale(title, (int(title.get_width() * k), int(title.get_height() * k)))
    ty = H // 2 - title.get_height() // 2 - 10
    if art:
        art(card, (W // 2, brand.get("art_y", ty + title.get_height() // 2)))
    card.blit(title, ((W - title.get_width()) // 2, ty))
    if brand.get("tagline"):
        tag = styled_text(brand["tagline"], font("Fredoka", 22), fill=((255, 255, 255), (235, 235, 235)),
                          outline=brand.get("outline", (30, 30, 40)), ow=3, shadow=None)
        card.blit(tag, ((W - tag.get_width()) // 2, ty + title.get_height() - 6))
    return card
