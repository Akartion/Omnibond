#!/usr/bin/env python3
"""
OmniBond - Shared Configuration, Constants, Palettes & Optional Tkinter Setup.
"""

from __future__ import annotations

import os
import sys

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
    HAS_TK = True
    _TkFrameBase = tk.Frame
except Exception:
    tk = None  # type: ignore
    filedialog = None  # type: ignore
    messagebox = None  # type: ignore
    HAS_TK = False
    _TkFrameBase = object

IS_WINDOWS = sys.platform.startswith("win")
HTTP_PROXY_PORT = 8080
SOCKS_PROXY_PORT = 1080
WEB_UI_PORT = 8085
TURBO_APP_KEY = "__turbo_accelerator__"
TURBO_APP_LABEL = "Turbo Accelerator (Built-in)"
BLOCK_INTERNET_RULE = "BLOCK"
RULES_FILE = os.path.join(os.path.expanduser("~"), ".omnibond_rules.json")

ADAPTER_PALETTE = [
    ("#2563eb", "#60a5fa", "#0d1f42"),  # 01 Blue
    ("#ea580c", "#fb923c", "#3b1a09"),  # 02 Orange
    ("#10b981", "#34d399", "#062e22"),  # 03 Emerald
    ("#7c3aed", "#a78bfa", "#261247"),  # 04 Purple
    ("#eab308", "#facc15", "#382b06"),  # 05 Amber
    ("#ec4899", "#f472b6", "#3d1028"),  # 06 Pink
]

SYSTEM_NOISE_EXES = {
    "svchost.exe", "conhost.exe", "csrss.exe", "smss.exe", "services.exe",
    "lsass.exe", "wininit.exe", "fontdrvhost.exe", "dwm.exe", "sihost.exe",
    "taskhostw.exe", "runtimebroker.exe", "searchindexer.exe", "spoolsv.exe",
    "dllhost.exe", "WmiPrvSE.exe", "wmiprvse.exe", "ctfmon.exe", "audiodg.exe",
    "system", "registry", "idle", "memory compression", "securityhealthservice.exe",
}

KNOWN_USER_APPS = {
    "steam.exe", "steamwebhelper.exe", "chrome.exe", "firefox.exe", "msedge.exe",
    "brave.exe", "opera.exe", "discord.exe", "spotify.exe", "vlc.exe",
    "obs64.exe", "epicgameslauncher.exe", "code.exe", "slack.exe", "telegram.exe",
    "whatsapp.exe", "zoom.exe", "teams.exe", "qbittorrent.exe", "idm.exe",
    "idman.exe", "curl.exe", "python.exe",
}


VIRTUAL_ADAPTER_KEYWORDS = (
    "vethernet",
    "wsl",
    "hyper-v",
    "default switch",
    "virtualbox",
    "vboxnet",
    "host-only",
    "vmware",
    "vmnet",
    "docker",
    "npcap",
    "loopback",
    "teredo",
    "isatap",
    "bluetooth",
)