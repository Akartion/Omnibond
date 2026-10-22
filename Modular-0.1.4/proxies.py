#!/usr/bin/env python3
"""
OmniBond - System-Wide HTTP/HTTPS (8080) & SOCKS5 (1080) Bonding Proxies.
"""

from __future__ import annotations

import socket
import socketserver
import struct
import threading
import urllib.parse
from typing import TYPE_CHECKING

from adapter_manager import NetworkAdapter
from routing_manager import AppRoutingManager

if TYPE_CHECKING:
    from engine import OmniBondEngine

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