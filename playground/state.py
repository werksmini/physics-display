"""Remember settings between runs (last scene, landscape flip), so the Pi can
boot straight back into whatever was showing. Stored outside the repo in
~/.config/physics-display/state.json so `git pull` never touches it."""
import json
from pathlib import Path

PATH = Path.home() / ".config" / "physics-display" / "state.json"


def load():
    try:
        return json.loads(PATH.read_text())
    except (OSError, ValueError):
        return {}


def save(**changes):
    data = load()
    data.update(changes)
    try:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        PATH.write_text(json.dumps(data, indent=2) + "\n")
    except OSError:
        pass                                   # read-only or no home: just don't remember
