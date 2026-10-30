"""A tiny OpenGL ES 2.0 layer, called straight through ctypes.

The Pi Zero 2 W's GPU (VideoCore IV) speaks OpenGL ES 2.0, which rules out
libraries that need newer OpenGL. The ES 2.0 functions are exported directly by
libGLESv2, so we load it and declare just the calls we use.

Write shaders in GLSL ES 1.00 (the ES 2.0 shading language):
- start fragment shaders with the PRECISION block below (or use `program()`,
  which adds it), no `#version` line needed
- no `texture()`, use `texture2D()`; no `in/out`, use `attribute/varying`
- loops need constant bounds; keep uniform arrays small (the Pi has ~16 vec4
  of fragment uniforms to play with)
- non-power-of-two textures must use CLAMP_TO_EDGE and no mipmaps (we do that)
"""
import ctypes
import ctypes.util

import pygame

# ---------------------------------------------------------------- constants
GL_FLOAT = 0x1406
GL_UNSIGNED_BYTE = 0x1401
GL_TRIANGLE_STRIP = 0x0005
GL_ARRAY_BUFFER = 0x8892
GL_STATIC_DRAW = 0x88E4
GL_FRAGMENT_SHADER = 0x8B30
GL_VERTEX_SHADER = 0x8B31
GL_COMPILE_STATUS = 0x8B81
GL_LINK_STATUS = 0x8B82
GL_INFO_LOG_LENGTH = 0x8B84
GL_TEXTURE_2D = 0x0DE1
GL_TEXTURE0 = 0x84C0
GL_TEXTURE_MIN_FILTER = 0x2801
GL_TEXTURE_MAG_FILTER = 0x2800
GL_TEXTURE_WRAP_S = 0x2802
GL_TEXTURE_WRAP_T = 0x2803
GL_LINEAR = 0x2601
GL_NEAREST = 0x2600
GL_CLAMP_TO_EDGE = 0x812F
GL_RGBA = 0x1908
GL_RGB = 0x1907
GL_FRAMEBUFFER = 0x8D40
GL_COLOR_ATTACHMENT0 = 0x8CE0
GL_FRAMEBUFFER_COMPLETE = 0x8CD5
GL_COLOR_BUFFER_BIT = 0x4000
GL_BLEND = 0x0BE2
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_UNPACK_ALIGNMENT = 0x0CF5
GL_PACK_ALIGNMENT = 0x0D05
GL_VENDOR, GL_RENDERER, GL_VERSION = 0x1F00, 0x1F01, 0x1F02
GL_MAX_FRAGMENT_UNIFORM_VECTORS = 0x8DFD

PRECISION = """
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
"""

# vertex shader for a full-screen quad: gives `uv` (0..1, top-left origin)
QUAD_VS = """
attribute vec2 a_pos;
varying vec2 uv;
void main() {
    uv = vec2(a_pos.x * 0.5 + 0.5, 0.5 - a_pos.y * 0.5);
    gl_Position = vec4(a_pos, 0.0, 1.0);
}
"""

_lib = None
c_uint_p = ctypes.POINTER(ctypes.c_uint)


