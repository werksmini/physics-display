"""Parameter state shared between the render loop and the web control panel,
plus the tiny HTTP server that serves the panel (standard library only)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
PANEL_HTML = HERE / "panel.html"


class Controller:
    def __init__(self, scenes, preset_path):
        self.lock = threading.Lock()
        self.scenes = scenes                  # {name: title}
        self.preset_path = preset_path        # function: scene name -> Path
        self.scene_name = None
        self.schema = []                      # list of Param
        self.values = {}
        self.show_fps = True
        self.pending_scene = None
        self.reset_requested = False
        self.last_error = ""

    # --- called from the render loop -------------------------------------
    def load_scene(self, name, scene_cls):
        values = {p.name: p.default for p in scene_cls.PARAMS}
        preset = self.preset_path(name)
        if preset.exists():
            try:
                saved = json.loads(preset.read_text())
                for p in scene_cls.PARAMS:
                    if p.name in saved:
                        values[p.name] = p.clamp(saved[p.name])
            except (OSError, ValueError):
                pass
        with self.lock:
            self.scene_name = name
            self.schema = list(scene_cls.PARAMS)
            self.values = values

    def take_pending_scene(self):
        with self.lock:
            name, self.pending_scene = self.pending_scene, None
            return name

    def take_reset(self):
        with self.lock:
            r, self.reset_requested = self.reset_requested, False
            return r

    # --- called from the web server --------------------------------------
    def state(self):
        with self.lock:
            return {
                "scene": self.scene_name,
                "scenes": [{"name": n, "title": t} for n, t in self.scenes.items()],
                "params": [dict(p.to_json(), value=self.values.get(p.name))
                           for p in self.schema],
                "show_fps": self.show_fps,
                "error": self.last_error,
            }

    def set_params(self, updates):
        with self.lock:
            by_name = {p.name: p for p in self.schema}
            for k, v in updates.items():
                p = by_name.get(k)
                if p is None:
                    continue
                v = p.clamp(v)
                if self.values.get(k) != v:
                    self.values = dict(self.values, **{k: v})
                    if p.reset:
                        self.reset_requested = True

    def request_scene(self, name):
        if name in self.scenes:
            with self.lock:
                self.pending_scene = name

    def request_reset(self):
        with self.lock:
            self.reset_requested = True

    def restore_defaults(self):
        with self.lock:
            self.values = {p.name: p.default for p in self.schema}
            self.reset_requested = True

    def save_preset(self):
        with self.lock:
            path = self.preset_path(self.scene_name)
            path.write_text(json.dumps(self.values, indent=2) + "\n")
            return str(path)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):          # keep the terminal quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n))
        except ValueError:
            return {}

    def do_GET(self):
        c = self.server.controller
        if self.path in ("/", "/index.html"):
            self._send(200, PANEL_HTML.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._send(200, json.dumps(c.state()))
        else:
            self._send(404, '{"error":"not found"}')

    def do_POST(self):
        c = self.server.controller
        body = self._json_body()
        if self.path == "/api/params":
            c.set_params(body)
        elif self.path == "/api/scene":
            c.request_scene(body.get("name", ""))
        elif self.path == "/api/reset":
            c.request_reset()
        elif self.path == "/api/defaults":
            c.restore_defaults()
        elif self.path == "/api/save":
            self._send(200, json.dumps({"saved": c.save_preset()}))
            return
        elif self.path == "/api/fps":
            c.show_fps = bool(body.get("on", True))
        else:
            self._send(404, '{"error":"not found"}')
            return
        self._send(200, '{"ok":true}')


def start_server(controller, port):
    srv = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    srv.daemon_threads = True
    srv.controller = controller
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
