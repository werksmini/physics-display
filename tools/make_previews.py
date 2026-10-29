"""Render a preview.png for every scene and rebuild the gallery (scenes/README.md).

    python tools/make_previews.py            # all scenes
    python tools/make_previews.py meadow     # just one

Each scene runs headless for a few seconds with its saved preset (or defaults).
A scene can define PREVIEW_TOUCH = (x_frac, y_frac) to hold a finger there
during the capture, e.g. to show wind.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pygame  # noqa: E402

from playground.control import Controller  # noqa: E402
from playground.loader import SCENES_DIR, list_scenes, load_module, preset_path  # noqa: E402
from playground.scene import Values  # noqa: E402

W, H = 480, 640
STEP = 1 / 60


def first_line(doc):
    return (doc or "").strip().splitlines()[0].rstrip(".") if doc else ""


def render(name):
    mod = load_module(name)
    ctrl = Controller({name: name}, preset_path)
    ctrl.load_scene(name, mod.Scene)
    scene = mod.Scene(W, H, Values(ctrl))
    for _ in range(120):
        scene.update(STEP)
    touch = getattr(mod.Scene, "PREVIEW_TOUCH", None)
    if touch:
        scene.touch("down", touch[0] * W, touch[1] * H)
    for _ in range(int(getattr(mod.Scene, "PREVIEW_AFTER", 150))):
        scene.update(STEP)
    surf = pygame.Surface((W, H))
    scene.draw(surf)
    out = SCENES_DIR / name / "preview.png"
    pygame.image.save(pygame.transform.smoothscale(surf, (W // 2, H // 2)), str(out))
    return mod


def gallery(mods):
    rows = []
    for name, mod in mods.items():
        title = getattr(mod.Scene, "TITLE", name)
        rows.append(f"| ![{name}]({name}/preview.png) | **[{title}]({name}/README.md)**<br>"
                    f"`python run.py {name}`<br>{first_line(mod.__doc__)} |")
    text = ("# Scenes\n\nEach folder is one scene: `scene.py` (the code), `README.md` (what it is "
            "and how to play), `preset.json` (saved slider settings, if any) and `preview.png`.\n\n"
            "Regenerate previews and this page with `python tools/make_previews.py`.\n\n"
            "| Preview | Scene |\n|---|---|\n" + "\n".join(rows) + "\n")
    (SCENES_DIR / "README.md").write_text(text)


def main():
    pygame.init()
    pygame.display.set_mode((1, 1))
    names = sys.argv[1:] or list(list_scenes())
    for n in names:
        render(n)
        print(f"preview: scenes/{n}/preview.png")
    gallery({n: load_module(n) for n in list_scenes()})
    print("gallery: scenes/README.md")


if __name__ == "__main__":
    main()
