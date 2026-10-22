#!/usr/bin/env python3
"""
OmniBond - Main Entrypoint, Startup Launcher, UAC Elevation & Self-Test Suite.
"""

from __future__ import annotations

import atexit
import ctypes
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

from adapter_manager import AdapterManager, NetworkAdapter
from config import (
    ADAPTER_PALETTE,
    BLOCK_INTERNET_RULE,
    HAS_TK,
    IS_WINDOWS,
    TURBO_APP_KEY,
    tk,
)
from desktop_gui import OmniBondDesktopGUI
from engine import (
    OmniBondEngine,
    _build_browser_launch_command,
    discover_existing_browsers,
    is_browser_running,
    launch_frameless_web_app,
)
from process_mapper import ProcessMapper
from routing_manager import AppRoutingManager
from system_optimizer import WindowsSystemOptimizer
from web_ui_html import WEB_UI_HTML

# =====================================================================
# 11. FAST, NON-BLOCKING SELF-TEST SUITE (--selftest)
# =====================================================================

def run_selftest() -> int:
    print("=== OmniBond Self-Test Suite ===")
    tmp_dir = tempfile.mkdtemp(prefix="omnibond_test_")
    rules_path = os.path.join(tmp_dir, "test_rules.json")

    engine = OmniBondEngine(persist_rules_path=rules_path, auto_scan_procs=False)
    engine.adapter_mgr.adapters.clear()
    b0, c0, f0 = ADAPTER_PALETTE[0]
    b1, c1, f1 = ADAPTER_PALETTE[1]
    engine.adapter_mgr.adapters["127.0.0.1"] = NetworkAdapter(
        name="Ethernet-Sim", ip="127.0.0.1", kind="Ethernet", badge_bg=b0, color=c0, fill_dark=f0
    )
    engine.adapter_mgr.adapters["127.0.0.2"] = NetworkAdapter(
        name="Wi-Fi-Sim", ip="127.0.0.2", kind="Wi-Fi", badge_bg=b1, color=c1, fill_dark=f1
    )

    payload_bytes = b"OMNIBOND_TEST_PAYLOAD_" * 4096

    class OriginHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            if self.path == "/ping":
                body = b"PONG"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/file.bin":
                rng = self.headers.get("Range")
                if rng and rng.startswith("bytes="):
                    s_str, e_str = rng.replace("bytes=", "").split("-")
                    start = int(s_str)
                    end = min(len(payload_bytes) - 1, int(e_str))
                    chunk = payload_bytes[start : end + 1]
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{len(payload_bytes)}")
                    self.send_header("Content-Length", str(len(chunk)))
                    self.end_headers()
                    self.wfile.write(chunk)
                else:
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(payload_bytes)))
                    self.end_headers()
                    self.wfile.write(payload_bytes)
            elif self.path == "/stream.m3u8":
                m3u8 = "#EXTM3U\n/seg1.ts\n/seg2.ts\n".encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Length", str(len(m3u8)))
                self.end_headers()
                self.wfile.write(m3u8)
            elif self.path in ("/seg1.ts", "/seg2.ts"):
                seg = f"SEGMENT_{self.path}_DATA".encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Length", str(len(seg)))
                self.end_headers()
                self.wfile.write(seg)
            else:
                self.send_error(404)

    origin_srv = ThreadingHTTPServer(("127.0.0.1", 0), OriginHandler)
    origin_port = origin_srv.server_address[1]
    threading.Thread(target=origin_srv.serve_forever, daemon=True).start()

    engine.start_services(http_port=0, socks_port=0, web_port=0)

    try:
        assert ProcessMapper.classify_process_category(
            "chrome.exe", "Browser window", False
        ) == "USER APPS"
        assert ProcessMapper.classify_process_category(
            "explorer.exe", "", False
        ) == "USER APPS"
        assert ProcessMapper.classify_process_category(
            "custom_daemon.exe", "", True
        ) == "ACTIVE NET"
        assert ProcessMapper.classify_process_category(
            "svchost.exe", "", False
        ) == "SERVICES / BG"
        assert engine.process_mapper.resolve_friendly_app_name("explorer.exe") == "File Explorer"
        assert "Gemini" in engine.process_mapper.resolve_friendly_app_name("chrome.exe", "Gemini - Google Chrome")
        assert "app.category === 'USER APPS'" in WEB_UI_HTML
        assert 'data-limit-mode="data_limit_gb"' in WEB_UI_HTML
        assert "styled-select-menu" in WEB_UI_HTML
        install_dir = os.path.join(tmp_dir, "location_test")
        os.makedirs(install_dir)
        engine.routing_mgr.set_favorite("chrome.exe", True)
        engine.process_mapper.register_custom_app_location("location_test.exe", install_dir)
        assert ProcessMapper(location_path=rules_path + ".locations")._exe_path_map[
            "location_test.exe"
        ] == install_dir
        assert AppRoutingManager(persist_path=rules_path).is_favorite("chrome.exe")
        assert engine.routing_mgr.get_all_entries()[0]["is_favorite"]

        import urllib.request
        for route, payload in (
            ("/api/favorite", {"app_name": "steam.exe", "favorite": True}),
            ("/api/app_location", {"app_name": "api_location.exe", "location": install_dir}),
            (
                "/api/adapter_limits",
                {
                    "adapter_name": "Ethernet-Sim",
                    "data_limit_gb": 0,
                    "cycle_hours": 24,
                    "download_limit_mbps": 1.0,
                    "upload_limit_mbps": 0.5,
                },
            ),
        ):
            req = urllib.request.Request(
                f"http://127.0.0.1:{engine.web_port}{route}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3.0) as response:
                assert json.loads(response.read().decode("utf-8"))["ok"]
        assert engine.routing_mgr.is_favorite("steam.exe")
        assert engine.process_mapper._exe_path_map["api_location.exe"] == install_dir
        assert engine.adapter_mgr.adapters["127.0.0.1"].download_limit_mbps == 1.0

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s_probe:
            s_probe.connect(("127.0.0.1", origin_port))
            local_port = s_probe.getsockname()[1]
            pid, exe_name = engine.process_mapper.resolve_client_port(local_port)
            print(f"[1/6] Socket-to-Process Mapping: port {local_port} -> PID={pid}, EXE={exe_name}")
            assert exe_name != ""

        engine.routing_mgr.set_rule("steam.exe", "127.0.0.1")
        engine.routing_mgr.set_rule("chrome.exe", "127.0.0.2")
        engine.routing_mgr.set_rule(TURBO_APP_KEY, "127.0.0.2")

        steam_candidates = engine.adapter_mgr.select_adapters_for_app("steam.exe")
        chrome_candidates = engine.adapter_mgr.select_adapters_for_app("chrome.exe")
        assert steam_candidates[0].ip == "127.0.0.1"
        assert chrome_candidates[0].ip == "127.0.0.2"
        print("[2/6] Per-App Rule Selection verified: steam.exe -> 127.0.0.1, chrome.exe -> 127.0.0.2")

        for app in ("steam.exe", "chrome.exe"):
            with socket.create_connection(("127.0.0.1", engine.http_port), timeout=3.0) as psock:
                req = (
                    f"GET http://127.0.0.1:{origin_port}/ping HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{origin_port}\r\n"
                    f"X-OmniBond-App: {app}\r\n\r\n"
                ).encode("latin-1")
                psock.sendall(req)
                chunks = []
                while True:
                    chunk = psock.recv(1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    if b"PONG" in b"".join(chunks):
                        break
                assert b"PONG" in b"".join(chunks)

        engine.routing_mgr.set_rule("blocked.exe", BLOCK_INTERNET_RULE)
        assert AppRoutingManager(persist_path=rules_path).is_internet_blocked("blocked.exe")
        assert engine.adapter_mgr.select_adapters_for_app("blocked.exe") == []
        engine.routing_mgr.set_rule(TURBO_APP_KEY, BLOCK_INTERNET_RULE)
        assert engine.adapter_mgr.get_exclusive_or_bonded_adapters(TURBO_APP_KEY) == []
        engine.routing_mgr.set_rule(TURBO_APP_KEY, "127.0.0.2")
        try:
            engine.adapter_mgr.create_bound_connection(
                "127.0.0.1", origin_port, app_name="blocked.exe"
            )
            raise AssertionError("Blocked application unexpectedly opened an upstream connection.")
        except PermissionError:
            pass

        with socket.create_connection(("127.0.0.1", engine.http_port), timeout=3.0) as blocked_http:
            blocked_http.sendall(
                (
                    f"GET http://127.0.0.1:{origin_port}/ping HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{origin_port}\r\n"
                    "X-OmniBond-App: blocked.exe\r\n\r\n"
                ).encode("latin-1")
            )
            assert b"403 Forbidden" in blocked_http.recv(1024)

        original_resolver = engine.process_mapper.resolve_client_port
        engine.process_mapper.resolve_client_port = lambda _port: (0, "blocked.exe")
        try:
            with socket.create_connection(("127.0.0.1", engine.socks_port), timeout=3.0) as blocked_socks:
                blocked_socks.sendall(b"\x05\x01\x00")
                assert blocked_socks.recv(2) == b"\x05\x00"
                blocked_socks.sendall(
                    b"\x05\x01\x00\x01\x7f\x00\x00\x01"
                    + struct.pack("!H", origin_port)
                )
                assert blocked_socks.recv(10)[1] == 0x02
        finally:
            engine.process_mapper.resolve_client_port = original_resolver
        print("[3/6] Per-App Internet Block verified for adapter, HTTP, and SOCKS paths.")

        engine.routing_mgr.tick_app_throughput()
        entries = {r["app_name"]: r for r in engine.routing_mgr.get_all_entries()}
        assert entries["steam.exe"]["last_adapter_ip"] == "127.0.0.1"
        assert entries["chrome.exe"]["last_adapter_ip"] == "127.0.0.2"
        assert entries["steam.exe"]["display_name"] == "Steam Client"
        assert entries["chrome.exe"]["display_name"] == "Google Chrome"
        assert "bps_history" in entries["steam.exe"]
        direct_telemetry_test = AppRoutingManager(persist_path="")
        direct_telemetry_test.record_process_bytes("tcp_test.exe", 4242, 8192)
        direct_telemetry_test.tick_app_throughput()
        direct_entry = {
            r["app_name"]: r for r in direct_telemetry_test.get_all_entries()
        }["tcp_test.exe"]
        assert direct_entry["bytes_transferred"] == 8192
        assert direct_entry["bps"] > 0
        print("[4/6] Proxy and direct per-app TCP speed history & friendly names verified.")

        limit_path = os.path.join(tmp_dir, "adapter_limits.json")
        limit_mgr = AdapterManager(
            AppRoutingManager(persist_path=""),
            refresh_on_init=False,
            limits_path=limit_path,
        )
        limit_mgr._system_counter_reader = object()
        limited_adapter = NetworkAdapter(name="Limited-Sim", ip="127.0.0.9")
        limited_adapter._last_system_total = 1000
        limit_mgr.adapters[limited_adapter.ip] = limited_adapter
        ok, message = limit_mgr.configure_adapter_limits(
            "Limited-Sim", 0.000001, 1.0, 0.1, 0.1
        )
        assert ok, message
        initial_limits = limit_mgr.get_adapter_limit_snapshot(limited_adapter)
        with limit_mgr._lock:
            limit_mgr._update_adapter_usage_locked(
                limited_adapter,
                2000,
                initial_limits["period_started_at"] + 1,
            )
            assert limit_mgr._save_adapter_limits_locked()
        assert limit_mgr.is_quota_exceeded(limited_adapter)
        assert limit_mgr.select_adapters_for_app("limited.exe") == []
        restored_limits = AdapterManager(
            AppRoutingManager(persist_path=""),
            refresh_on_init=False,
            limits_path=limit_path,
        )
        restored_adapter = NetworkAdapter(name="Limited-Sim", ip="127.0.0.9")
        restored_limits.adapters[restored_adapter.ip] = restored_adapter
        persisted_limit = restored_limits.get_adapter_limit_snapshot(restored_adapter)
        assert persisted_limit["usage_bytes"] == 1000
        assert restored_adapter.download_limit_mbps == 0.1
        rate_start = time.perf_counter()
        limited_adapter.wait_for_rate_limit(1000, True)
        assert time.perf_counter() - rate_start >= 0.07
        print("[5/6] Per-adapter data caps, bonding exclusion, speed throttling, and persistence verified.")

        out_bin = os.path.join(tmp_dir, "out.bin")
        engine.turbo.download_url(
            f"http://127.0.0.1:{origin_port}/file.bin", out_bin, block_size=16384
        )
        with open(out_bin, "rb") as f:
            downloaded = f.read()
        assert downloaded == payload_bytes
        assert all(b.adapter_ip == "127.0.0.2" for b in engine.turbo.blocks)

        out_ts = os.path.join(tmp_dir, "stream.ts")
        engine.turbo.download_url(f"http://127.0.0.1:{origin_port}/stream.m3u8", out_ts)
        with open(out_ts, "rb") as f:
            stitched = f.read()
        assert stitched == b"SEGMENT_/seg1.ts_DATASEGMENT_/seg2.ts_DATA"
        print("[6/7] Turbo Download & HLS Stream Accelerator verified.")

        # Verify true Round-Robin multi-NIC bonding when latencies differ slightly
        engine.adapter_mgr.adapters["127.0.0.1"].latency_ms = 12.4
        engine.adapter_mgr.adapters["127.0.0.2"].latency_ms = 28.9
        engine.routing_mgr.set_rule("browser_rr.exe", "AUTO")
        picked_first = [
            engine.adapter_mgr.select_adapters_for_app("browser_rr.exe")[0].ip
            for _ in range(4)
        ]
        assert "127.0.0.1" in picked_first and "127.0.0.2" in picked_first, (
            f"Expected Round-Robin across both adapters, got {picked_first}"
        )
        assert AdapterManager.is_virtual_adapter_name("vEthernet (WSL)")
        assert AdapterManager.is_virtual_adapter_name("VirtualBox Host-Only Network")
        assert not AdapterManager.is_virtual_adapter_name("Wi-Fi")
        assert WindowsSystemOptimizer._is_loopback_proxy_server("127.0.0.1:8080")
        ok_rep, _ = engine.sys_opt.repair_network()
        assert ok_rep and not engine.sys_opt.system_proxy_enabled
        print("[7/7] Multi-NIC Round-Robin bonding, virtual NIC filtering & network repair verified.")

        ff_tab_cmd = _build_browser_launch_command(
            "C:/Program Files/Mozilla Firefox/firefox.exe",
            "http://127.0.0.1:8085",
            open_in_running=True,
        )
        assert ff_tab_cmd == [
            "C:/Program Files/Mozilla Firefox/firefox.exe",
            "-new-tab",
            "http://127.0.0.1:8085",
        ]
        ff_new_cmd = _build_browser_launch_command(
            "C:/Program Files/Mozilla Firefox/firefox.exe",
            "http://127.0.0.1:8085",
            open_in_running=False,
        )
        assert ff_new_cmd == [
            "C:/Program Files/Mozilla Firefox/firefox.exe",
            "http://127.0.0.1:8085",
        ]
        ch_tab_cmd = _build_browser_launch_command(
            "C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe",
            "http://127.0.0.1:8085",
            open_in_running=True,
        )
        assert ch_tab_cmd == [
            "C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe",
            "http://127.0.0.1:8085",
        ]
        assert is_browser_running("C:/Program Files/Mozilla Firefox/firefox.exe", {"firefox.exe"})
        assert not is_browser_running("C:/Program Files/Mozilla Firefox/firefox.exe", {"chrome.exe"})
        print("[8/8] Running-browser detection & new-tab vs. launch command builder verified.")
        print("=== ALL SELF-TESTS PASSED ===")
        return 0
    finally:
        engine.stop_services()
        origin_srv.shutdown()
        origin_srv.server_close()
        shutil.rmtree(tmp_dir, ignore_errors=True)


# =====================================================================
# MAIN ENTRYPOINT
# =====================================================================

def show_startup_dialog() -> Optional[Tuple[str, bool]]:
    if not HAS_TK:
        return ("web", False)

    dialog = tk.Tk()
    dialog.title("OmniBond")
    dialog.configure(bg="#1e1e24")
    dialog.resizable(False, False)
    dialog.geometry("520x410")
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() - 520) // 2
    y = (dialog.winfo_screenheight() - 410) // 2
    dialog.geometry(f"520x410+{x}+{y}")

    selected_mode = tk.StringVar(value="web")
    request_admin = tk.BooleanVar(value=False)
    result: Dict[str, Optional[Tuple[str, bool]]] = {"selection": None}

    top = tk.Frame(dialog, bg="#0b0b0e", padx=24, pady=20)
    top.pack(fill=tk.X)
    tk.Label(
        top,
        text="OB",
        bg="#f59e0b",
        fg="#09090b",
        font=("Segoe UI", 11, "bold"),
        padx=7,
        pady=4,
    ).pack(side=tk.LEFT, padx=(0, 12))
    title = tk.Frame(top, bg="#0b0b0e")
    title.pack(side=tk.LEFT, fill=tk.X, expand=True)
    tk.Label(
        title,
        text="OmniBond",
        bg="#0b0b0e",
        fg="#fafafa",
        font=("Segoe UI", 14, "bold"),
    ).pack(anchor="w")
    tk.Label(
        title,
        text="CHOOSE YOUR DASHBOARD",
        bg="#0b0b0e",
        fg="#a1a1aa",
        font=("Consolas", 8, "bold"),
    ).pack(anchor="w", pady=(3, 0))

    body = tk.Frame(dialog, bg="#0b0b0e", padx=24, pady=18)
    body.pack(fill=tk.BOTH, expand=True, padx=1, pady=(1, 0))
    tk.Label(
        body,
        text="How would you like to launch OmniBond?",
        bg="#0b0b0e",
        fg="#fafafa",
        font=("Segoe UI", 10, "bold"),
    ).pack(anchor="w", pady=(0, 10))

    for value, heading, description in (
        ("web", "Browser Dashboard", "Open the dashboard in a new tab of your running browser (or launch your browser)."),
        ("native", "Native GUI", "Open the Windows desktop interface."),
    ):
        choice = tk.Frame(
            body,
            bg="#101016",
            highlightthickness=1,
            highlightbackground="#272734",
            padx=10,
            pady=8,
        )
        choice.pack(fill=tk.X, pady=4)
        radio = tk.Radiobutton(
            choice,
            text=heading,
            value=value,
            variable=selected_mode,
            bg="#101016",
            fg="#fafafa",
            activebackground="#101016",
            activeforeground="#fafafa",
            selectcolor="#14141c",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        radio.pack(fill=tk.X)
        tk.Label(
            choice,
            text=description,
            bg="#101016",
            fg="#a1a1aa",
            font=("Segoe UI", 8),
            anchor="w",
        ).pack(fill=tk.X, padx=(25, 0), pady=(2, 0))
        choice.bind("<Button-1>", lambda _event, mode=value: selected_mode.set(mode))

    admin_label = (
        "Ask Windows for Administrator access (UAC)"
        if IS_WINDOWS
        else "Administrator access is available on Windows only"
    )
    admin_check = tk.Checkbutton(
        body,
        text=admin_label,
        variable=request_admin,
        state=tk.NORMAL if IS_WINDOWS else tk.DISABLED,
        bg="#0b0b0e",
        fg="#fafafa" if IS_WINDOWS else "#52525b",
        activebackground="#0b0b0e",
        activeforeground="#fafafa",
        selectcolor="#14141c",
        font=("Segoe UI", 9),
        anchor="w",
    )
    admin_check.pack(fill=tk.X, pady=(12, 4))
    tk.Label(
        body,
        text="Administrator access can improve system-wide TCP diagnostics and network tuning.",
        bg="#0b0b0e",
        fg="#a1a1aa",
        font=("Segoe UI", 8),
        wraplength=450,
        justify=tk.LEFT,
    ).pack(anchor="w", padx=(24, 0))

    actions = tk.Frame(body, bg="#0b0b0e")
    actions.pack(fill=tk.X, side=tk.BOTTOM, pady=(16, 0))

    def cancel_startup():
        result["selection"] = None
        dialog.destroy()

    def launch():
        result["selection"] = (selected_mode.get(), request_admin.get())
        dialog.destroy()

    dialog.protocol("WM_DELETE_WINDOW", cancel_startup)
    tk.Button(
        actions,
        text="Cancel",
        command=cancel_startup,
        bg="#14141c",
        fg="#fafafa",
        activebackground="#1f1f2c",
        activeforeground="#fafafa",
        relief=tk.FLAT,
        highlightthickness=1,
        highlightbackground="#272734",
        padx=14,
        pady=7,
        font=("Segoe UI", 9, "bold"),
        cursor="hand2",
    ).pack(side=tk.RIGHT, padx=(8, 0))
    tk.Button(
        actions,
        text="Launch OmniBond",
        command=launch,
        bg="#f59e0b",
        fg="#09090b",
        activebackground="#fbbf24",
        activeforeground="#09090b",
        relief=tk.FLAT,
        highlightthickness=1,
        highlightbackground="#f59e0b",
        padx=14,
        pady=7,
        font=("Segoe UI", 9, "bold"),
        cursor="hand2",
    ).pack(side=tk.RIGHT)
    dialog.mainloop()
    return result["selection"]


def prompt_for_admin_restart(launch_mode: str) -> bool:
    """Request UAC elevation and return True when a replacement process was launched."""
    if not IS_WINDOWS or "--selftest" in sys.argv:
        return False

    shell32 = ctypes.windll.shell32
    shell32.ShellExecuteW.argtypes = [
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_int,
    ]
    shell32.ShellExecuteW.restype = ctypes.c_void_p
    shell32.IsUserAnAdmin.restype = wintypes.BOOL
    try:
        if shell32.IsUserAnAdmin():
            return False
    except OSError as exc:
        print(f"Could not check Administrator status; continuing normally: {exc}", file=sys.stderr)
        return False

    mode_flag = "--native" if launch_mode == "native" else "--web"
    launch_args = [arg for arg in sys.argv[1:] if arg not in ("--native", "--web", "--app")]
    launch_args.append(mode_flag)
    if getattr(sys, "frozen", False):
        executable = sys.executable
        parameters = subprocess.list2cmdline(launch_args)
    else:
        executable = sys.executable
        parameters = subprocess.list2cmdline([os.path.abspath(__file__), *launch_args])

    result = shell32.ShellExecuteW(
        None, "runas", executable, parameters, os.getcwd(), 1
    )
    result_code = int(result or 0)
    if result_code > 32:
        return True

    reason = (
        "The Administrator request was cancelled."
        if result_code == 1223
        else f"Windows could not start the Administrator process (error {result_code})."
    )
    print(f"{reason} OmniBond will continue as a normal user.", file=sys.stderr)
    return False


_CONSOLE_CTRL_HANDLER_REF = None


def _register_windows_console_cleanup(cleanup_fn: Callable[[], Any]) -> None:
    """
    Ensures closing the Windows console window (X button), logging off, or shutting down
    always restores the Windows system proxy and interface metrics before exit.
    """
    global _CONSOLE_CTRL_HANDLER_REF
    if not IS_WINDOWS:
        return
    try:
        HANDLER_ROUTINE = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

        def _ctrl_handler(ctrl_type: int) -> bool:
            # 0=CTRL_C, 1=CTRL_BREAK, 2=CTRL_CLOSE, 5=CTRL_LOGOFF, 6=CTRL_SHUTDOWN
            if ctrl_type in (0, 1, 2, 5, 6):
                try:
                    cleanup_fn()
                except Exception:
                    pass
            return False

        _CONSOLE_CTRL_HANDLER_REF = HANDLER_ROUTINE(_ctrl_handler)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(_CONSOLE_CTRL_HANDLER_REF, True)
    except Exception:
        pass


def main():
    if "--selftest" in sys.argv:
        sys.exit(run_selftest())

    if "--repair-network" in sys.argv:
        opt = WindowsSystemOptimizer()
        ok, msg = opt.repair_network()
        print(msg)
        sys.exit(0 if ok else 1)

    explicit_native = "--native" in sys.argv
    explicit_web = "--app" in sys.argv or "--web" in sys.argv
    if explicit_native:
        launch_mode = "native"
        request_admin = False
    elif explicit_web or not HAS_TK:
        launch_mode = "web"
        request_admin = False
    else:
        selection = show_startup_dialog()
        if selection is None:
            return
        launch_mode, request_admin = selection

    if request_admin and prompt_for_admin_restart(launch_mode):
        return

    engine = OmniBondEngine(auto_scan_procs=False, defer_adapter_scan=True)
    engine.start_services()

    def refresh_startup_state_in_background():
        try:
            engine.scan_and_sync_processes()
        except Exception as exc:
            print(f"Could not scan running processes during startup: {exc}", file=sys.stderr)
        try:
            engine.adapter_mgr.refresh_adapters()
        except Exception as exc:
            print(f"Could not discover network adapters during startup: {exc}", file=sys.stderr)

    threading.Thread(
        target=refresh_startup_state_in_background,
        name="omnibond-startup-scan",
        daemon=True,
    ).start()

    atexit.register(engine.stop_services)
    _register_windows_console_cleanup(engine.stop_services)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: (engine.stop_services(), sys.exit(0)))
        except Exception:
            pass

    url = f"http://127.0.0.1:{engine.web_port}"

    if launch_mode != "native":
        print(f"OmniBond running at {url}")
        print(f"HTTP/HTTPS Proxy: 127.0.0.1:{engine.http_port} | SOCKS5: 127.0.0.1:{engine.socks_port}")
        # Only use an isolated profile if --app was explicitly passed; otherwise open a new tab
        # in the user's running browser (or launch their installed browser if not running).
        app_profile_dir = None
        if "--app" in sys.argv:
            app_profile_dir = os.path.join(tempfile.gettempdir(), "omnibond_web_profile")
            os.makedirs(app_profile_dir, exist_ok=True)
        launch_t0 = time.monotonic()
        browser_process = launch_frameless_web_app(url, browser_profile=app_profile_dir)
        try:
            if browser_process:
                browser_process.wait()
                # If the browser handed off the new tab to an already-running browser process
                # and exited immediately (< 5s), keep the OmniBond service running while the tab is open.
                if (time.monotonic() - launch_t0) < 5.0:
                    print("Opened OmniBond tab in existing browser session; keeping OmniBond running (Ctrl+C to stop).")
                    while True:
                        time.sleep(1.0)
            else:
                print(f"OmniBond dashboard is available at {url}")
                print("Keeping OmniBond web service running (Ctrl+C to stop).")
                while True:
                    time.sleep(1.0)
        except KeyboardInterrupt:
            pass
        finally:
            restore_errors = engine.stop_services()
            for error in restore_errors:
                print(error, file=sys.stderr)
    else:
        gui = OmniBondDesktopGUI(engine)
        gui.run()


if __name__ == "__main__":
    main()