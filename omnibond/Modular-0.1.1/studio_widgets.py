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
    "explorer.exe", "steam.exe", "steamwebhelper.exe", "chrome.exe", "firefox.exe",
    "msedge.exe", "brave.exe", "opera.exe", "vivaldi.exe", "waterfox.exe",
    "librewolf.exe", "floorp.exe", "zen.exe", "discord.exe", "spotify.exe",
    "vlc.exe", "obs64.exe", "epicgameslauncher.exe", "code.exe", "slack.exe",
    "telegram.exe", "whatsapp.exe", "zoom.exe", "teams.exe", "ms-teams.exe",
    "qbittorrent.exe", "idm.exe", "idman.exe", "curl.exe", "python.exe",
    "windowsterminal.exe", "notepad.exe", "devenv.exe", "pycharm64.exe",
    "idea64.exe", "blender.exe", "photoshop.exe", "acrobat.exe", "onedrive.exe",
    "gemini.exe", "claude.exe", "chatgpt.exe",
}

FRIENDLY_APP_NAMES = {
    TURBO_APP_KEY: TURBO_APP_LABEL,
    "explorer.exe": "File Explorer",
    "chrome.exe": "Google Chrome",
    "firefox.exe": "Mozilla Firefox",
    "msedge.exe": "Microsoft Edge",
    "brave.exe": "Brave Browser",
    "opera.exe": "Opera Browser",
    "vivaldi.exe": "Vivaldi Browser",
    "waterfox.exe": "Waterfox",
    "librewolf.exe": "LibreWolf",
    "floorp.exe": "Floorp Browser",
    "zen.exe": "Zen Browser",
    "chromium.exe": "Chromium",
    "steam.exe": "Steam Client",
    "steamwebhelper.exe": "Steam Web Helper",
    "epicgameslauncher.exe": "Epic Games Launcher",
    "discord.exe": "Discord",
    "spotify.exe": "Spotify",
    "vlc.exe": "VLC Media Player",
    "obs64.exe": "OBS Studio",
    "code.exe": "Visual Studio Code",
    "devenv.exe": "Visual Studio",
    "pycharm64.exe": "PyCharm",
    "idea64.exe": "IntelliJ IDEA",
    "slack.exe": "Slack",
    "telegram.exe": "Telegram Desktop",
    "whatsapp.exe": "WhatsApp",
    "zoom.exe": "Zoom Workplace",
    "teams.exe": "Microsoft Teams",
    "ms-teams.exe": "Microsoft Teams",
    "qbittorrent.exe": "qBittorrent",
    "idm.exe": "Internet Download Manager",
    "idman.exe": "Internet Download Manager",
    "curl.exe": "cURL CLI",
    "python.exe": "Python Runtime",
    "pythonw.exe": "Python Background Runtime",
    "windowsterminal.exe": "Windows Terminal",
    "powershell.exe": "Windows PowerShell",
    "pwsh.exe": "PowerShell",
    "cmd.exe": "Command Prompt",
    "notepad.exe": "Notepad",
    "onedrive.exe": "Microsoft OneDrive",
    "gemini.exe": "Google Gemini",
    "claude.exe": "Claude Desktop",
    "chatgpt.exe": "ChatGPT Desktop",
    "svchost.exe": "Windows Service Host",
    "lsass.exe": "Local Security Authority",
    "services.exe": "Windows Services Manager",
    "spoolsv.exe": "Print Spooler Service",
    "searchindexer.exe": "Windows Search Indexer",
    "searchhost.exe": "Windows Search Host",
    "runtimebroker.exe": "Windows Runtime Broker",
    "taskhostw.exe": "Windows Task Host",
    "dwm.exe": "Desktop Window Manager",
    "sihost.exe": "Shell Infrastructure Host",
    "ctfmon.exe": "CTF Loader Service",
    "audiodg.exe": "Windows Audio Device Graph",
    "dllhost.exe": "COM Surrogate",
    "wmiprvse.exe": "WMI Provider Host",
    "securityhealthservice.exe": "Windows Security Service",
    "msmpeng.exe": "Microsoft Defender Antivirus",
    "applicationframehost.exe": "Windows App Frame Host",
    "systemsettings.exe": "Windows Settings",
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