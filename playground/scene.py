"""Scene building blocks.

A scene is a module in playground/scenes/ that defines `class Scene(BaseScene)`:

    class Scene(BaseScene):
        TITLE = "My scene"
        PARAMS = [
            Param("speed", 1.0, 0, 5, 0.1, "Speed"),
            Param("count", 50, 1, 200, 1, "Count", reset=True),  # rebuilds scene
        ]
        def setup(self): ...              # build state (self.w, self.h, self.p)
        def update(self, dt): ...         # advance one fixed time step
        def draw(self, surf): ...         # paint the frame
        def touch(self, kind, x, y): ...  # kind: "down" | "move" | "up"

Read parameters as self.p.speed every frame; slider changes apply instantly.
"""
from dataclasses import dataclass


@dataclass
class Param:
    name: str
    default: float
    min: float
    max: float
    step: float
    label: str = ""
    reset: bool = False      # changing it rebuilds the scene (calls setup again)
    help: str = ""
    choices: tuple = ()      # named options: the value is the index (shown as buttons in the panel)

    def __post_init__(self):
        if self.choices:
            self.min, self.max, self.step = 0, len(self.choices) - 1, 1

    def clamp(self, v):
        v = max(self.min, min(self.max, float(v)))
        if self.step >= 1 and float(self.step).is_integer():
            v = round(v)
        return v

    def to_json(self):
        return {"name": self.name, "label": self.label or self.name,
                "min": self.min, "max": self.max, "step": self.step,
                "default": self.default, "reset": self.reset, "help": self.help,
                "choices": list(self.choices)}


class Values:
    """Live view of the current parameter values: self.p.speed etc."""

    def __init__(self, controller):
        object.__setattr__(self, "_c", controller)

    def __getattr__(self, name):
        try:
            return self._c.values[name]
        except KeyError:
            raise AttributeError(name) from None


class BaseScene:
    TITLE = ""
    PARAMS: list = []
    LANDSCAPE = False        # True: drawn 640x480 and rotated onto the portrait panel
    GPU = False              # True: draws with shaders in draw_gl(gl) instead of draw(surf)

    def __init__(self, w, h, params, gl=None):
        self.w, self.h, self.p, self.gl = w, h, params, gl
        self.setup()

    def setup(self):
        pass

    def update(self, dt):
        pass

    def draw(self, surf):
        pass

    def draw_gl(self, gl):
        """GPU scenes: draw to the screen with gl (see playground/gl.py)."""
        pass

    def touch(self, kind, x, y):
        pass

    # Optional, for multi-touch: define
    #     def fingers(self, fingers): ...
    # and the runner calls it every frame with {finger id: (x, y)} for every finger down.
