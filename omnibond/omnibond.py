#!/usr/bin/env python3
"""
OmniBond - System-Wide Multi-Network Bonding Proxy, Per-Application Router
& Parallel Range / HLS (.m3u8) Stream Accelerator.

Upgrades in this version:
1. Fixed graph header layout: 2-tier non-overlapping title, live aggregate speed badge & legend row.
2. Custom Dark Studio Dropdown (replaces white Win32 ttk.Combobox popup).
3. Built-in Dropdown Category Filters (User Apps, Active Net, Pinned, Services/BG) + live search bar.
4. Per-Application real-time speed sparkline spline graph inside every Application Card.
5. "Focus ↗" / "Locate" action on every Application Card to bring the running program window to front
   or highlight its executable in Windows Explorer.
6. Only displays detected running user programs by default, plus a "+ Add Program" (.exe) button.
7. Unified URL input + glowing progress bar + block matrix in 03 Turbo Download & Stream Accelerator.
8. Upgraded StudioButtons with hover transitions and delayed descriptive hover tooltips everywhere.
"""

from __future__ import annotations

import atexit
import ctypes
from ctypes import wintypes
import json
import math
import os
import queue
import re
import shutil
import signal
import socket
import socketserver
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
    HAS_TK = True
    _TkFrameBase = tk.Frame
except Exception:
    tk = None  # type: ignore
    filedialog = None  # type: ignore
    messagebox = None  # type: ignore
    HAS_TK = False
    _TkFrameBase = object

IS_WINDOWS = sys.platform.startswith("win")
HTTP_PROXY_PORT = 8080
SOCKS_PROXY_PORT = 1080
WEB_UI_PORT = 8085
TURBO_APP_KEY = "__turbo_accelerator__"
TURBO_APP_LABEL = "Turbo Accelerator (Built-in)"
BLOCK_INTERNET_RULE = "BLOCK"
RULES_FILE = os.path.join(os.path.expanduser("~"), ".omnibond_rules.json")

ADAPTER_PALETTE = [
    ("#2563eb", "#60a5fa", "#0d1f42"),  # 01 Blue
    ("#ea580c", "#fb923c", "#3b1a09"),  # 02 Orange
    ("#10b981", "#34d399", "#062e22"),  # 03 Emerald
    ("#7c3aed", "#a78bfa", "#261247"),  # 04 Purple
    ("#eab308", "#facc15", "#382b06"),  # 05 Amber
    ("#ec4899", "#f472b6", "#3d1028"),  # 06 Pink
]

SYSTEM_NOISE_EXES = {
    "svchost.exe", "conhost.exe", "csrss.exe", "smss.exe", "services.exe",
    "lsass.exe", "wininit.exe", "fontdrvhost.exe", "dwm.exe", "sihost.exe",
    "taskhostw.exe", "runtimebroker.exe", "searchindexer.exe", "spoolsv.exe",
    "dllhost.exe", "WmiPrvSE.exe", "wmiprvse.exe", "ctfmon.exe", "audiodg.exe",
    "system", "registry", "idle", "memory compression", "securityhealthservice.exe",
}

KNOWN_USER_APPS = {
    "steam.exe", "steamwebhelper.exe", "chrome.exe", "firefox.exe", "msedge.exe",
    "brave.exe", "opera.exe", "discord.exe", "spotify.exe", "vlc.exe",
    "obs64.exe", "epicgameslauncher.exe", "code.exe", "slack.exe", "telegram.exe",
    "whatsapp.exe", "zoom.exe", "teams.exe", "qbittorrent.exe", "idm.exe",
    "idman.exe", "curl.exe", "python.exe",
}


# =====================================================================
# 1. SOCKET-TO-PROCESS MAPPING & WINDOW/PATH MANAGEMENT
# =====================================================================

class MIB_TCPROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("dwState", wintypes.DWORD),
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwRemoteAddr", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class MIB_TCPROW(ctypes.Structure):
    _fields_ = [
        ("dwState", wintypes.DWORD),
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwRemoteAddr", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
    ]


class MIB_TCP6ROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("dwState", wintypes.DWORD),
        ("ucLocalAddr", ctypes.c_ubyte * 16),
        ("dwLocalScopeId", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("ucRemoteAddr", ctypes.c_ubyte * 16),
        ("dwRemoteScopeId", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class MIB_TCP6ROW(ctypes.Structure):
    _fields_ = [
        ("dwState", wintypes.DWORD),
        ("ucLocalAddr", ctypes.c_ubyte * 16),
        ("dwLocalScopeId", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("ucRemoteAddr", ctypes.c_ubyte * 16),
        ("dwRemoteScopeId", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
    ]


class TCP_ESTATS_DATA_ROD_V0(ctypes.Structure):
    _fields_ = [
        ("DataBytesOut", ctypes.c_uint64),
        ("DataSegsOut", ctypes.c_uint64),
        ("DataBytesIn", ctypes.c_uint64),
        ("DataSegsIn", ctypes.c_uint64),
        ("SegsOut", ctypes.c_uint64),
        ("SegsIn", ctypes.c_uint64),
        ("SoftErrors", wintypes.ULONG),
        ("SoftErrorReason", wintypes.ULONG),
        ("SndUna", wintypes.ULONG),
        ("SndNxt", wintypes.ULONG),
        ("SndMax", wintypes.ULONG),
        ("ThruBytesAcked", ctypes.c_uint64),
        ("RcvNxt", wintypes.ULONG),
        ("ThruBytesReceived", ctypes.c_uint64),
    ]


@dataclass
class ProcessInfo:
    exe_name: str
    pid: int = 0
    full_path: str = ""
    window_title: str = ""
    category: str = "USER APPS"  # USER APPS | ACTIVE NET | SERVICES / BG
    has_active_socket: bool = False
    is_pinned: bool = False


class ProcessMapper:
    """Resolves local TCP client ports to Windows PIDs, paths, windows, and categories."""

    def __init__(self, location_path: Optional[str] = None):
        self._pid_cache: Dict[int, Tuple[str, str, float]] = {}
        self._port_cache: Dict[int, Tuple[int, str, float]] = {}
        self._exe_path_map: Dict[str, str] = {}
        self._exe_pid_map: Dict[str, int] = {}
        self._lock = threading.Lock()
        self._cache_ttl = 15.0
        self.location_path = location_path or (RULES_FILE + ".locations")
        self._load_custom_locations()

    def _load_custom_locations(self):
        try:
            with open(self.location_path, "r", encoding="utf-8") as f:
                locations = json.load(f)
            if isinstance(locations, dict):
                self._exe_path_map.update({
                    os.path.basename(str(name)).lower(): str(path)
                    for name, path in locations.items()
                    if str(name).strip() and str(path).strip()
                })
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError) as e:
            print(f"Could not load saved program locations: {e}", file=sys.stderr)

    def register_custom_app_location(self, app_name: str, location: str) -> str:
        key = os.path.basename((app_name or "").strip().lower())
        raw_path = (location or "").strip()
        if not key or not raw_path:
            return ""
        path = os.path.abspath(os.path.expanduser(raw_path))
        if not os.path.exists(path):
            return ""
        with self._lock:
            previous = self._exe_path_map.get(key)
            self._exe_path_map[key] = path
            try:
                with open(self.location_path, "w", encoding="utf-8") as f:
                    json.dump(self._exe_path_map, f, indent=2)
            except OSError as e:
                if previous is None:
                    self._exe_path_map.pop(key, None)
                else:
                    self._exe_path_map[key] = previous
                print(f"Could not save program location for {key}: {e}", file=sys.stderr)
                return ""
        return key

    def resolve_client_port(self, client_port: int) -> Tuple[int, str]:
        now = time.time()
        with self._lock:
            cached = self._port_cache.get(client_port)
            if cached and (now - cached[2]) < 2.0:
                return cached[0], cached[1]

        pid = self._lookup_pid_by_port(client_port)
        exe_name = self.get_exe_name(pid) if pid > 0 else "system/unknown"

        with self._lock:
            self._port_cache[client_port] = (pid, exe_name, now)
            if len(self._port_cache) > 2048:
                cutoff = now - 10.0
                self._port_cache = {
                    k: v for k, v in self._port_cache.items() if v[2] >= cutoff
                }
        return pid, exe_name

    def get_active_tcp_pids(self) -> Set[int]:
        """Returns all PIDs that currently own active IPv4 TCP connections."""
        pids: Set[int] = set()
        if not IS_WINDOWS:
            pids.add(os.getpid())
            return pids
        try:
            iphlpapi = ctypes.windll.iphlpapi
            AF_INET = 2
            TCP_TABLE_OWNER_PID_ALL = 5
            size = wintypes.DWORD(0)
            iphlpapi.GetExtendedTcpTable(
                None, ctypes.byref(size), False, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0
            )
            if size.value == 0:
                return pids
            buf = ctypes.create_string_buffer(size.value)
            if iphlpapi.GetExtendedTcpTable(
                buf, ctypes.byref(size), False, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0
            ) != 0:
                return pids
            num_entries = struct.unpack_from("<I", buf.raw, 0)[0]
            row_size = ctypes.sizeof(MIB_TCPROW_OWNER_PID)
            offset = 4
            for _ in range(num_entries):
                if offset + row_size > size.value:
                    break
                row = MIB_TCPROW_OWNER_PID.from_buffer_copy(buf.raw, offset)
                offset += row_size
                if row.dwOwningPid > 4:
                    pids.add(int(row.dwOwningPid))
        except Exception:
            pass
        return pids

    def _lookup_pid_by_port(self, client_port: int) -> int:
        if IS_WINDOWS:
            pid = self._lookup_pid_ctypes(client_port)
            if pid > 0:
                return pid
        return self._lookup_pid_netstat(client_port)

    def _lookup_pid_ctypes(self, client_port: int) -> int:
        try:
            iphlpapi = ctypes.windll.iphlpapi
            AF_INET = 2
            TCP_TABLE_OWNER_PID_ALL = 5
            size = wintypes.DWORD(0)
            iphlpapi.GetExtendedTcpTable(
                None, ctypes.byref(size), False, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0
            )
            if size.value == 0:
                return 0

            buf = ctypes.create_string_buffer(size.value)
            ret = iphlpapi.GetExtendedTcpTable(
                buf, ctypes.byref(size), False, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0
            )
            if ret != 0:
                return 0

            num_entries = struct.unpack_from("<I", buf.raw, 0)[0]
            row_size = ctypes.sizeof(MIB_TCPROW_OWNER_PID)
            offset = 4
            target_port_net = socket.htons(client_port)

            for _ in range(num_entries):
                if offset + row_size > size.value:
                    break
                row = MIB_TCPROW_OWNER_PID.from_buffer_copy(buf.raw, offset)
                offset += row_size
                if (row.dwLocalPort & 0xFFFF) == target_port_net:
                    if row.dwOwningPid > 0:
                        return int(row.dwOwningPid)
        except Exception:
            pass
        return 0

    def _lookup_pid_netstat(self, client_port: int) -> int:
        if not IS_WINDOWS:
            return os.getpid()
        try:
            proc = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True,
                text=True,
                timeout=1.2,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            needle = f":{client_port} "
            for line in proc.stdout.splitlines():
                if needle in line:
                    parts = line.split()
                    if len(parts) >= 5 and parts[1].endswith(f":{client_port}"):
                        return int(parts[-1])
        except Exception:
            pass
        return 0

    def get_exe_info(self, pid: int) -> Tuple[str, str]:
        """Returns (exe_name_lower, full_path) for a PID."""
        if pid <= 0:
            return "system/unknown", ""
        if pid == os.getpid():
            full = sys.executable or "python.exe"
            return os.path.basename(full).lower(), full

        now = time.time()
        with self._lock:
            cached = self._pid_cache.get(pid)
            if cached and (now - cached[2]) < self._cache_ttl:
                return cached[0], cached[1]

        exe_name = ""
        full_path = ""
        if IS_WINDOWS:
            try:
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                kernel32 = ctypes.windll.kernel32
                h_proc = kernel32.OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION, False, pid
                )
                if h_proc:
                    try:
                        buf_len = wintypes.DWORD(1024)
                        buf = ctypes.create_unicode_buffer(buf_len.value)
                        if kernel32.QueryFullProcessImageNameW(
                            h_proc, 0, buf, ctypes.byref(buf_len)
                        ):
                            full_path = buf.value
                            exe_name = os.path.basename(full_path).lower()
                    finally:
                        kernel32.CloseHandle(h_proc)
            except Exception:
                pass

        if not exe_name:
            exe_name = f"pid_{pid}"

        with self._lock:
            self._pid_cache[pid] = (exe_name, full_path, now)
            if exe_name and full_path:
                self._exe_path_map[exe_name] = full_path
            if exe_name and pid > 0:
                self._exe_pid_map[exe_name] = pid
        return exe_name, full_path

    def get_exe_name(self, pid: int) -> str:
        return self.get_exe_info(pid)[0]

    def register_custom_exe_path(self, full_path: str) -> str:
        full_path = (full_path or "").strip()
        if not full_path:
            return ""
        exe_name = os.path.basename(full_path).lower()
        return self.register_custom_app_location(exe_name, full_path)

    def get_visible_window_pids(self) -> Dict[int, str]:
        """Maps taskbar-style visible top-level windows to their process IDs."""
        pid_titles: Dict[int, str] = {}
        if not IS_WINDOWS:
            return pid_titles
        try:
            user32 = ctypes.windll.user32
            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            GW_OWNER = 4
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000

            def enum_cb(hwnd, _lparam):
                if user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, GW_OWNER):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        title = buf.value.strip()
                        extended_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                        is_taskbar_window = not (extended_style & WS_EX_TOOLWINDOW) or bool(
                            extended_style & WS_EX_APPWINDOW
                        )
                        if is_taskbar_window and title and title not in (
                            "Program Manager",
                            "Settings",
                            "Microsoft Text Input Application",
                        ):
                            pid = wintypes.DWORD(0)
                            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                            if pid.value > 0 and pid.value not in pid_titles:
                                pid_titles[int(pid.value)] = title
                return True

            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        except Exception:
            pass
        return pid_titles

    @staticmethod
    def classify_process_category(
        name: str, window_title: str, has_active_socket: bool, is_pinned: bool = False
    ) -> str:
        if name in SYSTEM_NOISE_EXES and not window_title and not is_pinned:
            return "SERVICES / BG"
        if window_title:
            return "USER APPS"
        if has_active_socket:
            return "ACTIVE NET"
        return "SERVICES / BG"

    def scan_detailed_processes(self, pinned_keys: Optional[Set[str]] = None) -> List[ProcessInfo]:
        """Scans running processes and classifies them into USER APPS, ACTIVE NET, or SERVICES / BG."""
        pinned_keys = pinned_keys or set()
        win_pids = self.get_visible_window_pids()
        net_pids = self.get_active_tcp_pids()
        discovered: Dict[str, ProcessInfo] = {}

        if IS_WINDOWS:
            try:
                proc = subprocess.run(
                    ["tasklist", "/FO", "CSV", "/NH"],
                    capture_output=True,
                    text=True,
                    timeout=1.8,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                for line in proc.stdout.splitlines():
                    if not line.startswith('"'):
                        continue
                    parts = [p.strip('"') for p in line.split('","')]
                    if len(parts) < 2:
                        continue
                    name = parts[0].strip().lower()
                    try:
                        pid = int(parts[1])
                    except ValueError:
                        pid = 0
                    if not name.endswith(".exe"):
                        continue

                    _, full_path = self.get_exe_info(pid) if (pid in win_pids or pid in net_pids or name in KNOWN_USER_APPS) else (name, "")
                    w_title = win_pids.get(pid, "")
                    has_net = pid in net_pids
                    is_pin = name in pinned_keys

                    category = self.classify_process_category(name, w_title, has_net, is_pin)

                    existing = discovered.get(name)
                    if not existing or (w_title and not existing.window_title) or (has_net and not existing.has_active_socket):
                        discovered[name] = ProcessInfo(
                            exe_name=name,
                            pid=pid,
                            full_path=full_path or self._exe_path_map.get(name, ""),
                            window_title=w_title,
                            category=category,
                            has_active_socket=has_net,
                            is_pinned=is_pin,
                        )
            except Exception:
                pass

        if not discovered:
            # Non-Windows / fallback environment
            for name in sorted(KNOWN_USER_APPS):
                discovered[name] = ProcessInfo(
                    exe_name=name,
                    pid=os.getpid(),
                    full_path=sys.executable,
                    window_title="Simulated App",
                    category="USER APPS",
                    has_active_socket=True,
                    is_pinned=name in pinned_keys,
                )

        result = list(discovered.values())
        result.sort(
            key=lambda p: (
                0 if p.is_pinned else 1,
                0 if p.category == "USER APPS" else (1 if p.category == "ACTIVE NET" else 2),
                0 if p.has_active_socket else 1,
                p.exe_name,
            )
        )
        return result

    def list_running_executables(self) -> List[str]:
        return [p.exe_name for p in self.scan_detailed_processes()]

    def focus_or_locate_app(self, app_name: str, last_pid: int = 0) -> Tuple[bool, str]:
        """Brings a running application's visible window to the foreground."""
        norm = os.path.basename(app_name.strip().lower())
        if norm == TURBO_APP_KEY or "turbo" in norm:
            return True, "Turbo Accelerator is built directly into Panel 03 below."

        if not IS_WINDOWS:
            return True, f"Simulated Focus/Locate for {norm} (PID {last_pid or os.getpid()})."

        # Refresh process table to find current PID and path
        procs = {p.exe_name: p for p in self.scan_detailed_processes()}
        pinfo = procs.get(norm)
        target_pid = (pinfo.pid if pinfo and pinfo.pid > 0 else last_pid) or self._exe_pid_map.get(norm, 0)
        focused_hwnd = 0
        if target_pid > 0:
            try:
                user32 = ctypes.windll.user32
                WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

                def find_window_cb(hwnd, _lparam):
                    nonlocal focused_hwnd
                    if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
                        wpid = wintypes.DWORD(0)
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
                        if int(wpid.value) == target_pid:
                            focused_hwnd = hwnd
                            return False
                    return True

                user32.EnumWindows(WNDENUMPROC(find_window_cb), 0)
                if focused_hwnd:
                    SW_RESTORE = 9
                    if user32.IsIconic(focused_hwnd):
                        user32.ShowWindow(focused_hwnd, SW_RESTORE)
                    user32.SetForegroundWindow(focused_hwnd)
                    return True, f"Switched focus to running {norm} window (PID {target_pid})."
            except Exception:
                pass

        if target_pid > 0:
            return False, f"{norm} is running in the background (PID {target_pid}) but has no visible window."
        return False, f"{norm} is not currently running, so there is no window to focus."

    def locate_app(self, app_name: str, last_pid: int = 0) -> Tuple[bool, str]:
        norm = os.path.basename((app_name or "").strip().lower())
        if norm == TURBO_APP_KEY:
            return False, "The built-in engine has no executable location."

        full_path = self._exe_path_map.get(norm, "")
        if not full_path or not os.path.exists(full_path):
            pinfo = next(
                (p for p in self.scan_detailed_processes() if p.exe_name == norm),
                None,
            )
            detected_path = pinfo.full_path if pinfo else ""
            full_path = detected_path
            target_pid = pinfo.pid if pinfo and pinfo.pid > 0 else last_pid
            if not full_path and target_pid > 0:
                _, full_path = self.get_exe_info(target_pid)

        if not full_path or not os.path.exists(full_path):
            return False, f"No saved or detected file location is available for {norm}."
        if not IS_WINDOWS:
            return False, "Opening program locations is supported only on Windows."

        try:
            if os.path.isdir(full_path):
                subprocess.Popen(["explorer.exe", full_path])
                return True, f"Opened the installation folder for {norm}."
            subprocess.Popen(["explorer.exe", f"/select,{full_path}"])
            return True, f"Opened the file location for {norm}."
        except OSError as e:
            return False, f"Could not open the file location for {norm}: {e}"


class WindowsProcessTcpCounters:
    """Samples per-connection TCP byte counters and aggregates them by process."""

    ERROR_ACCESS_DENIED = 5
    TCP_TABLE_OWNER_PID_ALL = 5
    TCP_STATE_ESTABLISHED = 5
    TCP_CONNECTION_ESTATS_DATA = 1

    def __init__(self):
        self.status = "Windows per-process TCP telemetry unavailable."
        self.diagnostics = "No TCP telemetry sample yet."
        self._enabled: Dict[Tuple[Any, ...], bool] = {}
        self._enable_errors: Dict[Tuple[Any, ...], int] = {}
        self._last_counters: Dict[Tuple[Any, ...], Tuple[int, int]] = {}
        self._last_seen: Dict[Tuple[Any, ...], float] = {}
        self._is_admin = False
        if not IS_WINDOWS:
            self.status = "Per-process TCP telemetry is only available on Windows."
            return

        iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.IsUserAnAdmin.restype = wintypes.BOOL
        self._is_admin = bool(shell32.IsUserAnAdmin())
        self._get_tcp_table = iphlpapi.GetExtendedTcpTable
        self._get_tcp6_table = self._get_tcp_table
        self._set_tcp_estats = iphlpapi.SetPerTcpConnectionEStats
        self._get_tcp_estats = iphlpapi.GetPerTcpConnectionEStats
        self._set_tcp6_estats = iphlpapi.SetPerTcp6ConnectionEStats
        self._get_tcp6_estats = iphlpapi.GetPerTcp6ConnectionEStats
        self._get_tcp_table.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.ULONG),
            wintypes.BOOL,
            wintypes.ULONG,
            wintypes.ULONG,
            wintypes.ULONG,
        ]
        self._get_tcp_table.restype = wintypes.ULONG
        self._set_tcp_estats.argtypes = [
            ctypes.POINTER(MIB_TCPROW),
            wintypes.ULONG,
            ctypes.POINTER(ctypes.c_ubyte),
            wintypes.ULONG,
            wintypes.ULONG,
            wintypes.ULONG,
        ]
        self._set_tcp_estats.restype = wintypes.ULONG
        self._get_tcp_estats.argtypes = [
            ctypes.POINTER(MIB_TCPROW),
            wintypes.ULONG,
            ctypes.c_void_p,
            wintypes.ULONG,
            wintypes.ULONG,
            ctypes.c_void_p,
            wintypes.ULONG,
            wintypes.ULONG,
            ctypes.POINTER(TCP_ESTATS_DATA_ROD_V0),
            wintypes.ULONG,
            wintypes.ULONG,
        ]
        self._get_tcp_estats.restype = wintypes.ULONG
        self._set_tcp6_estats.argtypes = [
            ctypes.POINTER(MIB_TCP6ROW),
            wintypes.ULONG,
            ctypes.POINTER(ctypes.c_ubyte),
            wintypes.ULONG,
            wintypes.ULONG,
            wintypes.ULONG,
        ]
        self._set_tcp6_estats.restype = wintypes.ULONG
        self._get_tcp6_estats.argtypes = [
            ctypes.POINTER(MIB_TCP6ROW),
            wintypes.ULONG,
            ctypes.c_void_p,
            wintypes.ULONG,
            wintypes.ULONG,
            ctypes.c_void_p,
            wintypes.ULONG,
            wintypes.ULONG,
            ctypes.POINTER(TCP_ESTATS_DATA_ROD_V0),
            wintypes.ULONG,
            wintypes.ULONG,
        ]
        self._get_tcp6_estats.restype = wintypes.ULONG
        self.status = (
            "Administrator permission required for direct app TCP speeds; "
            "OmniBond-routed app speeds remain available."
            if not self._is_admin
            else "Direct app TCP telemetry ready; waiting for TCP traffic."
        )

    def _read_table(self, get_table, family: int, row_type) -> List[Any]:
        size = wintypes.ULONG(0)
        result = get_table(
            None, ctypes.byref(size), False, family, self.TCP_TABLE_OWNER_PID_ALL, 0
        )
        if result not in (0, 122):
            raise OSError(result, "Could not query the Windows TCP table")
        if size.value == 0:
            return []

        buffer = ctypes.create_string_buffer(size.value)
        result = get_table(
            ctypes.cast(buffer, ctypes.c_void_p),
            ctypes.byref(size),
            False,
            family,
            self.TCP_TABLE_OWNER_PID_ALL,
            0,
        )
        if result != 0:
            raise OSError(result, "Could not read the Windows TCP table")

        count = struct.unpack_from("<I", buffer.raw, 0)[0]
        row_size = ctypes.sizeof(row_type)
        rows = []
        for index in range(count):
            offset = 4 + index * row_size
            if offset + row_size > size.value:
                raise OSError("Windows returned a truncated TCP table")
            rows.append(row_type.from_buffer_copy(buffer.raw, offset))
        return rows

    @staticmethod
    def _ipv4_row(owner_row: MIB_TCPROW_OWNER_PID) -> MIB_TCPROW:
        row = MIB_TCPROW()
        row.dwState = owner_row.dwState
        row.dwLocalAddr = owner_row.dwLocalAddr
        row.dwLocalPort = owner_row.dwLocalPort
        row.dwRemoteAddr = owner_row.dwRemoteAddr
        row.dwRemotePort = owner_row.dwRemotePort
        return row

    @staticmethod
    def _ipv6_row(owner_row: MIB_TCP6ROW_OWNER_PID) -> MIB_TCP6ROW:
        row = MIB_TCP6ROW()
        row.dwState = owner_row.dwState
        row.ucLocalAddr = owner_row.ucLocalAddr
        row.dwLocalScopeId = owner_row.dwLocalScopeId
        row.dwLocalPort = owner_row.dwLocalPort
        row.ucRemoteAddr = owner_row.ucRemoteAddr
        row.dwRemoteScopeId = owner_row.dwRemoteScopeId
        row.dwRemotePort = owner_row.dwRemotePort
        return row

    def _set_stats(self, row, setter) -> int:
        enabled = ctypes.c_ubyte(1)
        return setter(
            ctypes.pointer(row),
            self.TCP_CONNECTION_ESTATS_DATA,
            ctypes.pointer(enabled),
            0,
            ctypes.sizeof(enabled),
            0,
        )

    def _get_stats(self, row, getter) -> Tuple[int, int]:
        stats = TCP_ESTATS_DATA_ROD_V0()
        result = getter(
            ctypes.pointer(row),
            self.TCP_CONNECTION_ESTATS_DATA,
            None,
            0,
            0,
            None,
            0,
            0,
            ctypes.pointer(stats),
            0,
            ctypes.sizeof(stats),
        )
        if result != 0:
            raise OSError(result, "Could not read TCP byte counters")
        return int(stats.DataBytesIn), int(stats.DataBytesOut)

    def _record_delta(
        self,
        key: Tuple[Any, ...],
        pid: int,
        counters: Tuple[int, int],
        now: float,
        deltas_by_pid: Dict[int, int],
    ) -> None:
        previous = self._last_counters.get(key)
        if previous is not None:
            delta = max(0, counters[0] - previous[0]) + max(
                0, counters[1] - previous[1]
            )
            if delta:
                deltas_by_pid[pid] = deltas_by_pid.get(pid, 0) + delta
        self._last_counters[key] = counters
        self._last_seen[key] = now

    def sample(self) -> Dict[int, int]:
        if not IS_WINDOWS:
            return {}

        try:
            rows4 = self._read_table(self._get_tcp_table, 2, MIB_TCPROW_OWNER_PID)
            rows6 = self._read_table(self._get_tcp6_table, 23, MIB_TCP6ROW_OWNER_PID)
        except OSError as e:
            self.status = f"Windows TCP table read failed: {e}"
            return {}

        now = time.monotonic()
        active_keys: Set[Tuple[Any, ...]] = set()
        deltas_by_pid: Dict[int, int] = {}
        external_tcp_found = False
        sampled_flow = False
        access_denied = False
        counter_errors: Set[str] = set()
        read_errors: List[str] = []
        eligible_connections = 0
        enabled_connections = 0
        readable_connections = 0

        for owner_row in rows4:
            pid = int(owner_row.dwOwningPid)
            if (
                owner_row.dwState != self.TCP_STATE_ESTABLISHED
                or pid <= 4
                or pid == os.getpid()
                or socket.inet_ntoa(struct.pack("<I", owner_row.dwRemoteAddr)).startswith("127.")
            ):
                continue
            external_tcp_found = True
            eligible_connections += 1
            row = self._ipv4_row(owner_row)
            key = (
                4, pid, owner_row.dwLocalAddr, owner_row.dwLocalPort,
                owner_row.dwRemoteAddr, owner_row.dwRemotePort,
            )
            active_keys.add(key)
            self._last_seen[key] = now
            if key not in self._enabled:
                result = self._set_stats(row, self._set_tcp_estats)
                self._enabled[key] = result == 0
                if result != 0:
                    self._enable_errors[key] = result
                access_denied |= result == self.ERROR_ACCESS_DENIED
                if result != 0 and result != self.ERROR_ACCESS_DENIED:
                    counter_errors.add(str(OSError(result, "Could not enable IPv4 TCP statistics")))
            if not self._enabled[key]:
                result = self._enable_errors.get(key, 0)
                access_denied |= result == self.ERROR_ACCESS_DENIED
                if result and result != self.ERROR_ACCESS_DENIED:
                    counter_errors.add(str(OSError(result, "Could not enable IPv4 TCP statistics")))
                continue
            enabled_connections += 1
            try:
                counters = self._get_stats(row, self._get_tcp_estats)
            except OSError as e:
                access_denied |= e.errno == self.ERROR_ACCESS_DENIED
                if e.errno != self.ERROR_ACCESS_DENIED:
                    read_errors.append(str(e))
                continue
            sampled_flow = True
            readable_connections += 1
            self._record_delta(key, pid, counters, now, deltas_by_pid)

        for owner_row in rows6:
            pid = int(owner_row.dwOwningPid)
            if (
                owner_row.dwState != self.TCP_STATE_ESTABLISHED
                or pid <= 4
                or pid == os.getpid()
                or socket.inet_ntop(socket.AF_INET6, bytes(owner_row.ucRemoteAddr)) == "::1"
            ):
                continue
            external_tcp_found = True
            eligible_connections += 1
            row = self._ipv6_row(owner_row)
            key = (
                6, pid, bytes(owner_row.ucLocalAddr), owner_row.dwLocalScopeId,
                owner_row.dwLocalPort, bytes(owner_row.ucRemoteAddr),
                owner_row.dwRemoteScopeId, owner_row.dwRemotePort,
            )
            active_keys.add(key)
            self._last_seen[key] = now
            if key not in self._enabled:
                result = self._set_stats(row, self._set_tcp6_estats)
                self._enabled[key] = result == 0
                if result != 0:
                    self._enable_errors[key] = result
                access_denied |= result == self.ERROR_ACCESS_DENIED
                if result != 0 and result != self.ERROR_ACCESS_DENIED:
                    counter_errors.add(str(OSError(result, "Could not enable IPv6 TCP statistics")))
            if not self._enabled[key]:
                result = self._enable_errors.get(key, 0)
                access_denied |= result == self.ERROR_ACCESS_DENIED
                if result and result != self.ERROR_ACCESS_DENIED:
                    counter_errors.add(str(OSError(result, "Could not enable IPv6 TCP statistics")))
                continue
            enabled_connections += 1
            try:
                counters = self._get_stats(row, self._get_tcp6_estats)
            except OSError as e:
                access_denied |= e.errno == self.ERROR_ACCESS_DENIED
                if e.errno != self.ERROR_ACCESS_DENIED:
                    read_errors.append(str(e))
                continue
            sampled_flow = True
            readable_connections += 1
            self._record_delta(key, pid, counters, now, deltas_by_pid)

        self.diagnostics = (
            f"TCP flows: {eligible_connections}; counters enabled: "
            f"{enabled_connections}; readable: {readable_connections}."
        )
        stale_keys = {
            key for key, seen in self._last_seen.items()
            if key not in active_keys and now - seen > 10
        }
        for key in stale_keys:
            self._enabled.pop(key, None)
            self._enable_errors.pop(key, None)
            self._last_counters.pop(key, None)
            self._last_seen.pop(key, None)

        if access_denied and not sampled_flow:
            self.status = (
                "Administrator permission required for direct app TCP speeds; "
                "OmniBond-routed app speeds remain available."
            )
        elif access_denied:
            self.status = (
                "Partial direct app TCP telemetry; some connections require "
                "Administrator permission."
            )
        elif sampled_flow:
            self.status = "Direct app TCP telemetry active (TCP only; excludes UDP/QUIC)."
        elif read_errors:
            self.status = f"Direct app TCP telemetry error: {read_errors[0]}"
        elif counter_errors:
            self.status = f"Direct app TCP telemetry error: {sorted(counter_errors)[0]}"
        elif not self._is_admin and not sampled_flow:
            self.status = (
                "Administrator permission required for direct app TCP speeds; "
                "OmniBond-routed app speeds remain available."
            )
        elif external_tcp_found:
            self.status = (
                f"Direct app TCP telemetry could not read active connections. "
                f"{self.diagnostics}"
            )
        else:
            self.status = (
                "Direct app TCP telemetry ready; waiting for external TCP traffic "
                "(UDP/QUIC not included)."
            )
        return deltas_by_pid


# =====================================================================
# 2. PER-APPLICATION ROUTING & LIVE SPEED TELEMETRY MANAGER
# =====================================================================

@dataclass
class AppTrafficStats:
    app_name: str
    display_name: str
    last_pid: int = 0
    active_connections: int = 0
    total_connections: int = 0
    bytes_transferred: int = 0
    last_adapter_ip: str = "-"
    last_seen: float = 0.0
    is_running: bool = False
    category: str = "USER APPS"
    has_active_socket: bool = False
    window_title: str = ""
    full_path: str = ""
    bps_history: List[float] = field(default_factory=lambda: [0.0] * 36)
    _last_bytes: int = 0
    _last_tick: float = field(default_factory=time.time)

    @property
    def current_bps(self) -> float:
        return self.bps_history[-1] if self.bps_history else 0.0

