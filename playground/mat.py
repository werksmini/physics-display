"""Small 3D maths helpers (numpy, row-major, column vectors: p' = M @ p)."""
import math

import numpy as np


def perspective(fov_y_deg, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fov_y_deg) / 2)
    m = np.zeros((4, 4))
    m[0, 0], m[1, 1] = f / aspect, f
    m[2, 2], m[2, 3] = (far + near) / (near - far), 2 * far * near / (near - far)
    m[3, 2] = -1.0
    return m


def look_at(eye, target, up=(0.0, 1.0, 0.0)):
    eye, target, up = (np.asarray(v, float) for v in (eye, target, up))
    f = target - eye
    f /= np.linalg.norm(f)
    s = np.cross(f, up)
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.eye(4)
    m[0, :3], m[1, :3], m[2, :3] = s, u, -f
    m[:3, 3] = -m[:3, :3] @ eye
    return m


def model(pos, rot, scale=1.0):
    m = np.eye(4)
    m[:3, :3] = rot * scale
    m[:3, 3] = pos
    return m


def axis_angle(axis, angle):
    """Rotation matrix about a unit axis (Rodrigues)."""
    axis = np.asarray(axis, float)
    n = np.linalg.norm(axis)
    if n < 1e-9 or abs(angle) < 1e-12:
        return np.eye(3)
    x, y, z = axis / n
    c, s, C = math.cos(angle), math.sin(angle), 1 - math.cos(angle)
    return np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
                     [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
                     [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


def orthonormalize(r):
    u, _, vt = np.linalg.svd(r)
    return u @ vt