def _load():
    global _lib
    if _lib is not None:
        return _lib
    names = ["libGLESv2.so.2", "libGLESv2.so", ctypes.util.find_library("GLESv2")]
    for n in names:
        if not n:
            continue
        try:
            _lib = ctypes.CDLL(n)
            break
        except OSError:
            continue
    if _lib is None:
        raise OSError("OpenGL ES 2.0 library (libGLESv2) not found")
    sig = {
        "glGetString": (ctypes.c_char_p, [ctypes.c_uint]),
        "glGetError": (ctypes.c_uint, []),
        "glGetIntegerv": (None, [ctypes.c_uint, ctypes.POINTER(ctypes.c_int)]),
        "glViewport": (None, [ctypes.c_int] * 4),
        "glClearColor": (None, [ctypes.c_float] * 4),
        "glClear": (None, [ctypes.c_uint]),
        "glEnable": (None, [ctypes.c_uint]),
        "glDisable": (None, [ctypes.c_uint]),
        "glBlendFunc": (None, [ctypes.c_uint, ctypes.c_uint]),
        "glPixelStorei": (None, [ctypes.c_uint, ctypes.c_int]),
        "glCreateShader": (ctypes.c_uint, [ctypes.c_uint]),
        "glShaderSource": (None, [ctypes.c_uint, ctypes.c_int, ctypes.POINTER(ctypes.c_char_p), ctypes.c_void_p]),
        "glCompileShader": (None, [ctypes.c_uint]),
        "glGetShaderiv": (None, [ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_int)]),
        "glGetShaderInfoLog": (None, [ctypes.c_uint, ctypes.c_int, ctypes.c_void_p, ctypes.c_char_p]),
        "glDeleteShader": (None, [ctypes.c_uint]),
        "glCreateProgram": (ctypes.c_uint, []),
        "glAttachShader": (None, [ctypes.c_uint, ctypes.c_uint]),
        "glBindAttribLocation": (None, [ctypes.c_uint, ctypes.c_uint, ctypes.c_char_p]),
        "glLinkProgram": (None, [ctypes.c_uint]),
        "glGetProgramiv": (None, [ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_int)]),
        "glGetProgramInfoLog": (None, [ctypes.c_uint, ctypes.c_int, ctypes.c_void_p, ctypes.c_char_p]),
        "glUseProgram": (None, [ctypes.c_uint]),
        "glGetUniformLocation": (ctypes.c_int, [ctypes.c_uint, ctypes.c_char_p]),
        "glUniform1i": (None, [ctypes.c_int, ctypes.c_int]),
        "glUniform1f": (None, [ctypes.c_int, ctypes.c_float]),
        "glUniform2f": (None, [ctypes.c_int, ctypes.c_float, ctypes.c_float]),
        "glUniform3f": (None, [ctypes.c_int] + [ctypes.c_float] * 3),
        "glUniform4f": (None, [ctypes.c_int] + [ctypes.c_float] * 4),
        "glUniform4fv": (None, [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_float)]),
        "glGenBuffers": (None, [ctypes.c_int, c_uint_p]),
        "glBindBuffer": (None, [ctypes.c_uint, ctypes.c_uint]),
        "glBufferData": (None, [ctypes.c_uint, ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint]),
        "glVertexAttribPointer": (None, [ctypes.c_uint, ctypes.c_int, ctypes.c_uint, ctypes.c_ubyte, ctypes.c_int, ctypes.c_void_p]),
        "glEnableVertexAttribArray": (None, [ctypes.c_uint]),
        "glDrawArrays": (None, [ctypes.c_uint, ctypes.c_int, ctypes.c_int]),
        "glGenTextures": (None, [ctypes.c_int, c_uint_p]),
        "glDeleteTextures": (None, [ctypes.c_int, c_uint_p]),
        "glBindTexture": (None, [ctypes.c_uint, ctypes.c_uint]),
        "glActiveTexture": (None, [ctypes.c_uint]),
        "glTexParameteri": (None, [ctypes.c_uint, ctypes.c_uint, ctypes.c_int]),
        "glTexImage2D": (None, [ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]),
        "glTexSubImage2D": (None, [ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]),
        "glGenFramebuffers": (None, [ctypes.c_int, c_uint_p]),
        "glBindFramebuffer": (None, [ctypes.c_uint, ctypes.c_uint]),
        "glFramebufferTexture2D": (None, [ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_int]),
        "glCheckFramebufferStatus": (ctypes.c_uint, [ctypes.c_uint]),
        "glReadPixels": (None, [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]),
    }
    for name, (res, args) in sig.items():
        f = getattr(_lib, name)
        f.restype, f.argtypes = res, args
    return _lib


def request_es2_context():
    """Ask SDL for an OpenGL ES 2.0 context. Call before pygame.display.set_mode."""
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, 0x0004)    # ES profile
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 2)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 0)
    pygame.display.gl_set_attribute(pygame.GL_DOUBLEBUFFER, 1)


