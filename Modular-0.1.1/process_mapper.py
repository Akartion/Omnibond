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
import re
import socket
import struct
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional, Set, Tuple

from config import (
    FRIENDLY_APP_NAMES,
    IS_WINDOWS,
    KNOWN_USER_APPS,
    RULES_FILE,
    SYSTEM_NOISE_EXES,
    TURBO_APP_KEY,
    TURBO_APP_LABEL,
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


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
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
    display_name: str = ""


class ProcessMapper:
    """Resolves local TCP client ports to Windows PIDs, paths, windows, and categories."""

    def __init__(self, location_path: Optional[str] = None):
        self._pid_cache: Dict[int, Tuple[str, str, float]] = {}
        self._port_cache: Dict[int, Tuple[int, str, float]] = {}
        self._exe_path_map: Dict[str, str] = {}
        self._exe_pid_map: Dict[str, int] = {}
        self._file_desc_cache: Dict[str, str] = {}
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

    def _get_pe_file_description(self, full_path: str) -> str:
        """Reads the human-friendly FileDescription or ProductName from a Windows PE executable."""
        if not IS_WINDOWS or not full_path or not os.path.isfile(full_path):
            return ""
        norm_path = full_path.casefold()
        with self._lock:
            if norm_path in self._file_desc_cache:
                return self._file_desc_cache[norm_path]

        desc = ""
        try:
            version_dll = ctypes.windll.version
            handle = wintypes.DWORD(0)
            size = version_dll.GetFileVersionInfoSizeW(full_path, ctypes.byref(handle))
            if size > 0:
                buf = ctypes.create_string_buffer(size)
                if version_dll.GetFileVersionInfoW(full_path, 0, size, buf):
                    lp_translate = ctypes.c_void_p()
                    cb_translate = wintypes.UINT(0)
                    if version_dll.VerQueryValueW(
                        buf,
                        r"\VarFileInfo\Translation",
                        ctypes.byref(lp_translate),
                        ctypes.byref(cb_translate),
                    ) and cb_translate.value >= 4 and lp_translate.value:
                        lang, codepage = struct.unpack_from(
                            "<HH", ctypes.string_at(lp_translate.value, 4)
                        )
                        for field_name in ("FileDescription", "ProductName"):
                            sub_block = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\{field_name}"
                            lp_str = ctypes.c_wchar_p()
                            ch_len = wintypes.UINT(0)
                            if version_dll.VerQueryValueW(
                                buf,
                                sub_block,
                                ctypes.byref(lp_str),
                                ctypes.byref(ch_len),
                            ) and lp_str.value:
                                candidate = lp_str.value.strip()
                                if candidate and not candidate.lower().endswith(".exe"):
                                    desc = candidate
                                    break
        except Exception:
            pass

        with self._lock:
            self._file_desc_cache[norm_path] = desc
        return desc

    def resolve_friendly_app_name(
        self, exe_name: str, window_title: str = "", full_path: str = ""
    ) -> str:
        """
        Resolves the human-readable application or service name for an executable,
        using known friendly names, PE version metadata, and active window titles
        (including web apps like Gemini running inside a browser window).
        """
        norm = os.path.basename((exe_name or "").strip().lower())
        if not norm:
            return "System Process"
        if norm == TURBO_APP_KEY or "turbo" in norm:
            return TURBO_APP_LABEL

        w_title = (window_title or "").strip()
        # If a browser or app host window is running Gemini or a named web app, surface it clearly
        if w_title and "gemini" in w_title.lower():
            base_browser = FRIENDLY_APP_NAMES.get(norm, "")
            if base_browser and base_browser != "Google Gemini":
                return f"Gemini ({base_browser})"
            return "Google Gemini"

        if norm in FRIENDLY_APP_NAMES:
            return FRIENDLY_APP_NAMES[norm]

        pe_desc = self._get_pe_file_description(full_path or self._exe_path_map.get(norm, ""))
        if pe_desc:
            return pe_desc

        if w_title:
            # Extract clean application name from window title suffix/prefix
            parts = [p.strip() for p in re.split(r"\s+[-—–|]\s+", w_title) if p.strip()]
            if parts:
                candidate = parts[-1] if len(parts[-1]) >= 3 else parts[0]
                if 2 <= len(candidate) <= 32:
                    return candidate

        stem = norm[:-4] if norm.endswith(".exe") else norm
        # Convert camelCase / snake_case / hyphen-case stems into clean Title Case words
        cleaned = re.sub(r"[_-]+", " ", stem)
        cleaned = re.sub(r"([a-z])([A-Z])", r"\1 \2", cleaned).strip()
        if not cleaned:
            return norm
        return " ".join(
            w.upper() if len(w) <= 3 and w.isalpha() and w.lower() in ("ui", "cli", "id", "vm", "db", "ip", "tcp", "udp", "gui", "api", "svc")
            else w.capitalize()
            for w in cleaned.split()
        )

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
        """Returns all PIDs that currently own active IPv4 or IPv6 TCP connections."""
        pids: Set[int] = set()
        if not IS_WINDOWS:
            pids.add(os.getpid())
            return pids
        try:
            iphlpapi = ctypes.windll.iphlpapi
            AF_INET = 2
            AF_INET6 = 23
            TCP_TABLE_OWNER_PID_ALL = 5
            for family, row_type in ((AF_INET, MIB_TCPROW_OWNER_PID), (AF_INET6, MIB_TCP6ROW_OWNER_PID)):
                size = wintypes.DWORD(0)
                iphlpapi.GetExtendedTcpTable(
                    None, ctypes.byref(size), False, family, TCP_TABLE_OWNER_PID_ALL, 0
                )
                if size.value == 0:
                    continue
                buf = ctypes.create_string_buffer(size.value)
                if iphlpapi.GetExtendedTcpTable(
                    buf, ctypes.byref(size), False, family, TCP_TABLE_OWNER_PID_ALL, 0
                ) != 0:
                    continue
                num_entries = struct.unpack_from("<I", buf.raw, 0)[0]
                row_size = ctypes.sizeof(row_type)
                offset = 4
                for _ in range(num_entries):
                    if offset + row_size > size.value:
                        break
                    row = row_type.from_buffer_copy(buf.raw, offset)
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
        """
        Maps visible desktop & UWP windows to their owning process IDs.
        Also resolves child CoreWindow processes hosted inside ApplicationFrameHost.exe,
        File Explorer (CabinetWClass / ExploreWClass) windows, and prioritizes rich
        window titles (such as 'Gemini') when a process owns multiple windows.
        """
        pid_titles_list: Dict[int, List[str]] = {}
        if not IS_WINDOWS:
            return {}
        try:
            user32 = ctypes.windll.user32
            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            GW_OWNER = 4
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000

            def _record_title(pid_val: int, title_str: str):
                if pid_val <= 0 or not title_str:
                    return
                lst = pid_titles_list.setdefault(pid_val, [])
                if title_str not in lst:
                    # Prioritize Gemini or explicit app titles at the front
                    if "gemini" in title_str.lower():
                        lst.insert(0, title_str)
                    else:
                        lst.append(title_str)

            def enum_cb(hwnd, _lparam):
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()
                if not title or title in (
                    "Program Manager",
                    "Microsoft Text Input Application",
                    "Default IME",
                    "MSCTFIME UI",
                ):
                    return True

                class_buf = ctypes.create_unicode_buffer(64)
                user32.GetClassNameW(hwnd, class_buf, 64)
                wnd_class = class_buf.value.strip()

                extended_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                has_owner = bool(user32.GetWindow(hwnd, GW_OWNER))
                is_explorer_folder = wnd_class in ("CabinetWClass", "ExploreWClass")
                is_taskbar_window = (
                    is_explorer_folder
                    or bool(extended_style & WS_EX_APPWINDOW)
                    or (not has_owner and not (extended_style & WS_EX_TOOLWINDOW))
                )
                if not is_taskbar_window:
                    return True

                pid = wintypes.DWORD(0)
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                top_pid = int(pid.value)
                if top_pid <= 0:
                    return True

                _record_title(top_pid, title)

                # If hosted by ApplicationFrameHost.exe (UWP), also attribute the title to the child process
                if wnd_class == "ApplicationFrameWindow":
                    def child_cb(child_hwnd, _child_lparam):
                        cpid = wintypes.DWORD(0)
                        user32.GetWindowThreadProcessId(child_hwnd, ctypes.byref(cpid))
                        if cpid.value > 0 and int(cpid.value) != top_pid:
                            _record_title(int(cpid.value), title)
                        return True

                    user32.EnumChildWindows(hwnd, WNDENUMPROC(child_cb), 0)
                return True

            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        except Exception:
            pass

        return {pid: " · ".join(titles[:2]) for pid, titles in pid_titles_list.items() if titles}

    def _enumerate_windows_processes(self) -> List[Tuple[str, int]]:
        """
        Enumerates all running Windows processes (exe_name_lower, pid) using the fast
        Win32 CreateToolhelp32Snapshot API (< 5ms, never times out), falling back to tasklist.
        """
        results: List[Tuple[str, int]] = []
        if not IS_WINDOWS:
            return results

        try:
            kernel32 = ctypes.windll.kernel32
            TH32CS_SNAPPROCESS = 0x00000002
            INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
            h_snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if h_snap and h_snap != INVALID_HANDLE_VALUE:
                try:
                    entry = PROCESSENTRY32W()
                    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
                    if kernel32.Process32FirstW(h_snap, ctypes.byref(entry)):
                        while True:
                            name = (entry.szExeFile or "").strip().lower()
                            pid = int(entry.th32ProcessID)
                            if name.endswith(".exe") and pid > 0:
                                results.append((name, pid))
                            if not kernel32.Process32NextW(h_snap, ctypes.byref(entry)):
                                break
                finally:
                    kernel32.CloseHandle(h_snap)
        except Exception:
            pass

        if results:
            return results

        try:
            proc = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5.0,
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
                if name.endswith(".exe") and pid > 0:
                    results.append((name, pid))
        except Exception:
            pass

        return results

    @staticmethod
    def classify_process_category(
        name: str, window_title: str, has_active_socket: bool, is_pinned: bool = False
    ) -> str:
        norm = (name or "").strip().lower()
        if norm in SYSTEM_NOISE_EXES and not window_title and not is_pinned:
            return "SERVICES / BG"
        if window_title or norm in KNOWN_USER_APPS:
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
            for name, pid in self._enumerate_windows_processes():
                w_title = win_pids.get(pid, "")
                has_net = pid in net_pids
                is_pin = name in pinned_keys
                should_resolve_path = (
                    bool(w_title)
                    or has_net
                    or is_pin
                    or name in KNOWN_USER_APPS
                    or name not in discovered
                )
                _, full_path = self.get_exe_info(pid) if should_resolve_path else (name, "")
                if not full_path:
                    full_path = self._exe_path_map.get(name, "")

                if name == "explorer.exe" and not w_title:
                    w_title = "Windows Shell & File Explorer"

                category = self.classify_process_category(name, w_title, has_net, is_pin)
                existing = discovered.get(name)

                if existing is None:
                    friendly = self.resolve_friendly_app_name(name, w_title, full_path)
                    discovered[name] = ProcessInfo(
                        exe_name=name,
                        pid=pid,
                        full_path=full_path,
                        window_title=w_title,
                        category=category,
                        has_active_socket=has_net,
                        is_pinned=is_pin,
                        display_name=friendly,
                    )
                else:
                    # Merge multi-process info (e.g. Chrome/Edge/Explorer/svchost multiple PIDs)
                    if has_net and not existing.has_active_socket:
                        existing.has_active_socket = True
                        if existing.category != "USER APPS":
                            existing.category = self.classify_process_category(
                                name, existing.window_title or w_title, True, is_pin
                            )
                        existing.pid = pid
                    if w_title:
                        if not existing.window_title or (
                            "gemini" in w_title.lower() and "gemini" not in existing.window_title.lower()
                        ) or existing.window_title == "Windows Shell & File Explorer":
                            existing.window_title = w_title
                            existing.pid = pid
                        elif w_title not in existing.window_title and len(existing.window_title) < 48:
                            existing.window_title = f"{existing.window_title} · {w_title}"
                        existing.category = "USER APPS"
                    if full_path and not existing.full_path:
                        existing.full_path = full_path
                    existing.display_name = self.resolve_friendly_app_name(
                        name, existing.window_title, existing.full_path
                    )

        if not discovered:
            # Non-Windows / fallback environment
            for name in sorted(KNOWN_USER_APPS):
                w_title = "Google Gemini Web App" if name == "gemini.exe" else (
                    "Windows Shell & File Explorer" if name == "explorer.exe" else "Running Application"
                )
                discovered[name] = ProcessInfo(
                    exe_name=name,
                    pid=os.getpid(),
                    full_path=sys.executable,
                    window_title=w_title,
                    category="USER APPS",
                    has_active_socket=True,
                    is_pinned=name in pinned_keys,
                    display_name=self.resolve_friendly_app_name(name, w_title, sys.executable),
                )
            for svc_name in ("svchost.exe", "spoolsv.exe", "searchindexer.exe"):
                discovered[svc_name] = ProcessInfo(
                    exe_name=svc_name,
                    pid=os.getpid(),
                    full_path=sys.executable,
                    window_title="",
                    category="SERVICES / BG",
                    has_active_socket=False,
                    is_pinned=svc_name in pinned_keys,
                    display_name=self.resolve_friendly_app_name(svc_name, "", ""),
                )

        result = list(discovered.values())
        result.sort(
            key=lambda p: (
                0 if p.is_pinned else 1,
                0 if p.category == "USER APPS" else (1 if p.category == "ACTIVE NET" else 2),
                0 if p.has_active_socket else 1,
                p.display_name.casefold() if p.display_name else p.exe_name,
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

        if norm == "explorer.exe":
            try:
                subprocess.Popen(["explorer.exe"])
                return True, "Opened Windows File Explorer."
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