#!/usr/bin/env python3
"""
OmniBond - Socket-to-Process Mapping, Process Discovery & Window/Path Management.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional, Set, Tuple

from config import (
    IS_WINDOWS,
    KNOWN_USER_APPS,
    RULES_FILE,
    SYSTEM_NOISE_EXES,
    TURBO_APP_KEY,
)

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