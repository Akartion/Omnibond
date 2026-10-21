#!/usr/bin/env python3
"""
OmniBond - Network Adapter Discovery, Interface Counters, Rate Limits & Load Balancer.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
import json
import math
import os
import re
import socket
import struct
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from config import (
    ADAPTER_PALETTE,
    IS_WINDOWS,
    RULES_FILE,
    VIRTUAL_ADAPTER_KEYWORDS,
)
from routing_manager import AppRoutingManager

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