#!/usr/bin/env python3
"""
OmniBond - Windows System Proxy & Simultaneous Multi-NIC Optimizer.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from adapter_manager import AdapterManager
from config import HTTP_PROXY_PORT, IS_WINDOWS, RULES_FILE

# =====================================================================
# 5. WINDOWS SYSTEM PROXY & SIMULTANEOUS MULTI-NIC OPTIMIZER
# =====================================================================

class WindowsSystemOptimizer:
    def __init__(self, adapter_mgr: Optional[AdapterManager] = None, restore_file: str = RULES_FILE + ".sys_restore"):
        self.adapter_mgr = adapter_mgr
        self.restore_file = restore_file
        self.system_proxy_enabled = False
        self._proxy_snapshot: Optional[Dict[str, Tuple[bool, int, Any]]] = None
        self._nic_policy_snapshot: Optional[Tuple[bool, int, Any]] = None
        self._nic_policy_key_existed = False
        self._interface_metrics: Dict[Tuple[str, str], str] = {}
        self.recover_stale_network_state()

    @staticmethod
    def _is_loopback_proxy_server(proxy_server_val: Any) -> bool:
        if not proxy_server_val:
            return False
        text = str(proxy_server_val).strip().lower()
        return "127.0.0.1" in text or "localhost" in text

    @staticmethod
    def _notify_wininet_refresh():
        if not IS_WINDOWS:
            return
        try:
            INTERNET_OPTION_SETTINGS_CHANGED = 39
            INTERNET_OPTION_REFRESH = 37
            wininet = ctypes.windll.wininet
            wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
            wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)
        except Exception:
            pass

    @staticmethod
    def _read_registry_values(key, names: List[str]) -> Dict[str, Tuple[bool, int, Any]]:
        import winreg
        snapshot = {}
        for name in names:
            try:
                value, value_type = winreg.QueryValueEx(key, name)
                snapshot[name] = (True, value_type, value)
            except FileNotFoundError:
                snapshot[name] = (False, 0, None)
        return snapshot

    @classmethod
    def _sanitize_proxy_snapshot(
        cls, snapshot: Dict[str, Tuple[bool, int, Any]]
    ) -> Dict[str, Tuple[bool, int, Any]]:
        """
        Prevents snapshotting a stale OmniBond loopback proxy (127.0.0.1:8080) as the
        user's original proxy setting after an unclean shutdown.
        """
        import winreg
        srv_exists, _, srv_val = snapshot.get("ProxyServer", (False, 0, None))
        if srv_exists and cls._is_loopback_proxy_server(srv_val):
            cleaned = dict(snapshot)
            cleaned["ProxyEnable"] = (True, winreg.REG_DWORD, 0)
            cleaned["ProxyServer"] = (False, 0, None)
            return cleaned
        return snapshot

    @staticmethod
    def _restore_registry_values(key, snapshot: Dict[str, Tuple[bool, int, Any]]):
        import winreg
        for name, (exists, value_type, value) in snapshot.items():
            if exists:
                winreg.SetValueEx(key, name, 0, value_type, value)
            else:
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass

    def _save_restore_journal(self):
        if not self.restore_file:
            return
        try:
            payload = {
                "metrics": [
                    {"family": fam, "index": idx, "metric": met}
                    for (fam, idx), met in self._interface_metrics.items()
                ],
                "timestamp": time.time(),
            }
            with open(self.restore_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            pass

    def _clear_restore_journal(self):
        if not self.restore_file:
            return
        try:
            if os.path.exists(self.restore_file):
                os.remove(self.restore_file)
        except Exception:
            pass

    def recover_stale_network_state(self):
        """
        Automatically detects and cleans up leftover loopback proxy settings or
        modified interface metrics from a previous crashed or killed session.
        """
        if not IS_WINDOWS:
            return
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0,
                winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE,
            ) as key:
                snap = self._read_registry_values(key, ["ProxyEnable", "ProxyServer"])
                pe_exists, _, pe_val = snap.get("ProxyEnable", (False, 0, 0))
                ps_exists, _, ps_val = snap.get("ProxyServer", (False, 0, ""))
                if pe_exists and int(pe_val or 0) == 1 and ps_exists and self._is_loopback_proxy_server(ps_val):
                    winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
                    try:
                        winreg.DeleteValue(key, "ProxyServer")
                    except FileNotFoundError:
                        pass
                    self._notify_wininet_refresh()
        except Exception:
            pass

        if self.restore_file and os.path.exists(self.restore_file):
            try:
                with open(self.restore_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data.get("metrics", []):
                    fam = str(item.get("family", "ipv4"))
                    idx = str(item.get("index", ""))
                    if fam in ("ipv4", "ipv6") and idx.isdigit():
                        subprocess.run(
                            ["netsh", "interface", fam, "set", "interface", idx, "metric=automatic"],
                            capture_output=True,
                            text=True,
                            timeout=2.0,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        )
            except Exception:
                pass
            finally:
                self._clear_restore_journal()

    def set_system_proxy(self, enable: bool, host: str = "127.0.0.1", port: int = HTTP_PROXY_PORT) -> Tuple[bool, str]:
        if not IS_WINDOWS:
            self.system_proxy_enabled = enable
            return True, f"Simulated system proxy {'enabled' if enable else 'disabled'} (non-Windows)."
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0,
                winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE,
            ) as key:
                if enable:
                    if self._proxy_snapshot is None:
                        raw_snap = self._read_registry_values(
                            key, ["ProxyEnable", "ProxyServer", "ProxyOverride"]
                        )
                        self._proxy_snapshot = self._sanitize_proxy_snapshot(raw_snap)
                    winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
                    winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, f"{host}:{port}")
                    winreg.SetValueEx(
                        key,
                        "ProxyOverride",
                        0,
                        winreg.REG_SZ,
                        "localhost;127.*;10.*;192.168.*;172.16.*;172.17.*;172.18.*;172.19.*;172.20.*;172.21.*;172.22.*;172.23.*;172.24.*;172.25.*;172.26.*;172.27.*;172.28.*;172.29.*;172.30.*;172.31.*;<local>",
                    )
                elif self._proxy_snapshot is not None:
                    safe_snap = self._sanitize_proxy_snapshot(self._proxy_snapshot)
                    self._restore_registry_values(key, safe_snap)
                    self._proxy_snapshot = None
                else:
                    winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
                    try:
                        cur_srv, _ = winreg.QueryValueEx(key, "ProxyServer")
                        if self._is_loopback_proxy_server(cur_srv):
                            winreg.DeleteValue(key, "ProxyServer")
                    except FileNotFoundError:
                        pass

            self._notify_wininet_refresh()
            self.system_proxy_enabled = enable
            state = f"Enabled ({host}:{port})" if enable else "Disabled (Direct Routing)"
            return True, f"Windows System-Wide Proxy {state}."
        except Exception as e:
            return False, f"Failed updating Windows proxy: {e}"

    def _set_interface_metrics(
        self, family: str, enabled: bool, messages: List[str], failures: List[str]
    ):
        show_command = ["netsh", "interface", family, "show", "interfaces"]
        valid_if_indices: Set[int] = set()
        valid_names: Set[str] = set()
        if self.adapter_mgr is not None:
            for ad in self.adapter_mgr.get_adapters():
                if ad.enabled and ad.is_online and not self.adapter_mgr.is_virtual_adapter_name(ad.name):
                    if ad.if_index > 0:
                        valid_if_indices.add(ad.if_index)
                    valid_names.add(ad.name.casefold())

        try:
            proc = subprocess.run(
                show_command,
                capture_output=True,
                text=True,
                timeout=2.0,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if proc.returncode != 0:
                raise OSError(proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}")
            for line in proc.stdout.splitlines():
                parts = line.split()
                if len(parts) < 5 or not parts[0].isdigit() or parts[3].lower() != "connected":
                    continue
                index = parts[0]
                if_name = " ".join(parts[4:]).strip()
                if AdapterManager.is_virtual_adapter_name(if_name):
                    continue
                if enabled and (valid_if_indices or valid_names):
                    if int(index) not in valid_if_indices and if_name.casefold() not in valid_names:
                        continue

                key = (family, index)
                if enabled:
                    if key not in self._interface_metrics:
                        self._interface_metrics[key] = "automatic"
                    cmd = ["netsh", "interface", family, "set", "interface", index, "metric=15", "store=active"]
                elif key in self._interface_metrics:
                    self._interface_metrics.pop(key, None)
                    cmd = ["netsh", "interface", family, "set", "interface", index, "metric=automatic"]
                else:
                    continue

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=1.5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if result.returncode != 0:
                    failure = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
                    failures.append(f"Could not update {family.upper()} interface {index}: {failure}")
                    if not enabled:
                        self._interface_metrics[key] = "automatic"

            if self._interface_metrics:
                self._save_restore_journal()
            else:
                self._clear_restore_journal()

            messages.append(
                f"{family.upper()} interface metrics {'equalized (active session)' if enabled else 'restored to automatic'}."
            )
        except (OSError, subprocess.SubprocessError) as exc:
            messages.append(f"Could not update {family.upper()} interface metrics: {exc}")
            failures.append(str(exc))

    def optimize_multi_nic(
        self,
        optimize_ipv4: bool = True,
        optimize_ipv6: bool = False,
        keep_multi_nic: bool = True,
    ) -> Tuple[bool, str]:
        if not IS_WINDOWS:
            return True, "Multi-NIC optimization simulated on non-Windows platform."
        messages = []
        failures = []
        if keep_multi_nic:
            try:
                import winreg
                pol_path = r"Software\Policies\Microsoft\Windows\WcmSvc\GroupPolicy"
                if self._nic_policy_snapshot is None:
                    try:
                        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, pol_path, 0, winreg.KEY_QUERY_VALUE) as key:
                            self._nic_policy_key_existed = True
                            self._nic_policy_snapshot = self._read_registry_values(key, ["fMinimizeConnections"])["fMinimizeConnections"]
                    except FileNotFoundError:
                        self._nic_policy_key_existed = False
                        self._nic_policy_snapshot = (False, 0, None)
                with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, pol_path, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, "fMinimizeConnections", 0, winreg.REG_DWORD, 0)
                messages.append("Kept Windows connection minimization disabled.")
            except PermissionError:
                messages.append("Tip: Run as Administrator to update the multi-network policy.")
                failures.append("The multi-network policy update was denied.")
            except OSError as exc:
                messages.append(f"Could not update the multi-network policy: {exc}")
                failures.append(str(exc))
        elif self._nic_policy_snapshot is not None:
            try:
                import winreg
                pol_path = r"Software\Policies\Microsoft\Windows\WcmSvc\GroupPolicy"
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, pol_path, 0, winreg.KEY_SET_VALUE) as key:
                    self._restore_registry_values(key, {"fMinimizeConnections": self._nic_policy_snapshot})
                if not self._nic_policy_key_existed:
                    try:
                        winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, pol_path)
                    except FileNotFoundError:
                        pass
                self._nic_policy_snapshot = None
                messages.append("Restored the Windows connection minimization policy.")
            except OSError as exc:
                messages.append(f"Could not restore the multi-network policy: {exc}")
                failures.append(str(exc))

        self._set_interface_metrics("ipv4", optimize_ipv4, messages, failures)
        if optimize_ipv6 or any(fam == "ipv6" for fam, _ in self._interface_metrics):
            self._set_interface_metrics("ipv6", optimize_ipv6, messages, failures)

        return not failures, " ".join(messages)

    def repair_network(self) -> Tuple[bool, str]:
        """
        Emergency one-click Windows network repair:
        1. Disables any stuck Windows WinINet proxy (ProxyEnable=0) & refreshes WinINet.
        2. Resets WinHTTP proxy to direct.
        3. Restores all connected physical IPv4 and IPv6 interfaces back to metric=automatic.
        4. Flushes the Windows DNS resolver cache.
        """
        if not IS_WINDOWS:
            self.system_proxy_enabled = False
            self._proxy_snapshot = None
            return True, "Simulated network repair completed (proxy disabled, metrics reset to automatic)."

        steps: List[str] = []
        try:
            import winreg
            internet_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, internet_path, 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
                try:
                    cur_srv, _ = winreg.QueryValueEx(key, "ProxyServer")
                    if self._is_loopback_proxy_server(cur_srv):
                        winreg.DeleteValue(key, "ProxyServer")
                except FileNotFoundError:
                    pass
            self._proxy_snapshot = None
            self.system_proxy_enabled = False
            self._notify_wininet_refresh()
            steps.append("WinINet proxy reset to Direct.")
        except Exception as e:
            steps.append(f"Proxy reset warning: {e}")

        for family in ("ipv4", "ipv6"):
            try:
                proc = subprocess.run(
                    ["netsh", "interface", family, "show", "interfaces"],
                    capture_output=True,
                    text=True,
                    timeout=2.0,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                for line in proc.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 5 and parts[0].isdigit() and parts[3].lower() == "connected":
                        idx = parts[0]
                        if_name = " ".join(parts[4:]).strip()
                        if "loopback" in if_name.lower():
                            continue
                        subprocess.run(
                            ["netsh", "interface", family, "set", "interface", idx, "metric=automatic"],
                            capture_output=True,
                            text=True,
                            timeout=1.5,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        )
            except Exception:
                pass
        self._interface_metrics.clear()
        self._clear_restore_journal()
        steps.append("IPv4/IPv6 interface metrics restored to automatic.")

        try:
            subprocess.run(
                ["netsh", "winhttp", "reset", "proxy"],
                capture_output=True,
                text=True,
                timeout=2.0,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass

        try:
            subprocess.run(
                ["ipconfig", "/flushdns"],
                capture_output=True,
                text=True,
                timeout=2.0,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            steps.append("DNS cache flushed.")
        except Exception:
            pass

        if self.adapter_mgr is not None:
            try:
                self.adapter_mgr.refresh_adapters()
            except Exception:
                pass

        return True, " ".join(steps)

    def restore_system_settings(self) -> List[str]:
        errors: List[str] = []
        if not IS_WINDOWS:
            self.system_proxy_enabled = False
            return errors

        try:
            import winreg
            internet_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, internet_path, 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
                if self._proxy_snapshot is not None:
                    safe_snap = self._sanitize_proxy_snapshot(self._proxy_snapshot)
                    self._restore_registry_values(key, safe_snap)
                    self._proxy_snapshot = None
                else:
                    winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
                    try:
                        cur_srv, _ = winreg.QueryValueEx(key, "ProxyServer")
                        if self._is_loopback_proxy_server(cur_srv):
                            winreg.DeleteValue(key, "ProxyServer")
                    except FileNotFoundError:
                        pass
            self.system_proxy_enabled = False
            self._notify_wininet_refresh()
        except Exception as e:
            errors.append(f"Could not restore Windows proxy settings: {e}")

        try:
            import winreg
            pol_path = r"Software\Policies\Microsoft\Windows\WcmSvc\GroupPolicy"
            if self._nic_policy_snapshot is not None:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, pol_path, 0, winreg.KEY_SET_VALUE) as key:
                    self._restore_registry_values(key, {"fMinimizeConnections": self._nic_policy_snapshot})
                if not self._nic_policy_key_existed:
                    try:
                        winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, pol_path)
                    except FileNotFoundError:
                        pass
                self._nic_policy_snapshot = None
            for (family, idx) in list(self._interface_metrics.keys()):
                proc = subprocess.run(
                    ["netsh", "interface", family, "set", "interface", idx, "metric=automatic"],
                    capture_output=True,
                    text=True,
                    timeout=3.0,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if proc.returncode != 0:
                    errors.append(f"Could not restore {family.upper()} metric for interface {idx}: {proc.stderr.strip() or proc.stdout.strip()}")
            self._interface_metrics.clear()
            self._clear_restore_journal()
        except Exception as e:
            errors.append(f"Could not restore multi-NIC settings: {e}")
        return errors