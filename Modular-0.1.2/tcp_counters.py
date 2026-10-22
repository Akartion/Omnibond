#!/usr/bin/env python3
"""
OmniBond - Windows Per-Process TCP Extended Statistics (EStats) Telemetry.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import socket
import struct
import time
from typing import Any, Dict, List, Set, Tuple

from config import IS_WINDOWS
from process_mapper import (
    MIB_TCP6ROW,
    MIB_TCP6ROW_OWNER_PID,
    MIB_TCPROW,
    MIB_TCPROW_OWNER_PID,
)

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