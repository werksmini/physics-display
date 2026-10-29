"""Find and load scenes from the scenes/ folder.

Each scene is a folder:  scenes/<name>/scene.py   (plus optional preset.json,
README.md, preview.png). Scenes are loaded fresh from disk every time, so code
edits are picked up by "Restart scene" without stopping the program.
"""
import importlib.util
from pathlib import Path

SCENES_DIR = Path(__file__).resolve().parent.parent / "scenes"


def scene_dirs():
    return sorted(d for d in SCENES_DIR.iterdir()
                  if d.is_dir() and (d / "scene.py").exists() and not d.name.startswith("_"))


def load_module(name):
    path = SCENES_DIR / name / "scene.py"
    spec = importlib.util.spec_from_file_location(f"scenes_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def list_scenes():
    """{name: title} for every scene folder."""
    out = {}
    for d in scene_dirs():
        try:
            out[d.name] = getattr(load_module(d.name).Scene, "TITLE", "") or d.name
        except Exception as err:                      # still list broken scenes
            out[d.name] = f"{d.name} (failed to load: {err.__class__.__name__})"
    return out


def preset_path(name):
    return SCENES_DIR / name / "preset.json"