class AppRoutingManager:
    """
    Manages Per-Application Network Routing Rules & Live Per-App Speed Graphs.
    Tracks detected running programs and services, plus user-added apps and built-in Turbo.
    """

    def __init__(self, persist_path: str = RULES_FILE):
        self.persist_path = persist_path
        self.favorites_path = persist_path + ".favorites" if persist_path else ""
        self._lock = threading.Lock()
        self._rules: Dict[str, str] = {TURBO_APP_KEY: "AUTO"}
        self._user_added_apps: Set[str] = {TURBO_APP_KEY}
        self._favorites: Set[str] = set()
        self._stats: Dict[str, AppTrafficStats] = {
            TURBO_APP_KEY: AppTrafficStats(
                app_name=TURBO_APP_KEY,
                display_name=TURBO_APP_LABEL,
                is_running=True,
                window_title="Built-in Parallel Engine",
            )
        }
        self.load_rules()
        self.load_favorites()

    @staticmethod
    def normalize_app_name(app_name: str) -> str:
        name = (app_name or "").strip().lower()
        if not name:
            return "system/unknown"
        if name == TURBO_APP_KEY or "turbo" in name:
            return TURBO_APP_KEY
        return os.path.basename(name)

    def load_rules(self):
        if not self.persist_path or not os.path.exists(self.persist_path):
            return
        try:
            with open(self.persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                with self._lock:
                    for k, v in data.items():
                        norm = self.normalize_app_name(k)
                        rule_val = str(v).strip() if v else "AUTO"
                        self._rules[norm] = rule_val
                        if rule_val != "AUTO":
                            self._user_added_apps.add(norm)
                    self._rules.setdefault(TURBO_APP_KEY, "AUTO")
        except Exception:
            pass

    def load_favorites(self):
        if not self.favorites_path:
            return
        try:
            with open(self.favorites_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                with self._lock:
                    self._favorites = {self.normalize_app_name(str(name)) for name in data}
                    for key in self._favorites:
                        self._rules.setdefault(key, "AUTO")
                        self._stats.setdefault(
                            key,
                            AppTrafficStats(
                                app_name=key,
                                display_name=TURBO_APP_LABEL if key == TURBO_APP_KEY else key,
                            ),
                        )
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError) as e:
            print(f"Could not load application favorites: {e}", file=sys.stderr)

    def set_favorite(self, app_name: str, favorite: bool) -> bool:
        key = self.normalize_app_name(app_name)
        with self._lock:
            was_favorite = key in self._favorites
            if favorite:
                self._favorites.add(key)
                self._rules.setdefault(key, "AUTO")
                self._stats.setdefault(
                    key,
                    AppTrafficStats(
                        app_name=key,
                        display_name=TURBO_APP_LABEL if key == TURBO_APP_KEY else key,
                    ),
                )
            else:
                self._favorites.discard(key)
            payload = sorted(self._favorites)
        if self.favorites_path:
            try:
                with open(self.favorites_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
            except OSError as e:
                with self._lock:
                    if was_favorite:
                        self._favorites.add(key)
                    else:
                        self._favorites.discard(key)
                print(f"Could not save application favorites: {e}", file=sys.stderr)
                return False
        return True

    def is_favorite(self, app_name: str) -> bool:
        with self._lock:
            return self.normalize_app_name(app_name) in self._favorites

    def save_rules(self):
        if not self.persist_path:
            return
        try:
            with self._lock:
                payload = dict(self._rules)
            with open(self.persist_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            pass

    def set_rule(self, app_name: str, target_ip_or_auto: str, explicit_add: bool = True):
        key = self.normalize_app_name(app_name)
        val = (target_ip_or_auto or "AUTO").strip()
        if val.upper() in ("AUTO", "AUTO / BONDED", "BONDED", ""):
            val = "AUTO"
        elif val.upper() == BLOCK_INTERNET_RULE:
            val = BLOCK_INTERNET_RULE
        with self._lock:
            self._rules[key] = val
            if explicit_add:
                self._user_added_apps.add(key)
            if key not in self._stats:
                label = TURBO_APP_LABEL if key == TURBO_APP_KEY else key
                self._stats[key] = AppTrafficStats(app_name=key, display_name=label)
        self.save_rules()

    def remove_app(self, app_name: str):
        key = self.normalize_app_name(app_name)
        if key == TURBO_APP_KEY:
            self.set_rule(TURBO_APP_KEY, "AUTO")
            return
        with self._lock:
            self._rules.pop(key, None)
            self._user_added_apps.discard(key)
            self._stats.pop(key, None)
            self._favorites.discard(key)
        self.save_rules()
        if self.favorites_path:
            try:
                with open(self.favorites_path, "w", encoding="utf-8") as f:
                    json.dump(sorted(self._favorites), f, indent=2)
            except OSError as e:
                print(f"Could not save application favorites: {e}", file=sys.stderr)

    def get_rule(self, app_name: str) -> str:
        key = self.normalize_app_name(app_name)
        with self._lock:
            return self._rules.get(key, "AUTO")

    def is_internet_blocked(self, app_name: str) -> bool:
        return self.get_rule(app_name) == BLOCK_INTERNET_RULE

    def sync_running_programs(self, detailed_procs: List[ProcessInfo]):
        """
        Syncs detected running user programs so the router section automatically shows
        programs that are actually running (plus any user-added/pinned programs).
        """
        running_map = {p.exe_name: p for p in detailed_procs}
        with self._lock:
            # Mark running status on existing stats
            for key, st in self._stats.items():
                if key == TURBO_APP_KEY:
                    st.is_running = True
                    continue
                pinfo = running_map.get(key)
                if pinfo:
                    st.is_running = True
                    st.category = pinfo.category
                    st.has_active_socket = pinfo.has_active_socket
                    if pinfo.pid > 0:
                        st.last_pid = pinfo.pid
                    if pinfo.window_title:
                        st.window_title = pinfo.window_title
                    if pinfo.full_path:
                        st.full_path = pinfo.full_path
                else:
                    st.is_running = False

            # Track every running process so All and Services can include background processes.
            for p in detailed_procs:
                if p.exe_name not in self._stats:
                    self._stats[p.exe_name] = AppTrafficStats(
                        app_name=p.exe_name,
                        display_name=p.exe_name,
                        last_pid=p.pid,
                        is_running=True,
                        category=p.category,
                        has_active_socket=p.has_active_socket,
                        window_title=p.window_title,
                        full_path=p.full_path,
                    )
                self._rules.setdefault(p.exe_name, "AUTO")

    def record_connection_start(self, app_name: str, pid: int, adapter_ip: str):
        key = self.normalize_app_name(app_name)
        now = time.time()
        with self._lock:
            st = self._stats.get(key)
            if not st:
                label = TURBO_APP_LABEL if key == TURBO_APP_KEY else key
                st = AppTrafficStats(app_name=key, display_name=label, is_running=True)
                self._stats[key] = st
            if pid > 0:
                st.last_pid = pid
            st.is_running = True
            st.active_connections += 1
            st.total_connections += 1
            st.last_adapter_ip = adapter_ip
            st.last_seen = now
            self._rules.setdefault(key, "AUTO")

    def record_bytes(self, app_name: str, num_bytes: int):
        key = self.normalize_app_name(app_name)
        with self._lock:
            st = self._stats.get(key)
            if st:
                st.bytes_transferred += num_bytes
                st.last_seen = time.time()

    def record_process_bytes(self, app_name: str, pid: int, num_bytes: int):
        if num_bytes <= 0:
            return
        key = self.normalize_app_name(app_name)
        with self._lock:
            st = self._stats.get(key)
            if not st:
                st = AppTrafficStats(app_name=key, display_name=key)
                self._stats[key] = st
            st.last_pid = pid
            st.is_running = True
            st.has_active_socket = True
            st.bytes_transferred += num_bytes
            st.last_seen = time.time()
            self._rules.setdefault(key, "AUTO")

    def record_connection_end(self, app_name: str):
        key = self.normalize_app_name(app_name)
        with self._lock:
            st = self._stats.get(key)
            if st and st.active_connections > 0:
                st.active_connections -= 1

    def tick_app_throughput(self):
        """Updates live per-application speed history (bps_history) every 0.5s."""
        now = time.time()
        with self._lock:
            for st in self._stats.values():
                dt = max(0.05, now - st._last_tick)
                delta = max(0, st.bytes_transferred - st._last_bytes)
                raw_bps = delta / dt
                prev_bps = st.bps_history[-1] if st.bps_history else 0.0
                smoothed = (
                    raw_bps * 0.65 + prev_bps * 0.35
                    if raw_bps > 0
                    else (prev_bps * 0.50 if prev_bps > 48 else 0.0)
                )
                st._last_bytes = st.bytes_transferred
                st._last_tick = now
                st.bps_history.append(smoothed)
                if len(st.bps_history) > 36:
                    st.bps_history.pop(0)

    def get_all_entries(self, only_running_or_added: bool = True) -> List[Dict]:
        with self._lock:
            all_keys = set(self._rules.keys()) | set(self._stats.keys()) | self._favorites
            rows = []
            for key in all_keys:
                rule = self._rules.get(key, "AUTO")
                st = self._stats.get(key)
                is_builtin = key == TURBO_APP_KEY
                is_running = True if is_builtin else (st.is_running if st else False)
                is_user_added = key in self._user_added_apps or rule != "AUTO"
                has_traffic = (st.bytes_transferred > 0 or st.total_connections > 0) if st else False

                is_favorite = key in self._favorites
                if only_running_or_added and not (is_builtin or is_running or is_user_added or is_favorite or has_traffic):
                    continue

                label = TURBO_APP_LABEL if is_builtin else key
                rows.append({
                    "app_name": key,
                    "display_name": label,
                    "rule": rule,
                    "last_pid": st.last_pid if st else 0,
                    "active_connections": st.active_connections if st else 0,
                    "total_connections": st.total_connections if st else 0,
                    "bytes_transferred": st.bytes_transferred if st else 0,
                    "last_adapter_ip": st.last_adapter_ip if st else "-",
                    "is_builtin": is_builtin,
                    "is_running": is_running,
                    "category": st.category if st else "USER APPS",
                    "has_active_socket": st.has_active_socket if st else False,
                    "is_user_added": is_user_added,
                    "is_favorite": is_favorite,
                    "window_title": st.window_title if st else "",
                    "bps": round(st.current_bps, 1) if st else 0.0,
                    "bps_history": [round(x, 1) for x in st.bps_history[-30:]] if st else [0.0] * 30,
                })
            rows.sort(
                key=lambda r: (
                    0 if r["is_favorite"] else 1,
                    0 if r["is_builtin"] else 1,
                    0 if r["rule"] != "AUTO" else 1,
                    0 if r["bps"] > 0 else 1,
                    -r["bytes_transferred"],
                    0 if r["is_running"] else 1,
                    r["app_name"],
                )
            )
            return rows


# =====================================================================
# 3. NETWORK ADAPTER DISCOVERY & LOAD BALANCER
# =====================================================================

class MIB_IF_ROW2(ctypes.Structure):
    _fields_ = [
        ("InterfaceLuid", ctypes.c_ulonglong),
        ("InterfaceIndex", wintypes.ULONG),
        ("InterfaceGuid", ctypes.c_ubyte * 16),
        ("Alias", wintypes.WCHAR * 257),
        ("Description", wintypes.WCHAR * 257),
        ("PhysicalAddressLength", wintypes.ULONG),
        ("PhysicalAddress", ctypes.c_ubyte * 32),
        ("PermanentPhysicalAddress", ctypes.c_ubyte * 32),
        ("Mtu", wintypes.ULONG),
        ("Type", wintypes.ULONG),
        ("TunnelType", wintypes.ULONG),
        ("MediaType", wintypes.ULONG),
        ("PhysicalMediaType", wintypes.ULONG),
        ("AccessType", wintypes.ULONG),
        ("DirectionType", wintypes.ULONG),
        ("InterfaceAndOperStatusFlags", wintypes.BYTE),
        ("OperStatus", wintypes.ULONG),
        ("AdminStatus", wintypes.ULONG),
        ("MediaConnectState", wintypes.ULONG),
        ("NetworkGuid", ctypes.c_ubyte * 16),
        ("ConnectionType", wintypes.ULONG),
        ("TransmitLinkSpeed", ctypes.c_ulonglong),
        ("ReceiveLinkSpeed", ctypes.c_ulonglong),
        ("InOctets", ctypes.c_ulonglong),
        ("InUcastPkts", ctypes.c_ulonglong),
        ("InNUcastPkts", ctypes.c_ulonglong),
        ("InDiscards", ctypes.c_ulonglong),
        ("InErrors", ctypes.c_ulonglong),
        ("InUnknownProtos", ctypes.c_ulonglong),
        ("InUcastOctets", ctypes.c_ulonglong),
        ("InMulticastOctets", ctypes.c_ulonglong),
        ("InBroadcastOctets", ctypes.c_ulonglong),
        ("OutOctets", ctypes.c_ulonglong),
        ("OutUcastPkts", ctypes.c_ulonglong),
        ("OutNUcastPkts", ctypes.c_ulonglong),
        ("OutDiscards", ctypes.c_ulonglong),
        ("OutErrors", ctypes.c_ulonglong),
        ("OutUcastOctets", ctypes.c_ulonglong),
        ("OutMulticastOctets", ctypes.c_ulonglong),
        ("OutBroadcastOctets", ctypes.c_ulonglong),
        ("OutQLen", ctypes.c_ulonglong),
    ]


class MIB_IF_TABLE2(ctypes.Structure):
    _fields_ = [
        ("NumEntries", wintypes.ULONG),
        ("Table", MIB_IF_ROW2 * 1),
    ]


class MIB_IPADDRROW(ctypes.Structure):
    _fields_ = [
        ("dwAddr", wintypes.DWORD),
        ("dwIndex", wintypes.DWORD),
        ("dwMask", wintypes.DWORD),
        ("dwBCastAddr", wintypes.DWORD),
        ("dwReasmSize", wintypes.DWORD),
        ("unused1", wintypes.USHORT),
        ("wType", wintypes.USHORT),
    ]


class MIB_IPFORWARDROW(ctypes.Structure):
    _fields_ = [
        ("dwForwardDest", wintypes.DWORD),
        ("dwForwardMask", wintypes.DWORD),
        ("dwForwardPolicy", wintypes.DWORD),
        ("dwForwardNextHop", wintypes.DWORD),
        ("dwForwardIfIndex", wintypes.DWORD),
        ("dwForwardType", wintypes.DWORD),
        ("dwForwardProto", wintypes.DWORD),
        ("dwForwardAge", wintypes.DWORD),
        ("dwForwardNextHopAS", wintypes.DWORD),
        ("dwForwardMetric1", wintypes.DWORD),
        ("dwForwardMetric2", wintypes.DWORD),
        ("dwForwardMetric3", wintypes.DWORD),
        ("dwForwardMetric4", wintypes.DWORD),
        ("dwForwardMetric5", wintypes.DWORD),
    ]


VIRTUAL_ADAPTER_KEYWORDS = (
    "vethernet",
    "wsl",
    "hyper-v",
    "default switch",
    "virtualbox",
    "vboxnet",
    "host-only",
    "vmware",
    "vmnet",
    "docker",
    "npcap",
    "loopback",
    "teredo",
    "isatap",
    "bluetooth",
)


class WindowsInterfaceCounters:
    def __init__(self):
        self._iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
        self._get_if_table2 = self._iphlpapi.GetIfTable2
        self._get_if_table2.argtypes = [
            ctypes.POINTER(ctypes.POINTER(MIB_IF_TABLE2))
        ]
        self._get_if_table2.restype = wintypes.ULONG
        self._free_mib_table = self._iphlpapi.FreeMibTable
        self._free_mib_table.argtypes = [ctypes.c_void_p]
        self._free_mib_table.restype = None

    def read_details(self) -> Dict[str, Tuple[int, int, int, int]]:
        """Returns {alias_casefold: (in_octets, out_octets, if_index, oper_status)}."""
        table = ctypes.POINTER(MIB_IF_TABLE2)()
        result = self._get_if_table2(ctypes.byref(table))
        if result != 0:
            raise OSError(result, "GetIfTable2 could not read network counters")
        if not table:
            raise OSError("GetIfTable2 returned an empty interface table")

        try:
            rows = ctypes.cast(
                ctypes.addressof(table.contents) + MIB_IF_TABLE2.Table.offset,
                ctypes.POINTER(MIB_IF_ROW2),
            )
            return {
                rows[index].Alias.strip().casefold(): (
                    int(rows[index].InOctets),
                    int(rows[index].OutOctets),
                    int(rows[index].InterfaceIndex),
                    int(rows[index].OperStatus),
                )
                for index in range(table.contents.NumEntries)
                if rows[index].Alias.strip()
            }
        finally:
            self._free_mib_table(ctypes.cast(table, ctypes.c_void_p))

    def read(self) -> Dict[str, Tuple[int, int]]:
        details = self.read_details()
        return {k: (v[0], v[1]) for k, v in details.items()}


@dataclass
class NetworkAdapter:
    name: str
    ip: str
    kind: str = "Ethernet"
    enabled: bool = True
    weight: int = 1
    latency_ms: float = 15.0
    active_conns: int = 0
    bytes_sent: int = 0
    bytes_recv: int = 0
    fail_count: int = 0
    gateway: str = ""
    if_index: int = 0
    is_online: bool = True
    badge_bg: str = "#2563eb"
    color: str = "#60a5fa"
    fill_dark: str = "#0d1f42"
    bps_history: List[float] = field(default_factory=lambda: [0.0] * 60)
    system_bps_history: List[float] = field(default_factory=lambda: [0.0] * 60)
    system_bytes_sent: int = 0
    system_bytes_recv: int = 0
    _last_bytes: int = 0
    _last_tick: float = field(default_factory=time.time)
    _last_system_total: Optional[int] = None
    upload_limit_mbps: float = 0.0
    download_limit_mbps: float = 0.0
    _rate_limit_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _rate_limit_deadlines: Dict[str, float] = field(default_factory=dict, repr=False)

    @property
    def current_bps(self) -> float:
        return self.bps_history[-1] if self.bps_history else 0.0

    @property
    def system_current_bps(self) -> float:
        return self.system_bps_history[-1] if self.system_bps_history else 0.0

    def wait_for_rate_limit(self, byte_count: int, is_upload: bool):
        limit_mbps = self.upload_limit_mbps if is_upload else self.download_limit_mbps
        if limit_mbps <= 0 or byte_count <= 0:
            return
        bytes_per_second = limit_mbps * 1_000_000 / 8
        direction = "upload" if is_upload else "download"
        now = time.monotonic()
        with self._rate_limit_lock:
            start_at = max(now, self._rate_limit_deadlines.get(direction, now))
            finish_at = start_at + byte_count / bytes_per_second
            self._rate_limit_deadlines[direction] = finish_at
        delay = finish_at - now
        if delay > 0:
            time.sleep(delay)


class AdapterManager:
    def __init__(
        self,
        routing_mgr: AppRoutingManager,
        refresh_on_init: bool = True,
        limits_path: str = RULES_FILE + ".adapter_limits",
    ):
        self.routing_mgr = routing_mgr
        self._lock = threading.Lock()
        self.adapters: Dict[str, NetworkAdapter] = {}
        self._limits_path = limits_path
        self._adapter_limits = self._load_adapter_limits()
        self._last_limits_save = time.monotonic()
        self._rr_index = 0
        self._system_counter_reader = None
        self._system_counter_error_reported = False
        self.system_counter_status = (
            "Initializing Windows network counters"
            if IS_WINDOWS
            else "System adapter counters are only available on Windows"
        )
        if IS_WINDOWS:
            try:
                self._system_counter_reader = WindowsInterfaceCounters()
                self.system_counter_status = "Windows adapter counters available"
            except OSError as exc:
                self._system_counter_error_reported = True
                self.system_counter_status = f"Windows adapter counters unavailable: {exc}"
                print(f"System network counters are unavailable: {exc}", file=sys.stderr)
        if refresh_on_init:
            self.refresh_adapters()

    def _load_adapter_limits(self) -> Dict[str, Dict[str, Any]]:
        if not self._limits_path or not os.path.exists(self._limits_path):
            return {}
        try:
            with open(self._limits_path, "r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            print(f"Could not load adapter limits: {exc}", file=sys.stderr)
            return {}
        if not isinstance(payload, dict):
            print("Could not load adapter limits: invalid settings format.", file=sys.stderr)
            return {}
        limits: Dict[str, Dict[str, Any]] = {}
        for key, value in payload.items():
            if isinstance(key, str) and isinstance(value, dict):
                try:
                    limit_bytes = max(0, int(value.get("limit_bytes", 0)))
                    cycle_hours = float(value.get("cycle_hours", 720.0))
                    period_started_at = float(value.get("period_started_at", time.time()))
                    usage_bytes = max(0, int(value.get("usage_bytes", 0)))
                    last_system_total = value.get("last_system_total")
                    if last_system_total is not None:
                        last_system_total = max(0, int(last_system_total))
                    download_limit_mbps = float(value.get("download_limit_mbps", 0.0))
                    upload_limit_mbps = float(value.get("upload_limit_mbps", 0.0))
                    numeric_values = (
                        cycle_hours, period_started_at,
                        download_limit_mbps, upload_limit_mbps,
                    )
                    if (
                        not all(math.isfinite(number) for number in numeric_values)
                        or cycle_hours < (1 / 60)
                        or cycle_hours > 8760
                        or download_limit_mbps < 0
                        or upload_limit_mbps < 0
                        or download_limit_mbps > 100_000
                        or upload_limit_mbps > 100_000
                    ):
                        raise ValueError("out-of-range adapter limit")
                    limits[key.casefold()] = {
                        "limit_bytes": limit_bytes,
                        "cycle_hours": cycle_hours,
                        "period_started_at": period_started_at,
                        "usage_bytes": usage_bytes,
                        "last_system_total": last_system_total,
                        "download_limit_mbps": download_limit_mbps,
                        "upload_limit_mbps": upload_limit_mbps,
                    }
                except (TypeError, ValueError, OverflowError):
                    print(f"Ignoring invalid adapter limit settings for {key}.", file=sys.stderr)
        return limits

    def _save_adapter_limits_locked(self) -> bool:
        if not self._limits_path:
            return True
        temporary_path = self._limits_path + ".tmp"
        try:
            with open(temporary_path, "w", encoding="utf-8") as file:
                json.dump(self._adapter_limits, file, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, self._limits_path)
            self._last_limits_save = time.monotonic()
            return True
        except OSError as exc:
            print(f"Could not save adapter limits: {exc}", file=sys.stderr)
            try:
                os.remove(temporary_path)
            except OSError as cleanup_error:
                if not isinstance(cleanup_error, FileNotFoundError):
                    print(f"Could not remove temporary adapter limits file: {cleanup_error}", file=sys.stderr)
            return False

    def _limit_state_locked(self, adapter: NetworkAdapter) -> Dict[str, Any]:
        key = adapter.name.casefold()
        state = self._adapter_limits.setdefault(
            key,
            {
                "limit_bytes": 0,
                "cycle_hours": 720.0,
                "period_started_at": time.time(),
                "usage_bytes": 0,
                "last_system_total": None,
                "download_limit_mbps": 0.0,
                "upload_limit_mbps": 0.0,
            },
        )
        adapter.download_limit_mbps = max(0.0, float(state.get("download_limit_mbps", 0.0)))
        adapter.upload_limit_mbps = max(0.0, float(state.get("upload_limit_mbps", 0.0)))
        return state

    @staticmethod
    def _quota_exceeded(state: Dict[str, Any]) -> bool:
        limit_bytes = int(state.get("limit_bytes", 0))
        return limit_bytes > 0 and int(state.get("usage_bytes", 0)) >= limit_bytes

    def _update_adapter_usage_locked(self, adapter: NetworkAdapter, system_total: int, now: float):
        state = self._limit_state_locked(adapter)
        cycle_seconds = max(60.0, float(state.get("cycle_hours", 720.0)) * 3600)
        period_started_at = float(state.get("period_started_at", now))
        if now >= period_started_at + cycle_seconds:
            elapsed_periods = int((now - period_started_at) // cycle_seconds)
            state["period_started_at"] = period_started_at + elapsed_periods * cycle_seconds
            state["usage_bytes"] = 0

        previous_total = state.get("last_system_total")
        if previous_total is not None:
            previous_total = int(previous_total)
            delta = system_total - previous_total if system_total >= previous_total else system_total
            state["usage_bytes"] = int(state.get("usage_bytes", 0)) + max(0, delta)
        state["last_system_total"] = system_total

    def is_quota_exceeded(self, adapter: NetworkAdapter) -> bool:
        with self._lock:
            state = self._limit_state_locked(adapter)
            limit_bytes = int(state.get("limit_bytes", 0))
            return limit_bytes > 0 and int(state.get("usage_bytes", 0)) >= limit_bytes

    def get_adapter_limit_snapshot(self, adapter: NetworkAdapter) -> Dict[str, Any]:
        with self._lock:
            state = self._limit_state_locked(adapter)
            limit_bytes = int(state.get("limit_bytes", 0))
            usage_bytes = int(state.get("usage_bytes", 0))
            return {
                "data_limit_bytes": limit_bytes,
                "usage_bytes": usage_bytes,
                "cycle_hours": float(state.get("cycle_hours", 720.0)),
                "period_started_at": float(state.get("period_started_at", 0.0)),
                "download_limit_mbps": adapter.download_limit_mbps,
                "upload_limit_mbps": adapter.upload_limit_mbps,
                "quota_exceeded": limit_bytes > 0 and usage_bytes >= limit_bytes,
            }

    def configure_adapter_limits(
        self,
        adapter_name: str,
        data_limit_gb: float,
        cycle_hours: float,
        download_limit_mbps: float,
        upload_limit_mbps: float,
    ) -> Tuple[bool, str]:
        if not all(math.isfinite(value) for value in (
            data_limit_gb, cycle_hours, download_limit_mbps, upload_limit_mbps
        )):
            return False, "Limits must be finite numbers."
        if data_limit_gb < 0 or data_limit_gb > 1_000_000_000:
            return False, "Data cap must be between 0 and 1,000,000,000 GB."
        if cycle_hours < (1 / 60) or cycle_hours > 8760:
            return False, "Reset time must be 1 minute–1 year."
        if download_limit_mbps < 0 or upload_limit_mbps < 0:
            return False, "Speed limits must be non-negative."
        if download_limit_mbps > 100_000 or upload_limit_mbps > 100_000:
            return False, "Speed limits cannot exceed 100,000 Mbps."
        if data_limit_gb > 0 and self._system_counter_reader is None:
            return False, "Data caps require Windows network adapter counters, which are unavailable."

        with self._lock:
            adapter = next(
                (item for item in self.adapters.values() if item.name.casefold() == adapter_name.casefold()),
                None,
            )
            if adapter is None:
                return False, "The selected network adapter is no longer available."
            key = adapter.name.casefold()
            previous_state = self._adapter_limits.get(key)
            state = dict(previous_state or {})
            new_limit_bytes = int(data_limit_gb * 1_000_000_000)
            reset_window = (
                previous_state is None
                or int(previous_state.get("limit_bytes", 0)) != new_limit_bytes
                or float(previous_state.get("cycle_hours", 720.0)) != cycle_hours
            )
            state.update({
                "limit_bytes": new_limit_bytes,
                "cycle_hours": cycle_hours,
                "download_limit_mbps": download_limit_mbps,
                "upload_limit_mbps": upload_limit_mbps,
            })
            if reset_window:
                state.update({
                    "period_started_at": time.time(),
                    "usage_bytes": 0,
                    "last_system_total": adapter._last_system_total,
                })
            self._adapter_limits[key] = state
            adapter.download_limit_mbps = download_limit_mbps
            adapter.upload_limit_mbps = upload_limit_mbps
            if not self._save_adapter_limits_locked():
                if previous_state is None:
                    self._adapter_limits.pop(key, None)
                    adapter.download_limit_mbps = 0.0
                    adapter.upload_limit_mbps = 0.0
                else:
                    self._adapter_limits[key] = previous_state
                    adapter.download_limit_mbps = float(previous_state.get("download_limit_mbps", 0.0))
                    adapter.upload_limit_mbps = float(previous_state.get("upload_limit_mbps", 0.0))
                return False, "Could not save adapter limits. Check the application data folder permissions."
            message = "Adapter limits saved."
            if reset_window:
                message += " A fresh data-usage window has started."
            return True, message

    def _query_windows_ip_and_routes(self) -> Tuple[Dict[str, int], Dict[int, str]]:
        """
        Uses Windows IP Helper API (GetIpAddrTable & GetIpForwardTable) to map:
          - ip_to_ifindex: {ipv4_str: interface_index}
          - ifindex_to_gateway: {interface_index: default_gateway_ipv4_str}
        """
        ip_to_ifindex: Dict[str, int] = {}
        ifindex_to_gateway: Dict[int, str] = {}
        if not IS_WINDOWS:
            return ip_to_ifindex, ifindex_to_gateway

        try:
            iphlpapi = ctypes.windll.iphlpapi
            size = wintypes.ULONG(0)
            iphlpapi.GetIpAddrTable(None, ctypes.byref(size), False)
            if size.value > 0:
                buf = ctypes.create_string_buffer(size.value)
                if iphlpapi.GetIpAddrTable(buf, ctypes.byref(size), False) == 0:
                    num_entries = struct.unpack_from("<I", buf.raw, 0)[0]
                    row_size = ctypes.sizeof(MIB_IPADDRROW)
                    offset = 4
                    for _ in range(num_entries):
                        if offset + row_size > size.value:
                            break
                        row = MIB_IPADDRROW.from_buffer_copy(buf.raw, offset)
                        offset += row_size
                        ip_str = socket.inet_ntoa(struct.pack("<I", row.dwAddr))
                        if not ip_str.startswith("127.") and not ip_str.startswith("169.254.") and ip_str != "0.0.0.0":
                            ip_to_ifindex[ip_str] = int(row.dwIndex)
        except Exception:
            pass

        try:
            iphlpapi = ctypes.windll.iphlpapi
            size = wintypes.ULONG(0)
            iphlpapi.GetIpForwardTable(None, ctypes.byref(size), False)
            if size.value > 0:
                buf = ctypes.create_string_buffer(size.value)
                if iphlpapi.GetIpForwardTable(buf, ctypes.byref(size), False) == 0:
                    num_entries = struct.unpack_from("<I", buf.raw, 0)[0]
                    row_size = ctypes.sizeof(MIB_IPFORWARDROW)
                    offset = 4
                    best_metric: Dict[int, int] = {}
                    for _ in range(num_entries):
                        if offset + row_size > size.value:
                            break
                        row = MIB_IPFORWARDROW.from_buffer_copy(buf.raw, offset)
                        offset += row_size
                        # Default route 0.0.0.0/0
                        if row.dwForwardDest == 0 and row.dwForwardMask == 0:
                            gw_ip = socket.inet_ntoa(struct.pack("<I", row.dwForwardNextHop))
                            if gw_ip and gw_ip != "0.0.0.0" and not gw_ip.startswith("127."):
                                if_idx = int(row.dwForwardIfIndex)
                                metric = int(row.dwForwardMetric1)
                                if if_idx not in best_metric or metric < best_metric[if_idx]:
                                    best_metric[if_idx] = metric
                                    ifindex_to_gateway[if_idx] = gw_ip
        except Exception:
            pass

        return ip_to_ifindex, ifindex_to_gateway

    @staticmethod
    def is_virtual_adapter_name(name: str) -> bool:
        low = (name or "").lower()
        return any(kw in low for kw in VIRTUAL_ADAPTER_KEYWORDS)

    def bind_socket_to_adapter(
        self, sock: socket.socket, adapter: NetworkAdapter, is_loopback_dest: bool = False
    ) -> None:
        """
        Configures socket options and binds the socket to both the adapter's source IPv4
        address and, on Windows, its physical hardware interface index (IP_UNICAST_IF = 31)
        so packets are routed through the adapter's own Default Gateway instead of all
        falling back to the single lowest-metric system route.
        """
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 262144)
        except Exception:
            pass

        if is_loopback_dest or adapter.ip == "127.0.0.1" or adapter.ip.startswith("127."):
            return

        sock.bind((adapter.ip, 0))
        if IS_WINDOWS and adapter.if_index > 0:
            try:
                IP_UNICAST_IF = 31
                sock.setsockopt(
                    socket.IPPROTO_IP,
                    IP_UNICAST_IF,
                    struct.pack("!I", adapter.if_index),
                )
            except Exception:
                pass

    def _probe_adapter_connectivity(self, adapter: NetworkAdapter, timeout: float = 0.75) -> Tuple[bool, float]:
        """
        Quickly tests whether an adapter can route traffic to its gateway or public DNS.
        """
        if adapter.ip.startswith("127."):
            return True, 1.0

        targets: List[Tuple[str, int]] = []
        if adapter.gateway and adapter.gateway != "0.0.0.0":
            targets.append((adapter.gateway, 53))
            targets.append((adapter.gateway, 80))
        targets.extend([("1.1.1.1", 53), ("8.8.8.8", 53)])

        for host, port in targets:
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                self.bind_socket_to_adapter(sock, adapter, is_loopback_dest=False)
                t0 = time.perf_counter()
                sock.connect((host, port))
                rtt = max(1.0, (time.perf_counter() - t0) * 1000.0)
                return True, rtt
            except ConnectionRefusedError:
                # A TCP RST from the gateway proves Layer-2/Layer-3 reachability on that NIC
                rtt = max(1.0, (time.perf_counter() - t0) * 1000.0)
                return True, rtt
            except Exception:
                pass
            finally:
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass
        return bool(adapter.gateway), adapter.latency_ms

    def resolve_host_ipv4(self, host: str) -> str:
        """Thread-safe cached IPv4 DNS resolution to avoid blocking or IPv6 mismatch on bound sockets."""
        host = (host or "").strip()
        if not host:
            return "127.0.0.1"
        if host in ("localhost", "::1"):
            return "127.0.0.1"
        try:
            socket.inet_aton(host)
            return host
        except OSError:
            pass

        now = time.monotonic()
        dns_cache: Dict[str, Tuple[str, float]] = getattr(self, "_dns_cache", {})
        if not hasattr(self, "_dns_cache"):
            self._dns_cache = dns_cache
        with self._lock:
            cached = dns_cache.get(host.lower())
            if cached and (now - cached[1]) < 120.0:
                return cached[0]

        try:
            infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
            if infos:
                resolved = str(infos[0][4][0])
                with self._lock:
                    dns_cache[host.lower()] = (resolved, now)
                    if len(dns_cache) > 1024:
                        cutoff = now - 120.0
                        self._dns_cache = {k: v for k, v in dns_cache.items() if v[1] >= cutoff}
                return resolved
        except Exception:
            pass
        return host

    def refresh_adapters(self):
        discovered = self._discover_system_adapters()
        fallback = None
        if not discovered and not self.get_adapters():
            fallback_ip = self._get_default_local_ip()
            badge_bg, line_col, fill_dark = ADAPTER_PALETTE[0]
            fallback = NetworkAdapter(
                name="Primary Interface",
                ip=fallback_ip,
                kind="Ethernet",
                badge_bg=badge_bg,
                color=line_col,
                fill_dark=fill_dark,
            )

        to_probe: List[NetworkAdapter] = []
        with self._lock:
            discovered_ips = {item[1] for item in discovered}
            # Remove stale virtual/disconnected adapters that no longer exist and have no active traffic
            for existing_ip in list(self.adapters.keys()):
                if existing_ip not in discovered_ips and not existing_ip.startswith("127."):
                    existing_ad = self.adapters[existing_ip]
                    if existing_ad.active_conns <= 0:
                        self.adapters.pop(existing_ip, None)

            for item in discovered:
                name, ip, kind = item[0], item[1], item[2]
                gateway = item[3] if len(item) > 3 else ""
                if_index = int(item[4]) if len(item) > 4 else 0
                has_route = bool(gateway) or ip.startswith("127.")
                is_virt = self.is_virtual_adapter_name(name)

                if ip not in self.adapters:
                    idx = len(self.adapters) % len(ADAPTER_PALETTE)
                    badge_bg, line_col, fill_dark = ADAPTER_PALETTE[idx]
                    should_enable = has_route and not is_virt
                    adapter = NetworkAdapter(
                        name=name,
                        ip=ip,
                        kind=kind,
                        enabled=should_enable,
                        gateway=gateway,
                        if_index=if_index,
                        is_online=has_route,
                        badge_bg=badge_bg,
                        color=line_col,
                        fill_dark=fill_dark,
                    )
                    self.adapters[ip] = adapter
                    to_probe.append(adapter)
                else:
                    adapter = self.adapters[ip]
                    adapter.name = name
                    adapter.kind = kind
                    if gateway:
                        adapter.gateway = gateway
                    if if_index > 0:
                        adapter.if_index = if_index
                    adapter.is_online = has_route
                    adapter.fail_count = 0
                    if is_virt and not gateway:
                        adapter.enabled = False
                    to_probe.append(adapter)

            # Ensure at least one adapter is enabled if all discovered lacked explicit gateway metadata
            if self.adapters and not any(a.enabled for a in self.adapters.values()):
                non_virt = [a for a in self.adapters.values() if not self.is_virtual_adapter_name(a.name)]
                target = non_virt[0] if non_virt else next(iter(self.adapters.values()))
                target.enabled = True
                target.is_online = True

            if not self.adapters and fallback is not None:
                self.adapters[fallback.ip] = fallback
            for adapter in self.adapters.values():
                self._limit_state_locked(adapter)

        for adapter in to_probe:
            if not adapter.ip.startswith("127.") and adapter.enabled:
                online, rtt = self._probe_adapter_connectivity(adapter, timeout=0.6)
                with self._lock:
                    adapter.is_online = online
                    if online and rtt > 0:
                        adapter.latency_ms = 0.6 * adapter.latency_ms + 0.4 * rtt

    def get_adapters(self) -> List[NetworkAdapter]:
        with self._lock:
            return list(self.adapters.values())

    def _get_default_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def _discover_system_adapters(self) -> List[Tuple[str, str, str, str, int]]:
        results: List[Tuple[str, str, str, str, int]] = []
        seen_ips: Set[str] = set()
        ip_to_ifindex, ifindex_to_gateway = self._query_windows_ip_and_routes()
        alias_to_ifindex: Dict[str, int] = {}
        if self._system_counter_reader is not None and hasattr(self._system_counter_reader, "read_details"):
            try:
                for alias_key, details in self._system_counter_reader.read_details().items():
                    alias_to_ifindex[alias_key] = int(details[2])
            except Exception:
                pass

        if IS_WINDOWS:
            try:
                proc = subprocess.run(
                    ["ipconfig"],
                    capture_output=True,
                    text=True,
                    timeout=2.5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                blocks: List[Tuple[str, List[str]]] = []
                current_name = ""
                current_lines: List[str] = []
                for raw_line in proc.stdout.splitlines():
                    line = raw_line.rstrip()
                    if not line:
                        continue
                    if not line.startswith(" ") and not line.startswith("\t") and line.endswith(":"):
                        if current_name and current_lines:
                            blocks.append((current_name, current_lines))
                        header = line[:-1].strip()
                        for prefix in (
                            "Ethernet adapter ",
                            "Wireless LAN adapter ",
                            "PPP adapter ",
                            "Unknown adapter ",
                        ):
                            if header.lower().startswith(prefix.lower()):
                                header = header[len(prefix):]
                                break
                        current_name = header
                        current_lines = []
                    elif current_name:
                        current_lines.append(line)
                if current_name and current_lines:
                    blocks.append((current_name, current_lines))

                for block_name, blines in blocks:
                    block_text = "\n".join(blines)
                    if "media disconnected" in block_text.lower():
                        continue
                    ip_addr = ""
                    gw_addr = ""
                    in_gateway_field = False
                    for bline in blines:
                        low_line = bline.lower()
                        if "ipv4 address" in low_line or "ip address" in low_line or "ipv4" in low_line:
                            m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", bline)
                            if m and not ip_addr:
                                candidate = m.group(1)
                                if not candidate.startswith("127.") and not candidate.startswith("169.254."):
                                    ip_addr = candidate
                            in_gateway_field = False
                        elif "default gateway" in low_line:
                            in_gateway_field = True
                            m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", bline)
                            if m:
                                gw_candidate = m.group(1)
                                if gw_candidate != "0.0.0.0":
                                    gw_addr = gw_candidate
                        elif in_gateway_field and (":" not in bline.split(".")[0] if "." in bline else False):
                            m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", bline)
                            if m and not gw_addr:
                                gw_candidate = m.group(1)
                                if gw_candidate != "0.0.0.0":
                                    gw_addr = gw_candidate
                            in_gateway_field = False
                        elif ":" in bline:
                            in_gateway_field = False

                    if not ip_addr or ip_addr in seen_ips:
                        continue

                    if_idx = ip_to_ifindex.get(ip_addr) or alias_to_ifindex.get(block_name.casefold(), 0)
                    if not gw_addr and if_idx > 0:
                        gw_addr = ifindex_to_gateway.get(if_idx, "")

                    # Skip virtual/host-only switches that have no internet gateway
                    if self.is_virtual_adapter_name(block_name) and not gw_addr:
                        continue

                    seen_ips.add(ip_addr)
                    kind = self._classify_adapter(block_name)
                    results.append((block_name, ip_addr, kind, gw_addr, if_idx))
            except Exception:
                pass

        if not results:
            try:
                hostname = socket.gethostname()
                for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                    ip = info[4][0]
                    if not ip.startswith("127.") and not ip.startswith("169.254.") and ip not in seen_ips:
                        seen_ips.add(ip)
                        if_idx = ip_to_ifindex.get(ip, 0)
                        gw = ifindex_to_gateway.get(if_idx, "")
                        results.append((f"Interface ({ip})", ip, "Ethernet", gw, if_idx))
            except Exception:
                pass

        default_ip = self._get_default_local_ip()
        if default_ip and default_ip not in seen_ips and not default_ip.startswith("127."):
            if_idx = ip_to_ifindex.get(default_ip, 0)
            gw = ifindex_to_gateway.get(if_idx, "")
            results.insert(0, ("Primary Network", default_ip, "Ethernet", gw, if_idx))

        # Sort adapters with valid default gateways first
        results.sort(key=lambda item: (0 if item[3] else 1, self.is_virtual_adapter_name(item[0])))
        return results

    @staticmethod
    def _classify_adapter(name: str) -> str:
        low = name.lower()
        if "wi-fi" in low or "wlan" in low or "wireless" in low or "wifi" in low:
            return "Wi-Fi"
        if "usb" in low or "rndis" in low or "apple" in low or "android" in low or "tether" in low:
            return "USB Tether"
        if "vethernet" in low or "virtual" in low or "switch" in low:
            return "vSwitch"
        if "ethernet" in low or "lan" in low:
            return "Ethernet"
        return "Adapter"

    def get_enabled_adapters(self) -> List[NetworkAdapter]:
        with self._lock:
            eligible = [
                adapter for adapter in self.adapters.values()
                if not self._quota_exceeded(self._limit_state_locked(adapter))
            ]
            enabled = [adapter for adapter in eligible if adapter.enabled]
            if not enabled:
                return [a for a in eligible if not self.is_virtual_adapter_name(a.name)] or eligible
            return enabled

    def select_adapters_for_app(
        self, app_name: Optional[str] = None
    ) -> List[NetworkAdapter]:
        with self._lock:
            if app_name and self.routing_mgr.is_internet_blocked(app_name):
                return []
            eligible = [
                adapter for adapter in self.adapters.values()
                if not self._quota_exceeded(self._limit_state_locked(adapter))
            ]
            enabled = [adapter for adapter in eligible if adapter.enabled]
            if not enabled:
                enabled = [a for a in eligible if not self.is_virtual_adapter_name(a.name)] or eligible
            if not enabled:
                return []

            pinned_ip = "AUTO"
            if app_name:
                pinned_ip = self.routing_mgr.get_rule(app_name)

            self._rr_index = (self._rr_index + 1) % max(1, len(enabled))
            rotated = enabled[self._rr_index:] + enabled[:self._rr_index]
            # Use coarse latency tiers (150ms buckets) and integer load ratios so Python's
            # stable sort preserves the true Round-Robin rotation across healthy adapters
            # instead of always sticking to a single adapter with 0.1ms lower float latency.
            scored = sorted(
                rotated,
                key=lambda a: (
                    0 if a.is_online else 1,
                    min(a.fail_count, 6),
                    int(a.active_conns // max(1, a.weight)),
                    int(a.latency_ms // 150.0),
                ),
            )

            if pinned_ip and pinned_ip != "AUTO":
                pinned_adapter = self.adapters.get(pinned_ip)
                if pinned_adapter and not self._quota_exceeded(self._limit_state_locked(pinned_adapter)):
                    others = [a for a in scored if a.ip != pinned_ip]
                    return [pinned_adapter] + others

            return scored

    def get_exclusive_or_bonded_adapters(self, app_name: str) -> List[NetworkAdapter]:
        if self.routing_mgr.is_internet_blocked(app_name):
            return []
        pinned_ip = self.routing_mgr.get_rule(app_name)
        with self._lock:
            if pinned_ip and pinned_ip != "AUTO" and pinned_ip in self.adapters:
                adapter = self.adapters[pinned_ip]
                if not self._quota_exceeded(self._limit_state_locked(adapter)):
                    return [adapter]
                return []
        return self.get_enabled_adapters()

    def create_bound_connection(
        self,
        dest_host: str,
        dest_port: int,
        app_name: str = "system/unknown",
        pid: int = 0,
        timeout: float = 6.0,
    ) -> Tuple[socket.socket, NetworkAdapter]:
        if self.routing_mgr.is_internet_blocked(app_name):
            raise PermissionError(f"Internet access is disabled for {app_name}.")
        candidates = self.select_adapters_for_app(app_name)
        last_err = None
        is_loopback_dest = dest_host in ("127.0.0.1", "localhost", "::1")
        target_ip = "127.0.0.1" if is_loopback_dest else self.resolve_host_ipv4(dest_host)

        for adapter in candidates:
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                self.bind_socket_to_adapter(sock, adapter, is_loopback_dest=is_loopback_dest)
                t0 = time.perf_counter()
                sock.connect((target_ip, dest_port))
                rtt = (time.perf_counter() - t0) * 1000.0
                with self._lock:
                    adapter.latency_ms = 0.7 * adapter.latency_ms + 0.3 * rtt
                    adapter.active_conns += 1
                    adapter.fail_count = 0
                    adapter.is_online = True
                self.routing_mgr.record_connection_start(app_name, pid, adapter.ip)
                return sock, adapter
            except Exception as e:
                last_err = e
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass
                with self._lock:
                    adapter.fail_count += 1
                    if adapter.fail_count >= 5 and not adapter.gateway:
                        adapter.is_online = False

        # Fallback: try direct OS-routed unbound socket if all bound adapters failed
        # so the user's browser or application never loses internet connectivity.
        if candidates and not is_loopback_dest:
            fallback_adapter = candidates[0]
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                t0 = time.perf_counter()
                sock.connect((target_ip, dest_port))
                rtt = (time.perf_counter() - t0) * 1000.0
                with self._lock:
                    fallback_adapter.latency_ms = 0.7 * fallback_adapter.latency_ms + 0.3 * rtt
                    fallback_adapter.active_conns += 1
                self.routing_mgr.record_connection_start(app_name, pid, fallback_adapter.ip)
                return sock, fallback_adapter
            except Exception as e:
                last_err = e
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass

        raise OSError(f"All adapters failed connecting to {dest_host}:{dest_port}: {last_err}")

    def tick_throughput(self):
        now = time.time()
        system_counters = None
        if self._system_counter_reader is not None:
            try:
                system_counters = self._system_counter_reader.read()
            except OSError as exc:
                self._system_counter_reader = None
                if not self._system_counter_error_reported:
                    self._system_counter_error_reported = True
                    self.system_counter_status = f"Windows adapter counters unavailable: {exc}"
                    print(f"System network counters are unavailable: {exc}", file=sys.stderr)

        with self._lock:
            if system_counters is not None:
                unmatched = [
                    adapter.name
                    for adapter in self.adapters.values()
                    if adapter.name.casefold() not in system_counters
                ]
                self.system_counter_status = (
                    f"Windows adapter counters did not match: {', '.join(unmatched)}"
                    if unmatched
                    else "Windows adapter counters available"
                )
            for a in self.adapters.values():
                dt = max(0.05, now - a._last_tick)
                proxy_total = a.bytes_recv + a.bytes_sent
                proxy_delta = max(0, proxy_total - a._last_bytes)
                proxy_raw_bps = proxy_delta / dt
                proxy_prev_bps = a.bps_history[-1] if a.bps_history else 0.0
                proxy_smoothed = (
                    proxy_raw_bps * 0.65 + proxy_prev_bps * 0.35
                    if proxy_raw_bps > 0
                    else (proxy_prev_bps * 0.55 if proxy_prev_bps > 64 else 0.0)
                )
                a._last_bytes = proxy_total
                a.bps_history.append(proxy_smoothed)
                if len(a.bps_history) > 60:
                    a.bps_history.pop(0)

                counters = (
                    system_counters.get(a.name.casefold())
                    if system_counters is not None
                    else None
                )
                if counters is not None:
                    a.system_bytes_recv, a.system_bytes_sent = counters
                    total = a.system_bytes_recv + a.system_bytes_sent
                    self._update_adapter_usage_locked(a, total, now)
                    delta = (
                        max(0, total - a._last_system_total)
                        if a._last_system_total is not None
                        else 0
                    )
                    a._last_system_total = total
                    raw_bps = delta / dt
                    prev_bps = a.system_bps_history[-1] if a.system_bps_history else 0.0
                    smoothed = (
                        raw_bps * 0.65 + prev_bps * 0.35
                        if raw_bps > 0
                        else (prev_bps * 0.55 if prev_bps > 64 else 0.0)
                    )
                else:
                    smoothed = 0.0
                a._last_tick = now
                if a.fail_count > 0 and int(now) % 8 == 0:
                    a.fail_count = max(0, a.fail_count - 1)
                a.system_bps_history.append(smoothed)
                if len(a.system_bps_history) > 60:
                    a.system_bps_history.pop(0)
            if now - self._last_limits_save >= 30:
                self._save_adapter_limits_locked()


# =====================================================================
# 4. SYSTEM-WIDE HTTP/HTTPS (8080) & SOCKS5 (1080) BONDING PROXIES
# =====================================================================

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def relay_bidirectional(
    client_sock: socket.socket,
    remote_sock: socket.socket,
    adapter: NetworkAdapter,
    routing_mgr: AppRoutingManager,
    app_name: str,
):
    def pipe(src: socket.socket, dst: socket.socket, is_upload: bool):
        try:
            while True:
                data = src.recv(32768)
                if not data:
                    break
                adapter.wait_for_rate_limit(len(data), is_upload)
                dst.sendall(data)
                n = len(data)
                if is_upload:
                    adapter.bytes_sent += n
                else:
                    adapter.bytes_recv += n
                routing_mgr.record_bytes(app_name, n)
        except Exception:
            pass
        finally:
            try:
                dst.shutdown(socket.SHUT_WR)
            except Exception:
                pass

    t_up = threading.Thread(target=pipe, args=(client_sock, remote_sock, True), daemon=True)
    t_dn = threading.Thread(target=pipe, args=(remote_sock, client_sock, False), daemon=True)
    t_up.start()
    t_dn.start()
    t_up.join()
    t_dn.join()


class BondingHTTPProxyHandler(socketserver.BaseRequestHandler):
    def handle(self):
        engine: "OmniBondEngine" = self.server.engine  # type: ignore
        client_sock = self.request
        client_sock.settimeout(15.0)
        client_port = self.client_address[1]

        pid, app_name = engine.process_mapper.resolve_client_port(client_port)
        remote_sock = None
        adapter = None

        try:
            raw_head = b""
            while b"\r\n\r\n" not in raw_head and len(raw_head) < 65536:
                chunk = client_sock.recv(4096)
                if not chunk:
                    return
                raw_head += chunk

            header_part, _, body_remainder = raw_head.partition(b"\r\n\r\n")
            lines = header_part.decode("latin-1", errors="replace").split("\r\n")
            if not lines or not lines[0]:
                return

            parts = lines[0].split(" ")
            if len(parts) < 3:
                return
            method, target, version = parts[0], parts[1], parts[2]

            for hline in lines[1:]:
                if hline.lower().startswith("x-omnibond-app:"):
                    override = hline.split(":", 1)[1].strip()
                    if override:
                        app_name = engine.routing_mgr.normalize_app_name(override)

            if engine.routing_mgr.is_internet_blocked(app_name):
                client_sock.sendall(
                    b"HTTP/1.1 403 Forbidden\r\n"
                    b"Content-Type: text/plain; charset=utf-8\r\n"
                    b"Connection: close\r\n\r\n"
                    b"Internet access is disabled for this application."
                )
                return

            if method.upper() == "CONNECT":
                host, _, port_str = target.partition(":")
                port = int(port_str) if port_str else 443
                remote_sock, adapter = engine.adapter_mgr.create_bound_connection(
                    host, port, app_name=app_name, pid=pid
                )
                client_sock.sendall(
                    f"HTTP/1.1 200 Connection Established\r\n"
                    f"X-OmniBond-Adapter: {adapter.ip}\r\n"
                    f"X-OmniBond-App: {app_name}\r\n\r\n".encode("latin-1")
                )
                if body_remainder:
                    adapter.wait_for_rate_limit(len(body_remainder), True)
                    remote_sock.sendall(body_remainder)
                relay_bidirectional(
                    client_sock, remote_sock, adapter, engine.routing_mgr, app_name
                )
            else:
                parsed = urllib.parse.urlsplit(target)
                host = parsed.hostname or ""
                port = parsed.port or 80
                path = parsed.path or "/"
                if parsed.query:
                    path += "?" + parsed.query

                if not host:
                    for hline in lines[1:]:
                        if hline.lower().startswith("host:"):
                            hval = hline.split(":", 1)[1].strip()
                            host, _, p_str = hval.partition(":")
                            port = int(p_str) if p_str else 80
                            break

                remote_sock, adapter = engine.adapter_mgr.create_bound_connection(
                    host, port, app_name=app_name, pid=pid
                )
                rebuilt = [f"{method} {path} {version}"]
                for hline in lines[1:]:
                    low_h = hline.lower()
                    if not low_h.startswith("proxy-connection:") and not low_h.startswith("connection:"):
                        rebuilt.append(hline)
                rebuilt.append("Connection: close")
                rebuilt_bytes = ("\r\n".join(rebuilt) + "\r\n\r\n").encode("latin-1") + body_remainder
                adapter.wait_for_rate_limit(len(rebuilt_bytes), True)
                remote_sock.sendall(rebuilt_bytes)
                adapter.bytes_sent += len(rebuilt_bytes)
                engine.routing_mgr.record_bytes(app_name, len(rebuilt_bytes))

                relay_bidirectional(
                    client_sock, remote_sock, adapter, engine.routing_mgr, app_name
                )

        except Exception:
            pass
        finally:
            if adapter:
                adapter.active_conns = max(0, adapter.active_conns - 1)
                engine.routing_mgr.record_connection_end(app_name)
            if remote_sock:
                try:
                    remote_sock.close()
                except Exception:
                    pass
            try:
                client_sock.close()
            except Exception:
                pass


class BondingSOCKS5ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self):
        engine: "OmniBondEngine" = self.server.engine  # type: ignore
        client_sock = self.request
        client_sock.settimeout(15.0)
        client_port = self.client_address[1]

        pid, app_name = engine.process_mapper.resolve_client_port(client_port)
        remote_sock = None
        adapter = None

        try:
            hdr = client_sock.recv(2)
            if len(hdr) < 2 or hdr[0] != 0x05:
                return
            nmethods = hdr[1]
            client_sock.recv(nmethods)
            client_sock.sendall(b"\x05\x00")

            req = client_sock.recv(4)
            if len(req) < 4 or req[0] != 0x05 or req[1] != 0x01:
                client_sock.sendall(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
                return

            atyp = req[3]
            if atyp == 0x01:
                addr_bytes = client_sock.recv(4)
                host = socket.inet_ntoa(addr_bytes)
            elif atyp == 0x03:
                dlen = client_sock.recv(1)[0]
                host = client_sock.recv(dlen).decode("utf-8", errors="replace")
            elif atyp == 0x04:
                addr_bytes = client_sock.recv(16)
                host = socket.inet_ntop(socket.AF_INET6, addr_bytes)
            else:
                return

            port_bytes = client_sock.recv(2)
            port = struct.unpack("!H", port_bytes)[0]

            if engine.routing_mgr.is_internet_blocked(app_name):
                client_sock.sendall(b"\x05\x02\x00\x01\x00\x00\x00\x00\x00\x00")
                return

            remote_sock, adapter = engine.adapter_mgr.create_bound_connection(
                host, port, app_name=app_name, pid=pid
            )
            client_sock.sendall(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")
            relay_bidirectional(
                client_sock, remote_sock, adapter, engine.routing_mgr, app_name
            )
        except Exception:
            pass
        finally:
            if adapter:
                adapter.active_conns = max(0, adapter.active_conns - 1)
                engine.routing_mgr.record_connection_end(app_name)
            if remote_sock:
                try:
                    remote_sock.close()
                except Exception:
                    pass
            try:
                client_sock.close()
            except Exception:
                pass


# =====================================================================
# 5. WINDOWS SYSTEM PROXY & SIMULTANEOUS MULTI-NIC OPTIMIZER
# =====================================================================

class WindowsSystemOptimizer:
    def __init__(self, adapter_mgr: Optional[AdapterManager] = None, restore_file: str = RULES_FILE + ".sys_restore"):
        self.adapter_mgr = adapter_mgr
        self.restore_file = restore_file
        self.system_proxy_enabled = False
        self._proxy_snapshot: Optional[Dict[str, Tuple[bool, int, Any]]] = None
        self._nic_policy_snapshot: Optional[Tuple[bool, int, Any]] = None
        self._nic_policy_key_existed = False
        self._interface_metrics: Dict[Tuple[str, str], str] = {}
        self.recover_stale_network_state()

    @staticmethod
    def _is_loopback_proxy_server(proxy_server_val: Any) -> bool:
        if not proxy_server_val:
            return False
        text = str(proxy_server_val).strip().lower()
        return "127.0.0.1" in text or "localhost" in text

    @staticmethod
    def _notify_wininet_refresh():
        if not IS_WINDOWS:
            return
        try:
            INTERNET_OPTION_SETTINGS_CHANGED = 39
            INTERNET_OPTION_REFRESH = 37
            wininet = ctypes.windll.wininet
            wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
            wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)
        except Exception:
            pass

    @staticmethod
    def _read_registry_values(key, names: List[str]) -> Dict[str, Tuple[bool, int, Any]]:
        import winreg
        snapshot = {}
        for name in names:
            try:
                value, value_type = winreg.QueryValueEx(key, name)
                snapshot[name] = (True, value_type, value)
            except FileNotFoundError:
                snapshot[name] = (False, 0, None)
        return snapshot

    @classmethod
    def _sanitize_proxy_snapshot(
        cls, snapshot: Dict[str, Tuple[bool, int, Any]]
    ) -> Dict[str, Tuple[bool, int, Any]]:
        """
        Prevents snapshotting a stale OmniBond loopback proxy (127.0.0.1:8080) as the
        user's original proxy setting after an unclean shutdown.
        """
        import winreg
        srv_exists, _, srv_val = snapshot.get("ProxyServer", (False, 0, None))
        if srv_exists and cls._is_loopback_proxy_server(srv_val):
            cleaned = dict(snapshot)
            cleaned["ProxyEnable"] = (True, winreg.REG_DWORD, 0)
            cleaned["ProxyServer"] = (False, 0, None)
            return cleaned
        return snapshot

    @staticmethod
    def _restore_registry_values(key, snapshot: Dict[str, Tuple[bool, int, Any]]):
        import winreg
        for name, (exists, value_type, value) in snapshot.items():
            if exists:
                winreg.SetValueEx(key, name, 0, value_type, value)
            else:
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass

    def _save_restore_journal(self):
        if not self.restore_file:
            return
        try:
            payload = {
                "metrics": [
                    {"family": fam, "index": idx, "metric": met}
                    for (fam, idx), met in self._interface_metrics.items()
                ],
                "timestamp": time.time(),
            }
            with open(self.restore_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            pass

    def _clear_restore_journal(self):
        if not self.restore_file:
            return
        try:
            if os.path.exists(self.restore_file):
                os.remove(self.restore_file)
        except Exception:
            pass

    def recover_stale_network_state(self):
        """
        Automatically detects and cleans up leftover loopback proxy settings or
        modified interface metrics from a previous crashed or killed session.
        """
        if not IS_WINDOWS:
            return
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0,
                winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE,
            ) as key:
                snap = self._read_registry_values(key, ["ProxyEnable", "ProxyServer"])
                pe_exists, _, pe_val = snap.get("ProxyEnable", (False, 0, 0))
                ps_exists, _, ps_val = snap.get("ProxyServer", (False, 0, ""))
                if pe_exists and int(pe_val or 0) == 1 and ps_exists and self._is_loopback_proxy_server(ps_val):
                    winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
                    try:
                        winreg.DeleteValue(key, "ProxyServer")
                    except FileNotFoundError:
                        pass
                    self._notify_wininet_refresh()
        except Exception:
            pass

        if self.restore_file and os.path.exists(self.restore_file):
            try:
                with open(self.restore_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data.get("metrics", []):
                    fam = str(item.get("family", "ipv4"))
                    idx = str(item.get("index", ""))
                    if fam in ("ipv4", "ipv6") and idx.isdigit():
                        subprocess.run(
                            ["netsh", "interface", fam, "set", "interface", idx, "metric=automatic"],
                            capture_output=True,
                            text=True,
                            timeout=2.0,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        )
            except Exception:
                pass
            finally:
                self._clear_restore_journal()

    def set_system_proxy(self, enable: bool, host: str = "127.0.0.1", port: int = HTTP_PROXY_PORT) -> Tuple[bool, str]:
        if not IS_WINDOWS:
            self.system_proxy_enabled = enable
            return True, f"Simulated system proxy {'enabled' if enable else 'disabled'} (non-Windows)."
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0,
                winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE,
            ) as key:
                if enable:
                    if self._proxy_snapshot is None:
                        raw_snap = self._read_registry_values(
                            key, ["ProxyEnable", "ProxyServer", "ProxyOverride"]
                        )
                        self._proxy_snapshot = self._sanitize_proxy_snapshot(raw_snap)
                    winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
                    winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, f"{host}:{port}")
                    winreg.SetValueEx(
                        key,
                        "ProxyOverride",
                        0,
                        winreg.REG_SZ,
                        "localhost;127.*;10.*;192.168.*;172.16.*;172.17.*;172.18.*;172.19.*;172.20.*;172.21.*;172.22.*;172.23.*;172.24.*;172.25.*;172.26.*;172.27.*;172.28.*;172.29.*;172.30.*;172.31.*;<local>",
                    )
                elif self._proxy_snapshot is not None:
                    safe_snap = self._sanitize_proxy_snapshot(self._proxy_snapshot)
                    self._restore_registry_values(key, safe_snap)
                    self._proxy_snapshot = None
                else:
                    winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
                    try:
                        cur_srv, _ = winreg.QueryValueEx(key, "ProxyServer")
                        if self._is_loopback_proxy_server(cur_srv):
                            winreg.DeleteValue(key, "ProxyServer")
                    except FileNotFoundError:
                        pass

            self._notify_wininet_refresh()
            self.system_proxy_enabled = enable
            state = f"Enabled ({host}:{port})" if enable else "Disabled (Direct Routing)"
            return True, f"Windows System-Wide Proxy {state}."
        except Exception as e:
            return False, f"Failed updating Windows proxy: {e}"

    def _set_interface_metrics(
        self, family: str, enabled: bool, messages: List[str], failures: List[str]
    ):
        show_command = ["netsh", "interface", family, "show", "interfaces"]
        valid_if_indices: Set[int] = set()
        valid_names: Set[str] = set()
        if self.adapter_mgr is not None:
            for ad in self.adapter_mgr.get_adapters():
                if ad.enabled and ad.is_online and not self.adapter_mgr.is_virtual_adapter_name(ad.name):
                    if ad.if_index > 0:
                        valid_if_indices.add(ad.if_index)
                    valid_names.add(ad.name.casefold())

        try:
            proc = subprocess.run(
                show_command,
                capture_output=True,
                text=True,
                timeout=2.0,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if proc.returncode != 0:
                raise OSError(proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}")
            for line in proc.stdout.splitlines():
                parts = line.split()
                if len(parts) < 5 or not parts[0].isdigit() or parts[3].lower() != "connected":
                    continue
                index = parts[0]
                if_name = " ".join(parts[4:]).strip()
                if AdapterManager.is_virtual_adapter_name(if_name):
                    continue
                if enabled and (valid_if_indices or valid_names):
                    if int(index) not in valid_if_indices and if_name.casefold() not in valid_names:
                        continue

                key = (family, index)
                if enabled:
                    if key not in self._interface_metrics:
                        self._interface_metrics[key] = "automatic"
                    cmd = ["netsh", "interface", family, "set", "interface", index, "metric=15", "store=active"]
                elif key in self._interface_metrics:
                    self._interface_metrics.pop(key, None)
                    cmd = ["netsh", "interface", family, "set", "interface", index, "metric=automatic"]
                else:
                    continue

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=1.5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if result.returncode != 0:
                    failure = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
                    failures.append(f"Could not update {family.upper()} interface {index}: {failure}")
                    if not enabled:
                        self._interface_metrics[key] = "automatic"

            if self._interface_metrics:
                self._save_restore_journal()
            else:
                self._clear_restore_journal()

            messages.append(
                f"{family.upper()} interface metrics {'equalized (active session)' if enabled else 'restored to automatic'}."
            )
        except (OSError, subprocess.SubprocessError) as exc:
            messages.append(f"Could not update {family.upper()} interface metrics: {exc}")
            failures.append(str(exc))

    def optimize_multi_nic(
        self,
        optimize_ipv4: bool = True,
        optimize_ipv6: bool = False,
        keep_multi_nic: bool = True,
    ) -> Tuple[bool, str]:
        if not IS_WINDOWS:
            return True, "Multi-NIC optimization simulated on non-Windows platform."
        messages = []
        failures = []
        if keep_multi_nic:
            try:
                import winreg
                pol_path = r"Software\Policies\Microsoft\Windows\WcmSvc\GroupPolicy"
                if self._nic_policy_snapshot is None:
                    try:
                        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, pol_path, 0, winreg.KEY_QUERY_VALUE) as key:
                            self._nic_policy_key_existed = True
                            self._nic_policy_snapshot = self._read_registry_values(key, ["fMinimizeConnections"])["fMinimizeConnections"]
                    except FileNotFoundError:
                        self._nic_policy_key_existed = False
                        self._nic_policy_snapshot = (False, 0, None)
                with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, pol_path, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, "fMinimizeConnections", 0, winreg.REG_DWORD, 0)
                messages.append("Kept Windows connection minimization disabled.")
            except PermissionError:
                messages.append("Tip: Run as Administrator to update the multi-network policy.")
                failures.append("The multi-network policy update was denied.")
            except OSError as exc:
                messages.append(f"Could not update the multi-network policy: {exc}")
                failures.append(str(exc))
        elif self._nic_policy_snapshot is not None:
            try:
                import winreg
                pol_path = r"Software\Policies\Microsoft\Windows\WcmSvc\GroupPolicy"
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, pol_path, 0, winreg.KEY_SET_VALUE) as key:
                    self._restore_registry_values(key, {"fMinimizeConnections": self._nic_policy_snapshot})
                if not self._nic_policy_key_existed:
                    try:
                        winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, pol_path)
                    except FileNotFoundError:
                        pass
                self._nic_policy_snapshot = None
                messages.append("Restored the Windows connection minimization policy.")
            except OSError as exc:
                messages.append(f"Could not restore the multi-network policy: {exc}")
                failures.append(str(exc))

        self._set_interface_metrics("ipv4", optimize_ipv4, messages, failures)
        if optimize_ipv6 or any(fam == "ipv6" for fam, _ in self._interface_metrics):
            self._set_interface_metrics("ipv6", optimize_ipv6, messages, failures)

        return not failures, " ".join(messages)

    def repair_network(self) -> Tuple[bool, str]:
        """
        Emergency one-click Windows network repair:
        1. Disables any stuck Windows WinINet proxy (ProxyEnable=0) & refreshes WinINet.
        2. Resets WinHTTP proxy to direct.
        3. Restores all connected physical IPv4 and IPv6 interfaces back to metric=automatic.
        4. Flushes the Windows DNS resolver cache.
        """
        if not IS_WINDOWS:
            self.system_proxy_enabled = False
            self._proxy_snapshot = None
            return True, "Simulated network repair completed (proxy disabled, metrics reset to automatic)."

        steps: List[str] = []
        try:
            import winreg
            internet_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, internet_path, 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
                try:
                    cur_srv, _ = winreg.QueryValueEx(key, "ProxyServer")
                    if self._is_loopback_proxy_server(cur_srv):
                        winreg.DeleteValue(key, "ProxyServer")
                except FileNotFoundError:
                    pass
            self._proxy_snapshot = None
            self.system_proxy_enabled = False
            self._notify_wininet_refresh()
            steps.append("WinINet proxy reset to Direct.")
        except Exception as e:
            steps.append(f"Proxy reset warning: {e}")

        for family in ("ipv4", "ipv6"):
            try:
                proc = subprocess.run(
                    ["netsh", "interface", family, "show", "interfaces"],
                    capture_output=True,
                    text=True,
                    timeout=2.0,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                for line in proc.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 5 and parts[0].isdigit() and parts[3].lower() == "connected":
                        idx = parts[0]
                        if_name = " ".join(parts[4:]).strip()
                        if "loopback" in if_name.lower():
                            continue
                        subprocess.run(
                            ["netsh", "interface", family, "set", "interface", idx, "metric=automatic"],
                            capture_output=True,
                            text=True,
                            timeout=1.5,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        )
            except Exception:
                pass
        self._interface_metrics.clear()
        self._clear_restore_journal()
        steps.append("IPv4/IPv6 interface metrics restored to automatic.")

        try:
            subprocess.run(
                ["netsh", "winhttp", "reset", "proxy"],
                capture_output=True,
                text=True,
                timeout=2.0,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass

        try:
            subprocess.run(
                ["ipconfig", "/flushdns"],
                capture_output=True,
                text=True,
                timeout=2.0,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            steps.append("DNS cache flushed.")
        except Exception:
            pass

        if self.adapter_mgr is not None:
            try:
                self.adapter_mgr.refresh_adapters()
            except Exception:
                pass

        return True, " ".join(steps)

    def restore_system_settings(self) -> List[str]:
        errors: List[str] = []
        if not IS_WINDOWS:
            self.system_proxy_enabled = False
            return errors

        try:
            import winreg
            internet_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, internet_path, 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
                if self._proxy_snapshot is not None:
                    safe_snap = self._sanitize_proxy_snapshot(self._proxy_snapshot)
                    self._restore_registry_values(key, safe_snap)
                    self._proxy_snapshot = None
                else:
                    winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
                    try:
                        cur_srv, _ = winreg.QueryValueEx(key, "ProxyServer")
                        if self._is_loopback_proxy_server(cur_srv):
                            winreg.DeleteValue(key, "ProxyServer")
                    except FileNotFoundError:
                        pass
            self.system_proxy_enabled = False
            self._notify_wininet_refresh()
        except Exception as e:
            errors.append(f"Could not restore Windows proxy settings: {e}")

        try:
            import winreg
            pol_path = r"Software\Policies\Microsoft\Windows\WcmSvc\GroupPolicy"
            if self._nic_policy_snapshot is not None:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, pol_path, 0, winreg.KEY_SET_VALUE) as key:
                    self._restore_registry_values(key, {"fMinimizeConnections": self._nic_policy_snapshot})
                if not self._nic_policy_key_existed:
                    try:
                        winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, pol_path)
                    except FileNotFoundError:
                        pass
                self._nic_policy_snapshot = None
            for (family, idx) in list(self._interface_metrics.keys()):
                proc = subprocess.run(
                    ["netsh", "interface", family, "set", "interface", idx, "metric=automatic"],
                    capture_output=True,
                    text=True,
                    timeout=3.0,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if proc.returncode != 0:
                    errors.append(f"Could not restore {family.upper()} metric for interface {idx}: {proc.stderr.strip() or proc.stdout.strip()}")
            self._interface_metrics.clear()
            self._clear_restore_journal()
        except Exception as e:
            errors.append(f"Could not restore multi-NIC settings: {e}")
        return errors


# =====================================================================
# 6. TURBO DOWNLOAD & STREAM (.M3U8) ACCELERATOR
# =====================================================================

@dataclass
class DownloadBlock:
    index: int
    start: int
    end: int
    status: str = "pending"
    adapter_ip: str = ""
    color: str = "#18181f"
    data: Optional[bytes] = None


class TurboAccelerator:
    def __init__(self, adapter_mgr: AdapterManager, routing_mgr: AppRoutingManager):
        self.adapter_mgr = adapter_mgr
        self.routing_mgr = routing_mgr
        self.lock = threading.Lock()
        self.blocks: List[DownloadBlock] = []
        self.status_text: str = "Ready · Awaiting stream or file URL"
        self.is_running: bool = False
        self.progress_pct: float = 0.0
        self.speed_bps: float = 0.0
        self.total_bytes: int = 0
        self.downloaded_bytes: int = 0
        self.last_output_path: str = ""

    @staticmethod
    def _decode_chunked_body(raw_body: bytes) -> bytes:
        out = bytearray()
        pos = 0
        n = len(raw_body)
        while pos < n:
            line_end = raw_body.find(b"\r\n", pos)
            if line_end == -1:
                break
            size_str = raw_body[pos:line_end].split(b";", 1)[0].strip()
            if not size_str:
                break
            try:
                chunk_len = int(size_str, 16)
            except ValueError:
                break
            if chunk_len == 0:
                break
            chunk_start = line_end + 2
            chunk_end = chunk_start + chunk_len
            out.extend(raw_body[chunk_start:chunk_end])
            pos = chunk_end + 2
        return bytes(out) if out else raw_body

    def _http_get_bound(
        self, url: str, adapter: NetworkAdapter, byte_range: Optional[Tuple[int, int]] = None, timeout: float = 8.0
    ) -> Tuple[int, Dict[str, str], bytes]:
        current_url = url
        for _redirect_hop in range(5):
            parsed = urllib.parse.urlsplit(current_url)
            scheme = parsed.scheme.lower()
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or (443 if scheme == "https" else 80)
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query

            is_loopback = host in ("127.0.0.1", "localhost", "::1")
            target_ip = "127.0.0.1" if is_loopback else self.adapter_mgr.resolve_host_ipv4(host)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            self.adapter_mgr.bind_socket_to_adapter(sock, adapter, is_loopback_dest=is_loopback)

            self.routing_mgr.record_connection_start(TURBO_APP_KEY, os.getpid(), adapter.ip)
            adapter.active_conns += 1
            try:
                sock.connect((target_ip, port))
                if scheme == "https":
                    import ssl
                    ctx = ssl.create_default_context()
                    sock = ctx.wrap_socket(sock, server_hostname=host)

                headers = [
                    f"GET {path} HTTP/1.1",
                    f"Host: {host}:{port}" if parsed.port else f"Host: {host}",
                    "User-Agent: OmniBond/5.0",
                    "Connection: close",
                ]
                if byte_range is not None:
                    headers.append(f"Range: bytes={byte_range[0]}-{byte_range[1]}")
                req_bytes = ("\r\n".join(headers) + "\r\n\r\n").encode("latin-1")
                adapter.wait_for_rate_limit(len(req_bytes), True)
                sock.sendall(req_bytes)
                adapter.bytes_sent += len(req_bytes)
                self.routing_mgr.record_bytes(TURBO_APP_KEY, len(req_bytes))

                buf = bytearray()
                while True:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    adapter.wait_for_rate_limit(len(chunk), False)
                    buf.extend(chunk)
                    adapter.bytes_recv += len(chunk)
                    self.routing_mgr.record_bytes(TURBO_APP_KEY, len(chunk))

                raw = bytes(buf)
                head_bytes, _, body = raw.partition(b"\r\n\r\n")
                head_lines = head_bytes.decode("latin-1", errors="replace").split("\r\n")
                status_code = int(head_lines[0].split(" ")[1]) if len(head_lines[0].split(" ")) > 1 else 200
                resp_headers = {}
                for h in head_lines[1:]:
                    if ":" in h:
                        k, v = h.split(":", 1)
                        resp_headers[k.strip().lower()] = v.strip()

                if status_code in (301, 302, 303, 307, 308) and "location" in resp_headers:
                    current_url = urllib.parse.urljoin(current_url, resp_headers["location"])
                    continue

                if "chunked" in resp_headers.get("transfer-encoding", "").lower():
                    body = self._decode_chunked_body(body)

                return status_code, resp_headers, body
            finally:
                adapter.active_conns = max(0, adapter.active_conns - 1)
                self.routing_mgr.record_connection_end(TURBO_APP_KEY)
                try:
                    sock.close()
                except Exception:
                    pass

        raise RuntimeError(f"Too many HTTP redirects while requesting {url}")

    def download_url(
        self, url: str, output_path: str, block_size: int = 1024 * 1024
    ) -> str:
        self.is_running = True
        self.progress_pct = 0.0
        self.speed_bps = 0.0
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.status_text = f"Probing {url}..."
        t0 = time.perf_counter()

        try:
            adapters = self.adapter_mgr.get_exclusive_or_bonded_adapters(TURBO_APP_KEY)
            if not adapters:
                raise RuntimeError("No network adapters available.")

            if ".m3u8" in url.lower():
                return self._download_hls_stream(url, output_path, adapters, t0)

            status, hdrs, first_body, probe_adapter = 0, {}, b"", adapters[0]
            last_probe_err = None
            for cand in adapters:
                try:
                    status, hdrs, first_body = self._http_get_bound(url, cand, byte_range=(0, 0))
                    probe_adapter = cand
                    last_probe_err = None
                    break
                except Exception as exc:
                    last_probe_err = exc
            if last_probe_err is not None and status == 0:
                raise last_probe_err

            total_size = 0
            if "content-range" in hdrs:
                m = re.search(r"/(\d+)", hdrs["content-range"])
                if m:
                    total_size = int(m.group(1))
            elif "content-length" in hdrs and status == 200:
                total_size = len(first_body)

            if total_size <= 0 or status == 200:
                if status == 200 and first_body:
                    full_body = first_body
                else:
                    _, _, full_body = self._http_get_bound(url, probe_adapter, byte_range=None)
                with open(output_path, "wb") as f:
                    f.write(full_body)
                self.total_bytes = len(full_body)
                self.downloaded_bytes = len(full_body)
                self.blocks = [
                    DownloadBlock(0, 0, len(full_body) - 1, "done", adapters[0].ip, adapters[0].color)
                ]
                self.progress_pct = 100.0
                elapsed = max(0.001, time.perf_counter() - t0)
                self.speed_bps = len(full_body) / elapsed
                self.status_text = f"Completed · {len(full_body):,} bytes via {adapters[0].ip}"
                self.last_output_path = output_path
                return output_path

            self.total_bytes = total_size
            num_blocks = max(1, math.ceil(total_size / block_size))
            blocks: List[DownloadBlock] = []
            for i in range(num_blocks):
                start = i * block_size
                end = min(total_size - 1, (i + 1) * block_size - 1)
                blocks.append(DownloadBlock(index=i, start=start, end=end))
            self.blocks = blocks

            q_pending: "queue.Queue[DownloadBlock]" = queue.Queue()
            for b in blocks:
                q_pending.put(b)

            done_lock = threading.Lock()
            completed_count = 0
            bytes_done = 0

            def worker(adapter: NetworkAdapter):
                nonlocal completed_count, bytes_done
                while True:
                    try:
                        blk = q_pending.get_nowait()
                    except queue.Empty:
                        in_progress = [b for b in blocks if b.status == "active" and b.data is None]
                        if not in_progress:
                            break
                        blk = in_progress[0]
                        blk.status = "endgame"

                    if blk.data is not None:
                        continue

                    if blk.status == "pending":
                        blk.status = "active"
                    blk.adapter_ip = adapter.ip
                    blk.color = adapter.color

                    try:
                        st, _, chunk = self._http_get_bound(
                            url, adapter, byte_range=(blk.start, blk.end)
                        )
                        if st in (200, 206) and chunk:
                            with done_lock:
                                if blk.data is None:
                                    blk.data = chunk
                                    blk.status = "done"
                                    blk.adapter_ip = adapter.ip
                                    blk.color = adapter.color
                                    completed_count += 1
                                    bytes_done += len(chunk)
                                    self.downloaded_bytes = bytes_done
                                    self.progress_pct = (completed_count / num_blocks) * 100.0
                                    dt = max(0.001, time.perf_counter() - t0)
                                    self.speed_bps = bytes_done / dt
                                    self.status_text = (
                                        f"Accelerating · {completed_count}/{num_blocks} blocks "
                                        f"({self.progress_pct:.0f}%)"
                                    )
                    except Exception:
                        with done_lock:
                            if blk.data is None:
                                blk.status = "pending"
                                q_pending.put(blk)

            threads = []
            workers_per_adapter = max(1, min(4, math.ceil(num_blocks / max(1, len(adapters)))))
            for adapter in adapters:
                for _ in range(workers_per_adapter):
                    t = threading.Thread(target=worker, args=(adapter,), daemon=True)
                    t.start()
                    threads.append(t)

            for t in threads:
                t.join()

            with open(output_path, "wb") as f:
                for b in blocks:
                    if b.data:
                        f.write(b.data)

            elapsed = max(0.001, time.perf_counter() - t0)
            self.speed_bps = total_size / elapsed
            used_ips = sorted({b.adapter_ip for b in blocks if b.adapter_ip})
            self.status_text = (
                f"Done · {total_size:,} bytes in {elapsed:.2f}s via {', '.join(used_ips)}"
            )
            self.last_output_path = output_path
            return output_path
        finally:
            self.is_running = False

    def _download_hls_stream(
        self, m3u8_url: str, output_path: str, adapters: List[NetworkAdapter], t0: float
    ) -> str:
        _, _, playlist_bytes = self._http_get_bound(m3u8_url, adapters[0])
        playlist_text = playlist_bytes.decode("utf-8", errors="replace")
        seg_urls = []
        for line in playlist_text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                seg_urls.append(urllib.parse.urljoin(m3u8_url, line))

        self.blocks = [
            DownloadBlock(index=i, start=i, end=i) for i in range(len(seg_urls))
        ]
        q_seg: "queue.Queue[int]" = queue.Queue()
        for i in range(len(seg_urls)):
            q_seg.put(i)

        done_lock = threading.Lock()
        done_segs = 0

        def seg_worker(adapter: NetworkAdapter):
            nonlocal done_segs
            while True:
                try:
                    idx = q_seg.get_nowait()
                except queue.Empty:
                    break
                blk = self.blocks[idx]
                blk.status = "active"
                blk.adapter_ip = adapter.ip
                blk.color = adapter.color
                _, _, seg_data = self._http_get_bound(seg_urls[idx], adapter)
                with done_lock:
                    blk.data = seg_data
                    blk.status = "done"
                    done_segs += 1
                    self.progress_pct = (done_segs / max(1, len(seg_urls))) * 100.0

        threads = [
            threading.Thread(target=seg_worker, args=(a,), daemon=True)
            for a in adapters
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        total_bytes = 0
        with open(output_path, "wb") as f:
            for b in self.blocks:
                if b.data:
                    f.write(b.data)
                    total_bytes += len(b.data)

        elapsed = max(0.001, time.perf_counter() - t0)
        self.total_bytes = total_bytes
        self.downloaded_bytes = total_bytes
        self.progress_pct = 100.0
        self.speed_bps = total_bytes / elapsed
        self.status_text = f"HLS Stream Stitched ({len(seg_urls)} segments, {total_bytes:,} bytes)"
        self.last_output_path = output_path
        return output_path


# =====================================================================
# 7. WEB STUDIO UI (127.0.0.1:8085) - WITH PER-APP GRAPHS, FILTERS & FOCUS
# =====================================================================

WEB_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OmniBond</title>
<style>
  :root {
    --bg: #09090b;
    --panel: #0c0c0f;
    --card-hover: #121217;
    --hairline: #1e1e24;
    --text: #fafafa;
    --muted: #a1a1aa;
    --dim: #52525b;
    --amber: #f59e0b;
    --emerald: #10b981;
    --cyan: #38bdf8;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--hairline);
    color: var(--text);
    font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }

  .topbar {
    background: var(--panel);
    padding: 13px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
  }
  .brand-row { display: flex; align-items: center; gap: 12px; }
  .ob-badge {
    background: var(--amber);
    color: #09090b;
    font-weight: 900;
    font-size: 12px;
    padding: 4px 7px;
  }
  .brand-title { font-size: 16px; font-weight: 800; }
  .brand-sub {
    font-family: 'Consolas', monospace;
    font-size: 11px;
    color: var(--muted);
    margin-top: 2px;
  }
  .top-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

  .btn {
    background: #14141b;
    color: var(--text);
    border: 1px solid #272732;
    padding: 8px 14px;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.14s ease;
    position: relative;
  }
  .btn:hover { background: #1f1f2a; border-color: var(--amber); transform: translateY(-1px); }
  .btn.primary { background: #fafafa; color: #09090b; border-color: #fafafa; }
  .btn.primary:hover { background: var(--amber); border-color: var(--amber); }
  .btn.amber { background: var(--amber); color: #09090b; border-color: var(--amber); }
  .btn.active { color: var(--amber); border-color: var(--amber); }

  .workspace-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.18fr);
    gap: 1px;
    background: var(--hairline);
    flex: 1;
    min-height: 0;
  }
  @media (max-width: 1100px) { .workspace-grid { grid-template-columns: 1fr; } }

  .section-container {
    background: var(--panel);
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
  }
  .section-head {
    padding: 13px 18px 11px 18px;
    border-bottom: 1px solid var(--hairline);
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
  }
  .kicker {
    font-family: 'Consolas', monospace;
    font-size: 10.5px;
    font-weight: 700;
    color: var(--amber);
    letter-spacing: 0.8px;
    text-transform: uppercase;
  }
  .section-title { font-size: 16px; font-weight: 800; margin-top: 2px; }

  .bento-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
    gap: 1px;
    background: var(--hairline);
    border-bottom: 1px solid var(--hairline);
  }
  .adapter-scroll {
    width: 100%;
    overflow-x: auto;
    overscroll-behavior-x: contain;
    scrollbar-color: #3f3f46 #0c0c0f;
  }
  #adapterBentoGrid {
    display: flex;
    width: max-content;
    min-width: 100%;
  }
  #adapterBentoGrid .bento-card { flex: 0 0 280px; }
  .app-grid-scroll {
    min-height: 240px;
    max-height: min(58vh, 680px);
    overflow: auto;
    overscroll-behavior: contain;
    scrollbar-color: #3f3f46 #0c0c0f;
  }
  #appBentoGrid { border-bottom: 0; }
  #appBentoGrid.list-view { display: flex; flex-direction: column; gap: 1px; }
  #appBentoGrid.list-view .bento-card {
    width: 100%;
    min-height: 0;
    flex-direction: column;
    gap: 10px;
  }
  #appBentoGrid.list-view .bento-card > div:first-child { width: 100%; min-width: 0; }
  #appBentoGrid.list-view .card-actions { flex: 0 0 auto; align-self: stretch; width: 100%; }
  #appBentoGrid.list-view .card-select-wrap { width: 100%; }
  #appBentoGrid.list-view .sparkline-box { width: 100%; max-width: none; }
  .app-card-controls { display:flex; flex:0 0 auto; gap:6px; align-items:center; justify-content:flex-end; flex-wrap:nowrap; }
  .bento-card {
    background: var(--panel);
    padding: 13px 15px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    min-height: 175px;
    transition: background 0.15s;
  }
  .bento-card:hover { background: var(--card-hover); }
  .card-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
  }
  .num-badge {
    font-family: 'Consolas', monospace;
    font-size: 11px;
    font-weight: 800;
    color: #09090b;
    padding: 2px 6px;
  }
  .card-meta-links {
    font-family: 'Consolas', monospace;
    font-size: 10px;
    color: var(--muted);
  }
  .focus-link, .favorite-btn, .app-card-controls .card-btn {
    box-sizing: border-box;
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    height: 27px;
    padding: 0 7px;
    white-space: nowrap;
    font-family: 'Consolas', monospace;
    font-size: 9px;
    font-weight: 800;
    line-height: 1;
    cursor: pointer;
  }
  .favorite-btn {
    width: 30px;
    padding: 0;
    font-size: 14px;
  }
  .focus-link, .app-card-controls .card-btn {
    width: 76px;
    color: var(--text);
    background: #121218;
    border: 1px solid #30303b;
    text-transform: uppercase;
  }
  .focus-link:hover, .app-card-controls .card-btn:hover {
    background: #1c1c27;
    border-color: var(--amber);
  }
  .focus-link {
  }
  .favorite-btn {
    color: var(--text);
    background: #121218;
    border: 1px solid #30303b;
  }
  .favorite-btn.active { color: var(--amber); border-color: var(--amber); }

  .card-identity {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 9px;
  }
  .card-icon {
    width: 34px;
    height: 34px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    font-size: 12px;
    color: #fff;
    flex-shrink: 0;
  }
  .card-name { font-size: 14.5px; font-weight: 800; }
  .card-desc { font-size: 11px; color: var(--muted); margin-top: 1px; }

  .status-box {
    display: inline-block;
    font-family: 'Consolas', monospace;
    font-size: 10px;
    font-weight: 700;
    padding: 2px 6px;
    background: rgba(16, 185, 129, 0.08);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.35);
    margin-bottom: 6px;
  }
  .status-box.pinned {
    background: rgba(56, 189, 248, 0.1);
    color: #38bdf8;
    border-color: rgba(56, 189, 248, 0.4);
  }
  .status-box.quota-reached {
    background:rgba(239,68,68,.1);
    color:#f87171;
    border-color:rgba(239,68,68,.4);
  }

  .sparkline-box {
    background: #07070a;
    border: 1px solid #181820;
    padding: 4px 6px;
    margin-bottom: 8px;
  }
  .sparkline-head {
    display: flex;
    justify-content: space-between;
    font-family: 'Consolas', monospace;
    font-size: 9.5px;
    color: var(--muted);
    margin-bottom: 2px;
  }
  canvas.app-spark { width: 100%; height: 32px; display: block; }

  .card-actions { display: flex; gap: 6px; margin-top: auto; min-width: 0; }
  .card-btn, .card-select {
    flex: 1;
    background: #09090d;
    color: var(--text);
    border: 1px solid #272732;
    padding: 6px 8px;
    font-size: 10.5px;
    font-weight: 800;
    text-transform: uppercase;
    cursor: pointer;
  }
  .card-btn:hover, .styled-select-trigger:hover { border-color: var(--amber); background: #14141c; }
  .styled-select-wrap {
    position:relative;
    display:inline-flex;
    flex:1 1 auto;
    min-width:0;
    vertical-align:middle;
  }
  .styled-select-trigger {
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:8px;
    min-width:0;
    width:100%;
    height:31px;
    padding:5px 9px;
    overflow:hidden;
    color:var(--text);
    background:#14141b;
    border:1px solid #272732;
    border-radius:0;
    font:700 10px 'Segoe UI',system-ui,sans-serif;
    text-align:left;
    cursor:pointer;
  }
  .styled-select-wrap.card-select-wrap .styled-select-trigger {
    height:auto;
    min-height:31px;
    padding:6px 30px 6px 8px;
    color:var(--text);
    background:#09090d;
    border-color:#272732;
    font-size:10.5px;
    font-weight:800;
    text-transform:uppercase;
    background-image:linear-gradient(45deg,transparent 50%,var(--app-accent,var(--amber)) 50%),linear-gradient(135deg,var(--app-accent,var(--amber)) 50%,transparent 50%);
    background-position:calc(100% - 14px) 50%,calc(100% - 10px) 50%;
    background-size:4px 4px,4px 4px;
    background-repeat:no-repeat;
  }
  .styled-select-wrap.filter-select-wrap { flex:0 0 142px; height:31px; }
  .styled-select-wrap.sort-select-wrap { flex:0 0 154px; height:31px; margin-left:0; }
  .styled-select-wrap.limit-unit-select-wrap { flex:0 0 74px; }
  .styled-select-trigger-label {
    min-width:0;
    overflow:hidden;
    text-overflow:ellipsis;
    white-space:nowrap;
  }
  .styled-select-chevron { flex:0 0 auto; color:var(--amber); font-size:9px; }
  .styled-select-wrap.card-select-wrap .styled-select-chevron { display:none; }
  .styled-native-select {
    position:absolute!important;
    width:1px!important;
    height:1px!important;
    padding:0!important;
    margin:-1px!important;
    overflow:hidden!important;
    clip:rect(0,0,0,0)!important;
    white-space:nowrap!important;
    border:0!important;
  }
  .styled-select-menu {
    position:fixed;
    z-index:1000;
    display:none;
    width:max-content;
    min-width:0;
    max-width:min(360px,calc(100vw - 16px));
    max-height:min(280px,calc(100vh - 16px));
    overflow-y:auto;
    padding:4px;
    color:var(--text);
    background:#101016;
    border:1px solid #3a3a46;
    box-shadow:0 12px 30px rgba(0,0,0,.55);
  }
  .styled-select-wrap.open .styled-select-menu { display:block; }
  .styled-select-option {
    display:block;
    width:100%;
    padding:6px 8px;
    color:var(--text);
    background:transparent;
    border:0;
    font:700 10px 'Segoe UI',system-ui,sans-serif;
    line-height:1.4;
    text-align:left;
    white-space:normal;
    overflow-wrap:anywhere;
    cursor:pointer;
  }
  .styled-select-option:hover, .styled-select-option[aria-selected="true"] {
    color:#fff;
    background:#292932;
  }
  .view-switch { display:flex; align-items:center; gap:4px; }
  .view-switch .btn { padding:5px 9px; }
  .sort-select-wrap { margin-left:auto; }

  .router-toolbar {
    padding: 9px 18px;
    border-bottom: 1px solid var(--hairline);
    display: flex;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    background: #08080b;
  }
  .router-tool-group { display:flex; min-width:0; align-items:center; flex-wrap:wrap; gap:6px; }
  .router-tool-group:first-child { flex:1 1 auto; flex-wrap:nowrap; }
  .router-tool-group:last-child { flex:0 0 auto; justify-content:flex-end; margin-left:auto; }
  .view-switch { flex:0 0 auto; }
  .router-toolbar .btn { height:31px; padding:5px 10px; display:inline-flex; align-items:center; justify-content:center; }
  .adapter-limits {
    border-bottom:1px solid var(--hairline);
    background:#0b0b10;
  }
  .adapter-limits > summary {
    padding:9px 18px;
    color:var(--text);
    font:700 10px Consolas,monospace;
    letter-spacing:.4px;
    cursor:pointer;
    list-style:none;
  }
  .adapter-limits > summary::-webkit-details-marker { display:none; }
  .adapter-limits > summary::after { content:"+"; float:right; color:var(--amber); font-size:14px; }
  .adapter-limits[open] > summary::after { content:"−"; }
  .adapter-limit-note { padding:0 18px 9px; color:var(--muted); font-size:10px; line-height:1.5; }
  .adapter-limit-grid {
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(270px,1fr));
    gap:1px;
    background:var(--hairline);
  }
  .adapter-limit-card { background:#101016; padding:12px 14px; }
  .adapter-limit-title { margin-bottom:9px; font-size:12px; font-weight:800; }
  .adapter-limit-fields { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
  .adapter-limit-field { display:flex; flex-direction:column; gap:4px; color:var(--muted); font:700 9px Consolas,monospace; }
  .adapter-limit-field input {
    min-width:0;
    width:100%;
    height:30px;
    padding:5px 8px;
    color:var(--text);
    background:#09090d;
    border:1px solid #30303b;
    font:11px Consolas,monospace;
  }
  .adapter-limit-field input:focus, .adapter-limit-field select:focus { outline:none; border-color:var(--amber); }
  .limit-cycle-control { display:flex; gap:4px; }
  .adapter-limit-field .limit-cycle-control input { flex:1; }
  .adapter-limit-field .limit-cycle-control select {
    width:74px;
    color:var(--text);
    background:#09090d;
    border:1px solid #30303b;
    color-scheme:dark;
    font:10px Consolas,monospace;
  }
  .limit-mode-control { display:grid; gap:5px; }
  .limit-mode-control > input { width:100%; }
  .adapter-limit-field input:disabled { display:none; }
  .adapter-limit-meta { min-height:16px; margin-top:8px; color:var(--muted); font:10px Consolas,monospace; }
  .adapter-limit-meta.error, .modal-status.error { color:#f87171; }
  .adapter-limit-actions { display:flex; justify-content:flex-end; margin-top:8px; }
  .adapter-limit-actions .btn { height:29px; padding:4px 9px; }
  .adapter-limit-actions .btn:disabled { opacity:.55; cursor:wait; }
  .card-btn:disabled { opacity:.65; cursor:not-allowed; }
  .network-tuning-panel { width:min(500px,100%); }
  .tuning-options { display:grid; gap:9px; margin:16px 0; }
  .tuning-option {
    display:flex;
    align-items:flex-start;
    gap:10px;
    padding:11px 12px;
    background:#101016;
    border:1px solid #272732;
    color:var(--text);
    cursor:pointer;
  }
  .tuning-option input { accent-color:var(--amber); margin:2px 0 0; }
  .tuning-option strong { display:block; font-size:11px; }
  .tuning-option small { display:block; margin-top:3px; color:var(--muted); font-size:10px; line-height:1.5; }
  .tuning-limit-heading {
    margin:18px 0 8px;
    color:var(--amber);
    font:700 10px Consolas,monospace;
    letter-spacing:.5px;
  }
  .network-tuning-panel .adapter-limit-grid { margin-top:8px; }
  .network-tuning-panel .adapter-limit-card { border:1px solid #272732; }
  .network-tuning-panel .adapter-limit-fields { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .network-tuning-panel .adapter-limit-note { padding:0; }
  .modal-status { min-height:15px; margin-top:12px; color:var(--muted); font:10px Consolas,monospace; }
  .add-program-modal {
    position:fixed; inset:0; z-index:20; display:none;
    align-items:center; justify-content:center; padding:18px;
    background:rgba(0,0,0,.72);
  }
  .add-program-modal.open { display:flex; }
  .add-program-panel {
    width:min(460px,100%); max-height:min(90vh,620px); overflow:auto;
    background:#0c0c12; border:1px solid #30303b; border-top:2px solid var(--amber);
    padding:20px; box-shadow:0 18px 60px rgba(0,0,0,.6);
  }
  .add-program-panel h3 { font-size:15px; margin-bottom:18px; }
  .modal-field { display:flex; flex-direction:column; gap:7px; margin:13px 0; }
  .modal-field label { color:var(--muted); font:700 10px Consolas,monospace; text-transform:uppercase; }
  .modal-field select,.modal-field input {
    min-width:0; width:100%; background:#09090d; color:var(--text);
    border:1px solid #30303b; padding:9px 10px; font-size:12px;
  }
  .modal-field select {
    color-scheme: dark;
    appearance: none;
    padding-right: 34px;
    background-image: linear-gradient(45deg, transparent 50%, var(--amber) 50%), linear-gradient(135deg, var(--amber) 50%, transparent 50%);
    background-position: calc(100% - 15px) 50%, calc(100% - 11px) 50%;
    background-size: 4px 4px, 4px 4px;
    background-repeat: no-repeat;
  }
  .modal-field select option, .card-select option {
    color: var(--text);
    background: #0d0d12;
  }
  .modal-field select:focus, .modal-field input:focus {
    outline: none;
    border-color: var(--amber);
    box-shadow: 0 0 0 2px rgba(245, 158, 11, .14);
  }
  .modal-actions { display:flex; justify-content:flex-end; gap:8px; margin-top:16px; }
  /* Two-row non-overlapping Chart Section */
  .chart-section {
    padding: 14px 18px 16px 18px;
    flex: 1;
    display: flex;
    flex-direction: column;
  }
  .chart-row-1 {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  .chart-row-2 {
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
    margin-bottom: 10px;
    font-family: 'Consolas', monospace;
    font-size: 11px;
    color: var(--muted);
  }
  .legend-pill { display: flex; align-items: center; gap: 6px; }
  .legend-dot { width: 8px; height: 8px; border-radius: 50%; }
  .canvas-box { position: relative; width: 100%; flex: 1; min-height: 250px; }
  canvas#telemetryChart { width: 100%; height: 100%; display: block; }
  .speed-summary { display:flex; align-items:center; gap:8px; font-family:'Consolas',monospace; font-size:11px; }
  .speed-chip { border:1px solid #272732; background:#14141d; padding:5px 8px; color:var(--amber); white-space:nowrap; }

  /* Unified Bottom Turbo Accelerator Container */
  .bottom-container { background: var(--panel); padding: 14px 20px 18px 20px; }
  .turbo-unified-box {
    margin-top: 10px;
    background: transparent;
    border: 0;
    padding: 0;
  }
  .dl-input-row { display: flex; gap: 8px; align-items: center; }
  .dl-url-input {
    flex: 1;
    background: #0c0c12;
    color: var(--text);
    border: 1px solid #22222c;
    padding: 9px 12px;
    font-family: 'Consolas', monospace;
    font-size: 12px;
    outline: none;
  }
  .dl-url-input:focus { border-color: var(--amber); }
  .progress-track {
    width: 100%;
    height: 8px;
    background: #12121a;
    margin-top: 10px;
    margin-bottom: 8px;
    overflow: hidden;
    position: relative;
  }
  .progress-fill {
    height: 100%;
    width: 0%;
    background: linear-gradient(90deg, var(--amber), var(--emerald), var(--cyan));
    transition: width 0.2s ease;
  }
  .dl-meta-row {
    display: flex;
    justify-content: space-between;
    font-family: 'Consolas', monospace;
    font-size: 11px;
    color: var(--muted);
    margin-bottom: 6px;
  }
  .block-strip { display: flex; flex-wrap: wrap; gap: 3px; min-height: 18px; }
  .blk { width: 12px; height: 10px; background: #181822; }
  @media (max-width: 720px) {
    .chart-section { min-height: 340px; }
    #appBentoGrid.list-view .bento-card { flex-direction: column; }
    .dl-input-row { flex-wrap:wrap; }
    .dl-url-input { min-width:180px; }
    .top-actions { justify-content:flex-end; }
  }
  @media (max-width: 560px) {
    .router-tool-group { width:100%; }
    .router-tool-group:first-child { flex-wrap:wrap; }
    .router-tool-group:last-child { margin-left:0; }
    .styled-select-wrap.sort-select-wrap { margin-left:0; flex:1 1 140px; }
    .router-tool-group:last-child .btn { flex:1; }
  }
</style>
</head>
<body>

  <div class="topbar">
    <div class="brand-row">
      <div class="ob-badge">OB</div>
      <div>
        <div class="brand-title">OmniBond</div>
        <div class="brand-sub" id="serverEndpoints">
          &bull; HTTP/HTTPS 127.0.0.1:8080 &nbsp;&bull; SOCKS5 127.0.0.1:1080 &nbsp;&bull; Web Dashboard 127.0.0.1:8085
        </div>
      </div>
    </div>
    <div class="top-actions">
      <button class="btn primary" id="btnSysProxy" title="Route all Windows HTTP/HTTPS & SOCKS5 traffic across active adapters" onclick="toggleSystemProxy()">◈ Bonding: Off</button>
      <button class="btn" title="Configure Windows multi-network and IP route optimization" onclick="openNetworkTuning()">⚙ Network Tuning</button>
      <button class="btn" title="Reset Windows proxy to Direct, restore automatic interface metrics, and flush DNS" onclick="repairNetwork()">🩹 Repair Network</button>
      <button class="btn" id="btnGraphMode" aria-live="polite" aria-pressed="false" onclick="toggleGraphMode()">∿ Master Speed</button>
      <button class="btn" title="Re-scan Windows network adapters and IPv4 addresses" onclick="refreshAdapters()">⟳ Rescan Adapters</button>
    </div>
  </div>

  <div class="workspace-grid">
    <!-- 01 HARDWARE INTERFACES -->
    <div class="section-container">
      <div class="section-head">
        <div>
          <div class="kicker">01 / HARDWARE INTERFACES &middot; SOCKET BINDING</div>
          <div class="section-title">Active Network Adapters</div>
        </div>
        <div class="card-meta-links" id="adapterCountMeta">0 INTERFACES</div>
      </div>

      <div class="adapter-scroll" id="adapterScroll"><div class="bento-grid" id="adapterBentoGrid"></div></div>

      <div class="chart-section">
        <div class="chart-row-1">
          <span id="throughputSourceLabel" style="font-family:Consolas,monospace;font-size:11px;color:var(--muted);font-weight:700;">SYSTEM MULTI-NIC THROUGHPUT</span>
          <span class="speed-summary">
            <span class="speed-chip">LIVE <b id="liveTotalSpeed">0.0 KB/s</b></span>
            <span class="speed-chip">PEAK <b id="peakTotalSpeed">0.0 KB/s</b></span>
          </span>
        </div>
        <div class="chart-row-2" id="chartLegend"></div>
        <div class="canvas-box">
          <canvas id="telemetryChart" width="680" height="195"></canvas>
        </div>
      </div>
    </div>

    <!-- 02 APPLICATION ROUTER -->
    <div class="section-container">
      <div class="section-head">
        <div>
          <div class="kicker">02 / APPLICATION ROUTER &middot; GETEXTENDEDTCPTABLE PID ENGINE</div>
          <div class="section-title">Per-Application Network Pinning</div>
        </div>
        <div class="card-meta-links" id="pinnedCountMeta">RUNNING APPS</div>
      </div>

      <div class="router-toolbar">
        <div class="router-tool-group">
          <select class="filter-select" id="appFilterSelect" aria-label="Application category" title="Choose which application group to show" onchange="setProcFilter(this.value)">
            <option value="ALL">All programs</option>
            <option value="APPS">Apps</option>
            <option value="SERVICES">Services</option>
            <option value="FAVORITES">Favorites</option>
          </select>
          <div class="view-switch">
            <button class="btn active" id="gridViewBtn" onclick="setAppView('grid')">▦ Grid</button>
            <button class="btn" id="listViewBtn" onclick="setAppView('list')">☷ List</button>
          </div>
          <select class="sort-select" id="appSortSelect" aria-label="Sort applications" title="Sort apps by name or current network speed" onchange="setAppSort(this.value)">
            <option value="AZ">Name: A-Z</option>
            <option value="ZA">Name: Z-A</option>
            <option value="FAST">Speed: High–Low</option>
            <option value="SLOW">Speed: Low–High</option>
          </select>
        </div>
        <div class="router-tool-group">
          <button class="btn" title="Scan running applications" onclick="loadRunningApps()">⌕ Scan</button>
          <button class="btn amber" title="Choose an application or built-in engine and its network policy" onclick="openAddProgram()">＋ Add Program</button>
        </div>
      </div>

      <div class="app-grid-scroll" id="appGridScroll"><div class="bento-grid" id="appBentoGrid"></div></div>
    </div>
  </div>

  <div class="add-program-modal" id="addProgramModal" role="dialog" aria-modal="true" aria-labelledby="addProgramTitle">
    <div class="add-program-panel">
      <h3 id="addProgramTitle">Add application to OmniBond</h3>
      <div class="modal-field">
        <label for="addAppSelect">Engine / application</label>
        <select id="addAppSelect"></select>
      </div>
      <div class="modal-field">
        <label for="customAppName">Or enter an executable name</label>
        <input id="customAppName" type="text" placeholder="e.g. game.exe">
      </div>
      <div class="modal-field">
        <label for="addPolicySelect">Network policy</label>
        <select id="addPolicySelect"></select>
      </div>
      <div class="modal-actions">
        <button class="btn" onclick="closeAddProgram()">Cancel</button>
        <button class="btn amber" onclick="submitAddProgram()">Add &amp; apply policy</button>
      </div>
    </div>
  </div>

  <div class="add-program-modal" id="networkTuningModal" role="dialog" aria-modal="true" aria-labelledby="networkTuningTitle">
    <div class="add-program-panel network-tuning-panel">
      <h3 id="networkTuningTitle">Network Tuning</h3>
      <div class="tuning-options">
        <label class="tuning-option">
          <input type="checkbox" id="tuneMultiNic">
          <span><strong>Keep multiple adapters active</strong><small>Disable Windows connection minimization so Wi-Fi, Ethernet, and tethering can remain available together.</small></span>
        </label>
        <label class="tuning-option">
          <input type="checkbox" id="tuneIpv4">
          <span><strong>Balance IPv4 routes</strong><small>Set active IPv4 interface metrics to the OmniBond preferred value.</small></span>
        </label>
        <label class="tuning-option">
          <input type="checkbox" id="tuneIpv6">
          <span><strong>Balance IPv6 routes</strong><small>Set active IPv6 interface metrics to the OmniBond preferred value.</small></span>
        </label>
      </div>
      <div class="tuning-limit-heading">PER-ADAPTER DATA &amp; SPEED LIMITS</div>
      <div class="adapter-limit-note">Data caps count all adapter traffic; at the cap, OmniBond excludes the adapter from new connections without disrupting existing ones or other Windows apps. Custom upload/download limits apply to OmniBond-routed traffic only. Choose Unlimited or Custom for each cap and speed.</div>
      <div class="adapter-limit-grid" id="adapterLimitGrid"></div>
      <div class="modal-status" id="networkTuningStatus"></div>
      <div class="modal-actions">
        <button class="btn" onclick="closeNetworkTuning()">Close</button>
        <button class="btn amber" onclick="optimizeMultiNic()">Apply settings</button>
      </div>
    </div>
  </div>

  <div class="add-program-modal" id="noticeModal" role="dialog" aria-modal="true" aria-labelledby="noticeTitle">
    <div class="add-program-panel">
      <h3 id="noticeTitle">OmniBond</h3>
      <p id="noticeMessage" style="color:var(--muted);font-size:12px;line-height:1.6;white-space:pre-line;"></p>
      <div class="modal-field" id="noticeInputWrap" style="display:none;">
        <label id="noticeInputLabel" for="noticeInput"></label>
        <input id="noticeInput" type="text">
      </div>
      <div class="modal-actions">
        <button class="btn" id="noticeCancelBtn">Cancel</button>
        <button class="btn amber" id="noticeConfirmBtn">OK</button>
      </div>
    </div>
  </div>

  <!-- 03 PARALLEL DOWNLOAD ENGINE -->
  <div class="bottom-container">
    <div class="kicker">03 / PARALLEL RANGE &amp; HLS (.M3U8) ENGINE &middot; ENDGAME RACING</div>
    <div class="section-title" style="margin-top:2px;">Download &amp; Stream Accelerator</div>

    <div class="turbo-unified-box">
      <div class="dl-input-row">
        <span style="font-family:Consolas,monospace;font-size:11px;color:var(--amber);font-weight:700;">URL</span>
        <input type="text" id="dlUrl" class="dl-url-input" placeholder="https://example.com/largefile.iso or https://example.com/stream.m3u8">
        <button class="btn primary" title="Download across bonded adapters using parallel HTTP ranges" onclick="startDownload()">⬇ Download</button>
      </div>
      <div class="progress-track">
        <div class="progress-fill" id="dlProgressFill"></div>
      </div>
      <div class="dl-meta-row">
        <span id="dlStatus">Ready &middot; Awaiting stream or file URL</span>
        <span id="dlTelemetry" style="color:var(--amber);font-weight:700;">0% &middot; 0.0 KB/s</span>
      </div>
      <div class="block-strip" id="blockGrid"></div>
    </div>
  </div>

<script>
let latestState = null;
let allProcesses = [];
let currentFilter = 'ALL';
let currentAppView = localStorage.getItem('omnibond-app-view') || 'grid';
let currentAppSort = localStorage.getItem('omnibond-app-sort') || 'AZ';
let graphMode = localStorage.getItem('omnibond-graph-mode') === 'bonded' ? 'bonded' : 'master';
let peakTotalBps = 0;
let renderedAppStructure = '';
document.getElementById('appSortSelect').value = currentAppSort;

function adapterSpeed(adapter) {
  return graphMode === 'master' ? (adapter.system_bps || 0) : (adapter.bps || 0);
}

function adapterSpeedHistory(adapter) {
  return graphMode === 'master' ? (adapter.system_bps_history || []) : (adapter.bps_history || []);
}

function appSpeed(app) {
  return app.bps || 0;
}

function appSpeedHistory(app) {
  return app.bps_history || [];
}

function updateGraphModeButton() {
  const button = document.getElementById('btnGraphMode');
  const master = graphMode === 'master';
  button.textContent = master ? '∿ Master Speed' : '⇄ Bonded Speed';
  button.classList.toggle('active', !master);
  button.setAttribute('aria-pressed', !master);
  button.title = master
    ? 'Showing live traffic on the computer network interfaces. Click to show OmniBond bonded traffic.'
    : 'Showing traffic routed through OmniBond bonding. Click to show overall computer network traffic.';
}

function toggleGraphMode() {
  graphMode = graphMode === 'master' ? 'bonded' : 'master';
  localStorage.setItem('omnibond-graph-mode', graphMode);
  peakTotalBps = 0;
  updateGraphModeButton();
  fetchState();
}

function fmtBytes(b) {
  if (!b || b <= 0) return '0 B';
  if (b < 1024) return b + ' B';
  if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
  if (b < 1073741824) return (b / 1048576).toFixed(2) + ' MB';
  return (b / 1073741824).toFixed(2) + ' GB';
}

function fmtDataBytes(b) {
  if (!b || b <= 0) return '0 B';
  if (b < 1000) return `${Math.round(b)} B`;
  if (b < 1_000_000) return `${(b / 1000).toFixed(1)} KB`;
  if (b < 1_000_000_000) return `${(b / 1_000_000).toFixed(2)} MB`;
  return `${(b / 1_000_000_000).toFixed(2)} GB`;
}

function fmtSpeed(bps) {
  if (!bps || bps < 1) return '0.0 KB/s';
  if (bps < 1048576) return (bps / 1024).toFixed(1) + ' KB/s';
  return (bps / 1048576).toFixed(2) + ' MB/s';
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
}

function closeStyledSelects(except = null) {
  document.querySelectorAll('.styled-select-wrap.open').forEach(wrap => {
    if (wrap === except) return;
    wrap.classList.remove('open');
    wrap._styledMenu?.remove();
    wrap._styledMenu = null;
    wrap._styledTrigger?.setAttribute('aria-expanded', 'false');
  });
}

function positionStyledSelect(wrap) {
  const trigger = wrap._styledTrigger;
  const menu = wrap._styledMenu;
  if (!trigger || !menu) return;
  const rect = trigger.getBoundingClientRect();
  menu.style.minWidth = `${Math.min(Math.max(160, rect.width), window.innerWidth - 16)}px`;
  menu.style.maxWidth = `${Math.max(120, Math.min(360, window.innerWidth - 16))}px`;
  menu.style.maxHeight = `${Math.max(100, Math.min(280, window.innerHeight - 16))}px`;
  const menuHeight = Math.min(menu.scrollHeight, Math.max(100, Math.min(280, window.innerHeight - 16)));
  const below = window.innerHeight - rect.bottom - 8;
  const above = rect.top - 8;
  const placeAbove = below < Math.min(menuHeight, 150) && above > below;
  const left = Math.max(8, Math.min(rect.left, window.innerWidth - menu.offsetWidth - 8));
  const top = placeAbove
    ? Math.max(8, rect.top - menuHeight - 4)
    : Math.max(8, Math.min(rect.bottom + 4, window.innerHeight - menuHeight - 8));
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
}

function updateStyledSelectLabel(select) {
  const wrap = select.closest('.styled-select-wrap');
  if (!wrap?._styledLabel) return;
  const option = select.options[select.selectedIndex];
  wrap._styledLabel.textContent = option?.textContent?.trim() || 'Select';
  wrap._styledMenu?.querySelectorAll('[role="option"]').forEach((item, index) => {
    const selected = index === select.selectedIndex;
    item.setAttribute('aria-selected', String(selected));
  });
}

function syncStyledSelect(select) {
  if (!(select instanceof HTMLSelectElement)) return;
  let wrap = select.closest('.styled-select-wrap');
  if (!wrap) {
    wrap = document.createElement('span');
    const typeClass = select.classList.contains('card-select')
      ? 'card-select-wrap'
      : (select.classList.contains('filter-select')
        ? 'filter-select-wrap'
        : (select.classList.contains('sort-select')
          ? 'sort-select-wrap'
          : (select.dataset.limitField === 'cycle_unit' ? 'limit-unit-select-wrap' : '')));
    wrap.className = `styled-select-wrap ${typeClass}`.trim();
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);
  }
  let trigger = wrap._styledTrigger;
  if (!trigger) {
    trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'styled-select-trigger';
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    const linkedLabel = select.id
      ? document.querySelector(`label[for="${CSS.escape(select.id)}"]`)?.textContent?.trim()
      : '';
    trigger.setAttribute('aria-label', select.getAttribute('aria-label') || linkedLabel || select.title || 'Choose an option');
    trigger.innerHTML = '<span class="styled-select-trigger-label"></span><span class="styled-select-chevron" aria-hidden="true">▾</span>';
    wrap.insertBefore(trigger, select);
    wrap._styledTrigger = trigger;
    wrap._styledLabel = trigger.querySelector('.styled-select-trigger-label');
    trigger.addEventListener('click', () => {
      if (wrap.classList.contains('open')) {
        closeStyledSelects();
        return;
      }
      closeStyledSelects(wrap);
      const menu = document.createElement('div');
      menu.className = 'styled-select-menu';
      menu.style.display = 'block';
      menu.setAttribute('role', 'listbox');
      menu.setAttribute('aria-label', trigger.getAttribute('aria-label'));
      Array.from(select.options).forEach((option, index) => {
        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'styled-select-option';
        item.setAttribute('role', 'option');
        item.setAttribute('aria-selected', String(index === select.selectedIndex));
        item.textContent = option.textContent.trim();
        item.disabled = option.disabled;
        item.addEventListener('click', () => {
          select.selectedIndex = index;
          select.dispatchEvent(new Event('change', { bubbles: true }));
          closeStyledSelects();
          trigger.focus();
        });
        menu.appendChild(item);
      });
      document.body.appendChild(menu);
      wrap._styledMenu = menu;
      wrap.classList.add('open');
      trigger.setAttribute('aria-expanded', 'true');
      positionStyledSelect(wrap);
      const selected = menu.querySelector('[aria-selected="true"]:not(:disabled)');
      selected?.focus();
      positionStyledSelect(wrap);
    });
    trigger.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        event.stopPropagation();
        trigger.click();
        const items = wrap._styledMenu?.querySelectorAll('[role="option"]:not(:disabled)');
        if (items?.length) items[event.key === 'ArrowUp' ? items.length - 1 : 0].focus();
      }
    });
  }
  select.tabIndex = -1;
  select.setAttribute('aria-hidden', 'true');
  select.classList.add('styled-native-select');
  if (wrap._styledMenu) {
    wrap._styledMenu.replaceChildren();
    Array.from(select.options).forEach((option, index) => {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'styled-select-option';
      item.setAttribute('role', 'option');
      item.setAttribute('aria-selected', String(index === select.selectedIndex));
      item.textContent = option.textContent.trim();
      item.disabled = option.disabled;
      item.addEventListener('click', () => {
        select.selectedIndex = index;
        select.dispatchEvent(new Event('change', { bubbles: true }));
        closeStyledSelects();
        trigger.focus();
      });
      wrap._styledMenu.appendChild(item);
    });
    positionStyledSelect(wrap);
  }
  updateStyledSelectLabel(select);
}

function syncStyledSelects(root = document) {
  root.querySelectorAll('select').forEach(syncStyledSelect);
}

document.addEventListener('change', event => {
  if (event.target instanceof HTMLSelectElement) updateStyledSelectLabel(event.target);
});
document.addEventListener('click', event => {
  if (!event.target.closest('.styled-select-wrap') && !event.target.closest('.styled-select-menu')) {
    closeStyledSelects();
  }
});
document.addEventListener('keydown', event => {
  const wrap = document.querySelector('.styled-select-wrap.open');
  if (!wrap) return;
  if (event.key === 'Escape') {
    event.preventDefault();
    closeStyledSelects();
    wrap._styledTrigger?.focus();
  } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    const items = Array.from(wrap._styledMenu?.querySelectorAll('[role="option"]:not(:disabled)') || []);
    if (!items.length) return;
    event.preventDefault();
    const index = items.indexOf(document.activeElement);
    items[Math.max(0, Math.min(items.length - 1, index + (event.key === 'ArrowDown' ? 1 : -1)))].focus();
  } else if (event.key === 'Enter' && document.activeElement?.matches('.styled-select-option')) {
    event.preventDefault();
    document.activeElement.click();
  }
});
window.addEventListener('resize', closeStyledSelects);
window.addEventListener('scroll', closeStyledSelects, true);

function renderAdapterLimits(adapters) {
  const grid = document.getElementById('adapterLimitGrid');
  if (!grid || grid.contains(document.activeElement) || grid.querySelector('.styled-select-wrap.open')) return;
  grid.innerHTML = adapters.map(a => {
    const dataMode = a.data_limit_bytes ? 'custom' : 'unlimited';
    const downloadMode = a.download_limit_mbps > 0 ? 'custom' : 'unlimited';
    const uploadMode = a.upload_limit_mbps > 0 ? 'custom' : 'unlimited';
    const limitGb = a.data_limit_bytes ? (a.data_limit_bytes / 1_000_000_000).toFixed(3) : '';
    const usage = fmtDataBytes(a.usage_bytes || 0);
    const cap = a.data_limit_bytes ? fmtDataBytes(a.data_limit_bytes) : 'No data cap';
    const resetAt = new Date((a.period_started_at + a.cycle_hours * 3600) * 1000).toLocaleString();
    const cycleUnit = a.cycle_hours >= 24 && Math.abs(a.cycle_hours % 24) < 0.0001
      ? 'days'
      : (a.cycle_hours < 1 ? 'minutes' : 'hours');
    const cycleValue = cycleUnit === 'days'
      ? a.cycle_hours / 24
      : (cycleUnit === 'minutes' ? Math.round(a.cycle_hours * 60) : a.cycle_hours);
    const status = a.quota_exceeded
      ? 'LIMIT REACHED · excluded from new OmniBond connections'
      : `${usage} / ${cap} · window resets ${resetAt}`;
    return `
      <div class="adapter-limit-card">
        <div class="adapter-limit-title">${escapeHtml(a.name)} <span style="color:var(--muted);font-weight:500">· ${escapeHtml(a.kind)}</span></div>
        <div class="adapter-limit-fields">
          <label class="adapter-limit-field">DATA CAP
            <span class="limit-mode-control">
              <select data-limit-mode="data_limit_gb" aria-label="Data cap mode">
                <option value="unlimited" ${dataMode === 'unlimited' ? 'selected' : ''}>Unlimited</option>
                <option value="custom" ${dataMode === 'custom' ? 'selected' : ''}>Custom</option>
              </select>
              <input type="number" min="0.001" step="any" placeholder="GB" value="${limitGb}" data-limit-field="data_limit_gb" ${dataMode === 'unlimited' ? 'disabled' : ''}>
            </span>
          </label>
          <label class="adapter-limit-field">RESET WINDOW
            <span class="limit-cycle-control">
              <input type="number" min="1" step="0.01" value="${cycleValue}" data-limit-field="cycle_value">
              <select data-limit-field="cycle_unit" aria-label="Reset window unit">
                <option value="minutes" ${cycleUnit === 'minutes' ? 'selected' : ''}>min</option>
                <option value="hours" ${cycleUnit === 'hours' ? 'selected' : ''}>hours</option>
                <option value="days" ${cycleUnit === 'days' ? 'selected' : ''}>days</option>
              </select>
            </span>
          </label>
          <label class="adapter-limit-field">DOWNLOAD LIMIT (Mbps)
            <span class="limit-mode-control">
              <select data-limit-mode="download_limit_mbps" aria-label="Download speed limit mode">
                <option value="unlimited" ${downloadMode === 'unlimited' ? 'selected' : ''}>Unlimited</option>
                <option value="custom" ${downloadMode === 'custom' ? 'selected' : ''}>Custom</option>
              </select>
              <input type="number" min="0.001" step="any" placeholder="Mbps" value="${a.download_limit_mbps || ''}" data-limit-field="download_limit_mbps" ${downloadMode === 'unlimited' ? 'disabled' : ''}>
            </span>
          </label>
          <label class="adapter-limit-field">UPLOAD LIMIT (Mbps)
            <span class="limit-mode-control">
              <select data-limit-mode="upload_limit_mbps" aria-label="Upload speed limit mode">
                <option value="unlimited" ${uploadMode === 'unlimited' ? 'selected' : ''}>Unlimited</option>
                <option value="custom" ${uploadMode === 'custom' ? 'selected' : ''}>Custom</option>
              </select>
              <input type="number" min="0.001" step="any" placeholder="Mbps" value="${a.upload_limit_mbps || ''}" data-limit-field="upload_limit_mbps" ${uploadMode === 'unlimited' ? 'disabled' : ''}>
            </span>
          </label>
        </div>
        <div class="adapter-limit-meta">${status}</div>
        <div class="adapter-limit-actions">
          <button class="btn amber" data-adapter-name="${escapeHtml(a.name)}" onclick="saveAdapterLimits(this)">Save Limits</button>
        </div>
      </div>
    `;
  }).join('');
  syncStyledSelects(grid);
  grid.querySelectorAll('[data-limit-mode]').forEach(select => {
    select.addEventListener('change', () => {
      const input = select.closest('.adapter-limit-card')
        ?.querySelector(`[data-limit-field="${select.dataset.limitMode}"]`);
      if (!input) {
        console.error(`Missing input for adapter limit mode ${select.dataset.limitMode}.`);
        return;
      }
      input.disabled = select.value === 'unlimited';
      syncStyledSelect(select);
    });
  });
}

function splitAppTitle(name) {
  if (name.includes('Turbo Accelerator')) return ['Turbo', 'Engine'];
  const dot = name.lastIndexOf('.');
  if (dot > 0) {
    const base = name.slice(0, dot);
    return [base.charAt(0).toUpperCase() + base.slice(1), name.slice(dot)];
  }
  return [name, ''];
}

function setAppView(mode) {
  currentAppView = mode === 'list' ? 'list' : 'grid';
  localStorage.setItem('omnibond-app-view', currentAppView);
  document.getElementById('appBentoGrid').classList.toggle('list-view', currentAppView === 'list');
  document.getElementById('gridViewBtn').classList.toggle('active', currentAppView === 'grid');
  document.getElementById('listViewBtn').classList.toggle('active', currentAppView === 'list');
}

function setAppSort(mode) {
  currentAppSort = ['ZA', 'FAST', 'SLOW'].includes(mode) ? mode : 'AZ';
  localStorage.setItem('omnibond-app-sort', currentAppSort);
  if (latestState) fetchState();
}

function setProcFilter(cat) {
  currentFilter = cat;
  const select = document.getElementById('appFilterSelect');
  if (select && select.value !== cat) select.value = cat;
  fetchState();
}

function renderProcDropdown() {
  const sel = document.getElementById('addAppSelect');
  if (!sel) return;
  const prev = sel.value;
  let html = `<option value="__turbo_accelerator__">[ENGINE] Turbo Accelerator (Built-in)</option>`;
  for (const p of allProcesses) {
    const tag = p.category === 'USER APPS' ? 'APP' : (p.category === 'ACTIVE NET' ? 'NET' : 'BG');
    const title = p.window_title ? ` — ${p.window_title.slice(0, 24)}` : '';
    const safeName = p.exe_name.replaceAll('"', '&quot;');
    html += `<option value="${safeName}">[${tag}] ${p.exe_name} (PID ${p.pid})${title}</option>`;
  }
  sel.innerHTML = html;
  if (prev) sel.value = prev;
  syncStyledSelect(sel);
}

function matchesCurrentAppFilter(app) {
  if (currentFilter === 'APPS') return app.is_running && !app.is_builtin && app.category === 'USER APPS';
  if (currentFilter === 'SERVICES') {
    return app.is_running && ['SERVICES / BG', 'ACTIVE NET'].includes(app.category);
  }
  if (currentFilter === 'FAVORITES') return app.is_favorite;
  return true;
}

function drawSparkline(canvas, history, color) {
  if (!canvas || !history || history.length < 2) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  let maxV = 8192;
  for (const v of history) if (v * 1.15 > maxV) maxV = v * 1.15;

  ctx.beginPath();
  history.forEach((v, i) => {
    const x = (i / (history.length - 1)) * (w - 4) + 2;
    const y = h - 3 - Math.min(1, v / maxV) * (h - 7);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.6;
  ctx.stroke();

  ctx.lineTo(w - 2, h - 2);
  ctx.lineTo(2, h - 2);
  ctx.closePath();
  ctx.fillStyle = color + '28';
  ctx.fill();
}

function drawGoogleStyleChart(adapters) {
  const canvas = document.getElementById('telemetryChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  if (canvas.width !== Math.floor(rect.width * dpr) || canvas.height !== Math.floor(rect.height * dpr)) {
    canvas.width = Math.floor(rect.width * dpr);
    canvas.height = Math.floor(rect.height * dpr);
  }
  ctx.save();
  ctx.scale(dpr, dpr);

  const w = rect.width;
  const h = rect.height;
  const padL = 62, padR = 16, padT = 10, padB = 22;
  const plotW = Math.max(1, w - padL - padR);
  const plotH = Math.max(1, h - padT - padB);

  ctx.clearRect(0, 0, w, h);

  let maxBps = 64 * 1024;
  for (const a of adapters) {
    for (const v of adapterSpeedHistory(a)) {
      if (v * 1.18 > maxBps) maxBps = v * 1.18;
    }
  }

  ctx.font = '10px Consolas, monospace';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  const rows = 4;
  for (let r = 0; r <= rows; r++) {
    const y = padT + (plotH / rows) * r;
    const val = maxBps * (1 - r / rows);
    ctx.strokeStyle = r === rows ? '#27272a' : '#18181f';
    ctx.setLineDash(r === rows ? [] : [3, 3]);
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(w - padR, y);
    ctx.stroke();
    ctx.fillStyle = '#71717a';
    ctx.fillText(val <= 1 ? '0 B/s' : fmtSpeed(val), padL - 8, y);
  }
  ctx.setLineDash([]);

  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  const xLabels = ['-60s', '-45s', '-30s', '-15s', 'LIVE'];
  for (let i = 0; i < xLabels.length; i++) {
    const x = padL + (plotW / (xLabels.length - 1)) * i;
    ctx.fillStyle = i === xLabels.length - 1 ? '#f59e0b' : '#52525b';
    ctx.fillText(xLabels[i], x, padT + plotH + 6);
  }

  adapters.forEach((a) => {
    const hist = adapterSpeedHistory(a);
    if (hist.length < 2) return;
    const pts = hist.map((v, idx) => ({
      x: padL + (idx / (hist.length - 1)) * plotW,
      y: padT + plotH - Math.min(1, Math.max(0, v / maxBps)) * plotH
    }));

    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 0; i < pts.length - 1; i++) {
      const xc = (pts[i].x + pts[i + 1].x) / 2;
      const yc = (pts[i].y + pts[i + 1].y) / 2;
      ctx.quadraticCurveTo(pts[i].x, pts[i].y, xc, yc);
    }
    const last = pts[pts.length - 1];
    ctx.lineTo(last.x, last.y);
    ctx.strokeStyle = a.color;
    ctx.lineWidth = 2.2;
    ctx.stroke();

    ctx.lineTo(last.x, padT + plotH);
    ctx.lineTo(pts[0].x, padT + plotH);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, padT, 0, padT + plotH);
    grad.addColorStop(0, a.color + '44');
    grad.addColorStop(1, a.color + '00');
    ctx.fillStyle = grad;
    ctx.fill();
  });

  ctx.restore();
}

async function fetchState() {
  try {
    const res = await fetch('/api/state');
    const st = await res.json();
    latestState = st;
    document.getElementById('serverEndpoints').textContent =
      `• HTTP/HTTPS 127.0.0.1:${st.http_port} • SOCKS5 127.0.0.1:${st.socks_port} • Web Dashboard 127.0.0.1:${st.web_port}`;

    let totalBps = 0, enabledCnt = 0;
    st.adapters.forEach(a => { totalBps += adapterSpeed(a); if (a.enabled) enabledCnt++; });
    peakTotalBps = Math.max(peakTotalBps, totalBps);
    document.getElementById('liveTotalSpeed').textContent = fmtSpeed(totalBps);
    document.getElementById('peakTotalSpeed').textContent = fmtSpeed(peakTotalBps);
    document.getElementById('btnSysProxy').textContent = st.system_proxy ? '◈ Bonding: On' : '◈ Bonding: Off';
    updateGraphModeButton();
    const adapterTelemetryStatus = graphMode === 'master'
      ? st.system_adapter_telemetry_status
      : 'Adapter traffic routed through OmniBond';
    const adapterTelemetryLabel = graphMode === 'master'
      ? (adapterTelemetryStatus?.includes('unavailable') || adapterTelemetryStatus?.includes('did not match')
        ? 'SYSTEM NIC UNAVAILABLE'
        : 'SYSTEM NIC')
      : 'OMNIBOND';
    const adapterCountMeta = document.getElementById('adapterCountMeta');
    adapterCountMeta.textContent = `${enabledCnt} / ${st.adapters.length} INTERFACES BONDED · ${adapterTelemetryLabel}`;
    adapterCountMeta.title = adapterTelemetryStatus;
    const appCountMeta = document.getElementById('pinnedCountMeta');
    const appTelemetryStatus = st.system_app_telemetry_status || 'Per-app TCP telemetry status unavailable.';
    const appTelemetryLabel = appTelemetryStatus.startsWith('Administrator permission required')
      ? 'ADMIN REQUIRED'
      : (appTelemetryStatus.startsWith('Partial')
        ? 'PARTIAL TCP'
        : (appTelemetryStatus.includes('active') ? 'LIVE TCP'
          : (appTelemetryStatus.includes('waiting') ? 'WAITING TCP' : 'TCP STATUS')));
    appCountMeta.textContent = `${st.app_rules.length} ACTIVE / PINNED APPS · ${appTelemetryLabel}`;
    appCountMeta.title = `${appTelemetryStatus} OmniBond-proxied traffic is also tracked.`;
    document.getElementById('throughputSourceLabel').textContent = graphMode === 'master'
      ? 'MASTER SPEED · ALL COMPUTER NETWORK TRAFFIC'
      : 'BONDED SPEED · OMNIBOND ROUTED TRAFFIC';

    const sel = document.getElementById('addPolicySelect');
    const prevVal = sel.value;
    let opts = '<option value="AUTO">Auto / Bonded (All adapters)</option><option value="BLOCK">Block Internet</option>';
    st.adapters.forEach((a, i) => {
      opts += `<option value="${a.ip}">Pin to ${a.name} (${a.ip})</option>`;
    });
    if (sel.innerHTML !== opts) { sel.innerHTML = opts; if (prevVal) sel.value = prevVal; }
    syncStyledSelect(sel);

    // 01 Adapters
    document.getElementById('adapterBentoGrid').innerHTML = st.adapters.map((a, idx) => `
      <div class="bento-card">
        <div>
          <div class="card-top">
            <span class="num-badge" style="background:${a.color}">${String(idx + 1).padStart(2, '0')}</span>
            <span class="card-meta-links">IPV4 &middot; ${a.ip} &#8599;</span>
          </div>
          <div class="card-identity">
            <div class="card-icon" style="background:${a.badge_bg}">${a.kind.slice(0,2).toUpperCase()}</div>
            <div>
              <div class="card-name">${a.name} <span style="color:${a.color}">${a.kind}</span></div>
              <div class="card-desc">${a.latency_ms}ms RTT &middot; ${a.active_conns} Conns</div>
            </div>
          </div>
          <div class="status-box ${a.quota_exceeded ? 'quota-reached' : ''}">${a.quota_exceeded ? 'DATA CAP REACHED' : (a.enabled ? 'ACTIVE · ' + a.kind.toUpperCase() : 'DISABLED')}</div>
          <div style="font-size:11px;color:var(--dim);margin-bottom:8px;">
            Traffic: ${fmtBytes(graphMode === 'master' ? a.system_bytes_recv + a.system_bytes_sent : a.bytes_recv + a.bytes_sent)} &middot; Live: ${fmtSpeed(adapterSpeed(a))}
          </div>
        </div>
        <div class="card-actions">
          ${a.quota_exceeded
            ? '<button class="card-btn" disabled title="This adapter will rejoin OmniBond when its data window resets or the cap is removed">LIMIT REACHED · WAIT FOR RESET</button>'
            : `<button class="card-btn" title="Enable or disable this network adapter in the bonding pool" onclick="toggleAdapter('${escapeHtml(a.ip)}', ${!a.manually_enabled})">
                ${a.manually_enabled ? 'BONDED · CLICK TO TOGGLE' : 'DISABLED · CLICK TO ENABLE'}
              </button>`}
        </div>
      </div>
    `).join('');
    document.getElementById('adapterBentoGrid').style.minWidth = `${Math.max(100, st.adapters.length * 280)}px`;
    renderAdapterLimits(st.adapters);

    // 02 Applications with per-app speed sparklines & Focus button
    const paletteColors = ['#38bdf8', '#fb923c', '#34d399', '#a78bfa', '#facc15', '#f472b6'];
    const visibleAppRules = st.app_rules.filter(matchesCurrentAppFilter);
    visibleAppRules.sort((a, b) => {
      if (currentAppSort === 'ZA') return b.display_name.localeCompare(a.display_name, undefined, {sensitivity: 'base'});
      if (currentAppSort === 'FAST') return appSpeed(b) - appSpeed(a) || a.display_name.localeCompare(b.display_name, undefined, {sensitivity: 'base'});
      if (currentAppSort === 'SLOW') return appSpeed(a) - appSpeed(b) || a.display_name.localeCompare(b.display_name, undefined, {sensitivity: 'base'});
      return a.display_name.localeCompare(b.display_name, undefined, {sensitivity: 'base'});
    });
    const appGrid = document.getElementById('appBentoGrid');
    const appPolicyFocused = Boolean(
      document.activeElement?.closest?.('.card-select-wrap') || appGrid.querySelector('.card-select-wrap.open')
    );
    const appStructure = JSON.stringify([
      currentFilter,
      currentAppView,
      currentAppSort,
      graphMode,
      visibleAppRules.map(r => r.app_name),
      visibleAppRules.map(r => [
        r.app_name, r.display_name, r.rule, r.is_favorite, r.is_running,
        r.category, r.last_pid, r.window_title
      ]),
      st.adapters.map(a => [a.ip, a.name])
    ]);
    if (!appPolicyFocused && appStructure !== renderedAppStructure) {
      appGrid.innerHTML = visibleAppRules.map((r, idx) => {
      const col = paletteColors[idx % paletteColors.length];
      const [mainTitle, subExt] = splitAppTitle(r.display_name);
      const selectedRule = r.rule;
      let rowOpts = `<option value="AUTO" ${selectedRule === 'AUTO' ? 'selected' : ''}>Auto / Bonded</option>
        <option value="BLOCK" ${selectedRule === 'BLOCK' ? 'selected' : ''}>Block Internet</option>`;
      st.adapters.forEach(a => {
        rowOpts += `<option value="${a.ip}" ${selectedRule === a.ip ? 'selected' : ''}>${a.name} (${a.ip})</option>`;
      });

      return `
        <div class="bento-card" data-app-speed="${appSpeed(r)}">
          <div>
            <div class="card-top">
              <span class="num-badge" style="background:${col}">${String(idx + 1).padStart(2, '0')}</span>
              <div class="app-card-controls">
                <button class="favorite-btn ${r.is_favorite ? 'active' : ''}" title="${r.is_favorite ? 'Remove from favorites' : 'Add to favorites'}" onclick="toggleFavorite('${r.app_name}', ${!r.is_favorite})">${r.is_favorite ? '★' : '☆'}</button>
                <button class="focus-link" title="Bring the program window forward" onclick="focusApp('${r.app_name}', ${r.last_pid})">▣ Focus</button>
                <button class="card-btn" title="Open this program's file or installation location" onclick="locateApp('${r.app_name}', ${r.last_pid})">↗ Location</button>
              </div>
            </div>
            <div class="card-identity">
              <div class="card-icon" style="background:#14141d;color:${col};border:1px solid ${col}66;">${mainTitle.slice(0,2).toUpperCase()}</div>
              <div>
                <div class="card-name">${mainTitle}<span style="color:${col}">${subExt}</span></div>
                <div class="card-desc" id="app_desc_${idx}">${r.rule === 'BLOCK' ? 'Internet Disabled' : (r.window_title ? r.window_title.slice(0,26) : (r.is_running ? 'Running Process' : 'Pinned Rule'))}</div>
              </div>
            </div>
            <div class="sparkline-box">
              <div class="sparkline-head">
                <span title="Direct TCP traffic attributed to this application, plus OmniBond-proxied traffic. UDP/QUIC is not included.">APP SPEED</span>
                <span id="app_speed_${idx}" style="color:${col};font-weight:700;">${fmtSpeed(appSpeed(r))}</span>
              </div>
              <canvas class="app-spark" id="spark_${idx}" width="190" height="32"></canvas>
            </div>
            <div id="app_summary_${idx}" style="font-size:10.5px;color:var(--dim);margin-bottom:8px;">
              IP: ${r.last_adapter_ip} &middot; Conns: ${r.active_connections} (${r.total_connections}) &middot; ${fmtBytes(r.bytes_transferred)}
            </div>
          </div>
          <div class="card-actions">
            <select class="card-select" id="app_policy_${idx}" data-app-name="${escapeHtml(r.app_name)}" style="--app-accent:${col}" title="Select and apply a routing policy for ${r.display_name}" onchange="updateRuleInline('${r.app_name}', this.value)">
              ${rowOpts}
            </select>
          </div>
        </div>
      `;
      }).join('');
      syncStyledSelects(appGrid);
      setAppView(currentAppView);
      renderedAppStructure = appStructure;
    }
    visibleAppRules.forEach((r, idx) => {
      const col = paletteColors[idx % paletteColors.length];
      const speedNode = document.getElementById(`app_speed_${idx}`);
      const summaryNode = document.getElementById(`app_summary_${idx}`);
      const descriptionNode = document.getElementById(`app_desc_${idx}`);
      if (speedNode) speedNode.textContent = fmtSpeed(appSpeed(r));
      if (summaryNode) {
        summaryNode.textContent =
          `IP: ${r.last_adapter_ip} · Conns: ${r.active_connections} (${r.total_connections}) · ${fmtBytes(r.bytes_transferred)}`;
      }
      if (descriptionNode) {
        descriptionNode.textContent = r.rule === 'BLOCK'
          ? 'Internet Disabled'
          : (r.window_title ? r.window_title.slice(0, 26) : (r.is_running ? 'Running Process' : 'Pinned Rule'));
      }
      const cardNode = speedNode?.closest('.bento-card');
      if (cardNode) cardNode.dataset.appSpeed = String(appSpeed(r));
      drawSparkline(document.getElementById(`spark_${idx}`), appSpeedHistory(r), col);
    });

    // Legend & Main Chart
    document.getElementById('chartLegend').innerHTML = st.adapters.map((a, idx) => `
      <div class="legend-pill">
        <span class="legend-dot" style="background:${a.color}"></span>
        <span>${String(idx + 1).padStart(2, '0')} &middot; ${a.name} (<b>${fmtSpeed(adapterSpeed(a))}</b>)</span>
      </div>
    `).join('');
    drawGoogleStyleChart(st.adapters);

    // 03 Turbo
    const pct = Math.min(100, Math.max(0, st.turbo.progress_pct || 0));
    document.getElementById('dlProgressFill').style.width = `${pct}%`;
    document.getElementById('dlStatus').textContent = st.turbo.status_text;
    document.getElementById('dlTelemetry').textContent = `${pct.toFixed(0)}% · ${fmtSpeed(st.turbo.speed_bps)}`;
    document.getElementById('blockGrid').innerHTML = (st.turbo.blocks || []).map(b =>
      `<div class="blk" style="background:${b.status === 'pending' ? '#181822' : b.color}"></div>`
    ).join('');
  } catch (e) {
    console.error('Could not refresh OmniBond dashboard state.', e);
  }
}

async function loadRunningApps() {
  const res = await fetch('/api/processes');
  const data = await res.json();
  allProcesses = data.detailed || [];
  renderProcDropdown();
}

async function updateRuleInline(appName, ruleVal) {
  const policyApp = document.activeElement?.closest?.('.card-select-wrap')
    ? document.activeElement.closest('.card-select-wrap').querySelector('select')?.dataset.appName
    : null;
  if (policyApp) document.activeElement.blur();
  const res = await fetch('/api/rules', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({app_name: appName, rule: ruleVal})
  });
  if (!res.ok) {
    const data = await res.json();
    await showThemedDialog('Application Policy', data.message || 'Could not save this application policy.');
    return;
  }
  await fetchState();
  if (policyApp) {
    const matchingSelect = Array.from(document.querySelectorAll('.card-select'))
      .find(select => select.dataset.appName === policyApp);
    matchingSelect?.closest('.card-select-wrap')?._styledTrigger?.focus();
  }
}

async function toggleFavorite(appName, favorite) {
  const res = await fetch('/api/favorite', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({app_name: appName, favorite})
  });
  if (!res.ok) await showThemedDialog('Favorites', (await res.json()).message || 'Could not update favorite.');
  await fetchState();
}

function showThemedDialog(title, message, options = {}) {
  const modal = document.getElementById('noticeModal');
  const inputWrap = document.getElementById('noticeInputWrap');
  const input = document.getElementById('noticeInput');
  const cancel = document.getElementById('noticeCancelBtn');
  const confirm = document.getElementById('noticeConfirmBtn');
  const needsConfirmation = options.confirm === true || Boolean(options.inputLabel);
  document.getElementById('noticeTitle').textContent = title;
  document.getElementById('noticeMessage').textContent = message;
  document.getElementById('noticeInputLabel').textContent = options.inputLabel || '';
  inputWrap.style.display = options.inputLabel ? 'flex' : 'none';
  input.value = options.inputValue || '';
  cancel.style.display = needsConfirmation ? 'inline-flex' : 'none';
  confirm.textContent = options.confirmText || (needsConfirmation ? 'Continue' : 'OK');
  modal.classList.add('open');
  if (options.inputLabel) input.focus();
  else confirm.focus();
  return new Promise(resolve => {
    const finish = value => {
      modal.classList.remove('open');
      document.removeEventListener('keydown', onKeyDown);
      modal.onclick = null;
      resolve(value);
    };
    const onKeyDown = event => {
      if (event.key === 'Escape') finish(options.inputLabel ? null : false);
      if (event.key === 'Enter' && event.target === input) finish(input.value.trim());
    };
    confirm.onclick = () => finish(options.inputLabel ? input.value.trim() : true);
    cancel.onclick = () => finish(options.inputLabel ? null : false);
    modal.onclick = event => {
      if (event.target === modal) finish(options.inputLabel ? null : false);
    };
    document.addEventListener('keydown', onKeyDown);
  });
}

function openAddProgram() {
  renderProcDropdown();
  document.getElementById('customAppName').value = '';
  document.getElementById('addProgramModal').classList.add('open');
  document.getElementById('addAppSelect').focus();
}

function closeAddProgram() {
  document.getElementById('addProgramModal').classList.remove('open');
}

async function submitAddProgram() {
  const customName = document.getElementById('customAppName').value.trim();
  const appName = customName || document.getElementById('addAppSelect').value;
  const policy = document.getElementById('addPolicySelect').value || 'AUTO';
  if (!appName) return;
  await updateRuleInline(appName, policy);
  closeAddProgram();
}

async function locateApp(appName, pid) {
  let res = await fetch('/api/locate_app', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({app_name: appName, pid})
  });
  let data = await res.json();
  if (data.ok) return;
  if (!await showThemedDialog('Program Location', `${data.message || 'No location is available.'}\n\nChoose the executable or installation folder now?`, {confirm: true, confirmText: 'Choose location'})) {
    return;
  }
  const location = await showThemedDialog('Program Location', 'Select the full executable file path or installed folder path.', {inputLabel: 'Executable or installation folder'});
  if (!location || !location.trim()) return;
  res = await fetch('/api/app_location', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({app_name: appName, location: location.trim()})
  });
  data = await res.json();
  if (!res.ok || !data.ok) {
    await showThemedDialog('Program Location', data.message || 'Could not save this program location.');
    return;
  }
  res = await fetch('/api/locate_app', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({app_name: appName, pid})
  });
  data = await res.json();
  if (!data.ok) await showThemedDialog('Program Location', data.message || 'Could not open this program location.');
}

