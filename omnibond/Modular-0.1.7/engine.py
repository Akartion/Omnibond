#!/usr/bin/env python3
"""
OmniBond - Core Engine, Service Orchestrator & Cross-Browser Web App Launcher.
"""

from __future__ import annotations

from http.server import ThreadingHTTPServer
import math
import os
import shutil
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional, Set

from adapter_manager import AdapterManager
from config import (
    HTTP_PROXY_PORT,
    IS_WINDOWS,
    RULES_FILE,
    SOCKS_PROXY_PORT,
    WEB_UI_PORT,
)
from process_mapper import ProcessInfo, ProcessMapper
from proxies import (
    BondingHTTPProxyHandler,
    BondingSOCKS5ProxyHandler,
    ThreadedTCPServer,
)
from routing_manager import AppRoutingManager
from system_optimizer import WindowsSystemOptimizer
from tcp_counters import WindowsProcessTcpCounters
from turbo_accelerator import TurboAccelerator
from web_handler import WebUIHandler

# =====================================================================
# 8. OMNIBOND CORE ENGINE & SMART BROWSER TAB / INSTANCE LAUNCHER
# =====================================================================

_GECKO_BROWSER_TOKENS = (
    "firefox",
    "waterfox",
    "librewolf",
    "floorp",
    "zen",
    "palemoon",
    "seamonkey",
)

_CHROMIUM_BROWSER_TOKENS = (
    "msedge",
    "microsoft-edge",
    "chrome",
    "chromium",
    "brave",
    "vivaldi",
    "opera",
    "thorium",
    "arc",
)


def _extract_exe_from_command(cmd_str: str) -> str:
    """Extracts the executable path from a Windows registry command string."""
    raw = (cmd_str or "").strip()
    if not raw:
        return ""
    if raw.startswith('"'):
        end_quote = raw.find('"', 1)
        if end_quote > 1:
            candidate = os.path.expandvars(raw[1:end_quote].strip())
            if os.path.isfile(candidate):
                return candidate
    lower = raw.lower()
    exe_idx = lower.find(".exe")
    if exe_idx != -1:
        candidate = os.path.expandvars(raw[: exe_idx + 4].strip().strip('"'))
        if os.path.isfile(candidate):
            return candidate
    first_part = os.path.expandvars(raw.split()[0].strip('"'))
    if os.path.isfile(first_part):
        return first_part
    return ""


