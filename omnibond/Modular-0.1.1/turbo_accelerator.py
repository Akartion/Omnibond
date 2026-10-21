#!/usr/bin/env python3
"""
OmniBond - Turbo Parallel Range Downloader & HLS (.m3u8) Stream Accelerator.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
import queue
import re
import socket
import threading
import time
import urllib.parse
from typing import Dict, List, Optional, Tuple

from adapter_manager import AdapterManager, NetworkAdapter
from config import TURBO_APP_KEY
from routing_manager import AppRoutingManager

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