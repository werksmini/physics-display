"""Read taps straight from the Waveshare 2.8" DPI touchscreen (Goodix, evdev).

Measured on 2026-10-28 (Pi OS Trixie): touch reports X 0..640 left->right and
Y 0..480 top->bottom while the display is 480x640 portrait. Same direction,
wrong scale, so we rescale here.

Usage:
    touch = TouchScreen.open(screen_w, screen_h)   # None if not found
    for x, y in touch.taps():                      # call once per frame
        ...
"""
try:
    import evdev
    from evdev import ecodes
except ImportError:            # laptop / no evdev installed
    evdev = None

DEVICE_NAME = "Goodix"         # matches "11-005d Goodix Capacitive TouchScreen"
RAW_W, RAW_H = 640, 480        # range the controller actually reports


class TouchScreen:
    def __init__(self, dev, screen_w, screen_h):
        self.dev = dev
        self.sx = screen_w / RAW_W
        self.sy = screen_h / RAW_H
        self.x = self.y = 0
        self.pending_down = False

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

    def taps(self):
        """Return screen-space (x, y) for each new finger-down since last call."""
        out = []
        try:
            while True:
                ev = self.dev.read_one()
                if ev is None:
                    break
                if ev.type == ecodes.EV_ABS:
                    if ev.code == ecodes.ABS_X:
                        self.x = ev.value
                    elif ev.code == ecodes.ABS_Y:
                        self.y = ev.value
                elif ev.type == ecodes.EV_KEY and ev.code == ecodes.BTN_TOUCH:
                    if ev.value == 1:
                        self.pending_down = True
                elif ev.type == ecodes.EV_SYN and self.pending_down:
                    # X/Y arrive after BTN_TOUCH in the same report, so emit on SYN
                    out.append((self.x * self.sx, self.y * self.sy))
                    self.pending_down = False
        except (BlockingIOError, OSError):
            pass
        return out
