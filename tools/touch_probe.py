"""List input devices, show which one the games runner would use for touch, then
print finger positions (raw and scaled to the panel) until Ctrl+C.

    python tools/touch_probe.py              # 10.4" panel (1600x720), auto-detect
    python tools/touch_probe.py --small      # 2.8" panel (480x640, Goodix)

Useful when touch lands in the wrong place: tap the four corners and compare.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import evdev
except ImportError:
    sys.exit("evdev isn't installed (pip install evdev); this only runs on the Pi")

from playground.touch import EvdevTouch, _abs_range, _is_multitouch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--small", action="store_true", help="the 2.8\" DPI panel instead")
    args = ap.parse_args()
    w, h = (480, 640) if args.small else (1600, 720)

    print("Input devices:")
    for path in sorted(evdev.list_devices()):
        try:
            d = evdev.InputDevice(path)
        except OSError as err:
            print(f"  {path}: can't open ({err}); try sudo or add yourself to the 'input' group")
            continue
        mt = "multi-touch" if _is_multitouch(d) else ""
        print(f"  {path}: {d.name!r} {mt} range={_abs_range(d)}")

    touch = EvdevTouch.open(w, h) if args.small else EvdevTouch.open(w, h, name=None)
    if touch is None:
        sys.exit("No touch device found. Is the USB-C touch cable in the Pi's USB (data) port?")
    print(f"\nUsing {touch.dev.path} {touch.dev.name!r}: raw {touch.raw[0]}x{touch.raw[1]} -> panel {w}x{h}")
    print("Touch the screen (Ctrl+C to stop)...\n")
    try:
        while True:
            for kind, x, y in touch.events():
                print(f"{kind:4s}  x={x:7.1f}  y={y:6.1f}   fingers={len(touch.fingers)}")
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
