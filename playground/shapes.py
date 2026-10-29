"""Shared shape helpers for scenes."""
import numpy as np


def blade_shapes(x0, y0, L, a0, curve, theta, k=6):
    """Centreline points for many bending blades at once.

    Each blade starts at (x0, y0), has length L, a base angle a0 (radians from
    vertical, positive leans right), a rest curvature, and a wind bend theta.
    Bending grows toward the tip (t ** 1.5).
    Returns xs, ys with shape (n, k+1) and segment angles with shape (n, k).
    """
    t = (np.arange(k) + 0.5) / k
    ang = a0[:, None] + (curve + theta)[:, None] * t[None, :] ** 1.5
    seg = (L / k)[:, None]
    xs = np.concatenate([x0[:, None], x0[:, None] + np.cumsum(np.sin(ang) * seg, 1)], 1)
    ys = np.concatenate([y0[:, None], y0[:, None] - np.cumsum(np.cos(ang) * seg, 1)], 1)
    return xs, ys, ang


def tapered_polygon(xs, ys, ang, widths):
    """Outline points of a tapered blade around one centreline (lists for pygame)."""
    a = np.concatenate([ang, ang[-1:]])
    nx, ny = np.cos(a) * widths / 2, np.sin(a) * widths / 2
    left = list(zip((xs + nx).tolist(), (ys + ny).tolist()))
    right = list(zip((xs - nx).tolist(), (ys - ny).tolist()))
    return left + right[-2::-1]
