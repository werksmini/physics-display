"""Touch input from the Waveshare 2.8" DPI panel (Goodix controller, via evdev).

Measured 2026-10-28 on Pi OS Trixie: the controller reports X 0..640 left->right
and Y 0..480 top->bottom on the 480x640 portrait display (same direction,
wrong scale), so coordinates are rescaled here.

events() returns a list of (kind, x, y) with kind "down", "move" or "up".
"""
try:
    import evdev
    from evdev import ecodes
except ImportError:            # laptop / evdev not installed
    evdev = None

DEVICE_NAME = "Goodix"
RAW_W, RAW_H = 640, 480


class EvdevTouch:
    def __init__(self, dev, screen_w, screen_h):
        self.dev = dev
        self.sx = screen_w / RAW_W
        self.sy = screen_h / RAW_H
        self.x = self.y = 0
        self.down = False
        self.moved = False
        self.pending = None

    @classmethod
    def open(cls, screen_w, screen_h):
        if evdev is None:
            return None
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
            except OSError:
                continue
            if DEVICE_NAME in dev.name:
                return cls(dev, screen_w, screen_h)
        return None

    def events(self):
        out = []
        try:
            while True:
                ev = self.dev.read_one()
                if ev is None:
                    break
                if ev.type == ecodes.EV_ABS:
                    if ev.code == ecodes.ABS_X:
                        self.x, self.moved = ev.value, True
                    elif ev.code == ecodes.ABS_Y:
                        self.y, self.moved = ev.value, True
                elif ev.type == ecodes.EV_KEY and ev.code == ecodes.BTN_TOUCH:
                    self.pending = "down" if ev.value else "up"
                elif ev.type == ecodes.EV_SYN:
                    # X/Y arrive in the same report as BTN_TOUCH, so act on SYN
                    pos = (self.x * self.sx, self.y * self.sy)
                    if self.pending == "down":
                        self.down = True
                        out.append(("down", *pos))
                    elif self.pending == "up":
                        self.down = False
                        out.append(("up", *pos))
                    elif self.moved and self.down:
                        out.append(("move", *pos))
                    self.pending, self.moved = None, False
        except (BlockingIOError, OSError):
            pass
        return out