class GL:
    """Thin helpers over the raw calls. `gl.raw` is the ctypes library."""

    def __init__(self, width, height):
        self.raw = _load()
        self.width, self.height = width, height
        r = self.raw
        r.glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        r.glPixelStorei(GL_PACK_ALIGNMENT, 1)
        quad = (ctypes.c_float * 8)(-1, -1, 1, -1, -1, 1, 1, 1)
        buf = ctypes.c_uint()
        r.glGenBuffers(1, ctypes.byref(buf))
        r.glBindBuffer(GL_ARRAY_BUFFER, buf)
        r.glBufferData(GL_ARRAY_BUFFER, ctypes.sizeof(quad), quad, GL_STATIC_DRAW)
        self.quad_buf = buf.value
        self._blit = self.program("""
            uniform sampler2D tex;
            uniform int rot;          // 0 = as is, 1 = canvas turned counter-clockwise, 2 = clockwise
            uniform float alpha;
            uniform float flip;       // 1.0 for render-target textures (stored bottom row first)
            varying vec2 uv;
            void main() {
                vec2 t = uv;
                if (rot == 1) t = vec2(1.0 - uv.y, uv.x);
                else if (rot == 2) t = vec2(uv.y, 1.0 - uv.x);
                if (flip > 0.5) t.y = 1.0 - t.y;
                vec4 c = texture2D(tex, t);
                gl_FragColor = vec4(c.rgb, c.a * alpha);
            }""")
        self._tex_cache = {}

    def info(self):
        r = self.raw
        n = ctypes.c_int()
        r.glGetIntegerv(GL_MAX_FRAGMENT_UNIFORM_VECTORS, ctypes.byref(n))
        return {"vendor": r.glGetString(GL_VENDOR).decode(), "renderer": r.glGetString(GL_RENDERER).decode(),
                "version": r.glGetString(GL_VERSION).decode(), "max_frag_uniform_vec4": n.value}

    # ------------------------------------------------------------ shaders
    def _compile(self, kind, src):
        r = self.raw
        sh = r.glCreateShader(kind)
        data = ctypes.c_char_p(src.encode())
        r.glShaderSource(sh, 1, ctypes.byref(data), None)
        r.glCompileShader(sh)
        ok = ctypes.c_int()
        r.glGetShaderiv(sh, GL_COMPILE_STATUS, ctypes.byref(ok))
        if not ok.value:
            log = ctypes.create_string_buffer(4096)
            r.glGetShaderInfoLog(sh, 4096, None, log)
            raise RuntimeError(("vertex" if kind == GL_VERTEX_SHADER else "fragment")
                               + " shader failed to compile:\n" + log.value.decode(errors="replace"))
        return sh

    def program(self, frag_src, vert_src=QUAD_VS):
        """Compile a program. The fragment shader gets the precision block added."""
        r = self.raw
        vs = self._compile(GL_VERTEX_SHADER, vert_src)
        fs = self._compile(GL_FRAGMENT_SHADER, PRECISION + frag_src)
        prog = r.glCreateProgram()
        r.glAttachShader(prog, vs)
        r.glAttachShader(prog, fs)
        r.glBindAttribLocation(prog, 0, b"a_pos")
        r.glLinkProgram(prog)
        ok = ctypes.c_int()
        r.glGetProgramiv(prog, GL_LINK_STATUS, ctypes.byref(ok))
        if not ok.value:
            log = ctypes.create_string_buffer(4096)
            r.glGetProgramInfoLog(prog, 4096, None, log)
            raise RuntimeError("shader program failed to link:\n" + log.value.decode(errors="replace"))
        r.glDeleteShader(vs)
        r.glDeleteShader(fs)
        return Program(self, prog)

    # ------------------------------------------------------------ drawing
    def draw_quad(self):
        r = self.raw
        r.glBindBuffer(GL_ARRAY_BUFFER, self.quad_buf)
        r.glVertexAttribPointer(0, 2, GL_FLOAT, 0, 0, None)
        r.glEnableVertexAttribArray(0)
        r.glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)

    def viewport(self, x, y, w, h):
        self.raw.glViewport(x, y, w, h)

    def screen(self):
        """Draw to the display from here on."""
        self.raw.glBindFramebuffer(GL_FRAMEBUFFER, 0)
        self.raw.glViewport(0, 0, self.width, self.height)

    def clear(self, r=0.0, g=0.0, b=0.0):
        self.raw.glClearColor(r, g, b, 1.0)
        self.raw.glClear(GL_COLOR_BUFFER_BIT)

    # ------------------------------------------------------------ textures
    def texture(self, w, h, data=None, smooth=True):
        r = self.raw
        t = ctypes.c_uint()
        r.glGenTextures(1, ctypes.byref(t))
        r.glBindTexture(GL_TEXTURE_2D, t)
        f = GL_LINEAR if smooth else GL_NEAREST
        for p, v in ((GL_TEXTURE_MIN_FILTER, f), (GL_TEXTURE_MAG_FILTER, f),
                     (GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE), (GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)):
            r.glTexParameteri(GL_TEXTURE_2D, p, v)
        r.glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
        return Texture(self, t.value, w, h)

    def surface_texture(self, surf, key=None, smooth=True):
        """Upload a pygame Surface as a texture (re-using the texture for the same key)."""
        w, h = surf.get_size()
        data = pygame.image.tobytes(surf, "RGBA")
        tex = self._tex_cache.get(key) if key else None
        if tex is None or (tex.w, tex.h) != (w, h):
            tex = self.texture(w, h, data, smooth)
            if key:
                self._tex_cache[key] = tex
        else:
            tex.update(data)
        return tex

    def blit(self, tex, rot=0, alpha=1.0, blend=False):
        """Draw a texture over the whole current viewport (rot: see the blit shader)."""
        r = self.raw
        if blend:
            r.glEnable(GL_BLEND)
            r.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        p = self._blit
        p.use()
        tex.bind(0)
        p.set("tex", 0)
        p.set_int("rot", rot)
        p.set("alpha", alpha)
        p.set("flip", 1.0 if tex.flipped else 0.0)
        self.draw_quad()
        if blend:
            r.glDisable(GL_BLEND)

    def blit_at(self, tex, x, y, rot=0, alpha=1.0):
        """Draw a texture at screen pixel (x, y), top-left origin, with blending."""
        w, h = (tex.h, tex.w) if rot else (tex.w, tex.h)
        self.raw.glViewport(int(x), int(self.height - y - h), int(w), int(h))
        self.blit(tex, rot, alpha, blend=True)
        self.raw.glViewport(0, 0, self.width, self.height)

    def target(self, w, h, smooth=True):
        """An off-screen render target (draw into it, then use .tex)."""
        tex = self.texture(w, h, None, smooth)
        r = self.raw
        fb = ctypes.c_uint()
        r.glGenFramebuffers(1, ctypes.byref(fb))
        r.glBindFramebuffer(GL_FRAMEBUFFER, fb)
        r.glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex.id, 0)
        status = r.glCheckFramebufferStatus(GL_FRAMEBUFFER)
        r.glBindFramebuffer(GL_FRAMEBUFFER, 0)
        if status != GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError(f"render target {w}x{h} incomplete (0x{status:x})")
        tex.flipped = True
        return Target(self, fb.value, tex)

    def read_pixels(self):
        """The current framebuffer as a pygame Surface (for screenshots/tests)."""
        w, h = self.width, self.height
        buf = (ctypes.c_ubyte * (w * h * 4))()
        self.raw.glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, buf)
        img = pygame.image.frombuffer(bytes(buf), (w, h), "RGBA")
        return pygame.transform.flip(img, False, True)