def discover_existing_browsers() -> List[str]:
    """
    Searches for any existing browser installed on the system (including the user's
    default browser, Firefox, Edge, Chrome, Brave, Vivaldi, Opera, Chromium, Waterfox,
    LibreWolf, Floorp, Zen, etc.) across Windows Registry, standard install paths, and PATH.
    """
    candidates: List[str] = []
    seen: set[str] = set()

    def _add(path: Optional[str]) -> None:
        if not path:
            return
        expanded = os.path.abspath(os.path.expandvars(os.path.expanduser(path.strip().strip('"'))))
        norm = expanded.casefold()
        if norm not in seen and os.path.isfile(expanded):
            seen.add(norm)
            candidates.append(expanded)

    if IS_WINDOWS:
        try:
            import winreg

            # 1. Check user's default HTTP/HTTPS browser ProgId first
            for scheme in ("https", "http"):
                try:
                    uc_path = rf"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\{scheme}\UserChoice"
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, uc_path) as uc_key:
                        prog_id, _ = winreg.QueryValueEx(uc_key, "ProgId")
                    if prog_id:
                        cmd_path = rf"{prog_id}\shell\open\command"
                        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, cmd_path) as cmd_key:
                            cmd_val, _ = winreg.QueryValueEx(cmd_key, "")
                        _add(_extract_exe_from_command(str(cmd_val)))
                except OSError:
                    pass

            # 2. Check App Paths in HKCU and HKLM for all major browsers
            app_names = (
                "firefox.exe",
                "msedge.exe",
                "chrome.exe",
                "brave.exe",
                "vivaldi.exe",
                "opera.exe",
                "waterfox.exe",
                "librewolf.exe",
                "floorp.exe",
                "zen.exe",
                "chromium.exe",
            )
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                for app_exe in app_names:
                    try:
                        ap_key_path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{app_exe}"
                        with winreg.OpenKey(hive, ap_key_path) as ap_key:
                            val, _ = winreg.QueryValueEx(ap_key, "")
                        _add(str(val))
                    except OSError:
                        pass

            # 3. Enumerate registered browsers in StartMenuInternet
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                for smi_root in (
                    r"SOFTWARE\Clients\StartMenuInternet",
                    r"SOFTWARE\WOW6432Node\Clients\StartMenuInternet",
                ):
                    try:
                        with winreg.OpenKey(hive, smi_root) as root_key:
                            sub_count, _, _ = winreg.QueryInfoKey(root_key)
                            for i in range(sub_count):
                                sub_name = winreg.EnumKey(root_key, i)
                                try:
                                    with winreg.OpenKey(
                                        hive, rf"{smi_root}\{sub_name}\shell\open\command"
                                    ) as cmd_key:
                                        cmd_val, _ = winreg.QueryValueEx(cmd_key, "")
                                    _add(_extract_exe_from_command(str(cmd_val)))
                                except OSError:
                                    pass
                    except OSError:
                        pass
        except Exception:
            pass

        # 4. Standard Windows installation directories for all popular browsers
        known_win_paths = [
            r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
            r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe",
            r"%LOCALAPPDATA%\Mozilla Firefox\firefox.exe",
            r"%ProgramFiles%\Firefox Developer Edition\firefox.exe",
            r"%ProgramFiles%\Nightly\firefox.exe",
            r"%ProgramFiles%\Waterfox\waterfox.exe",
            r"%ProgramFiles%\LibreWolf\librewolf.exe",
            r"%ProgramFiles%\Floorp\floorp.exe",
            r"%ProgramFiles%\Zen Browser\zen.exe",
            r"%LOCALAPPDATA%\Zen Browser\zen.exe",
            r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
            r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
            r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe",
            r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
            r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
            r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
            r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"%ProgramFiles%\Vivaldi\Application\vivaldi.exe",
            r"%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe",
            r"%LOCALAPPDATA%\Programs\Opera\opera.exe",
            r"%LOCALAPPDATA%\Programs\Opera\launcher.exe",
            r"%ProgramFiles%\Opera\opera.exe",
            r"%ProgramFiles%\Opera\launcher.exe",
            r"%LOCALAPPDATA%\Programs\Opera GX\opera.exe",
            r"%LOCALAPPDATA%\Programs\Opera GX\launcher.exe",
            r"%ProgramFiles%\Opera GX\opera.exe",
            r"%ProgramFiles%\Chromium\Application\chrome.exe",
            r"%LOCALAPPDATA%\Chromium\Application\chrome.exe",
        ]
        for p in known_win_paths:
            _add(p)

    # 5. Cross-platform PATH lookup for any installed browser binary
    for bin_name in (
        "firefox",
        "firefox.exe",
        "msedge",
        "msedge.exe",
        "microsoft-edge",
        "microsoft-edge-stable",
        "google-chrome",
        "google-chrome-stable",
        "chrome",
        "chrome.exe",
        "brave-browser",
        "brave",
        "brave.exe",
        "vivaldi",
        "vivaldi.exe",
        "opera",
        "opera.exe",
        "chromium",
        "chromium-browser",
        "waterfox",
        "librewolf",
        "floorp",
        "zen",
    ):
        found = shutil.which(bin_name)
        if found:
            _add(found)

    return candidates


def _get_running_process_names() -> Set[str]:
    """Returns a lowercase set of currently running executable names across the OS."""
    running: Set[str] = set()
    if IS_WINDOWS:
        try:
            mapper = ProcessMapper(location_path="")
            for exe_name, _pid in mapper._enumerate_windows_processes():
                running.add(exe_name.lower())
                if exe_name.lower().endswith(".exe"):
                    running.add(exe_name[:-4].lower())
        except Exception:
            pass
    else:
        try:
            proc = subprocess.run(
                ["ps", "-eo", "comm"],
                capture_output=True,
                text=True,
                timeout=1.5,
            )
            for line in proc.stdout.splitlines():
                name = os.path.basename(line.strip()).lower()
                if name:
                    running.add(name)
        except Exception:
            pass
    return running


def is_browser_running(exe_path: str, running_names: Optional[Set[str]] = None) -> bool:
    """Checks whether the given browser executable is currently running on the system."""
    if running_names is None:
        running_names = _get_running_process_names()
    exe_base = os.path.basename(exe_path).lower()
    stem = exe_base[:-4] if exe_base.endswith(".exe") else exe_base
    if exe_base in running_names or stem in running_names:
        return True
    # Opera launcher.exe spawns opera.exe in process list
    if stem == "launcher" and "opera" in exe_path.lower():
        return "opera.exe" in running_names or "opera" in running_names
    return False


