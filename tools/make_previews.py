"""Render a preview.png for every scene and rebuild the gallery (scenes/README.md).

    python tools/make_previews.py            # all scenes
    python tools/make_previews.py meadow     # just one

Each scene runs headless for a few seconds with its saved preset (or defaults).
A scene can define PREVIEW_TOUCH = (x_frac, y_frac) to hold a finger there
during the capture, e.g. to show wind, or a preview(step) method to script it.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "offscreen")      # offscreen also gives GPU scenes a GL context
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pygame  # noqa: E402

from playground.control import Controller  # noqa: E402
from playground.loader import SCENES_DIR, list_scenes, load_module, preset_path  # noqa: E402
from playground.scene import Values  # noqa: E402

W, H = 480, 640
STEP = 1 / 60


def first_line(doc):
    return (doc or "").strip().splitlines()[0].rstrip(".") if doc else ""


GL = None


def gl_context():
    """A hidden OpenGL ES 2.0 context for GPU scenes (software-rendered if needed)."""
    global GL
    if GL is None:
        from playground import gl as glmod
        glmod.request_es2_context()
        pygame.display.set_mode((W, H), pygame.OPENGL)
        GL = glmod.GL(W, H)
    return GL


def render(name):
    mod = load_module(name)
    ctrl = Controller({name: name}, preset_path)
    ctrl.load_scene(name, mod.Scene)
    w, h = (H, W) if getattr(mod.Scene, "LANDSCAPE", False) else (W, H)
    gpu = getattr(mod.Scene, "GPU", False)
    scene = mod.Scene(w, h, Values(ctrl), gl=gl_context() if gpu else None)
    if hasattr(scene, "preview"):            # a scene can script its own preview
        scene.preview(STEP)
        touch = None
        mod.Scene.PREVIEW_AFTER = getattr(mod.Scene, "PREVIEW_AFTER", 0)
    else:
        for _ in range(120):
            scene.update(STEP)
        touch = getattr(mod.Scene, "PREVIEW_TOUCH", None)
    if touch:
        scene.touch("down", touch[0] * w, touch[1] * h)
    for _ in range(int(getattr(mod.Scene, "PREVIEW_AFTER", 150))):
        scene.update(STEP)
    if gpu:
        GL.screen()
        scene.draw_gl(GL)
        surf = GL.read_pixels()
    else:
        surf = pygame.Surface((w, h))
        scene.draw(surf)
    out = SCENES_DIR / name / "preview.png"
    pygame.image.save(pygame.transform.smoothscale(surf, (w // 2, h // 2)), str(out))
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
    names = sys.argv[1:] or list(list_scenes())
    for n in names:
        render(n)
        print(f"preview: scenes/{n}/preview.png")
    gallery({n: load_module(n) for n in list_scenes()})
    print("gallery: scenes/README.md")


if __name__ == "__main__":
    main()
