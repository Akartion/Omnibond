#!/usr/bin/env python3
"""
OmniBond - Web Studio UI HTTP & REST API Request Handler.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
import os
import subprocess
import threading
import time
import urllib.parse
from typing import Dict, TYPE_CHECKING

from config import IS_WINDOWS, filedialog, tk
from web_ui_html import WEB_UI_HTML

if TYPE_CHECKING:
    from engine import OmniBondEngine


def _open_native_exe_file_dialog() -> str:
    """Opens a native OS file picker dialog to select an executable (.exe) file."""
    if IS_WINDOWS:
        try:
            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$f = New-Object System.Windows.Forms.OpenFileDialog; "
                "$f.Title = 'Select Application Executable'; "
                "$f.Filter = 'Executable Programs (*.exe)|*.exe|All Files (*.*)|*.*'; "
                "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $f.FileName }"
            )
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-STA", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=120.0,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            chosen = (proc.stdout or "").strip()
            if chosen and os.path.isfile(chosen):
                return chosen
            if proc.returncode == 0:
                return ""
        except Exception:
            pass

    if tk is not None and filedialog is not None:
        try:
            temp_root = tk.Tk()
            temp_root.withdraw()
            temp_root.attributes("-topmost", True)
            try:
                chosen = filedialog.askopenfilename(
                    parent=temp_root,
                    title="Select Application Executable",
                    filetypes=[("Executable Programs", "*.exe"), ("All Files", "*.*")],
                )
            finally:
                temp_root.destroy()
            return (chosen or "").strip()
        except Exception:
            pass
    return ""


class WebUIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, payload: Dict, status: int = 200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        engine: "OmniBondEngine" = self.server.engine  # type: ignore
        if self.path == "/" or self.path.startswith("/index"):
            body = WEB_UI_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/api/state"):
            engine._dashboard_seen = True
            engine._last_dashboard_activity = time.monotonic()
            self._send_json(engine.get_state_snapshot())
        elif self.path.startswith("/api/processes"):
            detailed = engine.scan_and_sync_processes()
            self._send_json({
                "processes": [p.exe_name for p in detailed],
                "detailed": [p.__dict__ for p in detailed],
            })
        else:
            self.send_error(404)

    def do_POST(self):
        engine: "OmniBondEngine" = self.server.engine  # type: ignore
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            data = {}

        if self.path == "/api/rules":
            engine.routing_mgr.set_rule(data.get("app_name", ""), data.get("rule", "AUTO"), explicit_add=True)
            self._send_json({"ok": True})
        elif self.path == "/api/browse_exe":
            chosen_path = _open_native_exe_file_dialog()
            if not chosen_path:
                self._send_json({"ok": False, "cancelled": True})
                return
            exe_key = engine.process_mapper.register_custom_exe_path(chosen_path)
            app_name = exe_key or os.path.basename(chosen_path).lower()
            self._send_json({
                "ok": True,
                "app_name": app_name,
                "location": os.path.abspath(chosen_path),
            })
        elif self.path == "/api/favorite":
            app_name = str(data.get("app_name", "")).strip()
            if not app_name:
                self._send_json({"ok": False, "message": "An application name is required."}, 400)
                return
            ok = engine.routing_mgr.set_favorite(app_name, bool(data.get("favorite", True)))
            self._send_json(
                {"ok": ok, "message": "" if ok else "Could not persist the favorite setting."},
                200 if ok else 500,
            )
        elif self.path == "/api/app_location":
            app_name = str(data.get("app_name", "")).strip()
            location = str(data.get("location", "")).strip()
            key = engine.process_mapper.register_custom_app_location(app_name, location)
            if not key:
                self._send_json({"ok": False, "message": "Choose an existing executable or installation folder."}, 400)
                return
            engine.routing_mgr.set_rule(key, engine.routing_mgr.get_rule(key), explicit_add=True)
            self._send_json({"ok": True, "app_name": key, "location": os.path.abspath(location)})
        elif self.path == "/api/locate_app":
            ok, msg = engine.process_mapper.locate_app(
                data.get("app_name", ""), int(data.get("pid", 0))
            )
            self._send_json({"ok": ok, "message": msg}, 200 if ok else 404)
        elif self.path == "/api/focus_app":
            ok, msg = engine.process_mapper.focus_or_locate_app(
                data.get("app_name", ""), int(data.get("pid", 0))
            )
            self._send_json({"ok": ok, "message": msg})
        elif self.path == "/api/adapter_toggle":
            ip = data.get("ip", "")
            enabled = bool(data.get("enabled", True))
            if ip in engine.adapter_mgr.adapters:
                engine.adapter_mgr.adapters[ip].enabled = enabled
            self._send_json({"ok": True})
        elif self.path == "/api/adapter_limits":
            try:
                adapter_name = str(data.get("adapter_name", "")).strip()
                values = (
                    float(data.get("data_limit_gb", 0)),
                    float(data.get("cycle_hours", 720)),
                    float(data.get("download_limit_mbps", 0)),
                    float(data.get("upload_limit_mbps", 0)),
                )
            except (TypeError, ValueError, OverflowError):
                self._send_json({"ok": False, "message": "Enter valid numeric limits."}, 400)
                return
            if not adapter_name:
                self._send_json({"ok": False, "message": "Choose a network adapter."}, 400)
                return
            ok, message = engine.adapter_mgr.configure_adapter_limits(adapter_name, *values)
            self._send_json({"ok": ok, "message": message}, 200 if ok else 400)
        elif self.path == "/api/system_proxy":
            new_state = not engine.sys_opt.system_proxy_enabled
            ok, msg = engine.sys_opt.set_system_proxy(new_state, "127.0.0.1", engine.http_port)
            self._send_json({"ok": ok, "message": msg})
        elif self.path == "/api/repair_network":
            ok, msg = engine.sys_opt.repair_network()
            self._send_json({"ok": ok, "message": msg}, 200 if ok else 400)
        elif self.path == "/api/optimize_nic":
            ok, msg = engine.sys_opt.optimize_multi_nic(
                optimize_ipv4=data.get("ipv4", True) is True,
                optimize_ipv6=data.get("ipv6", False) is True,
                keep_multi_nic=data.get("keep_multi_nic", True) is True,
            )
            self._send_json({"ok": ok, "message": msg}, 200 if ok else 400)
        elif self.path == "/api/simulate_burst":
            engine.simulate_telemetry_wave()
            self._send_json({"ok": True})
        elif self.path == "/api/refresh_adapters":
            engine.adapter_mgr.refresh_adapters()
            self._send_json({"ok": True})
        elif self.path == "/api/download":
            url = data.get("url", "").strip()
            out = data.get("output_path", "").strip()
            if not out:
                fname = os.path.basename(urllib.parse.urlsplit(url).path) or "omnibond_download.bin"
                out = os.path.join(os.path.expanduser("~"), "Downloads", fname)
            threading.Thread(
                target=engine.turbo.download_url, args=(url, out), daemon=True
            ).start()
            self._send_json({"ok": True, "output_path": out})
        else:
            self.send_error(404)