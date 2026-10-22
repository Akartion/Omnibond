#!/usr/bin/env python3
"""
OmniBond - Per-Application Routing Rules & Live Speed Telemetry Manager.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import re
import sys
import threading
import time
from typing import Dict, List, Set

from config import (
    BLOCK_INTERNET_RULE,
    FRIENDLY_APP_NAMES,
    RULES_FILE,
    TURBO_APP_KEY,
    TURBO_APP_LABEL,
)
from process_mapper import ProcessInfo

# =====================================================================
# 2. PER-APPLICATION ROUTING & LIVE SPEED TELEMETRY MANAGER
# =====================================================================

def _default_friendly_label(app_key: str, window_title: str = "") -> str:
    norm = os.path.basename((app_key or "").strip().lower())
    if not norm:
        return "System Process"
    if norm == TURBO_APP_KEY or "turbo" in norm:
        return TURBO_APP_LABEL
    if window_title and "gemini" in window_title.lower():
        base = FRIENDLY_APP_NAMES.get(norm, "")
        return f"Gemini ({base})" if base and base != "Google Gemini" else "Google Gemini"
    if norm in FRIENDLY_APP_NAMES:
        return FRIENDLY_APP_NAMES[norm]
    stem = norm[:-4] if norm.endswith(".exe") else norm
    cleaned = re.sub(r"[_-]+", " ", stem)
    cleaned = re.sub(r"([a-z])([A-Z])", r"\1 \2", cleaned).strip()
    return " ".join(w.capitalize() for w in cleaned.split()) if cleaned else norm


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
                                display_name=_default_friendly_label(key),
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
                        display_name=_default_friendly_label(key),
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
                label = _default_friendly_label(key)
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
        Syncs detected running user programs and services so the router section
        automatically shows all running applications and background services
        (plus any user-added/pinned programs).
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
                    if getattr(pinfo, "display_name", ""):
                        st.display_name = pinfo.display_name
                    else:
                        st.display_name = _default_friendly_label(key, st.window_title)
                else:
                    st.is_running = False

            # Track every running process so All, Apps, and Services include all detected processes.
            for p in detailed_procs:
                friendly = getattr(p, "display_name", "") or _default_friendly_label(p.exe_name, p.window_title)
                if p.exe_name not in self._stats:
                    self._stats[p.exe_name] = AppTrafficStats(
                        app_name=p.exe_name,
                        display_name=friendly,
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
                label = _default_friendly_label(key)
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
                st = AppTrafficStats(app_name=key, display_name=_default_friendly_label(key))
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

                w_title = st.window_title if st else ""
                if is_builtin:
                    label = TURBO_APP_LABEL
                elif st and st.display_name and st.display_name != key:
                    label = st.display_name
                else:
                    label = _default_friendly_label(key, w_title)

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
                    "window_title": w_title,
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
                    r["display_name"].casefold(),
                )
            )
            return rows