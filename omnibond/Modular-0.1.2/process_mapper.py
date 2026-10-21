#!/usr/bin/env python3
"""
OmniBond - Socket-to-Process Mapping, Task-Manager-Grade Process Discovery & Window/Path Management.
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
    IS_WINDOWS,
    RULES_FILE,
    TURBO_APP_KEY,
    TURBO_APP_LABEL,
)

# =====================================================================
# 1. SOCKET-TO-PROCESS MAPPING & AUTOMATIC TASK-MANAGER PROCESS DISCOVERY
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


class SHFILEINFOW(ctypes.Structure):
    _fields_ = [
        ("hIcon", wintypes.HANDLE),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", wintypes.DWORD),
        ("szDisplayName", wintypes.WCHAR * 260),
        ("szTypeName", wintypes.WCHAR * 80),
    ]


# Configure 64-bit safe ctypes function signatures on Windows once at import time
if IS_WINDOWS:
    try:
        _k32 = ctypes.windll.kernel32
        _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        _k32.OpenProcess.restype = wintypes.HANDLE
        _k32.CloseHandle.argtypes = [wintypes.HANDLE]
        _k32.CloseHandle.restype = wintypes.BOOL
        _k32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        _k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        _k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        _k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        _k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        _k32.Process32FirstW.restype = wintypes.BOOL
        _k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        _k32.Process32NextW.restype = wintypes.BOOL
        _k32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        _k32.ProcessIdToSessionId.restype = wintypes.BOOL

        _u32 = ctypes.windll.user32
        _u32.IsWindowVisible.argtypes = [wintypes.HWND]
        _u32.IsWindowVisible.restype = wintypes.BOOL
        _u32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        _u32.GetWindow.restype = wintypes.HWND
        _u32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        _u32.GetWindowTextLengthW.restype = ctypes.c_int
        _u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        _u32.GetWindowTextW.restype = ctypes.c_int
        _u32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        _u32.GetClassNameW.restype = ctypes.c_int
        _u32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        _u32.GetWindowLongW.restype = wintypes.LONG
        _u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        _u32.GetWindowThreadProcessId.restype = wintypes.DWORD
        _u32.GetShellWindow.argtypes = []
        _u32.GetShellWindow.restype = wintypes.HWND

        _ver = ctypes.windll.version
        _ver.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        _ver.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        _ver.GetFileVersionInfoW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
        ]
        _ver.GetFileVersionInfoW.restype = wintypes.BOOL
        _ver.VerQueryValueW.argtypes = [
            wintypes.LPCVOID,
            wintypes.LPCWSTR,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.UINT),
        ]
        _ver.VerQueryValueW.restype = wintypes.BOOL

        _dwm = ctypes.windll.dwmapi
        _dwm.DwmGetWindowAttribute.argtypes = [
            wintypes.HWND,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        _dwm.DwmGetWindowAttribute.restype = ctypes.c_long
    except Exception:
        pass


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
    """
    Task-Manager-grade process & window mapper.
    Automatically detects all running applications, standalone web-app/PWA windows,
    active network daemons, and background Windows services directly from OS APIs
    without relying on any hardcoded application lists.
    """

    def __init__(self, location_path: Optional[str] = None):
        self._pid_cache: Dict[int, Tuple[str, str, float]] = {}
        self._port_cache: Dict[int, Tuple[int, str, float]] = {}
        self._exe_path_map: Dict[str, str] = {}
        self._exe_pid_map: Dict[str, int] = {}
        self._file_desc_cache: Dict[str, str] = {}
        self._service_desc_cache: Dict[str, str] = {}
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

    @staticmethod
    def _expand_indirect_string(raw_text: str) -> str:
        """Expands Windows indirect resource strings like '@%SystemRoot%\\system32\\shell32.dll,-123'."""
        text = (raw_text or "").strip()
        if not IS_WINDOWS or not text.startswith("@"):
            return text
        try:
            shlwapi = ctypes.windll.shlwapi
            shlwapi.SHLoadIndirectString.argtypes = [
                wintypes.LPCWSTR,
                wintypes.LPWSTR,
                wintypes.UINT,
                ctypes.c_void_p,
            ]
            shlwapi.SHLoadIndirectString.restype = ctypes.c_long
            out_buf = ctypes.create_unicode_buffer(512)
            if shlwapi.SHLoadIndirectString(text, out_buf, 512, None) == 0 and out_buf.value.strip():
                return out_buf.value.strip()
        except Exception:
            pass
        return ""

    def _get_pe_file_description(self, full_path: str) -> str:
        """
        Reads the official application name (`FileDescription` or `ProductName`) embedded
        in a Windows executable's PE Version Info resource table (identical to Windows Task Manager).
        """
        if not IS_WINDOWS or not full_path or not os.path.isfile(full_path):
            return ""
        norm_path = full_path.casefold()
        with self._lock:
            if norm_path in self._file_desc_cache:
                return self._file_desc_cache[norm_path]

        desc = ""
        try:
            version_dll = ctypes.windll.version
            dummy = wintypes.DWORD(0)
            size = version_dll.GetFileVersionInfoSizeW(full_path, ctypes.byref(dummy))
            if size > 0:
                buf = ctypes.create_string_buffer(size)
                if version_dll.GetFileVersionInfoW(full_path, 0, size, buf):
                    # Collect all language/codepage translation pairs from the PE header,
                    # plus standard Windows English/Unicode fallback pairs.
                    lang_cp_pairs: List[str] = []
                    lp_translate = ctypes.c_void_p(0)
                    cb_translate = wintypes.UINT(0)
                    if (
                        version_dll.VerQueryValueW(
                            buf,
                            r"\VarFileInfo\Translation",
                            ctypes.byref(lp_translate),
                            ctypes.byref(cb_translate),
                        )
                        and lp_translate.value
                        and cb_translate.value >= 4
                    ):
                        count = cb_translate.value // 4
                        raw_bytes = ctypes.string_at(lp_translate.value, count * 4)
                        for idx in range(count):
                            lang, cp = struct.unpack_from("<HH", raw_bytes, idx * 4)
                            pair = f"{lang:04x}{cp:04x}"
                            if pair not in lang_cp_pairs:
                                lang_cp_pairs.append(pair)

                    for fallback_pair in ("040904b0", "040904e4", "04090000", "000004b0"):
                        if fallback_pair not in lang_cp_pairs:
                            lang_cp_pairs.append(fallback_pair)

                    for pair in lang_cp_pairs:
                        for field_name in ("FileDescription", "ProductName"):
                            sub_block = f"\\StringFileInfo\\{pair}\\{field_name}"
                            lp_str = ctypes.c_void_p(0)
                            ch_len = wintypes.UINT(0)
                            if (
                                version_dll.VerQueryValueW(
                                    buf,
                                    sub_block,
                                    ctypes.byref(lp_str),
                                    ctypes.byref(ch_len),
                                )
                                and lp_str.value
                                and ch_len.value > 0
                            ):
                                candidate = ctypes.wstring_at(lp_str.value).strip()
                                if candidate.startswith("@"):
                                    candidate = self._expand_indirect_string(candidate)
                                if (
                                    candidate
                                    and len(candidate) >= 2
                                    and not candidate.lower().endswith(".exe")
                                ):
                                    desc = candidate
                                    break
                        if desc:
                            break
        except Exception:
            pass

        # Fallback to Windows Shell SHGetFileInfoW display name if PE VersionInfo was stripped
        if not desc:
            try:
                shell32 = ctypes.windll.shell32
                SHGFI_DISPLAYNAME = 0x000000200
                shfi = SHFILEINFOW()
                shell32.SHGetFileInfoW.argtypes = [
                    wintypes.LPCWSTR,
                    wintypes.DWORD,
                    ctypes.POINTER(SHFILEINFOW),
                    wintypes.UINT,
                    wintypes.UINT,
                ]
                shell32.SHGetFileInfoW.restype = ctypes.c_size_t
                if shell32.SHGetFileInfoW(
                    full_path, 0, ctypes.byref(shfi), ctypes.sizeof(shfi), SHGFI_DISPLAYNAME
                ):
                    candidate = (shfi.szDisplayName or "").strip()
                    if candidate and not candidate.lower().endswith(".exe"):
                        desc = candidate
            except Exception:
                pass

        with self._lock:
            self._file_desc_cache[norm_path] = desc
        return desc

    def _get_windows_service_display_name(self, exe_name: str) -> str:
        """Looks up a Windows Service's DisplayName from the Service Control Manager registry."""
        if not IS_WINDOWS or not exe_name:
            return ""
        stem = exe_name[:-4].lower() if exe_name.lower().endswith(".exe") else exe_name.lower()
        with self._lock:
            if stem in self._service_desc_cache:
                return self._service_desc_cache[stem]

        display = ""
        try:
            import winreg
            svc_path = rf"SYSTEM\CurrentControlSet\Services\{stem}"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, svc_path) as key:
                raw_disp, _ = winreg.QueryValueEx(key, "DisplayName")
                candidate = str(raw_disp).strip()
                if candidate.startswith("@"):
                    candidate = self._expand_indirect_string(candidate)
                if candidate and not candidate.lower().endswith(".exe"):
                    display = candidate
        except Exception:
            pass

        with self._lock:
            self._service_desc_cache[stem] = display
        return display

    @staticmethod
    def _clean_window_subject(window_title: str, app_label: str = "") -> str:
        """
        Extracts the active window/tab subject from a window title
        (e.g. 'Gemini - Google Chrome' -> 'Gemini', 'Gemini and 2 more pages - Microsoft Edge' -> 'Gemini').
        """
        cleaned = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", (window_title or "")).strip()
        if not cleaned:
            return ""
        parts = [p.strip() for p in re.split(r"\s+[-—–|]\s+", cleaned) if p.strip()]
        if len(parts) >= 2:
            # Strip trailing browser/profile segments like 'Personal', 'Work', 'and 3 more pages'
            subject = re.sub(r"\s+and\s+\d+\s+more\s+pages?$", "", parts[0], flags=re.IGNORECASE).strip()
            if subject and (not app_label or subject.casefold() != app_label.casefold()):
                return subject
        return cleaned

    def resolve_friendly_app_name(
        self, exe_name: str, window_title: str = "", full_path: str = ""
    ) -> str:
        """
        Dynamically resolves the human-readable application or service name directly from:
        1. The executable's PE Version Info (`FileDescription` / `ProductName`) on disk,
        2. Windows Shell / Service Control Manager metadata, and
        3. The live OS window title when a window is open,
        with zero hardcoded application dictionaries.
        """
        norm = os.path.basename((exe_name or "").strip().lower())
        if not norm:
            return "System Process"
        if norm == TURBO_APP_KEY or "turbo" in norm:
            return TURBO_APP_LABEL

        path_to_check = full_path or self._exe_path_map.get(norm, "")
        if not path_to_check and IS_WINDOWS:
            # Check standard System32 / Windows paths for OS binaries if PID path wasn't cached yet
            sys_root = os.environ.get("SystemRoot", r"C:\Windows")
            for folder in (sys_root, os.path.join(sys_root, "System32")):
                cand = os.path.join(folder, norm)
                if os.path.isfile(cand):
                    path_to_check = cand
                    break

        pe_desc = self._get_pe_file_description(path_to_check)
        svc_desc = "" if pe_desc else self._get_windows_service_display_name(norm)
        base_name = pe_desc or svc_desc

        w_title = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", (window_title or "")).strip()
        if w_title and w_title != "Windows Shell":
            subject = self._clean_window_subject(w_title, base_name)
            if base_name:
                # If the window has a distinct subject (such as a web app tab/window or folder),
                # show the base application name or combine when the window is a standalone web app.
                if subject and subject.casefold() != base_name.casefold() and len(subject) <= 28:
                    # If the window title does NOT end with the base app name, it's a standalone PWA/App window
                    if base_name.casefold() not in w_title.casefold():
                        return f"{subject} ({base_name})"
                return base_name
            if subject:
                return subject

        if base_name:
            return base_name

        stem = norm[:-4] if norm.endswith(".exe") else norm
        cleaned = re.sub(r"[_-]+", " ", stem)
        cleaned = re.sub(r"([a-z])([A-Z])", r"\1 \2", cleaned).strip()
        return " ".join(w.capitalize() for w in cleaned.split()) if cleaned else norm

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
        """Returns (exe_name_lower, full_path) for a PID using 64-bit safe Win32 handles."""
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

    @staticmethod
    def _is_window_cloaked(hwnd: int) -> bool:
        """Checks DwmGetWindowAttribute(DWMWA_CLOAKED=14) just like Windows Task Manager."""
        if not IS_WINDOWS:
            return False
        try:
            cloaked = wintypes.DWORD(0)
            DWMWA_CLOAKED = 14
            res = ctypes.windll.dwmapi.DwmGetWindowAttribute(
                hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
            )
            return res == 0 and cloaked.value != 0
        except Exception:
            return False

    @staticmethod
    def _get_shell_process_pid() -> int:
        """Returns the PID of the active Windows desktop shell (e.g. explorer.exe) via GetShellWindow()."""
        if not IS_WINDOWS:
            return 0
        try:
            user32 = ctypes.windll.user32
            shell_hwnd = user32.GetShellWindow()
            if shell_hwnd:
                pid = wintypes.DWORD(0)
                user32.GetWindowThreadProcessId(shell_hwnd, ctypes.byref(pid))
                return int(pid.value)
        except Exception:
            pass
        return 0

    @staticmethod
    def _get_process_session_id(pid: int) -> int:
        """Returns the Windows Session ID for a PID (Session 0 = Services, >0 = User Desktop)."""
        if not IS_WINDOWS or pid <= 0:
            return 1
        try:
            sess = wintypes.DWORD(0)
            if ctypes.windll.kernel32.ProcessIdToSessionId(pid, ctypes.byref(sess)):
                return int(sess.value)
        except Exception:
            pass
        return 1

    def get_visible_window_pids(self) -> Dict[int, str]:
        """
        Task-Manager-style visible window enumerator:
        - Filters out DWM-cloaked background frames (DWMWA_CLOAKED)
        - Resolves UWP apps hosted inside ApplicationFrameHost.exe via EnumChildWindows
        - Detects File Explorer folder windows and the active Windows Shell process via GetShellWindow()
        - Collects all visible top-level window titles per PID so multi-window apps & PWAs are preserved
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
            WS_EX_NOACTIVATE = 0x08000000

            def _record_title(pid_val: int, title_str: str):
                if pid_val <= 0 or not title_str:
                    return
                cleaned = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", title_str).strip()
                if not cleaned:
                    return
                lst = pid_titles_list.setdefault(pid_val, [])
                if cleaned not in lst:
                    lst.append(cleaned)

            def enum_cb(hwnd, _lparam):
                if not user32.IsWindowVisible(hwnd):
                    return True
                if self._is_window_cloaked(hwnd):
                    return True

                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()
                if not title or title in (
                    "Program Manager",
                    "Default IME",
                    "MSCTFIME UI",
                    "Windows Input Experience",
                    "Microsoft Text Input Application",
                ):
                    return True

                class_buf = ctypes.create_unicode_buffer(128)
                user32.GetClassNameW(hwnd, class_buf, 128)
                wnd_class = class_buf.value.strip()
                if wnd_class in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
                    return True

                extended_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                has_owner = bool(user32.GetWindow(hwnd, GW_OWNER))
                is_explorer_folder = wnd_class in ("CabinetWClass", "ExploreWClass")
                is_app_window = bool(extended_style & WS_EX_APPWINDOW)
                is_tool_or_noactivate = bool(extended_style & (WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE))
                if not (is_explorer_folder or is_app_window or (not has_owner and not is_tool_or_noactivate)):
                    return True

                pid = wintypes.DWORD(0)
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                top_pid = int(pid.value)
                if top_pid <= 0:
                    return True

                # UWP / Store apps hosted by ApplicationFrameHost.exe: resolve real child CoreWindow PID
                if wnd_class == "ApplicationFrameWindow":
                    child_pids: List[int] = []

                    def child_cb(child_hwnd, _child_lparam):
                        cpid = wintypes.DWORD(0)
                        user32.GetWindowThreadProcessId(child_hwnd, ctypes.byref(cpid))
                        if cpid.value > 0 and int(cpid.value) != top_pid:
                            child_pids.append(int(cpid.value))
                        return True

                    user32.EnumChildWindows(hwnd, WNDENUMPROC(child_cb), 0)
                    if child_pids:
                        for cpid_val in child_pids:
                            _record_title(cpid_val, title)
                        return True

                _record_title(top_pid, title)
                return True

            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

            # Always include the active Windows Desktop Shell process (e.g. explorer.exe)
            # even when zero folder windows are currently open on the desktop.
            shell_pid = self._get_shell_process_pid()
            if shell_pid > 0 and shell_pid not in pid_titles_list:
                pid_titles_list[shell_pid] = ["Windows Shell"]
        except Exception:
            pass

        return {pid: " · ".join(titles[:3]) for pid, titles in pid_titles_list.items() if titles}

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
            h_snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            invalid_handle = ctypes.c_void_p(-1).value
            if h_snap and h_snap != invalid_handle:
                try:
                    entry = PROCESSENTRY32W()
                    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
                    if kernel32.Process32FirstW(h_snap, ctypes.byref(entry)):
                        while True:
                            name = (entry.szExeFile or "").strip().lower()
                            pid = int(entry.th32ProcessID)
                            if name and pid > 4:
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
                if name and pid > 4:
                    results.append((name, pid))
        except Exception:
            pass

        return results

    @staticmethod
    def classify_process_category(
        name: str,
        window_title: str,
        has_active_socket: bool,
        is_pinned: bool = False,
        session_id: int = 1,
    ) -> str:
        """
        Classifies a process using Task Manager rules:
        - Any process with a visible uncloaked window (or the active desktop shell) -> 'USER APPS'
        - Any Session-0 process without a visible window -> 'SERVICES / BG'
        - Any user-session process without a window that has active TCP sockets -> 'ACTIVE NET'
        - All remaining background processes -> 'SERVICES / BG'
        """
        if window_title:
            return "USER APPS"
        if session_id == 0 and not is_pinned:
            return "SERVICES / BG"
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
                existing = discovered.get(name)

                # Query full executable path on disk once per unique executable (or when a window/socket is found)
                should_resolve_path = (
                    existing is None
                    or (not existing.full_path and (bool(w_title) or has_net or is_pin))
                )
                _, full_path = self.get_exe_info(pid) if should_resolve_path else (name, "")
                if not full_path:
                    full_path = self._exe_path_map.get(name, "")

                sess_id = 1 if w_title else self._get_process_session_id(pid)
                category = self.classify_process_category(name, w_title, has_net, is_pin, session_id=sess_id)

                if existing is None:
                    friendly = self.resolve_friendly_app_name(name, w_title, full_path)
                    discovered[name] = ProcessInfo(
                        exe_name=name,
                        pid=pid,
                        full_path=full_path,
                        window_title="" if w_title == "Windows Shell" else w_title,
                        category=category,
                        has_active_socket=has_net,
                        is_pinned=is_pin,
                        display_name=friendly,
                    )
                else:
                    if has_net and not existing.has_active_socket:
                        existing.has_active_socket = True
                        if existing.category != "USER APPS":
                            existing.category = self.classify_process_category(
                                name, existing.window_title, True, is_pin, session_id=sess_id
                            )
                        if existing.category != "USER APPS":
                            existing.pid = pid
                    if w_title:
                        clean_w = "" if w_title == "Windows Shell" else w_title
                        if clean_w:
                            if not existing.window_title:
                                existing.window_title = clean_w
                                existing.pid = pid
                            elif clean_w not in existing.window_title and len(existing.window_title) < 64:
                                existing.window_title = f"{existing.window_title} · {clean_w}"
                        existing.category = "USER APPS"
                    if full_path and not existing.full_path:
                        existing.full_path = full_path
                    existing.display_name = self.resolve_friendly_app_name(
                        name, existing.window_title, existing.full_path
                    )

        if not discovered:
            # Non-Windows / Linux / macOS live process enumeration via /proc or ps
            try:
                proc = subprocess.run(
                    ["ps", "-eo", "pid,comm,args"],
                    capture_output=True,
                    text=True,
                    timeout=2.0,
                )
                for line in proc.stdout.splitlines()[1:]:
                    parts = line.strip().split(None, 2)
                    if len(parts) < 2:
                        continue
                    try:
                        pid = int(parts[0])
                    except ValueError:
                        continue
                    comm = os.path.basename(parts[1]).lower()
                    if not comm or comm in discovered:
                        continue
                    discovered[comm] = ProcessInfo(
                        exe_name=comm,
                        pid=pid,
                        full_path=parts[1],
                        window_title="",
                        category="USER APPS" if pid == os.getpid() else "SERVICES / BG",
                        has_active_socket=pid in net_pids,
                        is_pinned=comm in pinned_keys,
                        display_name=self.resolve_friendly_app_name(comm, "", parts[1]),
                    )
            except Exception:
                pass

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