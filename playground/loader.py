"""Find and load scenes from the scenes/ folder.

Each scene is a folder:  scenes/<name>/scene.py   (plus optional preset.json,
README.md, preview.png). Scenes are loaded fresh from disk every time, so code
edits are picked up by "Restart scene" without stopping the program.
"""
import importlib.util
from pathlib import Path

SCENES_DIR = Path(__file__).resolve().parent.parent / "scenes"
RETIRED_DIR = SCENES_DIR / "_cpu"     # older CPU-drawn scenes: off the menu, still run by name


def scene_dirs(root=SCENES_DIR):
    return sorted(d for d in root.iterdir()
                  if d.is_dir() and (d / "scene.py").exists() and not d.name.startswith("_"))


def scene_dir(name):
    """The folder for a scene: scenes/<name>, or scenes/_cpu/<name> for a retired one."""
    d = SCENES_DIR / name
    return d if (d / "scene.py").exists() else RETIRED_DIR / name


def exists(name):
    return (scene_dir(name) / "scene.py").exists()


def load_module(name):
    path = scene_dir(name) / "scene.py"
    spec = importlib.util.spec_from_file_location(f"scenes_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def list_scenes(retired=False):
    """{name: title} for every scene on the menu (or, with retired=True, the retired ones)."""
    out = {}
    for d in scene_dirs(RETIRED_DIR if retired else SCENES_DIR):
        try:
            out[d.name] = getattr(load_module(d.name).Scene, "TITLE", "") or d.name
        except Exception as err:                      # still list broken scenes
            out[d.name] = f"{d.name} (failed to load: {err.__class__.__name__})"
    return out


def preset_path(name):
    return scene_dir(name) / "preset.json"
