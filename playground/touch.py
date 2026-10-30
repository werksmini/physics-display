"""Touch input from the Waveshare 2.8" DPI panel (Goodix controller, via evdev).

Measured 2026-10-28 on Pi OS Trixie: the controller reports X 0..640 left->right
and Y 0..480 top->bottom on the 480x640 portrait display (same direction,
wrong scale), so coordinates are rescaled here.

events() returns a list of (kind, x, y) with kind "down", "move" or "up" for the
first finger. The controller also reports up to 5 fingers using the Linux
multi-touch protocol (numbered slots, each with a tracking id and position);
after events(), `fingers` holds {tracking id: (x, y)} for every finger down.
"""
try:
    import evdev
    from evdev import ecodes
except ImportError:            # laptop / evdev not installed
    evdev = None

DEVICE_NAME = "Goodix"
MT_CODES = set()
if evdev is not None:
    MT_CODES = {ecodes.ABS_MT_SLOT, ecodes.ABS_MT_TRACKING_ID,
                ecodes.ABS_MT_POSITION_X, ecodes.ABS_MT_POSITION_Y}
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
        self.slot = 0
        self.slots = {}                  # slot -> [tracking id, raw x, raw y]
        self.fingers = {}                # tracking id -> (x, y) in screen pixels

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
                if ev.type == ecodes.EV_ABS and ev.code in MT_CODES:
                    if ev.code == ecodes.ABS_MT_SLOT:
                        self.slot = ev.value
                    else:
                        sl = self.slots.setdefault(self.slot, [-1, 0, 0])
                        if ev.code == ecodes.ABS_MT_TRACKING_ID:
                            sl[0] = ev.value
                        elif ev.code == ecodes.ABS_MT_POSITION_X:
                            sl[1] = ev.value
                        elif ev.code == ecodes.ABS_MT_POSITION_Y:
                            sl[2] = ev.value
                    continue
                if ev.type == ecodes.EV_ABS:
                    if ev.code == ecodes.ABS_X:
                        self.x, self.moved = ev.value, True
                    elif ev.code == ecodes.ABS_Y:
                        self.y, self.moved = ev.value, True
                elif ev.type == ecodes.EV_KEY and ev.code == ecodes.BTN_TOUCH:
                    self.pending = "down" if ev.value else "up"
                elif ev.type == ecodes.EV_SYN:
                    self.fingers = {sl[0]: (sl[1] * self.sx, sl[2] * self.sy)
                                    for sl in self.slots.values() if sl[0] >= 0}
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
