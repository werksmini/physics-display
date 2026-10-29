"""Draw pygame frames straight to the Linux framebuffer (/dev/fb0).

Fallback for when SDL's kmsdrm video driver can't start (e.g. "EGL not
initialized" on Pi OS Lite). Render into an ordinary pygame Surface, then call
fb.show(surface) once per frame.
"""
import fcntl
import os
import struct

import pygame

FBIOGET_VSCREENINFO = 0x4600


class FrameBuffer:
    def __init__(self, dev="/dev/fb0"):
        name = os.path.basename(dev)
        self.f = open(dev, "r+b", buffering=0)
        info = fcntl.ioctl(self.f, FBIOGET_VSCREENINFO, bytes(160))
        self.w, self.h, _, _, _, _, self.bpp = struct.unpack_from("7I", info)
        with open(f"/sys/class/graphics/{name}/stride") as s:
            self.stride = int(s.read())
        if self.bpp == 16:
            masks = (0xF800, 0x07E0, 0x001F, 0)          # RGB565
        elif self.bpp == 32:
            masks = (0xFF0000, 0x00FF00, 0x0000FF, 0)    # XRGB8888
        else:
            raise RuntimeError(f"unsupported framebuffer depth: {self.bpp} bpp")
        self.conv = pygame.Surface((self.w, self.h), 0, self.bpp, masks)
        self.row_bytes = self.w * self.bpp // 8

    @property
    def size(self):
        return self.w, self.h

    def show(self, surface):
        self.conv.blit(surface, (0, 0))
        data = self.conv.get_buffer().raw
        pitch = self.conv.get_pitch()
        self.f.seek(0)
        if pitch == self.stride:
            self.f.write(data[: self.stride * self.h])
        else:                                          # copy row by row
            for y in range(self.h):
                self.f.seek(y * self.stride)
                self.f.write(data[y * pitch : y * pitch + self.row_bytes])

    def clear(self):
        self.f.seek(0)
        self.f.write(bytes(self.stride * self.h))

    def close(self):
        self.f.close()