class Program:
    def __init__(self, gl, pid):
        self.gl, self.id = gl, pid
        self._loc = {}

    def use(self):
        self.gl.raw.glUseProgram(self.id)

    def loc(self, name):
        if name not in self._loc:
            self._loc[name] = self.gl.raw.glGetUniformLocation(self.id, name.encode())
        return self._loc[name]

    def set(self, name, *v):
        """Set a float uniform: 1-4 values."""
        loc = self.loc(name)
        if loc < 0:
            return
        r = self.gl.raw
        (None, r.glUniform1f, r.glUniform2f, r.glUniform3f, r.glUniform4f)[len(v)](loc, *map(float, v))

    def set_int(self, name, v):
        loc = self.loc(name)
        if loc >= 0:
            self.gl.raw.glUniform1i(loc, int(v))

    def set_vec4_array(self, name, values):
        """values: flat list of 4*n floats."""
        loc = self.loc(name)
        if loc >= 0:
            arr = (ctypes.c_float * len(values))(*values)
            self.gl.raw.glUniform4fv(loc, len(values) // 4, arr)


class Texture:
    flipped = False          # True for render-target textures

    def __init__(self, gl, tid, w, h):
        self.gl, self.id, self.w, self.h = gl, tid, w, h

    def bind(self, unit=0):
        self.gl.raw.glActiveTexture(GL_TEXTURE0 + unit)
        self.gl.raw.glBindTexture(GL_TEXTURE_2D, self.id)

    def update(self, data):
        self.bind(0)
        self.gl.raw.glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, self.w, self.h, GL_RGBA, GL_UNSIGNED_BYTE, data)


class Target:
    def __init__(self, gl, fb, tex):
        self.gl, self.fb, self.tex = gl, fb, tex

    def bind(self):
        self.gl.raw.glBindFramebuffer(GL_FRAMEBUFFER, self.fb)
        self.gl.raw.glViewport(0, 0, self.tex.w, self.tex.h)
