"""Shared helpers for scenes."""
import numpy as np


class ValueNoise2D:
    """Smooth random values in 0..1 over 2D space (vectorised value noise).

    noise(u, v) accepts numpy arrays; one unit in u/v is one noise 'cell'.
    Slide u/v over time to make the pattern drift.
    """

    def __init__(self, seed=0, size=256):
        self.g = np.random.default_rng(seed).random((size, size)).astype(np.float32)
        self.m = size - 1

    def __call__(self, u, v):
        iu, iv = np.floor(u).astype(np.int64), np.floor(v).astype(np.int64)
        fu, fv = u - iu, v - iv
        su, sv = fu * fu * (3 - 2 * fu), fv * fv * (3 - 2 * fv)    # smoothstep
        iu0, iv0, iu1, iv1 = iu & self.m, iv & self.m, (iu + 1) & self.m, (iv + 1) & self.m
        a, b = self.g[iv0, iu0], self.g[iv0, iu1]
        c, d = self.g[iv1, iu0], self.g[iv1, iu1]
        return a + (b - a) * su + (c - a) * sv + (a - b - c + d) * su * sv


def lerp_color(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))