async function focusApp(appName, pid) {
  const res = await fetch('/api/focus_app', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({app_name: appName, pid: pid})
  });
  const data = await res.json();
  if (!data.ok) await showThemedDialog('Application', data.message || 'Could not focus this application.');
}

async function toggleAdapter(ip, enabled) {
  await fetch('/api/adapter_toggle', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ip, enabled})
  });
  fetchState();
}

async function toggleSystemProxy() { await fetch('/api/system_proxy', {method: 'POST'}); fetchState(); }
async function repairNetwork() {
  const res = await fetch('/api/repair_network', {method: 'POST'});
  const data = await res.json();
  await fetchState();
  await showThemedDialog('Network Repaired', data.message || 'Windows proxy and interface metrics restored to default.');
}
function openNetworkTuning() {
  document.getElementById('tuneMultiNic').checked = localStorage.getItem('omnibond-tune-multi-nic') !== 'false';
  document.getElementById('tuneIpv4').checked = localStorage.getItem('omnibond-tune-ipv4') !== 'false';
  document.getElementById('tuneIpv6').checked = localStorage.getItem('omnibond-tune-ipv6') === 'true';
  document.getElementById('networkTuningStatus').textContent = '';
  document.getElementById('networkTuningModal').classList.add('open');
}
function closeNetworkTuning() {
  document.getElementById('networkTuningModal').classList.remove('open');
}
async function optimizeMultiNic() {
  const options = {
    keep_multi_nic: document.getElementById('tuneMultiNic').checked,
    ipv4: document.getElementById('tuneIpv4').checked,
    ipv6: document.getElementById('tuneIpv6').checked
  };
  const status = document.getElementById('networkTuningStatus');
  try {
    const res = await fetch('/api/optimize_nic', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(options)
    });
    const data = await res.json();
    status.textContent = data.message || 'Network tuning settings updated.';
    status.classList.toggle('error', !res.ok);
    if (res.ok) {
      localStorage.setItem('omnibond-tune-multi-nic', options.keep_multi_nic);
      localStorage.setItem('omnibond-tune-ipv4', options.ipv4);
      localStorage.setItem('omnibond-tune-ipv6', options.ipv6);
    }
  } catch (error) {
    status.textContent = `Could not apply network tuning: ${error.message}`;
    status.classList.add('error');
  }
}
async function saveAdapterLimits(button) {
  const card = button.closest('.adapter-limit-card');
  const cycleValue = Number(card.querySelector('[data-limit-field="cycle_value"]').value);
  const cycleUnit = card.querySelector('[data-limit-field="cycle_unit"]').value;
  const cycleHours = cycleValue * (cycleUnit === 'days' ? 24 : (cycleUnit === 'minutes' ? 1 / 60 : 1));
  const valueFor = (field, label) => {
    const mode = card.querySelector(`[data-limit-mode="${field}"]`);
    if (mode?.value === 'unlimited') return 0;
    const input = card.querySelector(`[data-limit-field="${field}"]`);
    const value = Number(input.value);
    if (!input.value.trim() || !Number.isFinite(value) || value <= 0) {
      input.focus();
      return { error: `Enter a value greater than zero for ${label}, or choose Unlimited.` };
    }
    return value;
  };
  if (!Number.isFinite(cycleHours) || cycleHours <= 0) {
    card.querySelector('[data-limit-field="cycle_value"]').focus();
    await showThemedDialog('Adapter limits', 'Reset window must be greater than zero.');
    return;
  }
  const dataLimit = valueFor('data_limit_gb', 'the data cap');
  const downloadLimit = valueFor('download_limit_mbps', 'the download limit');
  const uploadLimit = valueFor('upload_limit_mbps', 'the upload limit');
  const invalid = [dataLimit, downloadLimit, uploadLimit].find(value => typeof value === 'object');
  if (invalid) {
    await showThemedDialog('Adapter limits', invalid.error);
    return;
  }
  const payload = {
    adapter_name: button.dataset.adapterName,
    data_limit_gb: dataLimit,
    cycle_hours: cycleHours,
    download_limit_mbps: downloadLimit,
    upload_limit_mbps: uploadLimit
  };
  button.disabled = true;
  const status = card.querySelector('.adapter-limit-meta');
  try {
    const res = await fetch('/api/adapter_limits', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    status.textContent = data.message || (res.ok ? 'Adapter limits saved.' : 'Could not save adapter limits.');
    status.classList.toggle('error', !res.ok);
    if (res.ok) {
      button.blur();
      fetchState();
    }
  } catch (error) {
    status.textContent = `Could not save adapter limits: ${error.message}`;
    status.classList.add('error');
  } finally {
    button.disabled = false;
  }
}
async function simulateTrafficBurst() { await fetch('/api/simulate_burst', {method: 'POST'}); fetchState(); }
async function refreshAdapters() { await fetch('/api/refresh_adapters', {method: 'POST'}); fetchState(); }
async function startDownload() {
  const url = document.getElementById('dlUrl').value.trim();
  if (!url) return;
  await fetch('/api/download', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({url, output_path: ''})
  });
  fetchState();
}

