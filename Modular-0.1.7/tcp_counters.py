#!/usr/bin/env python3
"""
OmniBond - Windows Per-Process TCP & UDP/QUIC Network Throughput Telemetry.
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


class MIB_UDPROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class MIB_UDP6ROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("ucLocalAddr", ctypes.c_ubyte * 16),
        ("dwLocalScopeId", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class WindowsProcessTcpCounters:
    """
    Samples per-process network byte counters on Windows:
    1. Uses IP Helper `GetPerTcpConnectionEStats` / `GetPerTcp6ConnectionEStats` when elevated.
    2. Uses `GetExtendedTcpTable` + `GetExtendedUdpTable` + `GetProcessIoCounters` (which works
       without Administrator privileges and covers HTTP/3 QUIC & UDP streams) bounded by live
       physical NIC throughput so per-application speed graphs always respond to real traffic.
    """

    ERROR_ACCESS_DENIED = 5
    ERROR_INSUFFICIENT_BUFFER = 122
    TCP_TABLE_OWNER_PID_ALL = 5
    UDP_TABLE_OWNER_PID = 1
    TCP_STATE_ESTABLISHED = 5
    TCP_CONNECTION_ESTATS_DATA = 1
    ACTIVE_TCP_STATES = {3, 4, 5, 6, 7, 8, 9, 10, 11}

    def __init__(self):
        self.status = "Windows per-process TCP telemetry unavailable."
        self.diagnostics = "No TCP telemetry sample yet."
        self._enabled: Dict[Tuple[Any, ...], bool] = {}
        self._enable_errors: Dict[Tuple[Any, ...], int] = {}
        self._last_counters: Dict[Tuple[Any, ...], Tuple[int, int]] = {}
        self._last_seen: Dict[Tuple[Any, ...], float] = {}
        self._last_pid_io: Dict[int, int] = {}
        self._last_conn_counts: Dict[int, int] = {}
        self._is_admin = False
        if not IS_WINDOWS:
            self.status = "Per-process TCP telemetry is only available on Windows."
            return

        iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        shell32.IsUserAnAdmin.restype = wintypes.BOOL
        self._is_admin = bool(shell32.IsUserAnAdmin())

        self._kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self._kernel32.OpenProcess.restype = wintypes.HANDLE
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32.CloseHandle.restype = wintypes.BOOL
        self._kernel32.GetProcessIoCounters.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(IO_COUNTERS),
        ]
        self._kernel32.GetProcessIoCounters.restype = wintypes.BOOL

        self._get_tcp_table = iphlpapi.GetExtendedTcpTable
        self._get_tcp6_table = self._get_tcp_table
        self._get_udp_table = iphlpapi.GetExtendedUdpTable
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

        self._get_udp_table.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.ULONG),
            wintypes.BOOL,
            wintypes.ULONG,
            wintypes.ULONG,
            wintypes.ULONG,
        ]
        self._get_udp_table.restype = wintypes.ULONG

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
            "Live per-app socket & I/O telemetry active (Run as Admin for kernel TCP EStats)."
            if not self._is_admin
            else "Direct app TCP & socket telemetry ready; waiting for traffic."
        )

    def _read_table(self, get_table, family: int, table_class: int, row_type) -> List[Any]:
        """Reads an IP Helper TCP or UDP table with buffer slack and retry on growth."""
        size = wintypes.ULONG(0)
        result = get_table(None, ctypes.byref(size), False, family, table_class, 0)
        if result not in (0, self.ERROR_INSUFFICIENT_BUFFER):
            raise OSError(result, "Could not query the Windows socket table")
        if size.value == 0:
            return []

        for _attempt in range(4):
            alloc_size = wintypes.ULONG(size.value + 8192)
            buffer = ctypes.create_string_buffer(alloc_size.value)
            result = get_table(
                ctypes.cast(buffer, ctypes.c_void_p),
                ctypes.byref(alloc_size),
                False,
                family,
                table_class,
                0,
            )
            if result == 0:
                count = struct.unpack_from("<I", buffer.raw, 0)[0]
                row_size = ctypes.sizeof(row_type)
                rows = []
                for index in range(count):
                    offset = 4 + index * row_size
                    if offset + row_size > alloc_size.value:
                        break
                    rows.append(row_type.from_buffer_copy(buffer.raw, offset))
                return rows
            if result == self.ERROR_INSUFFICIENT_BUFFER:
                size.value = alloc_size.value
                continue
            raise OSError(result, "Could not read the Windows socket table")
        return []

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

    def _get_process_io_total(self, pid: int) -> int:
        """
        Queries cumulative process I/O transfer bytes via `GetProcessIoCounters`
        (requires only `PROCESS_QUERY_LIMITED_INFORMATION`, no Admin required).
        """
        if not IS_WINDOWS or pid <= 4:
            return -1
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h_proc = self._kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h_proc:
            return -1
        try:
            counters = IO_COUNTERS()
            if self._kernel32.GetProcessIoCounters(h_proc, ctypes.byref(counters)):
                return int(
                    counters.ReadTransferCount
                    + counters.WriteTransferCount
                    + counters.OtherTransferCount
                )
        except Exception:
            pass
        finally:
            self._kernel32.CloseHandle(h_proc)
        return -1

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
        else:
            # First time seeing this established connection after enabling EStats:
            # if counters already accumulated data since enabling, record initial burst
            initial = max(0, counters[0]) + max(0, counters[1])
            if 0 < initial <= 16 * 1024 * 1024:
                deltas_by_pid[pid] = deltas_by_pid.get(pid, 0) + initial
        self._last_counters[key] = counters
        self._last_seen[key] = now

    @property
    def last_connection_counts(self) -> Dict[int, int]:
        return dict(self._last_conn_counts)

    def sample(self, system_nic_delta_bytes: int = 0) -> Dict[int, int]:
        if not IS_WINDOWS:
            return {}

        try:
            rows4 = self._read_table(
                self._get_tcp_table, 2, self.TCP_TABLE_OWNER_PID_ALL, MIB_TCPROW_OWNER_PID
            )
            rows6 = self._read_table(
                self._get_tcp6_table, 23, self.TCP_TABLE_OWNER_PID_ALL, MIB_TCP6ROW_OWNER_PID
            )
        except OSError as e:
            self.status = f"Windows TCP table read failed: {e}"
            return {}

        udp4: List[Any] = []
        udp6: List[Any] = []
        try:
            udp4 = self._read_table(
                self._get_udp_table, 2, self.UDP_TABLE_OWNER_PID, MIB_UDPROW_OWNER_PID
            )
            udp6 = self._read_table(
                self._get_udp_table, 23, self.UDP_TABLE_OWNER_PID, MIB_UDP6ROW_OWNER_PID
            )
        except OSError:
            pass

        now = time.monotonic()
        active_keys: Set[Tuple[Any, ...]] = set()
        deltas_by_pid: Dict[int, int] = {}
        active_socket_pids: Dict[int, int] = {}
        udp_socket_pids: Set[int] = set()
        my_pid = os.getpid()

        external_tcp_found = False
        sampled_flow = False
        access_denied = False
        eligible_connections = 0
        enabled_connections = 0
        readable_connections = 0

        for owner_row in rows4:
            pid = int(owner_row.dwOwningPid)
            if pid <= 4 or pid == my_pid:
                continue
            remote_ip = socket.inet_ntoa(struct.pack("<I", owner_row.dwRemoteAddr))
            if remote_ip.startswith("127.") or remote_ip == "0.0.0.0":
                continue
            if int(owner_row.dwState) in self.ACTIVE_TCP_STATES:
                active_socket_pids[pid] = active_socket_pids.get(pid, 0) + 1
            if owner_row.dwState != self.TCP_STATE_ESTABLISHED:
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
            if not self._enabled[key]:
                result = self._enable_errors.get(key, 0)
                access_denied |= result == self.ERROR_ACCESS_DENIED
                continue
            enabled_connections += 1
            try:
                counters = self._get_stats(row, self._get_tcp_estats)
            except OSError as e:
                access_denied |= e.errno == self.ERROR_ACCESS_DENIED
                continue
            sampled_flow = True
            readable_connections += 1
            self._record_delta(key, pid, counters, now, deltas_by_pid)

        for owner_row in rows6:
            pid = int(owner_row.dwOwningPid)
            if pid <= 4 or pid == my_pid:
                continue
            remote_ip6 = socket.inet_ntop(socket.AF_INET6, bytes(owner_row.ucRemoteAddr))
            if remote_ip6 in ("::1", "::"):
                continue
            if int(owner_row.dwState) in self.ACTIVE_TCP_STATES:
                active_socket_pids[pid] = active_socket_pids.get(pid, 0) + 1
            if owner_row.dwState != self.TCP_STATE_ESTABLISHED:
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
            if not self._enabled[key]:
                result = self._enable_errors.get(key, 0)
                access_denied |= result == self.ERROR_ACCESS_DENIED
                continue
            enabled_connections += 1
            try:
                counters = self._get_stats(row, self._get_tcp6_estats)
            except OSError as e:
                access_denied |= e.errno == self.ERROR_ACCESS_DENIED
                continue
            sampled_flow = True
            readable_connections += 1
            self._record_delta(key, pid, counters, now, deltas_by_pid)

        # Track UDP/QUIC socket owners (browsers, Discord, games, streaming apps)
        for urow in udp4:
            pid = int(urow.dwOwningPid)
            if pid > 4 and pid != my_pid:
                local_ip = socket.inet_ntoa(struct.pack("<I", urow.dwLocalAddr))
                if not local_ip.startswith("127."):
                    udp_socket_pids.add(pid)
                    active_socket_pids.setdefault(pid, 1)
        for urow6 in udp6:
            pid = int(urow6.dwOwningPid)
            if pid > 4 and pid != my_pid:
                local_ip6 = socket.inet_ntop(socket.AF_INET6, bytes(urow6.ucLocalAddr))
                if local_ip6 != "::1":
                    udp_socket_pids.add(pid)
                    active_socket_pids.setdefault(pid, 1)

        self._last_conn_counts = active_socket_pids

        # Sample per-process I/O counters for all processes that own active TCP/UDP sockets.
        # This covers non-Admin sessions (where EStats is denied) and QUIC/HTTP3/UDP traffic.
        io_deltas_by_pid: Dict[int, int] = {}
        candidate_pids = set(active_socket_pids.keys()) | udp_socket_pids
        for pid in candidate_pids:
            io_total = self._get_process_io_total(pid)
            if io_total >= 0:
                prev_io = self._last_pid_io.get(pid)
                self._last_pid_io[pid] = io_total
                if prev_io is not None and io_total > prev_io:
                    io_deltas_by_pid[pid] = io_total - prev_io

        # Prune exited PIDs from _last_pid_io
        if len(self._last_pid_io) > 512:
            self._last_pid_io = {
                pid: val for pid, val in self._last_pid_io.items() if pid in candidate_pids
            }

        # Reconcile EStats TCP bytes with unattributed physical NIC bytes (UDP/QUIC or non-Admin TCP)
        estats_total = sum(deltas_by_pid.values())
        unattributed_nic_bytes = max(0, int(system_nic_delta_bytes) - estats_total)

        if unattributed_nic_bytes > 0 and candidate_pids:
            # Prefer processes that simultaneously have active sockets AND positive I/O transfer delta
            active_io_pids = {
                pid: delta for pid, delta in io_deltas_by_pid.items()
                if pid not in deltas_by_pid or pid in udp_socket_pids
            }
            total_io_delta = sum(active_io_pids.values())
            if total_io_delta > 0:
                budget = min(unattributed_nic_bytes, total_io_delta)
                for pid, io_delta in active_io_pids.items():
                    share = int(round(budget * (io_delta / total_io_delta)))
                    if share > 0:
                        deltas_by_pid[pid] = deltas_by_pid.get(pid, 0) + share
            elif not sampled_flow and active_socket_pids:
                # Fallback if Windows restricted OpenProcess on some socket-owning processes:
                # distribute across processes with active established TCP connections
                tcp_only_pids = {
                    pid: cnt for pid, cnt in active_socket_pids.items()
                    if cnt > 0 and pid not in udp_socket_pids
                } or active_socket_pids
                total_conns = max(1, sum(tcp_only_pids.values()))
                for pid, cnt in tcp_only_pids.items():
                    share = int(round(unattributed_nic_bytes * (cnt / total_conns)))
                    if share > 0:
                        deltas_by_pid[pid] = deltas_by_pid.get(pid, 0) + share

        self.diagnostics = (
            f"TCP flows: {eligible_connections}; EStats readable: {readable_connections}; "
            f"active socket PIDs: {len(active_socket_pids)}."
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

        if sampled_flow:
            self.status = "Direct app TCP & UDP/QUIC telemetry active."
        elif deltas_by_pid:
            self.status = "Live app socket & I/O telemetry active."
        elif access_denied or not self._is_admin:
            self.status = (
                "Live socket I/O telemetry ready (run as Administrator for kernel TCP EStats)."
            )
        elif external_tcp_found:
            self.status = f"Direct app telemetry active ({self.diagnostics})"
        else:
            self.status = "Direct app telemetry ready; waiting for network traffic."
        return deltas_by_pid