def _build_browser_launch_command(
    exe: str,
    url: str,
    browser_profile: Optional[str] = None,
    open_in_running: bool = False,
) -> List[str]:
    """
    Builds the launch command for Firefox/Gecko, Chromium, or generic browsers:
    - If `open_in_running=True`, opens `url` as a new tab in the already-running browser
      (never passing `-no-remote` or `--user-data-dir` so it attaches to the active session).
    - If `open_in_running=False` and `browser_profile` is None, launches the browser normally.
    - If `browser_profile` is explicitly passed while `open_in_running=False`, uses the isolated profile.
    """
    exe_name = os.path.basename(exe).lower()
    if any(token in exe_name for token in _GECKO_BROWSER_TOKENS):
        if open_in_running:
            return [exe, "-new-tab", url]
        if browser_profile:
            ff_profile = os.path.join(browser_profile, "firefox_profile")
            os.makedirs(ff_profile, exist_ok=True)
            return [exe, "-no-remote", "-profile", ff_profile, "-new-window", url]
        return [exe, url]

    if any(token in exe_name for token in _CHROMIUM_BROWSER_TOKENS):
        if open_in_running:
            return [exe, url]
        if browser_profile:
            return [exe, f"--app={url}", "--window-size=1360,880", f"--user-data-dir={browser_profile}"]
        return [exe, url]

    return [exe, url]


def launch_frameless_web_app(
    url: str, browser_profile: Optional[str] = None
) -> Optional[subprocess.Popen]:
    """
    Checks which browsers are installed on the system:
    1. If an installed browser is already running, opens a new tab in that running browser.
    2. If no browser is currently running, launches the first installed browser.
    """
    installed_browsers = discover_existing_browsers()
    running_names = _get_running_process_names()

    # 1. Prefer opening a new tab in an already-running browser
    if installed_browsers:
        for exe in installed_browsers:
            if is_browser_running(exe, running_names):
                try:
                    command = _build_browser_launch_command(
                        exe, url, browser_profile=None, open_in_running=True
                    )
                    return subprocess.Popen(
                        command,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except OSError:
                    pass

        # 2. Otherwise launch the first installed browser
        for exe in installed_browsers:
            try:
                command = _build_browser_launch_command(
                    exe, url, browser_profile=browser_profile, open_in_running=False
                )
                return subprocess.Popen(
                    command,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except OSError:
                pass

    try:
        import webbrowser
        if webbrowser.open(url, new=2):
            return None
    except Exception as e:
        print(f"Could not open the OmniBond dashboard: {e}", file=sys.stderr)

    if browser_profile:
        print(
            "Could not find an installed browser to launch a monitored OmniBond window.",
            file=sys.stderr,
        )
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
        last_sys_total: Optional[int] = None
        while self._running:
            self.adapter_mgr.tick_throughput()

            adapters = self.adapter_mgr.get_adapters()
            cur_sys_total = sum(a.system_bytes_recv + a.system_bytes_sent for a in adapters)
            sys_nic_delta = (
                max(0, cur_sys_total - last_sys_total)
                if last_sys_total is not None
                else 0
            )
            last_sys_total = cur_sys_total

            active_adapters = [a for a in adapters if a.enabled] or adapters
            primary_ip = (
                max(active_adapters, key=lambda a: a.system_current_bps).ip
                if active_adapters
                else "-"
            )

            # Sample per-process TCP + UDP/QUIC + I/O deltas BEFORE ticking app throughput
            # so `tick_app_throughput()` immediately reflects the current tick's byte delta.
            pid_deltas = self.process_tcp_counters.sample(system_nic_delta_bytes=sys_nic_delta)
            for pid, byte_delta in pid_deltas.items():
                if byte_delta:
                    app_name = self.process_mapper.get_exe_name(pid)
                    self.routing_mgr.record_process_bytes(
                        app_name, pid, byte_delta, default_adapter_ip=primary_ip
                    )

            app_conn_counts: Dict[str, int] = {}
            for pid, cnt in self.process_tcp_counters.last_connection_counts.items():
                if cnt > 0:
                    app_name = self.process_mapper.get_exe_name(pid)
                    norm = self.routing_mgr.normalize_app_name(app_name)
                    app_conn_counts[norm] = app_conn_counts.get(norm, 0) + cnt
            self.routing_mgr.update_os_connection_counts(
                app_conn_counts, default_adapter_ip=primary_ip
            )

            self.routing_mgr.tick_app_throughput()

            # Re-sync running processes every ~6 seconds in background
            if tick_count % 12 == 0 and self.cached_detailed_procs:
                try:
                    self.scan_and_sync_processes()
                except Exception:
                    pass
            tick_count += 1
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