syncStyledSelects();
loadRunningApps();
setAppView(currentAppView);
updateGraphModeButton();
fetchState();
setInterval(fetchState, 1200);
</script>
</body>
</html>
"""


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


# =====================================================================
# 8. OMNIBOND CORE ENGINE
# =====================================================================

def launch_frameless_web_app(
    url: str, browser_profile: Optional[str] = None
) -> Optional[subprocess.Popen]:
    if IS_WINDOWS:
        candidates = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
        for exe in candidates:
            if os.path.exists(exe):
                try:
                    command = [exe, f"--app={url}", "--window-size=1360,880"]
                    if browser_profile:
                        command.append(f"--user-data-dir={browser_profile}")
                    return subprocess.Popen(
                        command,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except OSError:
                    pass
    if browser_profile:
        print(
            "Could not find Edge or Chrome to launch a monitored OmniBond window.",
            file=sys.stderr,
        )
        return None
    try:
        import webbrowser
        if webbrowser.open(url):
            return None
    except Exception as e:
        print(f"Could not open the OmniBond dashboard: {e}", file=sys.stderr)
    return None


class OmniBondEngine:
    def __init__(
        self,
        persist_rules_path: str = RULES_FILE,
        auto_scan_procs: bool = True,
        defer_adapter_scan: bool = False,
    ):
        self.process_mapper = ProcessMapper(location_path=persist_rules_path + ".locations")
        self.routing_mgr = AppRoutingManager(persist_path=persist_rules_path)
        self.adapter_mgr = AdapterManager(
            self.routing_mgr,
            refresh_on_init=not defer_adapter_scan,
            limits_path=persist_rules_path + ".adapter_limits" if persist_rules_path else "",
        )
        self.process_tcp_counters = WindowsProcessTcpCounters()
        self.sys_opt = WindowsSystemOptimizer(
            adapter_mgr=self.adapter_mgr,
            restore_file=persist_rules_path + ".sys_restore" if persist_rules_path else "",
        )
        self.turbo = TurboAccelerator(self.adapter_mgr, self.routing_mgr)

        self.http_server: Optional[ThreadedTCPServer] = None
        self.socks_server: Optional[ThreadedTCPServer] = None
        self.web_server: Optional[ThreadingHTTPServer] = None
        self.http_port = HTTP_PROXY_PORT
        self.socks_port = SOCKS_PROXY_PORT
        self.web_port = WEB_UI_PORT
        self._running = False
        self._dashboard_seen = False
        self._last_dashboard_activity = time.monotonic()
        self.cached_detailed_procs: List[ProcessInfo] = []
        if auto_scan_procs:
            self.scan_and_sync_processes()

    def scan_and_sync_processes(self) -> List[ProcessInfo]:
        pinned_keys = set(self.routing_mgr._user_added_apps)
        detailed = self.process_mapper.scan_detailed_processes(pinned_keys=pinned_keys)
        self.routing_mgr.sync_running_programs(detailed)
        self.cached_detailed_procs = detailed
        return detailed

    def start_services(
        self,
        http_port: int = HTTP_PROXY_PORT,
        socks_port: int = SOCKS_PROXY_PORT,
        web_port: int = WEB_UI_PORT,
    ):
        def create_server(server_type, port: int, handler):
            try:
                return server_type(("127.0.0.1", port), handler)
            except OSError as exc:
                winerror = getattr(exc, "winerror", None)
                if port == 0 or (
                    exc.errno not in (13, 98, 10048)
                    and winerror not in (10013, 10048)
                ):
                    raise
                print(
                    f"Port {port} is unavailable; using an OS-assigned local port instead.",
                    file=sys.stderr,
                )
                return server_type(("127.0.0.1", 0), handler)

        self._running = True
        self.http_server = create_server(ThreadedTCPServer, http_port, BondingHTTPProxyHandler)
        self.http_server.engine = self  # type: ignore
        self.http_port = self.http_server.server_address[1]

        self.socks_server = create_server(ThreadedTCPServer, socks_port, BondingSOCKS5ProxyHandler)
        self.socks_server.engine = self  # type: ignore
        self.socks_port = self.socks_server.server_address[1]

        self.web_server = create_server(ThreadingHTTPServer, web_port, WebUIHandler)
        self.web_server.engine = self  # type: ignore
        self.web_port = self.web_server.server_address[1]

        threading.Thread(target=self.http_server.serve_forever, daemon=True).start()
        threading.Thread(target=self.socks_server.serve_forever, daemon=True).start()
        threading.Thread(target=self.web_server.serve_forever, daemon=True).start()
        threading.Thread(target=self._metrics_loop, daemon=True).start()

    def _metrics_loop(self):
        tick_count = 0
        while self._running:
            self.adapter_mgr.tick_throughput()
            self.routing_mgr.tick_app_throughput()
            for pid, byte_delta in self.process_tcp_counters.sample().items():
                if byte_delta:
                    app_name = self.process_mapper.get_exe_name(pid)
                    self.routing_mgr.record_process_bytes(app_name, pid, byte_delta)
            tick_count += 1
            # Periodically re-sync running processes every ~6 seconds in background
            if tick_count % 12 == 0:
                try:
                    self.scan_and_sync_processes()
                except Exception:
                    pass
            time.sleep(0.5)

    def simulate_telemetry_wave(self):
        """Injects a multi-NIC AND per-application throughput wave to preview both graphs."""
        with self.adapter_mgr._lock:
            for idx, a in enumerate(self.adapter_mgr.adapters.values()):
                if not a.enabled:
                    continue
                base = (idx + 1) * 480_000.0
                for step in range(14):
                    wave = base * (0.35 + 0.65 * abs(math.sin((step + idx * 2) * 0.45)))
                    a.bps_history.append(wave)
                    if len(a.bps_history) > 60:
                        a.bps_history.pop(0)
                a.bytes_recv += int(base * 2.5)

        adapters = self.adapter_mgr.get_adapters()
        with self.routing_mgr._lock:
            for idx, st in enumerate(self.routing_mgr._stats.values()):
                app_base = ((idx % 3) + 1) * 260_000.0
                for step in range(14):
                    wave = app_base * (0.25 + 0.75 * abs(math.cos((step + idx) * 0.5)))
                    st.bps_history.append(wave)
                    if len(st.bps_history) > 36:
                        st.bps_history.pop(0)
                st.bytes_transferred += int(app_base * 1.8)
                st._last_bytes = st.bytes_transferred
                if adapters:
                    st.last_adapter_ip = adapters[idx % len(adapters)].ip

    def stop_services(self) -> List[str]:
        self._running = False
        restore_errors = self.sys_opt.restore_system_settings()
        for srv in (self.http_server, self.socks_server, self.web_server):
            if srv:
                try:
                    srv.shutdown()
                    srv.server_close()
                except Exception:
                    pass
        return restore_errors

    def get_state_snapshot(self) -> Dict:
        adapters_list = []
        for a in self.adapter_mgr.get_adapters():
            limit_snapshot = self.adapter_mgr.get_adapter_limit_snapshot(a)
            quota_exceeded = limit_snapshot["quota_exceeded"]
            adapters_list.append({
                "name": a.name,
                "ip": a.ip,
                "kind": a.kind,
                "gateway": a.gateway,
                "if_index": a.if_index,
                "is_online": a.is_online,
                "enabled": a.enabled and not quota_exceeded,
                "manually_enabled": a.enabled,
                "weight": a.weight,
                "latency_ms": round(a.latency_ms, 1),
                "active_conns": a.active_conns,
                "bytes_sent": a.bytes_sent,
                "bytes_recv": a.bytes_recv,
                "system_bytes_sent": a.system_bytes_sent,
                "system_bytes_recv": a.system_bytes_recv,
                "badge_bg": a.badge_bg,
                "color": a.color,
                "fill_dark": a.fill_dark,
                "bps": round(a.current_bps, 1),
                "bps_history": [round(x, 1) for x in a.bps_history[-48:]],
                "system_bps": round(a.system_current_bps, 1),
                "system_bps_history": [round(x, 1) for x in a.system_bps_history[-48:]],
                **limit_snapshot,
            })
        blocks_list = [
            {
                "index": b.index,
                "status": b.status,
                "adapter_ip": b.adapter_ip,
                "color": b.color,
            }
            for b in self.turbo.blocks[:160]
        ]
        return {
            "system_proxy": self.sys_opt.system_proxy_enabled,
            "http_port": self.http_port,
            "socks_port": self.socks_port,
            "web_port": self.web_port,
            "adapters": adapters_list,
            "app_rules": self.routing_mgr.get_all_entries(only_running_or_added=True),
            "system_adapter_telemetry_status": self.adapter_mgr.system_counter_status,
            "system_app_telemetry_status": self.process_tcp_counters.status,
            "system_app_telemetry_details": self.process_tcp_counters.diagnostics,
            "turbo": {
                "is_running": self.turbo.is_running,
                "status_text": self.turbo.status_text,
                "progress_pct": self.turbo.progress_pct,
                "speed_bps": self.turbo.speed_bps,
                "blocks": blocks_list,
            },
        }


# =====================================================================
# 9. CUSTOM STUDIO UI COMPONENTS: HOVER TOOLTIPS, MODERN DROPDOWN & BUTTONS
# =====================================================================

class StudioTooltip:
    """
    Delayed dark-mode Studio Tooltip that explains what any button, dropdown,
    or interactive canvas control does when hovering the mouse over it.
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self._tip_win: Optional[tk.Toplevel] = None
        self._after_id: Optional[str] = None
        self._current_text: str = ""
        self._mouse_x: int = 0
        self._mouse_y: int = 0

    def bind_widget(self, widget: tk.Widget, title: str, description: str, delay_ms: int = 420):
        full_text = f"{title}\n{description}" if description else title

        def on_enter(event):
            self._mouse_x = event.x_root
            self._mouse_y = event.y_root
            self.schedule(full_text, delay_ms)

        def on_motion(event):
            self._mouse_x = event.x_root
            self._mouse_y = event.y_root

        def on_leave(_event):
            self.hide()

        widget.bind("<Enter>", on_enter, add="+")
        widget.bind("<Motion>", on_motion, add="+")
        widget.bind("<Leave>", on_leave, add="+")
        widget.bind("<ButtonPress>", on_leave, add="+")

    def schedule(self, text: str, delay_ms: int = 420):
        if text == self._current_text and self._tip_win is not None:
            return
        self.hide()
        self._current_text = text
        self._after_id = self.root.after(delay_ms, self._show)

    def _show(self):
        if not self._current_text:
            return
        try:
            win = tk.Toplevel(self.root)
            win.wm_overrideredirect(True)
            win.attributes("-topmost", True)
            win.configure(bg="#f59e0b")

            inner = tk.Frame(win, bg="#101016", padx=10, pady=7)
            inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

            lines = self._current_text.split("\n", 1)
            tk.Label(
                inner,
                text=lines[0],
                bg="#101016",
                fg="#f59e0b",
                font=("Consolas", 8, "bold"),
                anchor="w",
                justify=tk.LEFT,
            ).pack(anchor="w")

            if len(lines) > 1:
                tk.Label(
                    inner,
                    text=lines[1],
                    bg="#101016",
                    fg="#d4d4d8",
                    font=("Segoe UI", 8),
                    anchor="w",
                    justify=tk.LEFT,
                    wraplength=310,
                ).pack(anchor="w", pady=(2, 0))

            x = min(self.root.winfo_screenwidth() - 340, self._mouse_x + 14)
            y = min(self.root.winfo_screenheight() - 90, self._mouse_y + 18)
            win.wm_geometry(f"+{max(10, x)}+{max(10, y)}")
            self._tip_win = win
        except Exception:
            pass

    def hide(self):
        if self._after_id:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if self._tip_win:
            try:
                self._tip_win.destroy()
            except Exception:
                pass
            self._tip_win = None
        self._current_text = ""


class StudioDropdown(_TkFrameBase):
    """
    Custom Dark-Mode Dropdown Selector that replaces the glaring white Win32 ttk.Combobox.
    Supports:
    - Live Search / Filter input box inside the popup
    - Category Filter Tabs (e.g. ALL | USER APPS | ACTIVE NET | PINNED | BG)
    - Rich item rows with category badge, main label, and right-aligned subtitle
    """

    def __init__(
        self,
        parent: tk.Widget,
        root: tk.Tk,
        width_px: int = 230,
        categories: Optional[List[str]] = None,
        placeholder: str = "Select...",
        on_select: Optional[Callable[[str], None]] = None,
    ):
        super().__init__(
            parent,
            bg="#121218",
            highlightthickness=1,
            highlightbackground="#272732",
            width=width_px,
            height=30,
        )
        self.pack_propagate(False)
        self.root = root
        self.width_px = width_px
        self.categories = categories or []
        self.on_select = on_select

        self._items: List[Dict[str, str]] = []
        self._selected_value: str = ""
        self._selected_label: str = placeholder
        self._popup: Optional[tk.Toplevel] = None
        self._active_category: str = "ALL"

        self.lbl_text = tk.Label(
            self,
            text=self._selected_label,
            bg="#121218",
            fg="#fafafa",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
            padx=10,
            cursor="hand2",
        )
        self.lbl_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.lbl_arrow = tk.Label(
            self,
            text="▾",
            bg="#181822",
            fg="#f59e0b",
            font=("Consolas", 10, "bold"),
            width=3,
            cursor="hand2",
        )
        self.lbl_arrow.pack(side=tk.RIGHT, fill=tk.Y)

        for w in (self, self.lbl_text, self.lbl_arrow):
            w.bind("<Button-1>", self._toggle_popup)
            w.bind("<Enter>", self._on_hover_enter, add="+")
            w.bind("<Leave>", self._on_hover_leave, add="+")

    def _on_hover_enter(self, _e):
        self.configure(highlightbackground="#f59e0b")
        self.lbl_arrow.configure(bg="#272734")

    def _on_hover_leave(self, _e):
        if not self._popup:
            self.configure(highlightbackground="#272732")
            self.lbl_arrow.configure(bg="#181822")

    def set_items(self, items: List[Dict[str, str]]):
        """
        Each item dict:
          {"value": "steam.exe", "label": "steam.exe", "meta": "PID 4120 · Steam", "category": "USER APPS", "badge": "APP", "color": "#38bdf8"}
        """
        self._items = items
        if not self._selected_value and items:
            self.set_value(items[0]["value"], items[0]["label"])

    def set_value(self, value: str, display_label: Optional[str] = None):
        self._selected_value = value
        if display_label is None:
            found = next((it["label"] for it in self._items if it["value"] == value), value)
            display_label = found
        self._selected_label = display_label
        short = display_label if len(display_label) <= 26 else display_label[:24] + ".."
        self.lbl_text.configure(text=short)

    def get_value(self) -> str:
        return self._selected_value

    def _toggle_popup(self, _event=None):
        if self._popup and self._popup.winfo_exists():
            self._close_popup()
            return
        self._open_popup()

    def _close_popup(self):
        if self._popup:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None
        self.configure(highlightbackground="#272732")
        self.lbl_arrow.configure(bg="#181822", text="▾")

    def _open_popup(self):
        self.lbl_arrow.configure(text="▴")
        self.configure(highlightbackground="#f59e0b")

        pop = tk.Toplevel(self.root)
        pop.wm_overrideredirect(True)
        pop.attributes("-topmost", True)
        pop.configure(bg="#f59e0b")
        self._popup = pop

        pop_w = max(self.width_px, 370 if self.categories else 270)
        pop_h = 330 if self.categories else min(250, max(110, len(self._items) * 34 + 16))

        rx = self.winfo_rootx()
        ry = self.winfo_rooty() + self.winfo_height() + 2
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        if rx + pop_w > screen_w - 12:
            rx = screen_w - pop_w - 12
        if ry + pop_h > screen_h - 40:
            ry = self.winfo_rooty() - pop_h - 2
        pop.wm_geometry(f"{pop_w}x{pop_h}+{max(6, rx)}+{max(6, ry)}")

        body = tk.Frame(pop, bg="#0d0d12")
        body.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        search_var = tk.StringVar()

        # Optional Search + Category Filter Header
        if self.categories:
            top_filter = tk.Frame(body, bg="#12121a", padx=8, pady=6)
            top_filter.pack(fill=tk.X)

            tk.Label(
                top_filter, text="🔎", bg="#12121a", fg="#f59e0b", font=("Segoe UI", 9)
            ).pack(side=tk.LEFT, padx=(0, 4))

            ent_search = tk.Entry(
                top_filter,
                textvariable=search_var,
                bg="#08080c",
                fg="#fafafa",
                insertbackground="#f59e0b",
                relief=tk.FLAT,
                highlightthickness=1,
                highlightbackground="#272732",
                font=("Consolas", 9),
            )
            ent_search.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)
            ent_search.focus_set()

            cat_bar = tk.Frame(body, bg="#0a0a0f", padx=6, pady=5)
            cat_bar.pack(fill=tk.X)
            cat_btns: Dict[str, tk.Label] = {}

            def select_cat(cat_name: str):
                self._active_category = cat_name
                for cname, lbl in cat_btns.items():
                    if cname == cat_name:
                        lbl.configure(bg="#f59e0b", fg="#09090b")
                    else:
                        lbl.configure(bg="#161620", fg="#a1a1aa")
                render_rows()

            for c_name in self.categories:
                b = tk.Label(
                    cat_bar,
                    text=c_name,
                    bg="#f59e0b" if c_name == self._active_category else "#161620",
                    fg="#09090b" if c_name == self._active_category else "#a1a1aa",
                    font=("Consolas", 8, "bold"),
                    padx=7,
                    pady=2,
                    cursor="hand2",
                )
                b.pack(side=tk.LEFT, padx=2)
                b.bind("<Button-1>", lambda _e, cn=c_name: select_cat(cn))
                cat_btns[c_name] = b

        # Scrollable Dark Canvas List
        list_wrap = tk.Frame(body, bg="#0d0d12")
        list_wrap.pack(fill=tk.BOTH, expand=True)

        cv = tk.Canvas(list_wrap, bg="#0d0d12", highlightthickness=0, bd=0)
        cv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        row_regions: List[Tuple[int, int, str, str]] = []
        hover_row_idx = [-1]

        def render_rows(*_args):
            cv.delete("all")
            row_regions.clear()
            q = search_var.get().strip().lower()
            filtered = []
            for it in self._items:
                if self.categories and self._active_category != "ALL":
                    if self._active_category == "PINNED":
                        if not it.get("is_pinned"):
                            continue
                    elif it.get("category") != self._active_category:
                        continue
                if q and q not in it["label"].lower() and q not in it.get("meta", "").lower():
                    continue
                filtered.append(it)

            row_h = 32
            w_cv = pop_w - 4
            if not filtered:
                cv.create_text(
                    w_cv / 2, 40,
                    text="No matching programs found",
                    fill="#71717a",
                    font=("Segoe UI", 9),
                )
                cv.configure(scrollregion=(0, 0, w_cv, 80))
                return

            for idx, it in enumerate(filtered):
                y0 = idx * row_h
                y1 = y0 + row_h
                is_sel = it["value"] == self._selected_value
                is_hov = idx == hover_row_idx[0]
                bg_col = "#1f1f2b" if is_hov else ("#161621" if is_sel else "#0d0d12")
                cv.create_rectangle(0, y0, w_cv, y1, fill=bg_col, outline="")
                cv.create_line(0, y1 - 1, w_cv, y1 - 1, fill="#181820")

                badge_txt = it.get("badge", "")
                badge_col = it.get("color", "#38bdf8")
                text_x = 10
                if badge_txt:
                    cv.create_rectangle(8, y0 + 7, 42, y0 + 24, fill="#181824", outline=badge_col)
                    cv.create_text(25, y0 + 15, text=badge_txt, fill=badge_col, font=("Consolas", 7, "bold"))
                    text_x = 50

                lbl_col = "#f59e0b" if is_sel else "#fafafa"
                cv.create_text(
                    text_x, y0 + 16,
                    text=it["label"],
                    fill=lbl_col,
                    anchor="w",
                    font=("Segoe UI", 9, "bold" if is_sel else "normal"),
                )
                meta_txt = it.get("meta", "")
                if meta_txt:
                    cv.create_text(
                        w_cv - 12, y0 + 16,
                        text=meta_txt[:26],
                        fill="#71717a",
                        anchor="e",
                        font=("Consolas", 8),
                    )
                row_regions.append((y0, y1, it["value"], it["label"]))

            cv.configure(scrollregion=(0, 0, w_cv, len(filtered) * row_h))

        def on_cv_motion(event):
            cy = cv.canvasy(event.y)
            new_idx = int(cy // 32)
            if new_idx != hover_row_idx[0]:
                hover_row_idx[0] = new_idx
                render_rows()

        def on_cv_click(event):
            cy = cv.canvasy(event.y)
            for y0, y1, val, lbl in row_regions:
                if y0 <= cy <= y1:
                    self.set_value(val, lbl)
                    self._close_popup()
                    if self.on_select:
                        self.on_select(val)
                    break

        def on_mousewheel(event):
            cv.yview_scroll(int(-1 * (event.delta / 120)), "units")

        cv.bind("<Motion>", on_cv_motion)
        cv.bind("<Button-1>", on_cv_click)
        cv.bind("<MouseWheel>", on_mousewheel)
        pop.bind("<Escape>", lambda _e: self._close_popup())
        search_var.trace_add("write", render_rows)

        render_rows()

        # Close when clicking outside popup
        def check_outside_click(event):
            if not self._popup:
                return
            w_clicked = event.widget
            if w_clicked in (self, self.lbl_text, self.lbl_arrow):
                return
            try:
                if str(w_clicked).startswith(str(self._popup)):
                    return
            except Exception:
                pass
            self._close_popup()

        self.root.bind("<Button-1>", check_outside_click, add="+")


# =====================================================================
# 10. NATIVE TKINTER STUDIO GUI (ALL 8 IMPROVEMENTS INTEGRATED)
# =====================================================================

class OmniBondDesktopGUI:
    BG_HAIRLINE = "#1e1e24"
    BG_PANEL = "#0b0b0e"
    BG_CARD = "#0e0e12"
    BG_CARD_HOVER = "#14141a"
    TEXT_MAIN = "#fafafa"
    TEXT_MUTED = "#a1a1aa"
    TEXT_DIM = "#52525b"
    AMBER = "#f59e0b"
    EMERALD = "#10b981"
    CYAN = "#38bdf8"

    def __init__(self, engine: OmniBondEngine):
        self.engine = engine
        self.root = tk.Tk()
        self.root.title("OmniBond")
        self.root.geometry("1360x880")
        self.root.minsize(1100, 740)
        self.root.configure(bg=self.BG_HAIRLINE)

        self.tooltip = StudioTooltip(self.root)
        self._hover_chart_x: Optional[int] = None
        self._peak_bps: float = 0.0
        self.graph_mode = "master"
        self.app_view_mode = "grid"
        self.app_filter_mode = "ALL"
        self.app_sort_mode = "AZ"
        self.dd_app = None
        self.dd_policy = None
        self.ent_custom_app: Optional[tk.Entry] = None
        self._process_dropdown_items: List[Dict[str, str]] = []
        self._policy_dropdown_items: List[Dict[str, str]] = []
        self._process_scan_queue: "queue.Queue[Tuple[Optional[List[ProcessInfo]], Optional[Exception]]]" = queue.Queue()
        self._process_scan_in_progress = False
        self._network_tuning_options = {"keep_multi_nic": True, "ipv4": True, "ipv6": False}
        self._app_filter_buttons: Dict[str, tk.Button] = {}
        self._app_filter_button_labels: Dict[str, str] = {}
        self._adapter_card_regions: List[Tuple[int, int, int, int, str]] = []
        self._app_card_regions: List[Tuple[int, int, int, int, str, str, int]] = []
        self._last_Hovered_region_desc: str = ""

        self._build_flush_layout()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._schedule_refresh()

    def _make_studio_btn(
        self,
        parent: tk.Widget,
        text: str,
        tooltip_title: str,
        tooltip_desc: str,
        variant: str = "dark",  # dark | primary | amber | cyan
        cmd: Optional[Callable] = None,
        px: int = 13,
        py: int = 6,
    ) -> tk.Button:
        palette = {
            "dark": ("#14141c", "#fafafa", "#272734", "#1f1f2c", "#f59e0b"),
            "primary": ("#fafafa", "#09090b", "#fafafa", "#f59e0b", "#f59e0b"),
            "amber": ("#f59e0b", "#09090b", "#f59e0b", "#fbbf24", "#fafafa"),
            "cyan": ("#082f49", "#38bdf8", "#0284c7", "#0c4a6e", "#38bdf8"),
        }
        bg, fg, bd_col, hov_bg, hov_bd = palette.get(variant, palette["dark"])

        btn = tk.Button(
            parent,
            text=text,
            bg=bg,
            fg=fg,
            activebackground=hov_bg,
            activeforeground=fg,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=1,
            highlightbackground=bd_col,
            padx=px,
            pady=py,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            command=cmd,
        )

        def on_enter(_e):
            btn.configure(bg=hov_bg, highlightbackground=hov_bd)

        def on_leave(_e):
            btn.configure(bg=bg, highlightbackground=bd_col)

        btn.bind("<Enter>", on_enter, add="+")
        btn.bind("<Leave>", on_leave, add="+")
        self.tooltip.bind_widget(btn, tooltip_title, tooltip_desc)
        return btn

    def _build_flush_layout(self):
        self.root.grid_columnconfigure(0, weight=10)
        self.root.grid_columnconfigure(1, weight=12)
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_rowconfigure(2, weight=0)

        # -----------------------------------------------------------------
        # CONTAINER 0: TOP BAR (Flush)
        # -----------------------------------------------------------------
        topbar = tk.Frame(self.root, bg=self.BG_PANEL, padx=18, pady=12)
        topbar.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=0, pady=(0, 1))

        brand_left = tk.Frame(topbar, bg=self.BG_PANEL)
        brand_left.pack(side=tk.LEFT)

        tk.Label(
            brand_left,
            text="OB",
            bg=self.AMBER,
            fg="#09090b",
            font=("Segoe UI", 10, "bold"),
            padx=6,
            pady=3,
        ).pack(side=tk.LEFT, padx=(0, 12))

        title_col = tk.Frame(brand_left, bg=self.BG_PANEL)
        title_col.pack(side=tk.LEFT)
        tk.Label(
            title_col,
            text="OmniBond",
            bg=self.BG_PANEL,
            fg=self.TEXT_MAIN,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_col,
            text=f"▪ HTTP/HTTPS 127.0.0.1:{self.engine.http_port}    ▪ SOCKS5 127.0.0.1:{self.engine.socks_port}    ▪ Web Dashboard 127.0.0.1:{self.engine.web_port}",
            bg=self.BG_PANEL,
            fg=self.TEXT_MUTED,
            font=("Consolas", 9),
        ).pack(anchor="w")

        actions_right = tk.Frame(topbar, bg=self.BG_PANEL)
        actions_right.pack(side=tk.RIGHT)

        self.btn_proxy = self._make_studio_btn(
            actions_right,
            "◈ Bonding: Off",
            "SYSTEM-WIDE BONDING PROXY",
            "Configures Windows Internet Settings (WinINet) so browsers, games, and desktop apps automatically bond and load-balance across your active network interfaces.",
            variant="primary",
            cmd=self._toggle_system_proxy,
            px=14,
        )
        self.btn_proxy.pack(side=tk.LEFT, padx=(0, 6))

        self._make_studio_btn(
            actions_right,
            "⚙ Network Tuning",
            "SIMULTANEOUS MULTI-NIC OPTIMIZER",
            "Choose whether to keep multiple adapters active and balance IPv4 and IPv6 routes.",
            variant="dark",
            cmd=self._show_network_tuning,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._make_studio_btn(
            actions_right,
            "🩹 Repair Network",
            "EMERGENCY NETWORK RESET & REPAIR",
            "Resets Windows system proxy to Direct, restores all interface metrics to automatic, and flushes the DNS cache.",
            variant="dark",
            cmd=self._repair_network_gui,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self.btn_graph_mode = self._make_studio_btn(
            actions_right,
            "∿ Master Speed",
            "MASTER OR BONDED SPEED",
            "Switch between all computer network traffic and traffic routed through OmniBond.",
            variant="dark",
            cmd=self._toggle_graph_mode,
        )
        self.btn_graph_mode.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_graph_mode.bind(
            "<Leave>",
            lambda _event: self._style_graph_mode_button(),
            add="+",
        )

        self._make_studio_btn(
            actions_right,
            "⟳ Rescan Adapters",
            "RESCAN NETWORK ADAPTERS",
            "Re-scan Windows network adapters and IPv4 addresses.",
            variant="dark",
            cmd=self._rescan_nics,
        ).pack(side=tk.LEFT)

        # -----------------------------------------------------------------
        # CONTAINER 1: 01 / HARDWARE INTERFACES & NON-OVERLAPPING CHART
        # -----------------------------------------------------------------
        c01 = tk.Frame(self.root, bg=self.BG_PANEL)
        c01.grid(row=1, column=0, sticky="nsew", padx=(0, 1), pady=(0, 1))
        c01.grid_columnconfigure(0, weight=1)
        c01.grid_rowconfigure(0, weight=0)
        c01.grid_rowconfigure(1, weight=0)
        c01.grid_rowconfigure(2, weight=1)

        c01_head = tk.Frame(c01, bg=self.BG_PANEL, padx=18, pady=11)
        c01_head.grid(row=0, column=0, sticky="ew")

        c01_titles = tk.Frame(c01_head, bg=self.BG_PANEL)
        c01_titles.pack(side=tk.LEFT)
        tk.Label(
            c01_titles,
            text="01 / HARDWARE INTERFACES · SOCKET BINDING",
            bg=self.BG_PANEL,
            fg=self.AMBER,
            font=("Consolas", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            c01_titles,
            text="Active Network Adapters",
            bg=self.BG_PANEL,
            fg=self.TEXT_MAIN,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", pady=(1, 0))

        self.lbl_adapter_count_meta = tk.Label(
            c01_head,
            text="0 / 0 INTERFACES BONDED · SYSTEM NIC",
            bg="#14141d",
            fg=self.TEXT_MUTED,
            font=("Consolas", 8, "bold"),
            padx=8,
            pady=4,
        )
        self.lbl_adapter_count_meta.pack(side=tk.RIGHT, anchor="s")

        adapter_scroll_frame = tk.Frame(c01, bg=self.BG_PANEL)
        adapter_scroll_frame.grid(row=1, column=0, sticky="ew")
        adapter_scroll_frame.grid_columnconfigure(0, weight=1)
        self.canvas_adapters = tk.Canvas(
            adapter_scroll_frame,
            height=172,
            bg=self.BG_PANEL,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.canvas_adapters.configure(height=172)
        self.canvas_adapters.grid(row=0, column=0, sticky="ew")
        self.adapter_hscroll = tk.Scrollbar(
            adapter_scroll_frame,
            orient=tk.HORIZONTAL,
            command=self.canvas_adapters.xview,
            width=8,
            bg="#3f3f46",
            troughcolor="#0c0c0f",
            activebackground="#52525b",
            bd=0,
            highlightthickness=0,
            relief=tk.FLAT,
        )
        self.adapter_hscroll.grid(row=1, column=0, sticky="ew")
        self.canvas_adapters.configure(xscrollcommand=self.adapter_hscroll.set)
        self.canvas_adapters.bind("<Button-1>", self._on_adapter_card_click)
        self.canvas_adapters.bind("<Shift-MouseWheel>", self._on_adapter_mousewheel)
        self.canvas_adapters.bind("<MouseWheel>", self._on_adapter_mousewheel)
        self.tooltip.bind_widget(
            self.canvas_adapters,
            "NETWORK ADAPTER BENTO CARDS",
            "Click any network adapter card to enable or disable it in the multi-network bonding pool.",
            delay_ms=550,
        )

        self.canvas_chart = tk.Canvas(
            c01,
            bg=self.BG_PANEL,
            highlightthickness=0,
            bd=0,
        )
        self.canvas_chart.grid(row=2, column=0, sticky="nsew")
        self.canvas_chart.bind("<Motion>", self._on_chart_hover)
        self.canvas_chart.bind("<Leave>", self._on_chart_leave)

        # -----------------------------------------------------------------
        # CONTAINER 2: 02 / APPLICATION ROUTER (MODERN DROPDOWN, FILTERS, SPARKLINES & FOCUS)
        # -----------------------------------------------------------------
        c02 = tk.Frame(self.root, bg=self.BG_PANEL)
        c02.grid(row=1, column=1, sticky="nsew", padx=0, pady=(0, 1))
        c02.grid_columnconfigure(0, weight=1)
        c02.grid_rowconfigure(0, weight=0)
        c02.grid_rowconfigure(1, weight=0)
        c02.grid_rowconfigure(2, weight=1)

        c02_head = tk.Frame(c02, bg=self.BG_PANEL, padx=18, pady=11)
        c02_head.grid(row=0, column=0, sticky="ew")

        c02_titles = tk.Frame(c02_head, bg=self.BG_PANEL)
        c02_titles.pack(side=tk.LEFT)
        tk.Label(
            c02_titles,
            text="02 / APPLICATION ROUTER · GETEXTENDEDTCPTABLE PID ENGINE",
            bg=self.BG_PANEL,
            fg=self.AMBER,
            font=("Consolas", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            c02_titles,
            text="Per-Application Network Pinning",
            bg=self.BG_PANEL,
            fg=self.TEXT_MAIN,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", pady=(1, 0))

        self.lbl_running_badge = tk.Label(
            c02_head,
            text="DETECTED RUNNING APPS",
            bg="#14141d",
            fg=self.TEXT_MUTED,
            font=("Consolas", 8, "bold"),
            padx=8,
            pady=4,
        )
        self.lbl_running_badge.pack(side=tk.RIGHT, anchor="s")

        # Group filters and view controls on the left, with Scan/Add on the right.
        toolbar = tk.Frame(c02, bg="#08080b", padx=16, pady=9)
        toolbar.grid(row=1, column=0, sticky="ew")
        toolbar_actions = tk.Frame(toolbar, bg="#08080b")
        toolbar_actions.pack(fill=tk.X)
        left_controls = tk.Frame(toolbar_actions, bg="#08080b")
        left_controls.pack(side=tk.LEFT)
        filters = tk.Frame(left_controls, bg="#08080b")
        filters.pack(side=tk.LEFT)
        for label, mode in (("ALL", "ALL"), ("APPS", "APPS"), ("SERVICES", "SERVICES"), ("FAVORITES", "FAVORITES")):
            button_text = f"✓ {label}" if mode == self.app_filter_mode else label
            filter_button = tk.Button(
                filters,
                text=button_text,
                bg=self.AMBER if mode == self.app_filter_mode else "#14141c",
                fg="#09090b" if mode == self.app_filter_mode else self.TEXT_MAIN,
                activebackground="#fbbf24",
                activeforeground="#09090b" if mode == self.app_filter_mode else self.TEXT_MAIN,
                relief=tk.FLAT,
                bd=0,
                highlightthickness=1,
                highlightbackground=self.AMBER if mode == self.app_filter_mode else "#272734",
                padx=8,
                pady=4,
                cursor="hand2",
                font=("Segoe UI", 9, "bold"),
                command=lambda selected=mode: self._set_app_filter(selected),
            )
            self._app_filter_buttons[mode] = filter_button
            self._app_filter_button_labels[mode] = label
            self.tooltip.bind_widget(
                filter_button,
                f"{mode} APPLICATION FILTER",
                "Filter the application cards by running state, pinned rule, or favorites.",
            )
            filter_button.pack(side=tk.LEFT, padx=(0, 4))

        self._make_studio_btn(
            left_controls,
            "▦ Grid",
            "GRID APPLICATION VIEW",
            "Show applications as a compact multi-column grid.",
            variant="dark",
            cmd=lambda: self._set_app_view("grid"),
            px=8,
            py=4,
        ).pack(side=tk.LEFT, padx=(8, 4))
        self._make_studio_btn(
            left_controls,
            "☷ List",
            "LIST APPLICATION VIEW",
            "Show applications in a full-width list.",
            variant="dark",
            cmd=lambda: self._set_app_view("list"),
            px=8,
            py=4,
        ).pack(side=tk.LEFT)
        self.dd_app_sort = StudioDropdown(
            left_controls,
            self.root,
            width_px=154,
            placeholder="Sort apps",
        )
        self.dd_app_sort.pack(side=tk.LEFT, padx=(8, 0))
        self.dd_app_sort.set_items([
            {"value": "AZ", "label": "Name: A-Z", "meta": "Alphabetical", "badge": "A–Z", "color": self.CYAN},
            {"value": "ZA", "label": "Name: Z-A", "meta": "Reverse alphabetical", "badge": "Z–A", "color": self.CYAN},
            {"value": "FAST", "label": "Speed: High–Low", "meta": "Most active first", "badge": "↑", "color": self.EMERALD},
            {"value": "SLOW", "label": "Speed: Low–High", "meta": "Least active first", "badge": "↓", "color": self.EMERALD},
        ])
        self.dd_app_sort.set_value(self.app_sort_mode, "Name: A-Z")
        self.dd_app_sort.on_select = self._set_app_sort
        self.tooltip.bind_widget(
            self.dd_app_sort,
            "SORT APPLICATIONS",
            "Sort by application name or current network speed.",
        )

        right_actions = tk.Frame(toolbar_actions, bg="#08080b")
        right_actions.pack(side=tk.RIGHT)
        self._make_studio_btn(
            right_actions,
            "+ Add Program",
            "ADD APPLICATION & ROUTING POLICY",
            "Choose a detected application or the built-in engine, select a routing policy, or browse for an executable.",
            variant="cyan",
            cmd=self._open_add_program_popup,
            px=10,
            py=4,
        ).pack(side=tk.RIGHT)
        self._make_studio_btn(
            right_actions,
            "↻ Scan",
            "SCAN RUNNING WINDOWS PROCESSES",
            "Refreshes active Windows processes, visible application windows, and open TCP sockets.",
            variant="dark",
            cmd=self._refresh_process_dropdown,
            px=9,
            py=4,
        ).pack(side=tk.RIGHT, padx=(0, 6))

        self.app_scroll_frame = tk.Frame(c02, bg=self.BG_PANEL)
        self.app_scroll_frame.grid(row=2, column=0, sticky="nsew")
        self.app_scroll_frame.grid_rowconfigure(0, weight=1)
        self.app_scroll_frame.grid_columnconfigure(0, weight=1)
        self.canvas_apps = tk.Canvas(
            self.app_scroll_frame,
            bg=self.BG_PANEL,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.canvas_apps.grid(row=0, column=0, sticky="nsew")
        self.app_vscroll = tk.Scrollbar(
            self.app_scroll_frame,
            orient=tk.VERTICAL,
            command=self.canvas_apps.yview,
            width=8,
            bg="#3f3f46",
            troughcolor="#0c0c0f",
            activebackground="#52525b",
            bd=0,
            highlightthickness=0,
            relief=tk.FLAT,
        )
        self.app_vscroll.grid(row=0, column=1, sticky="ns")
        self.canvas_apps.configure(
            yscrollcommand=self.app_vscroll.set,
            yscrollincrement=40,
        )
        self.canvas_apps.bind("<Button-1>", self._on_app_card_click)
        self.canvas_apps.bind("<Motion>", self._on_app_card_motion)
        self.canvas_apps.bind("<Leave>", lambda _e: self.tooltip.hide())
        self.canvas_apps.bind("<MouseWheel>", self._on_app_mousewheel)

        # -----------------------------------------------------------------
        # CONTAINER 3: 03 / UNIFIED URL BAR + GLOWING PROGRESS TRACK & BLOCK MATRIX
        # -----------------------------------------------------------------
        c03 = tk.Frame(self.root, bg=self.BG_PANEL, padx=18, pady=12)
        c03.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=0, pady=0)

        c03_top = tk.Frame(c03, bg=self.BG_PANEL)
        c03_top.pack(fill=tk.X, pady=(0, 6))

        c03_titles = tk.Frame(c03_top, bg=self.BG_PANEL)
        c03_titles.pack(side=tk.LEFT)
        tk.Label(
            c03_titles,
            text="03 / PARALLEL RANGE & HLS (.M3U8) ENGINE · ENDGAME RACING",
            bg=self.BG_PANEL,
            fg=self.AMBER,
            font=("Consolas", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            c03_titles,
            text="Download & Stream Accelerator",
            bg=self.BG_PANEL,
            fg=self.TEXT_MAIN,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", pady=(1, 0))

        self.lbl_dl_badge = tk.Label(
            c03_top,
            text="IDLE · 0.0 KB/s · 0%",
            bg="#14141d",
            fg=self.AMBER,
            font=("Consolas", 9, "bold"),
            padx=10,
            pady=4,
        )
        self.lbl_dl_badge.pack(side=tk.RIGHT, anchor="s")

        # Unified URL + Progress + Block Console Box
        console_box = tk.Frame(c03, bg=self.BG_PANEL, padx=0, pady=0)
        console_box.pack(fill=tk.X)

        url_bar_frame = tk.Frame(console_box, bg=self.BG_PANEL)
        url_bar_frame.pack(fill=tk.X)

        tk.Label(
            url_bar_frame,
            text=" STREAM / FILE URL ",
            bg="#161622",
            fg=self.AMBER,
            font=("Consolas", 8, "bold"),
            padx=8,
            pady=7,
        ).pack(side=tk.LEFT)

        self.ent_url = tk.Entry(
            url_bar_frame,
            bg="#0d0d14",
            fg=self.TEXT_MAIN,
            insertbackground=self.AMBER,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground="#222230",
            font=("Consolas", 10),
        )
        self.ent_url.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=6)
        self.tooltip.bind_widget(
            self.ent_url,
            "DIRECT FILE OR HLS (.M3U8) STREAM URL",
            "Paste any HTTP/HTTPS file link or .m3u8 video stream URL to split and accelerate across your active network adapters.",
        )

        self._make_studio_btn(
            url_bar_frame,
            "⬇ Download",
            "START MULTI-NIC PARALLEL DOWNLOAD",
            "Splits the target file into parallel byte-range blocks across your enabled network adapters with Endgame Backup Racing.",
            variant="primary",
            cmd=self._start_turbo_download,
            px=16,
            py=6,
        ).pack(side=tk.LEFT)

        # Integrated Glowing Progress Bar + Segmented Block Matrix Canvas
        self.canvas_dl_unified = tk.Canvas(
            console_box,
            height=46,
            bg="#07070a",
            highlightthickness=0,
            bd=0,
        )
        self.canvas_dl_unified.pack(fill=tk.X, pady=(8, 0))
        self.tooltip.bind_widget(
            self.canvas_dl_unified,
            "LIVE PROGRESS & MULTI-NIC BLOCK MATRIX",
            "Top bar shows overall download completion and live speed; bottom segments show individual blocks color-coded by the network adapter downloading them.",
            delay_ms=550,
        )

        self._refresh_process_dropdown()

    # -----------------------------------------------------------------
    # DROPDOWN & ACTION HANDLERS
    # -----------------------------------------------------------------

    def _refresh_process_dropdown(self):
        if self._process_scan_in_progress:
            return
        self._process_scan_in_progress = True

        def scan_processes():
            try:
                self._process_scan_queue.put((self.engine.scan_and_sync_processes(), None))
            except Exception as exc:
                self._process_scan_queue.put((None, exc))

        threading.Thread(
            target=scan_processes,
            name="omnibond-process-scan",
            daemon=True,
        ).start()

    def _apply_process_scan_result(self):
        try:
            detailed, error = self._process_scan_queue.get_nowait()
        except queue.Empty:
            return
        self._process_scan_in_progress = False
        if error:
            print(f"Could not refresh running applications: {error}", file=sys.stderr)
            return
        if detailed is None:
            return
        dd_items: List[Dict[str, str]] = [
            {
                "value": TURBO_APP_KEY,
                "label": TURBO_APP_LABEL,
                "meta": "Built-in Engine",
                "category": "USER APPS",
                "badge": "ENG",
                "color": self.AMBER,
                "is_pinned": self.engine.routing_mgr.get_rule(TURBO_APP_KEY) != "AUTO",
            }
        ]
        for p in detailed:
            if p.category == "USER APPS":
                badge, col = "APP", "#38bdf8"
            elif p.category == "ACTIVE NET":
                badge, col = "NET", "#34d399"
            else:
                badge, col = "BG", "#a1a1aa"

            meta_parts = [f"PID {p.pid}"]
            if p.window_title:
                meta_parts.append(p.window_title[:20])
            elif p.has_active_socket:
                meta_parts.append("Active Socket")

            dd_items.append({
                "value": p.exe_name,
                "label": p.exe_name,
                "meta": " · ".join(meta_parts),
                "category": p.category,
                "badge": badge,
                "color": col,
                "is_pinned": p.is_pinned or (self.engine.routing_mgr.get_rule(p.exe_name) != "AUTO"),
            })
        self._process_dropdown_items = dd_items
        if self.dd_app is not None and self.dd_app.winfo_exists():
            self.dd_app.set_items(dd_items)

    def _refresh_policy_dropdown(self, adapters: List[NetworkAdapter]):
        pol_items: List[Dict[str, str]] = [
            {
                "value": "AUTO",
                "label": "Auto / Bonded (All NICs)",
                "meta": "Load Balanced",
                "badge": "ALL",
                "color": self.EMERALD,
            },
            {
                "value": BLOCK_INTERNET_RULE,
                "label": "Block Internet",
                "meta": "Disable network access",
                "badge": "BLOCK",
                "color": "#ef4444",
            }
        ]
        for idx, a in enumerate(adapters):
            pol_items.append({
                "value": a.ip,
                "label": f"{idx + 1:02d} · {a.name} ({a.ip})",
                "meta": a.kind,
                "badge": f"#{idx + 1:02d}",
                "color": a.color,
            })
        self._policy_dropdown_items = pol_items
        if self.dd_policy is not None and self.dd_policy.winfo_exists():
            self.dd_policy.set_items(pol_items)

    def _assign_app_rule(self):
        if self.dd_app is None or self.dd_policy is None:
            return False
        custom_name = self.ent_custom_app.get().strip() if self.ent_custom_app else ""
        app_val = custom_name or self.dd_app.get_value().strip()
        if not app_val:
            return False
        target_ip = self.dd_policy.get_value().strip() or "AUTO"
        self.engine.routing_mgr.set_rule(app_val, target_ip, explicit_add=True)
        self._update_ui()
        return True

    def _open_add_program_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("Add application")
        popup.configure(bg=self.BG_PANEL)
        popup.resizable(False, False)
        popup.transient(self.root)
        popup.grab_set()
        popup.geometry(f"510x370+{self.root.winfo_rootx() + 220}+{self.root.winfo_rooty() + 180}")

        def close_popup():
            self.dd_app = None
            self.dd_policy = None
            self.ent_custom_app = None
            popup.destroy()

        popup.protocol(
            "WM_DELETE_WINDOW",
            close_popup,
        )

        body = tk.Frame(popup, bg=self.BG_PANEL, padx=18, pady=16)
        body.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            body, text="ADD APPLICATION TO OMNIBOND", bg=self.BG_PANEL,
            fg=self.AMBER, font=("Consolas", 9, "bold"),
        ).pack(anchor="w", pady=(0, 12))
        tk.Label(
            body, text="Engine / application", bg=self.BG_PANEL,
            fg=self.TEXT_MUTED, font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        self.dd_app = StudioDropdown(
            body, self.root, width_px=460,
            categories=["ALL", "USER APPS", "ACTIVE NET", "PINNED", "SERVICES / BG"],
            placeholder="Select a running application...",
        )
        self.dd_app.pack(fill=tk.X, pady=(5, 12))
        self.dd_app.set_items(self._process_dropdown_items)

        tk.Label(
            body, text="Or enter an executable name", bg=self.BG_PANEL,
            fg=self.TEXT_MUTED, font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        self.ent_custom_app = tk.Entry(
            body,
            bg="#0d0d14",
            fg=self.TEXT_MAIN,
            insertbackground=self.AMBER,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground="#222230",
            font=("Consolas", 10),
        )
        self.ent_custom_app.pack(fill=tk.X, pady=(5, 12), ipady=5)

        tk.Label(
            body, text="Network policy", bg=self.BG_PANEL,
            fg=self.TEXT_MUTED, font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        self.dd_policy = StudioDropdown(
            body, self.root, width_px=460, categories=[],
            placeholder="Auto / Bonded",
        )
        self.dd_policy.pack(fill=tk.X, pady=(5, 12))
        self.dd_policy.set_items(self._policy_dropdown_items)

        actions = tk.Frame(body, bg=self.BG_PANEL)
        actions.pack(fill=tk.X, side=tk.BOTTOM)
        self._make_studio_btn(
            actions, "Cancel", "CLOSE", "Close without adding an application.",
            variant="dark",
            cmd=close_popup,
            px=10, py=5,
        ).pack(side=tk.RIGHT, padx=(6, 0))
        self._make_studio_btn(
            actions, "Add & Apply Policy", "ADD APPLICATION AND APPLY POLICY",
            "Save the selected application with the chosen adapter policy.",
            variant="amber", cmd=lambda: self._assign_app_rule_and_close(popup), px=10, py=5,
        ).pack(side=tk.RIGHT)

    def _assign_app_rule_and_close(self, popup: tk.Toplevel):
        if self._assign_app_rule():
            self.dd_app = None
            self.dd_policy = None
            self.ent_custom_app = None
            popup.destroy()

    def _choose_app_location(self, app_name: str):
        is_folder = messagebox.askyesno(
            "Program Location",
            "Choose an installation folder?\n\nSelect No to choose the executable file.",
        )
        if is_folder:
            location = filedialog.askdirectory(title=f"Choose the installation folder for {app_name}")
        else:
            location = filedialog.askopenfilename(
                title=f"Choose the executable for {app_name}",
                filetypes=[("Executable Programs", "*.exe"), ("All Files", "*.*")],
            )
        if not location:
            return
        key = self.engine.process_mapper.register_custom_app_location(app_name, location)
        if not key:
            messagebox.showwarning("Program Location", "The selected path could not be saved.")
            return
        self.engine.routing_mgr.set_rule(key, self.engine.routing_mgr.get_rule(key), explicit_add=True)
        self._refresh_process_dropdown()
        self._update_ui()

    def _set_app_view(self, mode: str):
        self.app_view_mode = "list" if mode == "list" else "grid"
        self.canvas_apps.yview_moveto(0)
        self._draw_app_bento_cards(
            self._sort_app_entries(self._filter_app_entries(self.engine.routing_mgr.get_all_entries(only_running_or_added=True))),
            self.engine.adapter_mgr.get_adapters(),
        )

    def _set_app_filter(self, mode: str):
        self.app_filter_mode = mode
        for filter_mode, button in self._app_filter_buttons.items():
            label = self._app_filter_button_labels[filter_mode]
            active = filter_mode == mode
            button.configure(text=f"✓ {label}" if filter_mode == mode else label)
            button.configure(
                bg=self.AMBER if active else "#14141c",
                fg="#09090b" if active else self.TEXT_MAIN,
                activeforeground="#09090b" if active else self.TEXT_MAIN,
                highlightbackground=self.AMBER if active else "#272734",
            )
        self._update_ui()

    def _set_app_sort(self, mode: str):
        self.app_sort_mode = mode if mode in ("AZ", "ZA", "FAST", "SLOW") else "AZ"
        label = {
            "AZ": "Name: A-Z",
            "ZA": "Name: Z-A",
            "FAST": "Speed: High–Low",
            "SLOW": "Speed: Low–High",
        }[self.app_sort_mode]
        self.dd_app_sort.set_value(self.app_sort_mode, label)
        self._update_ui()

    def _sort_app_entries(self, entries: List[Dict]) -> List[Dict]:
        if self.app_sort_mode == "ZA":
            return sorted(entries, key=lambda entry: entry["display_name"].casefold(), reverse=True)
        if self.app_sort_mode == "FAST":
            return sorted(entries, key=lambda entry: (-entry.get("bps", 0), entry["display_name"].casefold()))
        if self.app_sort_mode == "SLOW":
            return sorted(entries, key=lambda entry: (entry.get("bps", 0), entry["display_name"].casefold()))
        return sorted(entries, key=lambda entry: entry["display_name"].casefold())

    def _show_card_policy_menu(self, app_key: str, screen_x: int, screen_y: int):
        selected = self.engine.routing_mgr.get_rule(app_key)
        menu = tk.Menu(
            self.root,
            tearoff=False,
            bg="#0d0d12",
            fg=self.TEXT_MAIN,
            font=("Segoe UI", 9),
            activebackground=self.AMBER,
            activeforeground="#09090b",
            activeborderwidth=0,
            borderwidth=1,
            relief=tk.FLAT,
        )
        options = [
            ("AUTO", "Auto / Bonded (All NICs)"),
            (BLOCK_INTERNET_RULE, "Block Internet"),
        ]
        options.extend(
            (adapter.ip, f"{adapter.name} ({adapter.ip})")
            for adapter in self.engine.adapter_mgr.get_adapters()
        )
        for value, label in options:
            menu.add_command(
                label=("✓ " if value == selected else "  ") + label,
                command=lambda chosen=value: self._select_card_policy(app_key, chosen),
            )
        menu.tk_popup(screen_x, screen_y)

    def _select_card_policy(self, app_key: str, policy: str):
        self.engine.routing_mgr.set_rule(app_key, policy, explicit_add=True)
        self._update_ui()

    def _filter_app_entries(self, entries: List[Dict]) -> List[Dict]:
        if self.app_filter_mode == "APPS":
            return [
                entry for entry in entries
                if entry.get("is_running")
                and not entry.get("is_builtin")
                and entry.get("category") != "SERVICES / BG"
            ]
        if self.app_filter_mode == "SERVICES":
            return [
                entry for entry in entries
                if entry.get("is_running") and entry.get("category") == "SERVICES / BG"
            ]
        if self.app_filter_mode == "FAVORITES":
            return [entry for entry in entries if entry.get("is_favorite")]
        return entries

    def _on_app_mousewheel(self, event):
        self.canvas_apps.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_adapter_mousewheel(self, event):
        self.canvas_adapters.xview_scroll(int(-1 * (event.delta / 120)), "units")

    def _rescan_nics(self):
        self.engine.adapter_mgr.refresh_adapters()
        self._update_ui()

    def _on_chart_hover(self, event):
        self._hover_chart_x = event.x
        self._draw_google_chart(self.engine.adapter_mgr.get_adapters())

    def _on_chart_leave(self, _event):
        self._hover_chart_x = None
        self._draw_google_chart(self.engine.adapter_mgr.get_adapters())

    def _on_adapter_card_click(self, event):
        canvas_x = self.canvas_adapters.canvasx(event.x)
        canvas_y = self.canvas_adapters.canvasy(event.y)
        for x0, y0, x1, y1, ip in self._adapter_card_regions:
            if x0 <= canvas_x <= x1 and y0 <= canvas_y <= y1:
                ad = self.engine.adapter_mgr.adapters.get(ip)
                if ad:
                    if self.engine.adapter_mgr.is_quota_exceeded(ad):
                        return
                    ad.enabled = not ad.enabled
                    self._update_ui()
                break

    def _on_app_card_motion(self, event):
        canvas_x = self.canvas_apps.canvasx(event.x)
        canvas_y = self.canvas_apps.canvasy(event.y)
        for x0, y0, x1, y1, rtype, app_key, _pid in self._app_card_regions:
            if x0 <= canvas_x <= x1 and y0 <= canvas_y <= y1:
                desc_key = f"{rtype}:{app_key}"
                if desc_key != self._last_Hovered_region_desc:
                    self._last_Hovered_region_desc = desc_key
                    if rtype == "focus":
                        self.tooltip.schedule(
                            f"FOCUS {app_key.upper()}\nBrings the running {app_key} window to the foreground.",
                            delay_ms=280,
                        )
                    elif rtype == "favorite":
                        self.tooltip.schedule(
                            f"TOGGLE FAVORITE ({app_key.upper()})\nFavorites stay visible and sort ahead of other application cards.",
                            delay_ms=280,
                        )
                    elif rtype == "location":
                        self.tooltip.schedule(
                            f"OPEN LOCATION ({app_key.upper()})\nOpens this application's executable in Explorer or its saved installation folder.",
                            delay_ms=280,
                        )
                    elif rtype == "policy":
                        self.tooltip.schedule(
                            f"SELECT ROUTING POLICY ({app_key.upper()})\nChoose a policy to apply it to this application.",
                            delay_ms=350,
                        )
                return
        self._last_Hovered_region_desc = ""
        self.tooltip.hide()

    def _on_app_card_click(self, event):
        canvas_x = self.canvas_apps.canvasx(event.x)
        canvas_y = self.canvas_apps.canvasy(event.y)
        for x0, y0, x1, y1, rtype, app_key, last_pid in self._app_card_regions:
            if x0 <= canvas_x <= x1 and y0 <= canvas_y <= y1:
                if rtype == "focus":
                    ok, msg = self.engine.process_mapper.focus_or_locate_app(app_key, last_pid)
                    if not ok:
                        messagebox.showinfo("Focus Program", msg)
                    return
                if rtype == "location":
                    ok, msg = self.engine.process_mapper.locate_app(app_key, last_pid)
                    if not ok:
                        if messagebox.askyesno("Program Location", f"{msg}\n\nChoose an executable or installation folder now?"):
                            self._choose_app_location(app_key)
                        else:
                            messagebox.showinfo("Program Location", msg)
                    return
                if rtype == "favorite":
                    saved = self.engine.routing_mgr.set_favorite(
                        app_key, not self.engine.routing_mgr.is_favorite(app_key)
                    )
                    if not saved:
                        messagebox.showwarning("Favorites", "Could not save this favorite setting.")
                    self._update_ui()
                    return
                if rtype == "policy":
                    self._show_card_policy_menu(app_key, event.x_root, event.y_root)
                    return

    def _toggle_system_proxy(self):
        new_state = not self.engine.sys_opt.system_proxy_enabled
        ok, msg = self.engine.sys_opt.set_system_proxy(new_state, "127.0.0.1", self.engine.http_port)
        if not ok:
            messagebox.showwarning("OmniBond", msg)
        self._update_ui()

    def _repair_network_gui(self):
        ok, msg = self.engine.sys_opt.repair_network()
        self._update_ui()
        messagebox.showinfo("Network Repaired", msg)

    def _show_network_tuning(self):
        window = tk.Toplevel(self.root)
        window.title("Network Tuning")
        window.configure(bg=self.BG_PANEL)
        window.geometry("820x720")
        window.minsize(680, 520)
        window.transient(self.root)
        window.grab_set()

        panel = tk.Frame(window, bg=self.BG_PANEL, padx=20, pady=16)
        panel.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            panel,
            text="NETWORK TUNING",
            bg=self.BG_PANEL,
            fg=self.AMBER,
            font=("Consolas", 10, "bold"),
        ).pack(anchor="w")
        tk.Label(
            panel,
            text="Choose which Windows network optimizations to apply.",
            bg=self.BG_PANEL,
            fg=self.TEXT_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(4, 12))

        options = {
            "keep_multi_nic": tk.BooleanVar(value=self._network_tuning_options["keep_multi_nic"]),
            "ipv4": tk.BooleanVar(value=self._network_tuning_options["ipv4"]),
            "ipv6": tk.BooleanVar(value=self._network_tuning_options["ipv6"]),
        }
        labels = (
            ("keep_multi_nic", "Keep multiple network adapters active"),
            ("ipv4", "Balance IPv4 interface routes"),
            ("ipv6", "Balance IPv6 interface routes"),
        )
        for key, label in labels:
            tk.Checkbutton(
                panel,
                text=label,
                variable=options[key],
                bg=self.BG_PANEL,
                fg=self.TEXT_MAIN,
                activebackground=self.BG_PANEL,
                activeforeground=self.TEXT_MAIN,
                selectcolor="#14141c",
                font=("Segoe UI", 9),
                anchor="w",
                padx=4,
            ).pack(fill=tk.X, pady=4)

        optimization_status = tk.Label(
            panel,
            text="",
            bg=self.BG_PANEL,
            fg=self.TEXT_MUTED,
            font=("Consolas", 8),
            justify=tk.LEFT,
            wraplength=760,
        )
        optimization_status.pack(fill=tk.X, pady=(8, 8))

        tk.Label(
            panel,
            text="PER-ADAPTER DATA & SPEED LIMITS",
            bg=self.BG_PANEL,
            fg=self.AMBER,
            font=("Consolas", 9, "bold"),
        ).pack(anchor="w", pady=(6, 4))
        tk.Label(
            panel,
            text=(
                "Data caps count all adapter traffic and exclude the adapter from new OmniBond "
                "connections when reached. Custom speed limits apply to OmniBond-routed traffic."
            ),
            bg=self.BG_PANEL,
            fg=self.TEXT_MUTED,
            font=("Segoe UI", 8),
            justify=tk.LEFT,
            wraplength=760,
        ).pack(fill=tk.X, pady=(0, 8))

        limits_frame = tk.Frame(panel, bg=self.BG_PANEL)
        limits_frame.pack(fill=tk.BOTH, expand=True)
        limits_frame.grid_rowconfigure(0, weight=1)
        limits_frame.grid_columnconfigure(0, weight=1)
        limits_canvas = tk.Canvas(
            limits_frame,
            bg=self.BG_PANEL,
            highlightthickness=0,
            bd=0,
        )
        limits_canvas.grid(row=0, column=0, sticky="nsew")
        limits_scrollbar = tk.Scrollbar(
            limits_frame,
            orient=tk.VERTICAL,
            command=limits_canvas.yview,
            width=8,
            bg="#3f3f46",
            troughcolor="#0c0c0f",
            activebackground="#52525b",
            bd=0,
            highlightthickness=0,
            relief=tk.FLAT,
        )
        limits_scrollbar.grid(row=0, column=1, sticky="ns")
        limits_canvas.configure(yscrollcommand=limits_scrollbar.set)
        limits_content = tk.Frame(limits_canvas, bg=self.BG_PANEL)
        limits_window_id = limits_canvas.create_window(
            (0, 0), window=limits_content, anchor="nw"
        )
        limits_content.bind(
            "<Configure>",
            lambda _event: limits_canvas.configure(
                scrollregion=limits_canvas.bbox("all")
            ),
        )
        limits_canvas.bind(
            "<Configure>",
            lambda event: limits_canvas.itemconfigure(limits_window_id, width=event.width),
        )
        limits_canvas.bind(
            "<MouseWheel>",
            lambda event: limits_canvas.yview_scroll(int(-event.delta / 120), "units"),
        )

        adapters = self.engine.adapter_mgr.get_adapters()
        if not adapters:
            tk.Label(
                limits_content,
                text="No network adapters are currently available.",
                bg=self.BG_PANEL,
                fg=self.TEXT_MUTED,
                font=("Segoe UI", 9),
                padx=12,
                pady=16,
            ).pack(fill=tk.X)

        def add_dropdown(parent, variable, values, width=12, command=None):
            dropdown = tk.OptionMenu(parent, variable, *values, command=command)
            dropdown.configure(
                bg="#09090d",
                fg=self.TEXT_MAIN,
                activebackground="#1f1f2c",
                activeforeground=self.TEXT_MAIN,
                highlightthickness=1,
                highlightbackground="#30303b",
                relief=tk.FLAT,
                bd=0,
                width=width,
                font=("Consolas", 8),
                anchor="w",
            )
            dropdown["menu"].configure(
                bg="#101016",
                fg=self.TEXT_MAIN,
                activebackground="#292932",
                activeforeground=self.TEXT_MAIN,
                font=("Segoe UI", 9),
                bd=0,
            )
            return dropdown

        for adapter in adapters:
            snapshot = self.engine.adapter_mgr.get_adapter_limit_snapshot(adapter)
            card = tk.Frame(
                limits_content,
                bg="#101016",
                highlightthickness=1,
                highlightbackground=self.BG_HAIRLINE,
                padx=12,
                pady=10,
            )
            card.pack(fill=tk.X, pady=(0, 6))
            tk.Label(
                card,
                text=f"{adapter.name}  ·  {adapter.kind}",
                bg="#101016",
                fg=self.TEXT_MAIN,
                font=("Segoe UI", 10, "bold"),
            ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

            cycle_hours = snapshot["cycle_hours"]
            if cycle_hours >= 24 and abs(cycle_hours % 24) < 0.0001:
                cycle_unit, cycle_value = "days", cycle_hours / 24
            elif cycle_hours < 1:
                cycle_unit, cycle_value = "minutes", round(cycle_hours * 60)
            else:
                cycle_unit, cycle_value = "hours", cycle_hours

            def add_field(parent, title, row, column):
                cell = tk.Frame(parent, bg="#101016")
                cell.grid(
                    row=row,
                    column=column,
                    sticky="ew",
                    padx=(0, 8) if column == 0 else (8, 0),
                    pady=4,
                )
                tk.Label(
                    cell,
                    text=title,
                    bg="#101016",
                    fg=self.TEXT_MUTED,
                    font=("Consolas", 8, "bold"),
                ).pack(anchor="w", pady=(0, 3))
                return cell

            card.grid_columnconfigure(0, weight=1)
            card.grid_columnconfigure(1, weight=1)

            data_cell = add_field(card, "DATA CAP", 1, 0)
            data_mode = tk.StringVar(
                value="Custom" if snapshot["data_limit_bytes"] else "Unlimited"
            )
            data_mode_wrap = tk.Frame(data_cell, bg="#101016")
            data_mode_wrap.pack(fill=tk.X)
            data_entry = tk.Entry(
                data_mode_wrap,
                bg="#09090d",
                fg=self.TEXT_MAIN,
                insertbackground=self.AMBER,
                disabledbackground="#09090d",
                disabledforeground=self.TEXT_MUTED,
                relief=tk.FLAT,
                highlightthickness=1,
                highlightbackground="#30303b",
                font=("Consolas", 9),
            )
            if snapshot["data_limit_bytes"]:
                data_entry.insert(0, f"{snapshot['data_limit_bytes'] / 1_000_000_000:.3f}")
            else:
                data_entry.configure(state=tk.DISABLED)
            data_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
            data_mode_menu = add_dropdown(
                data_mode_wrap,
                data_mode,
                ("Unlimited", "Custom"),
                width=10,
                command=lambda choice, entry=data_entry: entry.configure(
                    state=tk.NORMAL if choice == "Custom" else tk.DISABLED
                ),
            )
            data_mode_menu.pack(side=tk.RIGHT, padx=(5, 0))

            cycle_cell = add_field(card, "RESET WINDOW", 1, 1)
            cycle_wrap = tk.Frame(cycle_cell, bg="#101016")
            cycle_wrap.pack(fill=tk.X)
            cycle_entry = tk.Entry(
                cycle_wrap,
                bg="#09090d",
                fg=self.TEXT_MAIN,
                insertbackground=self.AMBER,
                relief=tk.FLAT,
                highlightthickness=1,
                highlightbackground="#30303b",
                font=("Consolas", 9),
                width=10,
            )
            cycle_entry.insert(0, f"{cycle_value:g}")
            cycle_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
            cycle_unit_var = tk.StringVar(value=cycle_unit)
            add_dropdown(
                cycle_wrap,
                cycle_unit_var,
                ("minutes", "hours", "days"),
                width=9,
            ).pack(side=tk.RIGHT, padx=(5, 0))

            def add_speed_field(title, row, initial_value):
                cell = add_field(card, title, row, 0)
                mode = tk.StringVar(
                    value="Custom" if initial_value > 0 else "Unlimited"
                )
                wrap = tk.Frame(cell, bg="#101016")
                wrap.pack(fill=tk.X)
                value_entry = tk.Entry(
                    wrap,
                    bg="#09090d",
                    fg=self.TEXT_MAIN,
                    insertbackground=self.AMBER,
                    disabledbackground="#09090d",
                    disabledforeground=self.TEXT_MUTED,
                    relief=tk.FLAT,
                    highlightthickness=1,
                    highlightbackground="#30303b",
                    font=("Consolas", 9),
                )
                if initial_value > 0:
                    value_entry.insert(0, f"{initial_value:g}")
                else:
                    value_entry.configure(state=tk.DISABLED)
                value_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
                mode_menu = add_dropdown(
                    wrap,
                    mode,
                    ("Unlimited", "Custom"),
                    width=10,
                    command=lambda choice, entry=value_entry: entry.configure(
                        state=tk.NORMAL if choice == "Custom" else tk.DISABLED
                    ),
                )
                mode_menu.pack(side=tk.RIGHT, padx=(5, 0))
                return mode, value_entry

            download_mode, download_entry = add_speed_field(
                "DOWNLOAD LIMIT (Mbps)", 2, snapshot["download_limit_mbps"]
            )
            upload_cell = add_field(card, "UPLOAD LIMIT (Mbps)", 2, 1)
            upload_mode = tk.StringVar(
                value="Custom" if snapshot["upload_limit_mbps"] > 0 else "Unlimited"
            )
            upload_wrap = tk.Frame(upload_cell, bg="#101016")
            upload_wrap.pack(fill=tk.X)
            upload_entry = tk.Entry(
                upload_wrap,
                bg="#09090d",
                fg=self.TEXT_MAIN,
                insertbackground=self.AMBER,
                disabledbackground="#09090d",
                disabledforeground=self.TEXT_MUTED,
                relief=tk.FLAT,
                highlightthickness=1,
                highlightbackground="#30303b",
                font=("Consolas", 9),
            )
            if snapshot["upload_limit_mbps"] > 0:
                upload_entry.insert(0, f"{snapshot['upload_limit_mbps']:g}")
            else:
                upload_entry.configure(state=tk.DISABLED)
            upload_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
            add_dropdown(
                upload_wrap,
                upload_mode,
                ("Unlimited", "Custom"),
                width=10,
                command=lambda choice, entry=upload_entry: entry.configure(
                    state=tk.NORMAL if choice == "Custom" else tk.DISABLED
                ),
            ).pack(side=tk.RIGHT, padx=(5, 0))

            reset_at = time.strftime(
                "%Y-%m-%d %H:%M",
                time.localtime(snapshot["period_started_at"] + cycle_hours * 3600),
            )
            current_cap = (
                self._fmt_bytes(snapshot["data_limit_bytes"])
                if snapshot["data_limit_bytes"] else "No data cap"
            )
            status_text = (
                "LIMIT REACHED · excluded from new OmniBond connections"
                if snapshot["quota_exceeded"]
                else (
                    f"{self._fmt_bytes(snapshot['usage_bytes'])} / {current_cap} · "
                    f"window resets {reset_at}"
                )
            )
            status_label = tk.Label(
                card,
                text=status_text,
                bg="#101016",
                fg="#f87171" if snapshot["quota_exceeded"] else self.TEXT_MUTED,
                font=("Consolas", 8),
                justify=tk.LEFT,
                anchor="w",
            )
            status_label.grid(row=3, column=0, sticky="ew", pady=(5, 0))

            def save_limits(
                adapter_name=adapter.name,
                status=status_label,
                data_mode_var=data_mode,
                data_field=data_entry,
                cycle_field=cycle_entry,
                unit_var=cycle_unit_var,
                download_mode_var=download_mode,
                download_field=download_entry,
                upload_mode_var=upload_mode,
                upload_field=upload_entry,
            ):
                try:
                    cycle_value_num = float(cycle_field.get().strip())
                    if cycle_value_num <= 0:
                        raise ValueError("Reset window must be greater than zero.")
                    cycle_unit_value = unit_var.get()
                    cycle_multiplier = {
                        "minutes": 1 / 60,
                        "hours": 1,
                        "days": 24,
                    }[cycle_unit_value]
                    data_gb = 0.0
                    if data_mode_var.get() == "Custom":
                        data_gb = float(data_field.get().strip())
                        if data_gb <= 0:
                            raise ValueError("Enter a data cap greater than zero, or choose Unlimited.")
                    download_mbps = 0.0
                    if download_mode_var.get() == "Custom":
                        download_mbps = float(download_field.get().strip())
                        if download_mbps <= 0:
                            raise ValueError("Enter a download limit greater than zero, or choose Unlimited.")
                    upload_mbps = 0.0
                    if upload_mode_var.get() == "Custom":
                        upload_mbps = float(upload_field.get().strip())
                        if upload_mbps <= 0:
                            raise ValueError("Enter an upload limit greater than zero, or choose Unlimited.")
                except ValueError as exc:
                    status.configure(text=str(exc), fg="#f87171")
                    return

                ok, message = self.engine.adapter_mgr.configure_adapter_limits(
                    adapter_name,
                    data_gb,
                    cycle_value_num * cycle_multiplier,
                    download_mbps,
                    upload_mbps,
                )
                status.configure(
                    text=message,
                    fg="#34d399" if ok else "#f87171",
                )
                if ok:
                    self._update_ui()

            self._make_studio_btn(
                card,
                "Save Limits",
                "SAVE ADAPTER DATA AND SPEED LIMITS",
                "Apply the data cap, reset window, and OmniBond upload/download speed limits.",
                variant="amber",
                cmd=save_limits,
                px=9,
                py=4,
            ).grid(row=3, column=1, sticky="e", pady=(4, 0))

        actions = tk.Frame(panel, bg=self.BG_PANEL)
        actions.pack(fill=tk.X, pady=(8, 0))
        self._make_studio_btn(
            actions,
            "Close",
            "CLOSE NETWORK TUNING",
            "Close without applying changes.",
            variant="dark",
            cmd=window.destroy,
            px=12,
            py=6,
        ).pack(side=tk.RIGHT, padx=(6, 0))

        def apply_options():
            selected = {key: variable.get() for key, variable in options.items()}
            ok, msg = self.engine.sys_opt.optimize_multi_nic(
                keep_multi_nic=selected["keep_multi_nic"],
                optimize_ipv4=selected["ipv4"],
                optimize_ipv6=selected["ipv6"],
            )
            if ok:
                self._network_tuning_options.update(selected)
            optimization_status.configure(
                text=msg,
                fg="#34d399" if ok else "#f87171",
            )

        self._make_studio_btn(
            actions,
            "Apply Settings",
            "APPLY NETWORK TUNING",
            "Apply the selected Windows multi-network, IPv4, and IPv6 route settings.",
            variant="amber",
            cmd=apply_options,
            px=12,
            py=6,
        ).pack(side=tk.RIGHT)

    def _start_turbo_download(self):
        url = self.ent_url.get().strip()
        if not url:
            return
        fname = os.path.basename(urllib.parse.urlsplit(url).path) or "omnibond_download.bin"
        out = os.path.join(os.path.expanduser("~"), "Downloads", fname)
        threading.Thread(target=self.engine.turbo.download_url, args=(url, out), daemon=True).start()

    @staticmethod
    def _fmt_bytes(num: float) -> str:
        if num <= 0:
            return "0 B"
        if num < 1024:
            return f"{int(num)} B"
        if num < 1048576:
            return f"{num / 1024:.1f} KB"
        if num < 1073741824:
            return f"{num / 1048576:.2f} MB"
        return f"{num / 1073741824:.2f} GB"

    @classmethod
    def _fmt_speed(cls, bps: float) -> str:
        if bps < 1:
            return "0.0 KB/s"
        if bps < 1048576:
            return f"{bps / 1024:.1f} KB/s"
        return f"{bps / 1048576:.2f} MB/s"

    @staticmethod
    def _adapter_speed(adapter: NetworkAdapter, graph_mode: str) -> float:
        return adapter.system_current_bps if graph_mode == "master" else adapter.current_bps

    @staticmethod
    def _adapter_speed_history(adapter: NetworkAdapter, graph_mode: str) -> List[float]:
        return adapter.system_bps_history if graph_mode == "master" else adapter.bps_history

    @staticmethod
    def _adapter_traffic_bytes(adapter: NetworkAdapter, graph_mode: str) -> int:
        if graph_mode == "master":
            return adapter.system_bytes_recv + adapter.system_bytes_sent
        return adapter.bytes_recv + adapter.bytes_sent

    def _toggle_graph_mode(self):
        self.graph_mode = "bonded" if self.graph_mode == "master" else "master"
        self._peak_bps = 0.0
        self._style_graph_mode_button()
        self._update_ui()

    def _style_graph_mode_button(self):
        master = self.graph_mode == "master"
        self.btn_graph_mode.configure(
            text="∿ Master Speed" if master else "⇄ Bonded Speed",
            fg=self.TEXT_MAIN if master else self.AMBER,
            highlightbackground="#272734" if master else self.AMBER,
        )

    # -----------------------------------------------------------------
    # 01: ADAPTER BENTO CARDS
    # -----------------------------------------------------------------

    def _draw_adapter_bento_cards(self, adapters: List[NetworkAdapter]):
        c = self.canvas_adapters
        c.delete("all")
        self._adapter_card_regions.clear()

        w = max(280, c.winfo_width())
        h = max(168, c.winfo_height())
        visible_cols = max(1, min(3, len(adapters)))
        cell_w = max(260, w / visible_cols)
        content_w = max(w, int(cell_w * len(adapters)))

        c.create_line(0, 0, content_w, 0, fill=self.BG_HAIRLINE)
        c.create_line(0, h - 1, content_w, h - 1, fill=self.BG_HAIRLINE)

        for idx, a in enumerate(adapters):
            x0 = int(idx * cell_w)
            x1 = int((idx + 1) * cell_w)
            y0, y1 = 1, h - 1
            self._adapter_card_regions.append((x0, y0, x1, y1, a.ip))

            if idx > 0:
                c.create_line(x0, 0, x0, h, fill=self.BG_HAIRLINE)

            pad_x = x0 + 15
            c.create_rectangle(pad_x, 12, pad_x + 24, 29, fill=a.color, outline="")
            c.create_text(pad_x + 12, 20, text=f"{idx + 1:02d}", fill="#09090b", font=("Consolas", 9, "bold"))
            c.create_text(
                x1 - 12, 20,
                text=f"IPV4 · {a.ip} ↗",
                fill=self.TEXT_MUTED,
                anchor="e",
                font=("Consolas", 8),
            )

            c.create_rectangle(pad_x, 38, pad_x + 34, 72, fill=a.badge_bg, outline="")
            c.create_text(
                pad_x + 17, 55,
                text=a.kind[:2].upper(),
                fill="#ffffff",
                font=("Segoe UI", 9, "bold"),
            )

            short_name = a.name if len(a.name) <= 16 else a.name[:14] + ".."
            c.create_text(
                pad_x + 44, 47,
                text=short_name,
                fill=self.TEXT_MAIN,
                anchor="w",
                font=("Segoe UI", 10, "bold"),
            )
            c.create_text(
                pad_x + 44, 63,
                text=f"{a.kind} · {a.latency_ms:.0f}ms RTT",
                fill=self.TEXT_MUTED,
                anchor="w",
                font=("Segoe UI", 8),
            )

            limits = self.engine.adapter_mgr.get_adapter_limit_snapshot(a)
            if limits["quota_exceeded"]:
                pill_text, pill_fg, pill_bg, pill_bd = (
                    "DATA CAP REACHED", "#f87171", "#2b1111", "#991b1b"
                )
            elif a.enabled:
                pill_text, pill_fg, pill_bg, pill_bd = (
                    f"ACTIVE · {a.kind.upper()}", "#34d399", "#06281e", "#059669"
                )
            else:
                pill_text, pill_fg, pill_bg, pill_bd = (
                    "STANDBY · DISABLED", self.TEXT_MUTED, "#141418", self.BG_HAIRLINE
                )
            pill_w = len(pill_text) * 6 + 14
            c.create_rectangle(pad_x, 82, pad_x + pill_w, 100, fill=pill_bg, outline=pill_bd)
            c.create_text(
                pad_x + 7, 91,
                text=pill_text,
                fill=pill_fg,
                anchor="w",
                font=("Consolas", 8, "bold"),
            )

            c.create_text(
                pad_x, 113,
                text=(
                    f"{a.active_conns} Conns · "
                    f"{self._fmt_bytes(self._adapter_traffic_bytes(a, self.graph_mode))} · "
                    f"{self._fmt_speed(self._adapter_speed(a, self.graph_mode))}"
                ),
                fill=self.TEXT_DIM,
                anchor="w",
                font=("Segoe UI", 8),
            )

            btn_y0, btn_y1 = h - 35, h - 9
            c.create_rectangle(
                pad_x, btn_y0, x1 - 14, btn_y1,
                fill="#111118",
                outline="#272732",
                stipple="gray50" if limits["quota_exceeded"] else "",
            )
            c.create_text(
                (pad_x + x1 - 14) / 2,
                (btn_y0 + btn_y1) / 2,
                text=(
                    "LIMIT REACHED · WAIT FOR RESET"
                    if limits["quota_exceeded"]
                    else ("BONDED · CLICK TO TOGGLE" if a.enabled else "DISABLED · CLICK TO ENABLE")
                ),
                fill=self.TEXT_DIM if limits["quota_exceeded"] else (
                    self.TEXT_MAIN if a.enabled else self.TEXT_MUTED
                ),
                font=("Segoe UI", 8, "bold"),
            )
        c.configure(scrollregion=(0, 0, content_w, h))

    # -----------------------------------------------------------------
    # 02: APPLICATION BENTO CARDS WITH LIVE SPEED SPARKLINE & FOCUS BUTTON
    # -----------------------------------------------------------------

    def _draw_app_bento_cards(self, entries: List[Dict], adapters: List[NetworkAdapter]):
        c = self.canvas_apps
        c.delete("all")
        self._app_card_regions.clear()

        w = max(480, c.winfo_width())
        cols = 1 if self.app_view_mode == "list" else (3 if w >= 780 else 2)
        items = entries
        rows = max(1, math.ceil(max(1, len(items)) / cols))
        cell_w = w / cols
        cell_h = 185
        content_h = max(c.winfo_height(), rows * cell_h)

        c.create_line(0, 0, w, 0, fill=self.BG_HAIRLINE)
        ip_to_name = {a.ip: a.name for a in adapters}

        for idx, r in enumerate(items):
            row = idx // cols
            col = idx % cols
            x0 = int(col * cell_w)
            x1 = int((col + 1) * cell_w)
            y0 = int(row * cell_h)
            y1 = int((row + 1) * cell_h)

            if col > 0:
                c.create_line(x0, y0, x0, y1, fill=self.BG_HAIRLINE)
            if row > 0:
                c.create_line(x0, y0, x1, y0, fill=self.BG_HAIRLINE)
            c.create_line(x0, y1, x1, y1, fill=self.BG_HAIRLINE)

            _, accent_col, fill_dark = ADAPTER_PALETTE[idx % len(ADAPTER_PALETTE)]
            pad_x = x0 + 14

            # 1. Number badge and consistent per-app actions.
            c.create_rectangle(pad_x, y0 + 11, pad_x + 24, y0 + 28, fill=accent_col, outline="")
            c.create_text(
                pad_x + 12, y0 + 19,
                text=f"{idx + 1:02d}",
                fill="#09090b",
                font=("Consolas", 9, "bold"),
            )

            fav_x0, fav_y0, fav_x1, fav_y1 = x1 - 172, y0 + 10, x1 - 150, y0 + 28
            favorite = bool(r.get("is_favorite"))
            c.create_rectangle(
                fav_x0, fav_y0, fav_x1, fav_y1,
                fill="#2b2110" if favorite else "#111118",
                outline=self.AMBER if favorite else "#34343e",
            )
            c.create_text(
                (fav_x0 + fav_x1) / 2, (fav_y0 + fav_y1) / 2,
                text="★" if favorite else "☆",
                fill=self.AMBER if favorite else self.TEXT_MUTED,
                font=("Segoe UI Symbol", 9, "bold"),
            )
            self._app_card_regions.append((fav_x0, fav_y0, fav_x1, fav_y1, "favorite", r["app_name"], r["last_pid"]))

            foc_x0, foc_y0, foc_x1, foc_y1 = x1 - 146, y0 + 10, x1 - 82, y0 + 28
            c.create_rectangle(foc_x0, foc_y0, foc_x1, foc_y1, fill="#171720", outline="#34343e")
            c.create_text(
                (foc_x0 + foc_x1) / 2, (foc_y0 + foc_y1) / 2,
                text="▣ FOCUS",
                fill=self.TEXT_MAIN,
                font=("Consolas", 8, "bold"),
            )
            self._app_card_regions.append((foc_x0, foc_y0, foc_x1, foc_y1, "focus", r["app_name"], r["last_pid"]))

            loc_x0, loc_y0, loc_x1, loc_y1 = x1 - 76, y0 + 10, x1 - 12, y0 + 28
            c.create_rectangle(loc_x0, loc_y0, loc_x1, loc_y1, fill="#171720", outline="#34343e")
            c.create_text(
                (loc_x0 + loc_x1) / 2, (loc_y0 + loc_y1) / 2,
                text="↗ LOCATE",
                fill=self.TEXT_MAIN,
                font=("Consolas", 8, "bold"),
            )
            self._app_card_regions.append((loc_x0, loc_y0, loc_x1, loc_y1, "location", r["app_name"], r["last_pid"]))

            # 2. App Identity Row (Icon + Two-Tone Title + Running Window/PID Subtitle)
            disp = r["display_name"]
            if "Turbo Accelerator" in disp:
                part1, part2 = "Turbo", "Engine"
                sub_desc = "Parallel range & stream splitter"
            elif "." in disp:
                dot = disp.rfind(".")
                part1 = disp[:dot].capitalize()
                part2 = disp[dot:]
                sub_desc = r["window_title"][:24] if r.get("window_title") else (
                    f"Running · PID {r['last_pid']}" if r.get("is_running") and r.get("last_pid") else "Pinned Process Rule"
                )
            else:
                part1, part2 = disp.capitalize(), ""
                sub_desc = "Process socket routing rule"

            c.create_rectangle(pad_x, y0 + 36, pad_x + 32, y0 + 68, fill="#14141d", outline=accent_col)
            c.create_text(
                pad_x + 16, y0 + 52,
                text=part1[:2].upper(),
                fill=accent_col,
                font=("Segoe UI", 9, "bold"),
            )

            title_x = pad_x + 40
            short_p1 = part1 if len(part1) <= 12 else part1[:11] + "…"
            t_id = c.create_text(
                title_x, y0 + 44,
                text=short_p1,
                fill=self.TEXT_MAIN,
                anchor="w",
                font=("Segoe UI", 10, "bold"),
            )
            bbox = c.bbox(t_id)
            next_x = bbox[2] if bbox else title_x + len(short_p1) * 7
            c.create_text(
                next_x, y0 + 44,
                text=part2,
                fill=accent_col,
                anchor="w",
                font=("Segoe UI", 10, "bold"),
            )
            c.create_text(
                title_x, y0 + 60,
                text=sub_desc,
                fill=self.TEXT_MUTED,
                anchor="w",
                font=("Segoe UI", 8),
            )

            # 3. Embedded Per-Application Speed Sparkline Graph
            spk_x0, spk_y0 = pad_x, y0 + 76
            spk_x1, spk_y1 = x1 - 12, y0 + 122
            c.create_rectangle(spk_x0, spk_y0, spk_x1, spk_y1, fill="#07070a", outline="#1b1b24")
            c.create_text(
                spk_x0 + 6, spk_y0 + 9,
                text="APP THROUGHPUT",
                fill=self.TEXT_DIM,
                anchor="w",
                font=("Consolas", 7, "bold"),
            )
            c.create_text(
                spk_x1 - 6, spk_y0 + 9,
                text=self._fmt_speed(r.get("bps", 0.0)),
                fill=accent_col,
                anchor="e",
                font=("Consolas", 8, "bold"),
            )

            hist = r.get("bps_history", [])
            if len(hist) >= 2:
                max_app_bps = max(8192.0, max(hist) * 1.15)
                gw = max(20, (spk_x1 - spk_x0) - 8)
                gh = max(12, (spk_y1 - spk_y0) - 20)
                gx0 = spk_x0 + 4
                gy_base = spk_y1 - 3
                s_pts: List[Tuple[float, float]] = []
                for h_i, h_val in enumerate(hist):
                    px = gx0 + (h_i / (len(hist) - 1)) * gw
                    py = gy_base - min(1.0, max(0.0, h_val / max_app_bps)) * gh
                    s_pts.append((px, py))
                spline = self._catmull_rom_spline(s_pts, subdivisions=2)
                if len(spline) >= 4:
                    poly = [gx0, gy_base] + spline + [gx0 + gw, gy_base]
                    c.create_polygon(*poly, fill=fill_dark, stipple="gray50", outline="")
                    c.create_line(*spline, fill=accent_col, width=1.6)
                    lx, ly = s_pts[-1]
                    c.create_oval(lx - 2.5, ly - 2.5, lx + 2.5, ly + 2.5, fill=accent_col, outline="")

            # 4. Status Pill + Telemetry Summary Row
            is_pinned = r["rule"] != "AUTO"
            if r["rule"] == BLOCK_INTERNET_RULE:
                pill_text = "BLOCKED · NO INTERNET"
                pill_bg, pill_bd, pill_fg = "#3f1212", "#dc2626", "#fca5a5"
            elif is_pinned:
                nic_label = ip_to_name.get(r["rule"], r["rule"])
                pill_text = f"PINNED · {nic_label[:10].upper()}"
                pill_bg, pill_bd, pill_fg = "#082f49", "#0284c7", "#38bdf8"
            else:
                pill_text = "AUTO · BONDED"
                pill_bg, pill_bd, pill_fg = "#06281e", "#059669", "#34d399"

            pill_w = len(pill_text) * 6 + 10
            c.create_rectangle(pad_x, y0 + 128, pad_x + pill_w, y0 + 144, fill=pill_bg, outline=pill_bd)
            c.create_text(
                pad_x + 5, y0 + 136,
                text=pill_text,
                fill=pill_fg,
                anchor="w",
                font=("Consolas", 7, "bold"),
            )

            c.create_text(
                x1 - 12, y0 + 136,
                text=f"{r['active_connections']} Conns · {self._fmt_bytes(r['bytes_transferred'])}",
                fill=self.TEXT_DIM,
                anchor="e",
                font=("Consolas", 8),
            )

            # 5. Bottom Policy Action Button
            btn_y0, btn_y1 = y1 - 31, y1 - 7
            c.create_rectangle(pad_x, btn_y0, x1 - 12, btn_y1, fill="#111118", outline="#272732")
            selected_policy = r["rule"]
            if selected_policy == "AUTO":
                selected_name = "AUTO / BONDED"
            elif selected_policy == BLOCK_INTERNET_RULE:
                selected_name = "BLOCK INTERNET"
            else:
                selected_name = ip_to_name.get(selected_policy, selected_policy)
            action_lbl = f"POLICY: {selected_name}  [CLICK TO SELECT]"
            c.create_text(
                (pad_x + x1 - 12) / 2,
                (btn_y0 + btn_y1) / 2,
                text=action_lbl,
                fill=self.TEXT_MAIN,
                font=("Segoe UI", 8, "bold"),
            )
            self._app_card_regions.append((pad_x, btn_y0, x1 - 12, btn_y1, "policy", r["app_name"], r["last_pid"]))
        c.configure(scrollregion=(0, 0, w, content_h))

    # -----------------------------------------------------------------
    # FIXED TWO-TIER NON-OVERLAPPING GOOGLE SPLINE CHART
    # -----------------------------------------------------------------

    @staticmethod
    def _catmull_rom_spline(pts: List[Tuple[float, float]], subdivisions: int = 4) -> List[float]:
        if len(pts) < 2:
            return []
        out: List[float] = []
        n = len(pts)
        for i in range(n - 1):
            p0 = pts[max(0, i - 1)]
            p1 = pts[i]
            p2 = pts[i + 1]
            p3 = pts[min(n - 1, i + 2)]
            for step in range(subdivisions):
                t = step / subdivisions
                t2 = t * t
                t3 = t2 * t
                x = 0.5 * (
                    (2 * p1[0])
                    + (-p0[0] + p2[0]) * t
                    + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                    + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
                )
                y = 0.5 * (
                    (2 * p1[1])
                    + (-p0[1] + p2[1]) * t
                    + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                    + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
                )
                out.extend([x, y])
        out.extend([pts[-1][0], pts[-1][1]])
        return out

    def _draw_google_chart(self, adapters: List[NetworkAdapter]):
        c = self.canvas_chart
        c.delete("all")
        w = max(360, c.winfo_width())
        h = max(200, c.winfo_height())

        pad_l, pad_r, pad_b = 68, 20, 26

        total_bps = sum(self._adapter_speed(a, self.graph_mode) for a in adapters)
        if total_bps > self._peak_bps:
            self._peak_bps = total_bps

        # ROW 1 (y=16): Title on Left | Combined Speed Badge + Peak on Right
        c.create_text(
            18, 16,
            text=(
                "MASTER SPEED · ALL COMPUTER NETWORK TRAFFIC"
                if self.graph_mode == "master"
                else "BONDED SPEED · OMNIBOND ROUTED TRAFFIC"
            ),
            fill=self.TEXT_MUTED,
            anchor="w",
            font=("Consolas", 9, "bold"),
        )

        speed_str = f"LIVE: {self._fmt_speed(total_bps)}   ·   PEAK: {self._fmt_speed(self._peak_bps)}"
        c.create_rectangle(w - len(speed_str) * 6.5 - 26, 6, w - 16, 26, fill="#14141d", outline="#272734")
        c.create_text(
            w - 22, 16,
            text=speed_str,
            fill=self.AMBER,
            anchor="e",
            font=("Consolas", 8, "bold"),
        )

        # Wrap every adapter metric into the available width before sizing the plot.
        leg_x, leg_y = 18, 38
        for idx, a in enumerate(adapters):
            lbl = (
                f"{idx + 1:02d}·{a.name[:11]} "
                f"({self._fmt_speed(self._adapter_speed(a, self.graph_mode))})"
            )
            item_width = 18 + len(lbl) * 6.0
            if leg_x + item_width > w - 12 and leg_x > 18:
                leg_x, leg_y = 18, leg_y + 14
            c.create_oval(leg_x, leg_y - 4, leg_x + 8, leg_y + 4, fill=a.color, outline="")
            tid = c.create_text(
                leg_x + 12, leg_y,
                text=lbl,
                fill=self.TEXT_MUTED,
                anchor="w",
                font=("Consolas", 8),
            )
            bbox = c.bbox(tid)
            leg_x = (bbox[2] + 16) if bbox else (leg_x + 145)
        pad_t = max(62, leg_y + 20)
        plot_w = max(1, w - pad_l - pad_r)
        plot_h = max(1, h - pad_t - pad_b)

        # Compute Dynamic Y-Axis Scale
        max_bps = 64 * 1024.0
        for a in adapters:
            history = self._adapter_speed_history(a, self.graph_mode)
            if history:
                max_bps = max(max_bps, max(history) * 1.18)

        # Y-Axis Labels & Gridlines
        rows = 4
        for r in range(rows + 1):
            y = pad_t + (plot_h / rows) * r
            val = max_bps * (1.0 - r / rows)
            line_col = "#272730" if r == rows else "#16161d"
            dash_pat = () if r == rows else (2, 4)
            c.create_line(pad_l, y, w - pad_r, y, fill=line_col, dash=dash_pat)
            lbl_txt = "0 B/s" if val < 1 else self._fmt_speed(val)
            c.create_text(
                pad_l - 8, y,
                text=lbl_txt,
                fill=self.TEXT_DIM,
                anchor="e",
                font=("Consolas", 8),
            )

        # X-Axis Timeline Ticks
        x_ticks = [("-60s", 0.0), ("-45s", 0.25), ("-30s", 0.50), ("-15s", 0.75), ("LIVE", 1.0)]
        for txt, frac in x_ticks:
            tx = pad_l + plot_w * frac
            c.create_text(
                tx, pad_t + plot_h + 11,
                text=txt,
                fill=self.AMBER if txt == "LIVE" else self.TEXT_DIM,
                anchor="center",
                font=("Consolas", 8, "bold" if txt == "LIVE" else "normal"),
            )

        baseline_y = pad_t + plot_h
        for a in adapters:
            hist = self._adapter_speed_history(a, self.graph_mode)
            if len(hist) < 2:
                continue
            ctrl_pts: List[Tuple[float, float]] = []
            for idx, val in enumerate(hist):
                x = pad_l + (idx / (len(hist) - 1)) * plot_w
                norm = min(1.0, max(0.0, val / max_bps))
                y = baseline_y - norm * plot_h
                ctrl_pts.append((x, y))

            spline_coords = self._catmull_rom_spline(ctrl_pts, subdivisions=3)
            if len(spline_coords) >= 4:
                poly_coords = [pad_l, baseline_y] + spline_coords + [pad_l + plot_w, baseline_y]
                c.create_polygon(*poly_coords, fill=a.fill_dark, stipple="gray50", outline="")
                c.create_line(
                    *spline_coords,
                    fill=a.color,
                    width=2.4,
                    capstyle=tk.ROUND,
                    joinstyle=tk.ROUND,
                )
                lx, ly = ctrl_pts[-1]
                c.create_oval(lx - 6, ly - 6, lx + 6, ly + 6, fill="", outline=a.color, width=1)
                c.create_oval(lx - 3, ly - 3, lx + 3, ly + 3, fill=a.color, outline="")

        # Hover Crosshair Tooltip
        if self._hover_chart_x is not None and pad_l <= self._hover_chart_x <= (pad_l + plot_w) and adapters:
            hx = self._hover_chart_x
            c.create_line(hx, pad_t, hx, baseline_y, fill="#52525b", dash=(2, 2))
            hist_len = len(self._adapter_speed_history(adapters[0], self.graph_mode))
            rel = (hx - pad_l) / max(1.0, plot_w)
            sample_idx = min(hist_len - 1, max(0, int(round(rel * (hist_len - 1)))))

            lines = []
            for idx, a in enumerate(adapters):
                history = self._adapter_speed_history(a, self.graph_mode)
                val = history[sample_idx] if sample_idx < len(history) else 0.0
                px = pad_l + (sample_idx / max(1, hist_len - 1)) * plot_w
                py = baseline_y - min(1.0, max(0.0, val / max_bps)) * plot_h
                c.create_oval(px - 4, py - 4, px + 4, py + 4, fill=a.color, outline="#09090b", width=1.5)
                lines.append((f"{idx + 1:02d} {a.name[:12]}: {self._fmt_speed(val)}", a.color))

            box_w = 180
            box_h = 16 + len(lines) * 16
            bx0 = hx + 12 if hx + 12 + box_w < w - pad_r else hx - box_w - 12
            by0 = pad_t + 6
            c.create_rectangle(bx0, by0, bx0 + box_w, by0 + box_h, fill="#121218", outline="#3f3f46")
            for l_idx, (txt, col) in enumerate(lines):
                c.create_text(
                    bx0 + 10, by0 + 13 + l_idx * 16,
                    text=txt,
                    fill=col,
                    anchor="w",
                    font=("Consolas", 8, "bold"),
                )

    # -----------------------------------------------------------------
    # 03: UNIFIED GLOWING PROGRESS TRACK & BLOCK MATRIX
    # -----------------------------------------------------------------

    def _draw_unified_turbo_bar(self):
        c = self.canvas_dl_unified
        c.delete("all")
        w = max(400, c.winfo_width())

        pct = min(100.0, max(0.0, self.engine.turbo.progress_pct))
        spd = self._fmt_speed(self.engine.turbo.speed_bps)
        state_lbl = "ACTIVE" if self.engine.turbo.is_running else "READY"
        self.lbl_dl_badge.configure(text=f"{state_lbl} · {spd} · {pct:.0f}%")

        # 1. Status & Percentage Header Line (y=8)
        c.create_text(
            2, 7,
            text=self.engine.turbo.status_text,
            fill=self.TEXT_MUTED,
            anchor="w",
            font=("Consolas", 8),
        )
        c.create_text(
            w - 2, 7,
            text=f"{pct:.1f}% COMPLETE",
            fill=self.AMBER if pct > 0 else self.TEXT_DIM,
            anchor="e",
            font=("Consolas", 8, "bold"),
        )

        # 2. Glowing Smooth Progress Bar Track (y=17..25)
        c.create_rectangle(0, 17, w, 25, fill="#12121a", outline="#1e1e2a")
        fill_w = int((pct / 100.0) * w)
        if fill_w > 0:
            c.create_rectangle(1, 18, fill_w, 24, fill=self.EMERALD if pct >= 100 else self.AMBER, outline="")

        # 3. Segmented Multi-NIC Block Allocation Matrix (y=30..44)
        blocks = self.engine.turbo.blocks[:90]
        if blocks:
            num_b = len(blocks)
            gap = 2
            bw = max(6.0, (w - (num_b - 1) * gap) / num_b)
            for idx, b in enumerate(blocks):
                bx0 = idx * (bw + gap)
                col = "#14141d" if b.status == "pending" else b.color
                c.create_rectangle(bx0, 30, bx0 + bw, 43, fill=col, outline="")
        else:
            # Subtle idle placeholder segments aligned with the URL bar
            slots = 48
            gap = 3
            bw = (w - (slots - 1) * gap) / slots
            for i in range(slots):
                bx0 = i * (bw + gap)
                c.create_rectangle(bx0, 31, bx0 + bw, 42, fill="#111118", outline="")

    def _update_ui(self):
        if self.engine.sys_opt.system_proxy_enabled:
            self.btn_proxy.configure(text="◈ Bonding: On")
        else:
            self.btn_proxy.configure(text="◈ Bonding: Off")

        adapters = self.engine.adapter_mgr.get_adapters()
        self._refresh_policy_dropdown(adapters)

        enabled_adapter_count = sum(
            1 for adapter in adapters
            if adapter.enabled and not self.engine.adapter_mgr.is_quota_exceeded(adapter)
        )
        adapter_telemetry_status = self.engine.adapter_mgr.system_counter_status
        adapter_telemetry_label = (
            "OMNIBOND"
            if self.graph_mode == "bonded"
            else (
                "SYSTEM NIC UNAVAILABLE"
                if "unavailable" in adapter_telemetry_status.casefold()
                or "did not match" in adapter_telemetry_status.casefold()
                else "SYSTEM NIC"
            )
        )
        self.lbl_adapter_count_meta.configure(
            text=(
                f"{enabled_adapter_count} / {len(adapters)} INTERFACES BONDED · "
                f"{adapter_telemetry_label}"
            )
        )

        entries = self.engine.routing_mgr.get_all_entries(only_running_or_added=True)
        app_telemetry_status = self.engine.process_tcp_counters.status
        app_telemetry_label = (
            "ADMIN REQUIRED"
            if app_telemetry_status.startswith("Administrator permission required")
            else (
                "PARTIAL TCP"
                if app_telemetry_status.startswith("Partial")
                else (
                    "LIVE TCP"
                    if "active" in app_telemetry_status.casefold()
                    else (
                        "WAITING TCP"
                        if "waiting" in app_telemetry_status.casefold()
                        else "TCP STATUS"
                    )
                )
            )
        )
        self.lbl_running_badge.configure(
            text=f"{len(entries)} ACTIVE / PINNED APPS · {app_telemetry_label}"
        )

        self._draw_adapter_bento_cards(adapters)
        self._draw_app_bento_cards(self._sort_app_entries(self._filter_app_entries(entries)), adapters)
        self._draw_google_chart(adapters)
        self._draw_unified_turbo_bar()

    def _schedule_refresh(self):
        try:
            self._apply_process_scan_result()
            self._update_ui()
        except Exception:
            pass
        self.root.after(1200, self._schedule_refresh)

    def _on_close(self):
        errors = self.engine.stop_services()
        if errors:
            messagebox.showwarning(
                "Network Settings Restoration",
                "OmniBond stopped, but some Windows settings could not be restored:\n\n"
                + "\n".join(errors),
            )
        self.root.destroy()

    def run(self):
        self.root.mainloop()


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
            "chrome.exe", "", True
        ) == "ACTIVE NET"
        assert ProcessMapper.classify_process_category(
            "svchost.exe", "", False
        ) == "SERVICES / BG"
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
        assert "bps_history" in entries["steam.exe"]
        direct_telemetry_test = AppRoutingManager(persist_path="")
        direct_telemetry_test.record_process_bytes("tcp_test.exe", 4242, 8192)
        direct_telemetry_test.tick_app_throughput()
        direct_entry = {
            r["app_name"]: r for r in direct_telemetry_test.get_all_entries()
        }["tcp_test.exe"]
        assert direct_entry["bytes_transferred"] == 8192
        assert direct_entry["bps"] > 0
        print("[4/6] Proxy and direct per-app TCP speed history verified.")

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
        ("web", "Browser Dashboard", "Open the websocket dashboard in an app-style browser window."),
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

    def refresh_adapters_in_background():
        try:
            engine.adapter_mgr.refresh_adapters()
        except Exception as exc:
            print(f"Could not discover network adapters during startup: {exc}", file=sys.stderr)

    threading.Thread(
        target=refresh_adapters_in_background,
        name="omnibond-adapter-scan",
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
        app_profile_dir = os.path.join(tempfile.gettempdir(), "omnibond_web_profile")
        os.makedirs(app_profile_dir, exist_ok=True)
        launch_t0 = time.monotonic()
        browser_process = launch_frameless_web_app(url, browser_profile=app_profile_dir)
        try:
            if browser_process:
                browser_process.wait()
                # If Edge/Chrome handed off to an already-running browser process and exited
                # immediately (< 4s), keep the OmniBond service running while the tab is open.
                if (time.monotonic() - launch_t0) < 4.0:
                    print("Browser handed off window to existing session; keeping OmniBond running (Ctrl+C to stop).")
                    while True:
                        time.sleep(1.0)
            else:
                print(f"OmniBond dashboard is available at {url}")
                print("No desktop browser could be auto-launched, so the web service will stay running until you stop it.")
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