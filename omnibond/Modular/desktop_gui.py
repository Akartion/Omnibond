#!/usr/bin/env python3
"""
OmniBond - Native Tkinter Studio Desktop GUI.
"""

from __future__ import annotations

import math
import os
import queue
import sys
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple
import urllib.parse

from adapter_manager import NetworkAdapter
from config import (
    ADAPTER_PALETTE,
    BLOCK_INTERNET_RULE,
    TURBO_APP_KEY,
    TURBO_APP_LABEL,
    filedialog,
    messagebox,
    tk,
)
from engine import OmniBondEngine
from process_mapper import ProcessInfo
from studio_widgets import StudioDropdown, StudioTooltip

# =====================================================================
# 10. NATIVE TKINTER STUDIO GUI (ALL 8 IMPROVEMENTS INTEGRATED)
# =====================================================================

class OmniBondDesktopGUI:
    BG_HAIRLINE = "#1e1e24"
    BG_PANEL = "#0b0b0e"
    BG_CARD = "#0e0e12"
    BG_CARD_HOVER = "#14141a"
    TEXT_MAIN = "#fafafa"
    TEXT_MUTED = "#a1a1aa"
    TEXT_DIM = "#52525b"
    AMBER = "#f59e0b"
    EMERALD = "#10b981"
    CYAN = "#38bdf8"

    def __init__(self, engine: OmniBondEngine):
        self.engine = engine
        self.root = tk.Tk()
        self.root.title("OmniBond")
        self.root.geometry("1360x880")
        self.root.minsize(1100, 740)
        self.root.configure(bg=self.BG_HAIRLINE)

        self.tooltip = StudioTooltip(self.root)
        self._hover_chart_x: Optional[int] = None
        self._peak_bps: float = 0.0
        self.graph_mode = "master"
        self.app_view_mode = "grid"
        self.app_filter_mode = "ALL"
        self.app_sort_mode = "AZ"
        self.dd_app = None
        self.dd_policy = None
        self.ent_custom_app: Optional[tk.Entry] = None
        self._process_dropdown_items: List[Dict[str, str]] = []
        self._policy_dropdown_items: List[Dict[str, str]] = []
        self._process_scan_queue: "queue.Queue[Tuple[Optional[List[ProcessInfo]], Optional[Exception]]]" = queue.Queue()
        self._process_scan_in_progress = False
        self._network_tuning_options = {"keep_multi_nic": True, "ipv4": True, "ipv6": False}
        self._app_filter_buttons: Dict[str, tk.Button] = {}
        self._app_filter_button_labels: Dict[str, str] = {}
        self._adapter_card_regions: List[Tuple[int, int, int, int, str]] = []
        self._app_card_regions: List[Tuple[int, int, int, int, str, str, int]] = []
        self._last_Hovered_region_desc: str = ""

        self._build_flush_layout()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._schedule_refresh()

    def _make_studio_btn(
        self,
        parent: tk.Widget,
        text: str,
        tooltip_title: str,
        tooltip_desc: str,
        variant: str = "dark",  # dark | primary | amber | cyan
        cmd: Optional[Callable] = None,
        px: int = 13,
        py: int = 6,
    ) -> tk.Button:
        palette = {
            "dark": ("#14141c", "#fafafa", "#272734", "#1f1f2c", "#f59e0b"),
            "primary": ("#fafafa", "#09090b", "#fafafa", "#f59e0b", "#f59e0b"),
            "amber": ("#f59e0b", "#09090b", "#f59e0b", "#fbbf24", "#fafafa"),
            "cyan": ("#082f49", "#38bdf8", "#0284c7", "#0c4a6e", "#38bdf8"),
        }
        bg, fg, bd_col, hov_bg, hov_bd = palette.get(variant, palette["dark"])

        btn = tk.Button(
            parent,
            text=text,
            bg=bg,
            fg=fg,
            activebackground=hov_bg,
            activeforeground=fg,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=1,
            highlightbackground=bd_col,
            padx=px,
            pady=py,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            command=cmd,
        )

        def on_enter(_e):
            btn.configure(bg=hov_bg, highlightbackground=hov_bd)

        def on_leave(_e):
            btn.configure(bg=bg, highlightbackground=bd_col)

        btn.bind("<Enter>", on_enter, add="+")
        btn.bind("<Leave>", on_leave, add="+")
        self.tooltip.bind_widget(btn, tooltip_title, tooltip_desc)
        return btn

    def _build_flush_layout(self):
        self.root.grid_columnconfigure(0, weight=10)
        self.root.grid_columnconfigure(1, weight=12)
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_rowconfigure(2, weight=0)

        # -----------------------------------------------------------------
        # CONTAINER 0: TOP BAR (Flush)
        # -----------------------------------------------------------------
        topbar = tk.Frame(self.root, bg=self.BG_PANEL, padx=18, pady=12)
        topbar.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=0, pady=(0, 1))

        brand_left = tk.Frame(topbar, bg=self.BG_PANEL)
        brand_left.pack(side=tk.LEFT)

        tk.Label(
            brand_left,
            text="OB",
            bg=self.AMBER,
            fg="#09090b",
            font=("Segoe UI", 10, "bold"),
            padx=6,
            pady=3,
        ).pack(side=tk.LEFT, padx=(0, 12))

        title_col = tk.Frame(brand_left, bg=self.BG_PANEL)
        title_col.pack(side=tk.LEFT)
        tk.Label(
            title_col,
            text="OmniBond",
            bg=self.BG_PANEL,
            fg=self.TEXT_MAIN,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_col,
            text=f"▪ HTTP/HTTPS 127.0.0.1:{self.engine.http_port}    ▪ SOCKS5 127.0.0.1:{self.engine.socks_port}    ▪ Web Dashboard 127.0.0.1:{self.engine.web_port}",
            bg=self.BG_PANEL,
            fg=self.TEXT_MUTED,
            font=("Consolas", 9),
        ).pack(anchor="w")

        actions_right = tk.Frame(topbar, bg=self.BG_PANEL)
        actions_right.pack(side=tk.RIGHT)

        self.btn_proxy = self._make_studio_btn(
            actions_right,
            "◈ Bonding: Off",
            "SYSTEM-WIDE BONDING PROXY",
            "Configures Windows Internet Settings (WinINet) so browsers, games, and desktop apps automatically bond and load-balance across your active network interfaces.",
            variant="primary",
            cmd=self._toggle_system_proxy,
            px=14,
        )
        self.btn_proxy.pack(side=tk.LEFT, padx=(0, 6))

        self._make_studio_btn(
            actions_right,
            "⚙ Network Tuning",
            "SIMULTANEOUS MULTI-NIC OPTIMIZER",
            "Choose whether to keep multiple adapters active and balance IPv4 and IPv6 routes.",
            variant="dark",
            cmd=self._show_network_tuning,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._make_studio_btn(
            actions_right,
            "🩹 Repair Network",
            "EMERGENCY NETWORK RESET & REPAIR",
            "Resets Windows system proxy to Direct, restores all interface metrics to automatic, and flushes the DNS cache.",
            variant="dark",
            cmd=self._repair_network_gui,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self.btn_graph_mode = self._make_studio_btn(
            actions_right,
            "∿ Master Speed",
            "MASTER OR BONDED SPEED",
            "Switch between all computer network traffic and traffic routed through OmniBond.",
            variant="dark",
            cmd=self._toggle_graph_mode,
        )
        self.btn_graph_mode.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_graph_mode.bind(
            "<Leave>",
            lambda _event: self._style_graph_mode_button(),
            add="+",
        )

        self._make_studio_btn(
            actions_right,
            "⟳ Rescan Adapters",
            "RESCAN NETWORK ADAPTERS",
            "Re-scan Windows network adapters and IPv4 addresses.",
            variant="dark",
            cmd=self._rescan_nics,
        ).pack(side=tk.LEFT)

        # -----------------------------------------------------------------
        # CONTAINER 1: 01 / HARDWARE INTERFACES & NON-OVERLAPPING CHART
        # -----------------------------------------------------------------
        c01 = tk.Frame(self.root, bg=self.BG_PANEL)
        c01.grid(row=1, column=0, sticky="nsew", padx=(0, 1), pady=(0, 1))
        c01.grid_columnconfigure(0, weight=1)
        c01.grid_rowconfigure(0, weight=0)
        c01.grid_rowconfigure(1, weight=0)
        c01.grid_rowconfigure(2, weight=1)

        c01_head = tk.Frame(c01, bg=self.BG_PANEL, padx=18, pady=11)
        c01_head.grid(row=0, column=0, sticky="ew")

        c01_titles = tk.Frame(c01_head, bg=self.BG_PANEL)
        c01_titles.pack(side=tk.LEFT)
        tk.Label(
            c01_titles,
            text="01 / HARDWARE INTERFACES · SOCKET BINDING",
            bg=self.BG_PANEL,
            fg=self.AMBER,
            font=("Consolas", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            c01_titles,
            text="Active Network Adapters",
            bg=self.BG_PANEL,
            fg=self.TEXT_MAIN,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", pady=(1, 0))

        self.lbl_adapter_count_meta = tk.Label(
            c01_head,
            text="0 / 0 INTERFACES BONDED · SYSTEM NIC",
            bg="#14141d",
            fg=self.TEXT_MUTED,
            font=("Consolas", 8, "bold"),
            padx=8,
            pady=4,
        )
        self.lbl_adapter_count_meta.pack(side=tk.RIGHT, anchor="s")

        adapter_scroll_frame = tk.Frame(c01, bg=self.BG_PANEL)
        adapter_scroll_frame.grid(row=1, column=0, sticky="ew")
        adapter_scroll_frame.grid_columnconfigure(0, weight=1)
        self.canvas_adapters = tk.Canvas(
            adapter_scroll_frame,
            height=172,
            bg=self.BG_PANEL,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.canvas_adapters.configure(height=172)
        self.canvas_adapters.grid(row=0, column=0, sticky="ew")
        self.adapter_hscroll = tk.Scrollbar(
            adapter_scroll_frame,
            orient=tk.HORIZONTAL,
            command=self.canvas_adapters.xview,
            width=8,
            bg="#3f3f46",
            troughcolor="#0c0c0f",
            activebackground="#52525b",
            bd=0,
            highlightthickness=0,
            relief=tk.FLAT,
        )
        self.adapter_hscroll.grid(row=1, column=0, sticky="ew")
        self.canvas_adapters.configure(xscrollcommand=self.adapter_hscroll.set)
        self.canvas_adapters.bind("<Button-1>", self._on_adapter_card_click)
        self.canvas_adapters.bind("<Shift-MouseWheel>", self._on_adapter_mousewheel)
        self.canvas_adapters.bind("<MouseWheel>", self._on_adapter_mousewheel)
        self.tooltip.bind_widget(
            self.canvas_adapters,
            "NETWORK ADAPTER BENTO CARDS",
            "Click any network adapter card to enable or disable it in the multi-network bonding pool.",
            delay_ms=550,
        )

        self.canvas_chart = tk.Canvas(
            c01,
            bg=self.BG_PANEL,
            highlightthickness=0,
            bd=0,
        )
        self.canvas_chart.grid(row=2, column=0, sticky="nsew")
        self.canvas_chart.bind("<Motion>", self._on_chart_hover)
        self.canvas_chart.bind("<Leave>", self._on_chart_leave)

        # -----------------------------------------------------------------
        # CONTAINER 2: 02 / APPLICATION ROUTER (MODERN DROPDOWN, FILTERS, SPARKLINES & FOCUS)
        # -----------------------------------------------------------------
        c02 = tk.Frame(self.root, bg=self.BG_PANEL)
        c02.grid(row=1, column=1, sticky="nsew", padx=0, pady=(0, 1))
        c02.grid_columnconfigure(0, weight=1)
        c02.grid_rowconfigure(0, weight=0)
        c02.grid_rowconfigure(1, weight=0)
        c02.grid_rowconfigure(2, weight=1)

        c02_head = tk.Frame(c02, bg=self.BG_PANEL, padx=18, pady=11)
        c02_head.grid(row=0, column=0, sticky="ew")

        c02_titles = tk.Frame(c02_head, bg=self.BG_PANEL)
        c02_titles.pack(side=tk.LEFT)
        tk.Label(
            c02_titles,
            text="02 / APPLICATION ROUTER · GETEXTENDEDTCPTABLE PID ENGINE",
            bg=self.BG_PANEL,
            fg=self.AMBER,
            font=("Consolas", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            c02_titles,
            text="Per-Application Network Pinning",
            bg=self.BG_PANEL,
            fg=self.TEXT_MAIN,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", pady=(1, 0))

        self.lbl_running_badge = tk.Label(
            c02_head,
            text="DETECTED RUNNING APPS",
            bg="#14141d",
            fg=self.TEXT_MUTED,
            font=("Consolas", 8, "bold"),
            padx=8,
            pady=4,
        )
        self.lbl_running_badge.pack(side=tk.RIGHT, anchor="s")

        # Group filters and view controls on the left, with Scan/Add on the right.
        toolbar = tk.Frame(c02, bg="#08080b", padx=16, pady=9)
        toolbar.grid(row=1, column=0, sticky="ew")
        toolbar_actions = tk.Frame(toolbar, bg="#08080b")
        toolbar_actions.pack(fill=tk.X)
        left_controls = tk.Frame(toolbar_actions, bg="#08080b")
        left_controls.pack(side=tk.LEFT)
        filters = tk.Frame(left_controls, bg="#08080b")
        filters.pack(side=tk.LEFT)
        for label, mode in (("ALL", "ALL"), ("APPS", "APPS"), ("SERVICES", "SERVICES"), ("FAVORITES", "FAVORITES")):
            button_text = f"✓ {label}" if mode == self.app_filter_mode else label
            filter_button = tk.Button(
                filters,
                text=button_text,
                bg=self.AMBER if mode == self.app_filter_mode else "#14141c",
                fg="#09090b" if mode == self.app_filter_mode else self.TEXT_MAIN,
                activebackground="#fbbf24",
                activeforeground="#09090b" if mode == self.app_filter_mode else self.TEXT_MAIN,
                relief=tk.FLAT,
                bd=0,
                highlightthickness=1,
                highlightbackground=self.AMBER if mode == self.app_filter_mode else "#272734",
                padx=8,
                pady=4,
                cursor="hand2",
                font=("Segoe UI", 9, "bold"),
                command=lambda selected=mode: self._set_app_filter(selected),
            )
            self._app_filter_buttons[mode] = filter_button
            self._app_filter_button_labels[mode] = label
            self.tooltip.bind_widget(
                filter_button,
                f"{mode} APPLICATION FILTER",
                "Filter the application cards by running state, pinned rule, or favorites.",
            )
            filter_button.pack(side=tk.LEFT, padx=(0, 4))

        self._make_studio_btn(
            left_controls,
            "▦ Grid",
            "GRID APPLICATION VIEW",
            "Show applications as a compact multi-column grid.",
            variant="dark",
            cmd=lambda: self._set_app_view("grid"),
            px=8,
            py=4,
        ).pack(side=tk.LEFT, padx=(8, 4))
        self._make_studio_btn(
            left_controls,
            "☷ List",
            "LIST APPLICATION VIEW",
            "Show applications in a full-width list.",
            variant="dark",
            cmd=lambda: self._set_app_view("list"),
            px=8,
            py=4,
        ).pack(side=tk.LEFT)
        self.dd_app_sort = StudioDropdown(
            left_controls,
            self.root,
            width_px=154,
            placeholder="Sort apps",
        )
        self.dd_app_sort.pack(side=tk.LEFT, padx=(8, 0))
        self.dd_app_sort.set_items([
            {"value": "AZ", "label": "Name: A-Z", "meta": "Alphabetical", "badge": "A–Z", "color": self.CYAN},
            {"value": "ZA", "label": "Name: Z-A", "meta": "Reverse alphabetical", "badge": "Z–A", "color": self.CYAN},
            {"value": "FAST", "label": "Speed: High–Low", "meta": "Most active first", "badge": "↑", "color": self.EMERALD},
            {"value": "SLOW", "label": "Speed: Low–High", "meta": "Least active first", "badge": "↓", "color": self.EMERALD},
        ])
        self.dd_app_sort.set_value(self.app_sort_mode, "Name: A-Z")
        self.dd_app_sort.on_select = self._set_app_sort
        self.tooltip.bind_widget(
            self.dd_app_sort,
            "SORT APPLICATIONS",
            "Sort by application name or current network speed.",
        )

        right_actions = tk.Frame(toolbar_actions, bg="#08080b")
        right_actions.pack(side=tk.RIGHT)
        self._make_studio_btn(
            right_actions,
            "+ Add Program",
            "ADD APPLICATION & ROUTING POLICY",
            "Choose a detected application or the built-in engine, select a routing policy, or browse for an executable.",
            variant="cyan",
            cmd=self._open_add_program_popup,
            px=10,
            py=4,
        ).pack(side=tk.RIGHT)
        self._make_studio_btn(
            right_actions,
            "↻ Scan",
            "SCAN RUNNING WINDOWS PROCESSES",
            "Refreshes active Windows processes, visible application windows, and open TCP sockets.",
            variant="dark",
            cmd=self._refresh_process_dropdown,
            px=9,
            py=4,
        ).pack(side=tk.RIGHT, padx=(0, 6))

        self.app_scroll_frame = tk.Frame(c02, bg=self.BG_PANEL)
        self.app_scroll_frame.grid(row=2, column=0, sticky="nsew")
        self.app_scroll_frame.grid_rowconfigure(0, weight=1)
        self.app_scroll_frame.grid_columnconfigure(0, weight=1)
        self.canvas_apps = tk.Canvas(
            self.app_scroll_frame,
            bg=self.BG_PANEL,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.canvas_apps.grid(row=0, column=0, sticky="nsew")
        self.app_vscroll = tk.Scrollbar(
            self.app_scroll_frame,
            orient=tk.VERTICAL,
            command=self.canvas_apps.yview,
            width=8,
            bg="#3f3f46",
            troughcolor="#0c0c0f",
            activebackground="#52525b",
            bd=0,
            highlightthickness=0,
            relief=tk.FLAT,
        )
        self.app_vscroll.grid(row=0, column=1, sticky="ns")
        self.canvas_apps.configure(
            yscrollcommand=self.app_vscroll.set,
            yscrollincrement=40,
        )
        self.canvas_apps.bind("<Button-1>", self._on_app_card_click)
        self.canvas_apps.bind("<Motion>", self._on_app_card_motion)
        self.canvas_apps.bind("<Leave>", lambda _e: self.tooltip.hide())
        self.canvas_apps.bind("<MouseWheel>", self._on_app_mousewheel)

        # -----------------------------------------------------------------
        # CONTAINER 3: 03 / UNIFIED URL BAR + GLOWING PROGRESS TRACK & BLOCK MATRIX
        # -----------------------------------------------------------------
        c03 = tk.Frame(self.root, bg=self.BG_PANEL, padx=18, pady=12)
        c03.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=0, pady=0)

        c03_top = tk.Frame(c03, bg=self.BG_PANEL)
        c03_top.pack(fill=tk.X, pady=(0, 6))

        c03_titles = tk.Frame(c03_top, bg=self.BG_PANEL)
        c03_titles.pack(side=tk.LEFT)
        tk.Label(
            c03_titles,
            text="03 / PARALLEL RANGE & HLS (.M3U8) ENGINE · ENDGAME RACING",
            bg=self.BG_PANEL,
            fg=self.AMBER,
            font=("Consolas", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            c03_titles,
            text="Download & Stream Accelerator",
            bg=self.BG_PANEL,
            fg=self.TEXT_MAIN,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", pady=(1, 0))

        self.lbl_dl_badge = tk.Label(
            c03_top,
            text="IDLE · 0.0 KB/s · 0%",
            bg="#14141d",
            fg=self.AMBER,
            font=("Consolas", 9, "bold"),
            padx=10,
            pady=4,
        )
        self.lbl_dl_badge.pack(side=tk.RIGHT, anchor="s")

        # Unified URL + Progress + Block Console Box
        console_box = tk.Frame(c03, bg=self.BG_PANEL, padx=0, pady=0)
        console_box.pack(fill=tk.X)

        url_bar_frame = tk.Frame(console_box, bg=self.BG_PANEL)
        url_bar_frame.pack(fill=tk.X)

        tk.Label(
            url_bar_frame,
            text=" STREAM / FILE URL ",
            bg="#161622",
            fg=self.AMBER,
            font=("Consolas", 8, "bold"),
            padx=8,
            pady=7,
        ).pack(side=tk.LEFT)

        self.ent_url = tk.Entry(
            url_bar_frame,
            bg="#0d0d14",
            fg=self.TEXT_MAIN,
            insertbackground=self.AMBER,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground="#222230",
            font=("Consolas", 10),
        )
        self.ent_url.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=6)
        self.tooltip.bind_widget(
            self.ent_url,
            "DIRECT FILE OR HLS (.M3U8) STREAM URL",
            "Paste any HTTP/HTTPS file link or .m3u8 video stream URL to split and accelerate across your active network adapters.",
        )

        self._make_studio_btn(
            url_bar_frame,
            "⬇ Download",
            "START MULTI-NIC PARALLEL DOWNLOAD",
            "Splits the target file into parallel byte-range blocks across your enabled network adapters with Endgame Backup Racing.",
            variant="primary",
            cmd=self._start_turbo_download,
            px=16,
            py=6,
        ).pack(side=tk.LEFT)

        # Integrated Glowing Progress Bar + Segmented Block Matrix Canvas
        self.canvas_dl_unified = tk.Canvas(
            console_box,
            height=46,
            bg="#07070a",
            highlightthickness=0,
            bd=0,
        )
        self.canvas_dl_unified.pack(fill=tk.X, pady=(8, 0))
        self.tooltip.bind_widget(
            self.canvas_dl_unified,
            "LIVE PROGRESS & MULTI-NIC BLOCK MATRIX",
            "Top bar shows overall download completion and live speed; bottom segments show individual blocks color-coded by the network adapter downloading them.",
            delay_ms=550,
        )

        self._refresh_process_dropdown()

    # -----------------------------------------------------------------
    # DROPDOWN & ACTION HANDLERS
    # -----------------------------------------------------------------

    def _refresh_process_dropdown(self):
        if self._process_scan_in_progress:
            return
        self._process_scan_in_progress = True

        def scan_processes():
            try:
                self._process_scan_queue.put((self.engine.scan_and_sync_processes(), None))
            except Exception as exc:
                self._process_scan_queue.put((None, exc))

        threading.Thread(
            target=scan_processes,
            name="omnibond-process-scan",
            daemon=True,
        ).start()

    def _apply_process_scan_result(self):
        try:
            detailed, error = self._process_scan_queue.get_nowait()
        except queue.Empty:
            return
        self._process_scan_in_progress = False
        if error:
            print(f"Could not refresh running applications: {error}", file=sys.stderr)
            return
        if detailed is None:
            return
        dd_items: List[Dict[str, str]] = [
            {
                "value": TURBO_APP_KEY,
                "label": TURBO_APP_LABEL,
                "meta": "Built-in Engine",
                "category": "USER APPS",
                "badge": "ENG",
                "color": self.AMBER,
                "is_pinned": self.engine.routing_mgr.get_rule(TURBO_APP_KEY) != "AUTO",
            }
        ]
        for p in detailed:
            if p.category == "USER APPS":
                badge, col = "APP", "#38bdf8"
            elif p.category == "ACTIVE NET":
                badge, col = "NET", "#34d399"
            else:
                badge, col = "BG", "#a1a1aa"

            meta_parts = [f"PID {p.pid}"]
            if p.window_title:
                meta_parts.append(p.window_title[:20])
            elif p.has_active_socket:
                meta_parts.append("Active Socket")

            dd_items.append({
                "value": p.exe_name,
                "label": p.exe_name,
                "meta": " · ".join(meta_parts),
                "category": p.category,
                "badge": badge,
                "color": col,
                "is_pinned": p.is_pinned or (self.engine.routing_mgr.get_rule(p.exe_name) != "AUTO"),
            })
        self._process_dropdown_items = dd_items
        if self.dd_app is not None and self.dd_app.winfo_exists():
            self.dd_app.set_items(dd_items)

    def _refresh_policy_dropdown(self, adapters: List[NetworkAdapter]):
        pol_items: List[Dict[str, str]] = [
            {
                "value": "AUTO",
                "label": "Auto / Bonded (All NICs)",
                "meta": "Load Balanced",
                "badge": "ALL",
                "color": self.EMERALD,
            },
            {
                "value": BLOCK_INTERNET_RULE,
                "label": "Block Internet",
                "meta": "Disable network access",
                "badge": "BLOCK",
                "color": "#ef4444",
            }
        ]
        for idx, a in enumerate(adapters):
            pol_items.append({
                "value": a.ip,
                "label": f"{idx + 1:02d} · {a.name} ({a.ip})",
                "meta": a.kind,
                "badge": f"#{idx + 1:02d}",
                "color": a.color,
            })
        self._policy_dropdown_items = pol_items
        if self.dd_policy is not None and self.dd_policy.winfo_exists():
            self.dd_policy.set_items(pol_items)

    def _assign_app_rule(self):
        if self.dd_app is None or self.dd_policy is None:
            return False
        custom_name = self.ent_custom_app.get().strip() if self.ent_custom_app else ""
        app_val = custom_name or self.dd_app.get_value().strip()
        if not app_val:
            return False
        target_ip = self.dd_policy.get_value().strip() or "AUTO"
        self.engine.routing_mgr.set_rule(app_val, target_ip, explicit_add=True)
        self._update_ui()
        return True

    def _open_add_program_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("Add application")
        popup.configure(bg=self.BG_PANEL)
        popup.resizable(False, False)
        popup.transient(self.root)
        popup.grab_set()
        popup.geometry(f"510x370+{self.root.winfo_rootx() + 220}+{self.root.winfo_rooty() + 180}")

        def close_popup():
            self.dd_app = None
            self.dd_policy = None
            self.ent_custom_app = None
            popup.destroy()

        popup.protocol(
            "WM_DELETE_WINDOW",
            close_popup,
        )

        body = tk.Frame(popup, bg=self.BG_PANEL, padx=18, pady=16)
        body.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            body, text="ADD APPLICATION TO OMNIBOND", bg=self.BG_PANEL,
            fg=self.AMBER, font=("Consolas", 9, "bold"),
        ).pack(anchor="w", pady=(0, 12))
        tk.Label(
            body, text="Engine / application", bg=self.BG_PANEL,
            fg=self.TEXT_MUTED, font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        self.dd_app = StudioDropdown(
            body, self.root, width_px=460,
            categories=["ALL", "USER APPS", "ACTIVE NET", "PINNED", "SERVICES / BG"],
            placeholder="Select a running application...",
        )
        self.dd_app.pack(fill=tk.X, pady=(5, 12))
        self.dd_app.set_items(self._process_dropdown_items)

        tk.Label(
            body, text="Or enter an executable name", bg=self.BG_PANEL,
            fg=self.TEXT_MUTED, font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        self.ent_custom_app = tk.Entry(
            body,
            bg="#0d0d14",
            fg=self.TEXT_MAIN,
            insertbackground=self.AMBER,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground="#222230",
            font=("Consolas", 10),
        )
        self.ent_custom_app.pack(fill=tk.X, pady=(5, 12), ipady=5)

        tk.Label(
            body, text="Network policy", bg=self.BG_PANEL,
            fg=self.TEXT_MUTED, font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        self.dd_policy = StudioDropdown(
            body, self.root, width_px=460, categories=[],
            placeholder="Auto / Bonded",
        )
        self.dd_policy.pack(fill=tk.X, pady=(5, 12))
        self.dd_policy.set_items(self._policy_dropdown_items)

        actions = tk.Frame(body, bg=self.BG_PANEL)
        actions.pack(fill=tk.X, side=tk.BOTTOM)
        self._make_studio_btn(
            actions, "Cancel", "CLOSE", "Close without adding an application.",
            variant="dark",
            cmd=close_popup,
            px=10, py=5,
        ).pack(side=tk.RIGHT, padx=(6, 0))
        self._make_studio_btn(
            actions, "Add & Apply Policy", "ADD APPLICATION AND APPLY POLICY",
            "Save the selected application with the chosen adapter policy.",
            variant="amber", cmd=lambda: self._assign_app_rule_and_close(popup), px=10, py=5,
        ).pack(side=tk.RIGHT)

    def _assign_app_rule_and_close(self, popup: tk.Toplevel):
        if self._assign_app_rule():
            self.dd_app = None
            self.dd_policy = None
            self.ent_custom_app = None
            popup.destroy()

    def _choose_app_location(self, app_name: str):
        is_folder = messagebox.askyesno(
            "Program Location",
            "Choose an installation folder?\n\nSelect No to choose the executable file.",
        )
        if is_folder:
            location = filedialog.askdirectory(title=f"Choose the installation folder for {app_name}")
        else:
            location = filedialog.askopenfilename(
                title=f"Choose the executable for {app_name}",
                filetypes=[("Executable Programs", "*.exe"), ("All Files", "*.*")],
            )
        if not location:
            return
        key = self.engine.process_mapper.register_custom_app_location(app_name, location)
        if not key:
            messagebox.showwarning("Program Location", "The selected path could not be saved.")
            return
        self.engine.routing_mgr.set_rule(key, self.engine.routing_mgr.get_rule(key), explicit_add=True)
        self._refresh_process_dropdown()
        self._update_ui()

    def _set_app_view(self, mode: str):
        self.app_view_mode = "list" if mode == "list" else "grid"
        self.canvas_apps.yview_moveto(0)
        self._draw_app_bento_cards(
            self._sort_app_entries(self._filter_app_entries(self.engine.routing_mgr.get_all_entries(only_running_or_added=True))),
            self.engine.adapter_mgr.get_adapters(),
        )

    def _set_app_filter(self, mode: str):
        self.app_filter_mode = mode
        for filter_mode, button in self._app_filter_buttons.items():
            label = self._app_filter_button_labels[filter_mode]
            active = filter_mode == mode
            button.configure(text=f"✓ {label}" if filter_mode == mode else label)
            button.configure(
                bg=self.AMBER if active else "#14141c",
                fg="#09090b" if active else self.TEXT_MAIN,
                activeforeground="#09090b" if active else self.TEXT_MAIN,
                highlightbackground=self.AMBER if active else "#272734",
            )
        self._update_ui()

    def _set_app_sort(self, mode: str):
        self.app_sort_mode = mode if mode in ("AZ", "ZA", "FAST", "SLOW") else "AZ"
        label = {
            "AZ": "Name: A-Z",
            "ZA": "Name: Z-A",
            "FAST": "Speed: High–Low",
            "SLOW": "Speed: Low–High",
        }[self.app_sort_mode]
        self.dd_app_sort.set_value(self.app_sort_mode, label)
        self._update_ui()

    def _sort_app_entries(self, entries: List[Dict]) -> List[Dict]:
        if self.app_sort_mode == "ZA":
            return sorted(entries, key=lambda entry: entry["display_name"].casefold(), reverse=True)
        if self.app_sort_mode == "FAST":
            return sorted(entries, key=lambda entry: (-entry.get("bps", 0), entry["display_name"].casefold()))
        if self.app_sort_mode == "SLOW":
            return sorted(entries, key=lambda entry: (entry.get("bps", 0), entry["display_name"].casefold()))
        return sorted(entries, key=lambda entry: entry["display_name"].casefold())

    def _show_card_policy_menu(self, app_key: str, screen_x: int, screen_y: int):
        selected = self.engine.routing_mgr.get_rule(app_key)
        menu = tk.Menu(
            self.root,
            tearoff=False,
            bg="#0d0d12",
            fg=self.TEXT_MAIN,
            font=("Segoe UI", 9),
            activebackground=self.AMBER,
            activeforeground="#09090b",
            activeborderwidth=0,
            borderwidth=1,
            relief=tk.FLAT,
        )
        options = [
            ("AUTO", "Auto / Bonded (All NICs)"),
            (BLOCK_INTERNET_RULE, "Block Internet"),
        ]
        options.extend(
            (adapter.ip, f"{adapter.name} ({adapter.ip})")
            for adapter in self.engine.adapter_mgr.get_adapters()
        )
        for value, label in options:
            menu.add_command(
                label=("✓ " if value == selected else "  ") + label,
                command=lambda chosen=value: self._select_card_policy(app_key, chosen),
            )
        menu.tk_popup(screen_x, screen_y)

    def _select_card_policy(self, app_key: str, policy: str):
        self.engine.routing_mgr.set_rule(app_key, policy, explicit_add=True)
        self._update_ui()

    def _filter_app_entries(self, entries: List[Dict]) -> List[Dict]:
        if self.app_filter_mode == "APPS":
            return [
                entry for entry in entries
                if entry.get("is_running")
                and not entry.get("is_builtin")
                and entry.get("category") != "SERVICES / BG"
            ]
        if self.app_filter_mode == "SERVICES":
            return [
                entry for entry in entries
                if entry.get("is_running") and entry.get("category") == "SERVICES / BG"
            ]
        if self.app_filter_mode == "FAVORITES":
            return [entry for entry in entries if entry.get("is_favorite")]
        return entries

    def _on_app_mousewheel(self, event):
        self.canvas_apps.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_adapter_mousewheel(self, event):
        self.canvas_adapters.xview_scroll(int(-1 * (event.delta / 120)), "units")

    def _rescan_nics(self):
        self.engine.adapter_mgr.refresh_adapters()
        self._update_ui()

    def _on_chart_hover(self, event):
        self._hover_chart_x = event.x
        self._draw_google_chart(self.engine.adapter_mgr.get_adapters())

    def _on_chart_leave(self, _event):
        self._hover_chart_x = None
        self._draw_google_chart(self.engine.adapter_mgr.get_adapters())

    def _on_adapter_card_click(self, event):
        canvas_x = self.canvas_adapters.canvasx(event.x)
        canvas_y = self.canvas_adapters.canvasy(event.y)
        for x0, y0, x1, y1, ip in self._adapter_card_regions:
            if x0 <= canvas_x <= x1 and y0 <= canvas_y <= y1:
                ad = self.engine.adapter_mgr.adapters.get(ip)
                if ad:
                    if self.engine.adapter_mgr.is_quota_exceeded(ad):
                        return
                    ad.enabled = not ad.enabled
                    self._update_ui()
                break

    def _on_app_card_motion(self, event):
        canvas_x = self.canvas_apps.canvasx(event.x)
        canvas_y = self.canvas_apps.canvasy(event.y)
        for x0, y0, x1, y1, rtype, app_key, _pid in self._app_card_regions:
            if x0 <= canvas_x <= x1 and y0 <= canvas_y <= y1:
                desc_key = f"{rtype}:{app_key}"
                if desc_key != self._last_Hovered_region_desc:
                    self._last_Hovered_region_desc = desc_key
                    if rtype == "focus":
                        self.tooltip.schedule(
                            f"FOCUS {app_key.upper()}\nBrings the running {app_key} window to the foreground.",
                            delay_ms=280,
                        )
                    elif rtype == "favorite":
                        self.tooltip.schedule(
                            f"TOGGLE FAVORITE ({app_key.upper()})\nFavorites stay visible and sort ahead of other application cards.",
                            delay_ms=280,
                        )
                    elif rtype == "location":
                        self.tooltip.schedule(
                            f"OPEN LOCATION ({app_key.upper()})\nOpens this application's executable in Explorer or its saved installation folder.",
                            delay_ms=280,
                        )
                    elif rtype == "policy":
                        self.tooltip.schedule(
                            f"SELECT ROUTING POLICY ({app_key.upper()})\nChoose a policy to apply it to this application.",
                            delay_ms=350,
                        )
                return
        self._last_Hovered_region_desc = ""
        self.tooltip.hide()

    def _on_app_card_click(self, event):
        canvas_x = self.canvas_apps.canvasx(event.x)
        canvas_y = self.canvas_apps.canvasy(event.y)
        for x0, y0, x1, y1, rtype, app_key, last_pid in self._app_card_regions:
            if x0 <= canvas_x <= x1 and y0 <= canvas_y <= y1:
                if rtype == "focus":
                    ok, msg = self.engine.process_mapper.focus_or_locate_app(app_key, last_pid)
                    if not ok:
                        messagebox.showinfo("Focus Program", msg)
                    return
                if rtype == "location":
                    ok, msg = self.engine.process_mapper.locate_app(app_key, last_pid)
                    if not ok:
                        if messagebox.askyesno("Program Location", f"{msg}\n\nChoose an executable or installation folder now?"):
                            self._choose_app_location(app_key)
                        else:
                            messagebox.showinfo("Program Location", msg)
                    return
                if rtype == "favorite":
                    saved = self.engine.routing_mgr.set_favorite(
                        app_key, not self.engine.routing_mgr.is_favorite(app_key)
                    )
                    if not saved:
                        messagebox.showwarning("Favorites", "Could not save this favorite setting.")
                    self._update_ui()
                    return
                if rtype == "policy":
                    self._show_card_policy_menu(app_key, event.x_root, event.y_root)
                    return

    def _toggle_system_proxy(self):
        new_state = not self.engine.sys_opt.system_proxy_enabled
        ok, msg = self.engine.sys_opt.set_system_proxy(new_state, "127.0.0.1", self.engine.http_port)
        if not ok:
            messagebox.showwarning("OmniBond", msg)
        self._update_ui()

    def _repair_network_gui(self):
        ok, msg = self.engine.sys_opt.repair_network()
        self._update_ui()
        messagebox.showinfo("Network Repaired", msg)

    def _show_network_tuning(self):
        window = tk.Toplevel(self.root)
        window.title("Network Tuning")
        window.configure(bg=self.BG_PANEL)
        window.geometry("820x720")
        window.minsize(680, 520)
        window.transient(self.root)
        window.grab_set()

        panel = tk.Frame(window, bg=self.BG_PANEL, padx=20, pady=16)
        panel.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            panel,
            text="NETWORK TUNING",
            bg=self.BG_PANEL,
            fg=self.AMBER,
            font=("Consolas", 10, "bold"),
        ).pack(anchor="w")
        tk.Label(
            panel,
            text="Choose which Windows network optimizations to apply.",
            bg=self.BG_PANEL,
            fg=self.TEXT_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(4, 12))

        options = {
            "keep_multi_nic": tk.BooleanVar(value=self._network_tuning_options["keep_multi_nic"]),
            "ipv4": tk.BooleanVar(value=self._network_tuning_options["ipv4"]),
            "ipv6": tk.BooleanVar(value=self._network_tuning_options["ipv6"]),
        }
        labels = (
            ("keep_multi_nic", "Keep multiple network adapters active"),
            ("ipv4", "Balance IPv4 interface routes"),
            ("ipv6", "Balance IPv6 interface routes"),
        )
        for key, label in labels:
            tk.Checkbutton(
                panel,
                text=label,
                variable=options[key],
                bg=self.BG_PANEL,
                fg=self.TEXT_MAIN,
                activebackground=self.BG_PANEL,
                activeforeground=self.TEXT_MAIN,
                selectcolor="#14141c",
                font=("Segoe UI", 9),
                anchor="w",
                padx=4,
            ).pack(fill=tk.X, pady=4)

        optimization_status = tk.Label(
            panel,
            text="",
            bg=self.BG_PANEL,
            fg=self.TEXT_MUTED,
            font=("Consolas", 8),
            justify=tk.LEFT,
            wraplength=760,
        )
        optimization_status.pack(fill=tk.X, pady=(8, 8))

        tk.Label(
            panel,
            text="PER-ADAPTER DATA & SPEED LIMITS",
            bg=self.BG_PANEL,
            fg=self.AMBER,
            font=("Consolas", 9, "bold"),
        ).pack(anchor="w", pady=(6, 4))
        tk.Label(
            panel,
            text=(
                "Data caps count all adapter traffic and exclude the adapter from new OmniBond "
                "connections when reached. Custom speed limits apply to OmniBond-routed traffic."
            ),
            bg=self.BG_PANEL,
            fg=self.TEXT_MUTED,
            font=("Segoe UI", 8),
            justify=tk.LEFT,
            wraplength=760,
        ).pack(fill=tk.X, pady=(0, 8))

        limits_frame = tk.Frame(panel, bg=self.BG_PANEL)
        limits_frame.pack(fill=tk.BOTH, expand=True)
        limits_frame.grid_rowconfigure(0, weight=1)
        limits_frame.grid_columnconfigure(0, weight=1)
        limits_canvas = tk.Canvas(
            limits_frame,
            bg=self.BG_PANEL,
            highlightthickness=0,
            bd=0,
        )
        limits_canvas.grid(row=0, column=0, sticky="nsew")
        limits_scrollbar = tk.Scrollbar(
            limits_frame,
            orient=tk.VERTICAL,
            command=limits_canvas.yview,
            width=8,
            bg="#3f3f46",
            troughcolor="#0c0c0f",
            activebackground="#52525b",
            bd=0,
            highlightthickness=0,
            relief=tk.FLAT,
        )
        limits_scrollbar.grid(row=0, column=1, sticky="ns")
        limits_canvas.configure(yscrollcommand=limits_scrollbar.set)
        limits_content = tk.Frame(limits_canvas, bg=self.BG_PANEL)
        limits_window_id = limits_canvas.create_window(
            (0, 0), window=limits_content, anchor="nw"
        )
        limits_content.bind(
            "<Configure>",
            lambda _event: limits_canvas.configure(
                scrollregion=limits_canvas.bbox("all")
            ),
        )
        limits_canvas.bind(
            "<Configure>",
            lambda event: limits_canvas.itemconfigure(limits_window_id, width=event.width),
        )
        limits_canvas.bind(
            "<MouseWheel>",
            lambda event: limits_canvas.yview_scroll(int(-event.delta / 120), "units"),
        )

        adapters = self.engine.adapter_mgr.get_adapters()
        if not adapters:
            tk.Label(
                limits_content,
                text="No network adapters are currently available.",
                bg=self.BG_PANEL,
                fg=self.TEXT_MUTED,
                font=("Segoe UI", 9),
                padx=12,
                pady=16,
            ).pack(fill=tk.X)

        def add_dropdown(parent, variable, values, width=12, command=None):
            dropdown = tk.OptionMenu(parent, variable, *values, command=command)
            dropdown.configure(
                bg="#09090d",
                fg=self.TEXT_MAIN,
                activebackground="#1f1f2c",
                activeforeground=self.TEXT_MAIN,
                highlightthickness=1,
                highlightbackground="#30303b",
                relief=tk.FLAT,
                bd=0,
                width=width,
                font=("Consolas", 8),
                anchor="w",
            )
            dropdown["menu"].configure(
                bg="#101016",
                fg=self.TEXT_MAIN,
                activebackground="#292932",
                activeforeground=self.TEXT_MAIN,
                font=("Segoe UI", 9),
                bd=0,
            )
            return dropdown

        for adapter in adapters:
            snapshot = self.engine.adapter_mgr.get_adapter_limit_snapshot(adapter)
            card = tk.Frame(
                limits_content,
                bg="#101016",
                highlightthickness=1,
                highlightbackground=self.BG_HAIRLINE,
                padx=12,
                pady=10,
            )
            card.pack(fill=tk.X, pady=(0, 6))
            tk.Label(
                card,
                text=f"{adapter.name}  ·  {adapter.kind}",
                bg="#101016",
                fg=self.TEXT_MAIN,
                font=("Segoe UI", 10, "bold"),
            ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

            cycle_hours = snapshot["cycle_hours"]
            if cycle_hours >= 24 and abs(cycle_hours % 24) < 0.0001:
                cycle_unit, cycle_value = "days", cycle_hours / 24
            elif cycle_hours < 1:
                cycle_unit, cycle_value = "minutes", round(cycle_hours * 60)
            else:
                cycle_unit, cycle_value = "hours", cycle_hours

            def add_field(parent, title, row, column):
                cell = tk.Frame(parent, bg="#101016")
                cell.grid(
                    row=row,
                    column=column,
                    sticky="ew",
                    padx=(0, 8) if column == 0 else (8, 0),
                    pady=4,
                )
                tk.Label(
                    cell,
                    text=title,
                    bg="#101016",
                    fg=self.TEXT_MUTED,
                    font=("Consolas", 8, "bold"),
                ).pack(anchor="w", pady=(0, 3))
                return cell

            card.grid_columnconfigure(0, weight=1)
            card.grid_columnconfigure(1, weight=1)

            data_cell = add_field(card, "DATA CAP", 1, 0)
            data_mode = tk.StringVar(
                value="Custom" if snapshot["data_limit_bytes"] else "Unlimited"
            )
            data_mode_wrap = tk.Frame(data_cell, bg="#101016")
            data_mode_wrap.pack(fill=tk.X)
            data_entry = tk.Entry(
                data_mode_wrap,
                bg="#09090d",
                fg=self.TEXT_MAIN,
                insertbackground=self.AMBER,
                disabledbackground="#09090d",
                disabledforeground=self.TEXT_MUTED,
                relief=tk.FLAT,
                highlightthickness=1,
                highlightbackground="#30303b",
                font=("Consolas", 9),
            )
            if snapshot["data_limit_bytes"]:
                data_entry.insert(0, f"{snapshot['data_limit_bytes'] / 1_000_000_000:.3f}")
            else:
                data_entry.configure(state=tk.DISABLED)
            data_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
            data_mode_menu = add_dropdown(
                data_mode_wrap,
                data_mode,
                ("Unlimited", "Custom"),
                width=10,
                command=lambda choice, entry=data_entry: entry.configure(
                    state=tk.NORMAL if choice == "Custom" else tk.DISABLED
                ),
            )
            data_mode_menu.pack(side=tk.RIGHT, padx=(5, 0))

            cycle_cell = add_field(card, "RESET WINDOW", 1, 1)
            cycle_wrap = tk.Frame(cycle_cell, bg="#101016")
            cycle_wrap.pack(fill=tk.X)
            cycle_entry = tk.Entry(
                cycle_wrap,
                bg="#09090d",
                fg=self.TEXT_MAIN,
                insertbackground=self.AMBER,
                relief=tk.FLAT,
                highlightthickness=1,
                highlightbackground="#30303b",
                font=("Consolas", 9),
                width=10,
            )
            cycle_entry.insert(0, f"{cycle_value:g}")
            cycle_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
            cycle_unit_var = tk.StringVar(value=cycle_unit)
            add_dropdown(
                cycle_wrap,
                cycle_unit_var,
                ("minutes", "hours", "days"),
                width=9,
            ).pack(side=tk.RIGHT, padx=(5, 0))

            def add_speed_field(title, row, initial_value):
                cell = add_field(card, title, row, 0)
                mode = tk.StringVar(
                    value="Custom" if initial_value > 0 else "Unlimited"
                )
                wrap = tk.Frame(cell, bg="#101016")
                wrap.pack(fill=tk.X)
                value_entry = tk.Entry(
                    wrap,
                    bg="#09090d",
                    fg=self.TEXT_MAIN,
                    insertbackground=self.AMBER,
                    disabledbackground="#09090d",
                    disabledforeground=self.TEXT_MUTED,
                    relief=tk.FLAT,
                    highlightthickness=1,
                    highlightbackground="#30303b",
                    font=("Consolas", 9),
                )
                if initial_value > 0:
                    value_entry.insert(0, f"{initial_value:g}")
                else:
                    value_entry.configure(state=tk.DISABLED)
                value_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
                mode_menu = add_dropdown(
                    wrap,
                    mode,
                    ("Unlimited", "Custom"),
                    width=10,
                    command=lambda choice, entry=value_entry: entry.configure(
                        state=tk.NORMAL if choice == "Custom" else tk.DISABLED
                    ),
                )
                mode_menu.pack(side=tk.RIGHT, padx=(5, 0))
                return mode, value_entry

            download_mode, download_entry = add_speed_field(
                "DOWNLOAD LIMIT (Mbps)", 2, snapshot["download_limit_mbps"]
            )
            upload_cell = add_field(card, "UPLOAD LIMIT (Mbps)", 2, 1)
            upload_mode = tk.StringVar(
                value="Custom" if snapshot["upload_limit_mbps"] > 0 else "Unlimited"
            )
            upload_wrap = tk.Frame(upload_cell, bg="#101016")
            upload_wrap.pack(fill=tk.X)
            upload_entry = tk.Entry(
                upload_wrap,
                bg="#09090d",
                fg=self.TEXT_MAIN,
                insertbackground=self.AMBER,
                disabledbackground="#09090d",
                disabledforeground=self.TEXT_MUTED,
                relief=tk.FLAT,
                highlightthickness=1,
                highlightbackground="#30303b",
                font=("Consolas", 9),
            )
            if snapshot["upload_limit_mbps"] > 0:
                upload_entry.insert(0, f"{snapshot['upload_limit_mbps']:g}")
            else:
                upload_entry.configure(state=tk.DISABLED)
            upload_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
            add_dropdown(
                upload_wrap,
                upload_mode,
                ("Unlimited", "Custom"),
                width=10,
                command=lambda choice, entry=upload_entry: entry.configure(
                    state=tk.NORMAL if choice == "Custom" else tk.DISABLED
                ),
            ).pack(side=tk.RIGHT, padx=(5, 0))

            reset_at = time.strftime(
                "%Y-%m-%d %H:%M",
                time.localtime(snapshot["period_started_at"] + cycle_hours * 3600),
            )
            current_cap = (
                self._fmt_bytes(snapshot["data_limit_bytes"])
                if snapshot["data_limit_bytes"] else "No data cap"
            )
            status_text = (
                "LIMIT REACHED · excluded from new OmniBond connections"
                if snapshot["quota_exceeded"]
                else (
                    f"{self._fmt_bytes(snapshot['usage_bytes'])} / {current_cap} · "
                    f"window resets {reset_at}"
                )
            )
            status_label = tk.Label(
                card,
                text=status_text,
                bg="#101016",
                fg="#f87171" if snapshot["quota_exceeded"] else self.TEXT_MUTED,
                font=("Consolas", 8),
                justify=tk.LEFT,
                anchor="w",
            )
            status_label.grid(row=3, column=0, sticky="ew", pady=(5, 0))

            def save_limits(
                adapter_name=adapter.name,
                status=status_label,
                data_mode_var=data_mode,
                data_field=data_entry,
                cycle_field=cycle_entry,
                unit_var=cycle_unit_var,
                download_mode_var=download_mode,
                download_field=download_entry,
                upload_mode_var=upload_mode,
                upload_field=upload_entry,
            ):
                try:
                    cycle_value_num = float(cycle_field.get().strip())
                    if cycle_value_num <= 0:
                        raise ValueError("Reset window must be greater than zero.")
                    cycle_unit_value = unit_var.get()
                    cycle_multiplier = {
                        "minutes": 1 / 60,
                        "hours": 1,
                        "days": 24,
                    }[cycle_unit_value]
                    data_gb = 0.0
                    if data_mode_var.get() == "Custom":
                        data_gb = float(data_field.get().strip())
                        if data_gb <= 0:
                            raise ValueError("Enter a data cap greater than zero, or choose Unlimited.")
                    download_mbps = 0.0
                    if download_mode_var.get() == "Custom":
                        download_mbps = float(download_field.get().strip())
                        if download_mbps <= 0:
                            raise ValueError("Enter a download limit greater than zero, or choose Unlimited.")
                    upload_mbps = 0.0
                    if upload_mode_var.get() == "Custom":
                        upload_mbps = float(upload_field.get().strip())
                        if upload_mbps <= 0:
                            raise ValueError("Enter an upload limit greater than zero, or choose Unlimited.")
                except ValueError as exc:
                    status.configure(text=str(exc), fg="#f87171")
                    return

                ok, message = self.engine.adapter_mgr.configure_adapter_limits(
                    adapter_name,
                    data_gb,
                    cycle_value_num * cycle_multiplier,
                    download_mbps,
                    upload_mbps,
                )
                status.configure(
                    text=message,
                    fg="#34d399" if ok else "#f87171",
                )
                if ok:
                    self._update_ui()

            self._make_studio_btn(
                card,
                "Save Limits",
                "SAVE ADAPTER DATA AND SPEED LIMITS",
                "Apply the data cap, reset window, and OmniBond upload/download speed limits.",
                variant="amber",
                cmd=save_limits,
                px=9,
                py=4,
            ).grid(row=3, column=1, sticky="e", pady=(4, 0))

        actions = tk.Frame(panel, bg=self.BG_PANEL)
        actions.pack(fill=tk.X, pady=(8, 0))
        self._make_studio_btn(
            actions,
            "Close",
            "CLOSE NETWORK TUNING",
            "Close without applying changes.",
            variant="dark",
            cmd=window.destroy,
            px=12,
            py=6,
        ).pack(side=tk.RIGHT, padx=(6, 0))

        def apply_options():
            selected = {key: variable.get() for key, variable in options.items()}
            ok, msg = self.engine.sys_opt.optimize_multi_nic(
                keep_multi_nic=selected["keep_multi_nic"],
                optimize_ipv4=selected["ipv4"],
                optimize_ipv6=selected["ipv6"],
            )
            if ok:
                self._network_tuning_options.update(selected)
            optimization_status.configure(
                text=msg,
                fg="#34d399" if ok else "#f87171",
            )

        self._make_studio_btn(
            actions,
            "Apply Settings",
            "APPLY NETWORK TUNING",
            "Apply the selected Windows multi-network, IPv4, and IPv6 route settings.",
            variant="amber",
            cmd=apply_options,
            px=12,
            py=6,
        ).pack(side=tk.RIGHT)

    def _start_turbo_download(self):
        url = self.ent_url.get().strip()
        if not url:
            return
        fname = os.path.basename(urllib.parse.urlsplit(url).path) or "omnibond_download.bin"
        out = os.path.join(os.path.expanduser("~"), "Downloads", fname)
        threading.Thread(target=self.engine.turbo.download_url, args=(url, out), daemon=True).start()

    @staticmethod
    def _fmt_bytes(num: float) -> str:
        if num <= 0:
            return "0 B"
        if num < 1024:
            return f"{int(num)} B"
        if num < 1048576:
            return f"{num / 1024:.1f} KB"
        if num < 1073741824:
            return f"{num / 1048576:.2f} MB"
        return f"{num / 1073741824:.2f} GB"

    @classmethod
    def _fmt_speed(cls, bps: float) -> str:
        if bps < 1:
            return "0.0 KB/s"
        if bps < 1048576:
            return f"{bps / 1024:.1f} KB/s"
        return f"{bps / 1048576:.2f} MB/s"

    @staticmethod
    def _adapter_speed(adapter: NetworkAdapter, graph_mode: str) -> float:
        return adapter.system_current_bps if graph_mode == "master" else adapter.current_bps

    @staticmethod
    def _adapter_speed_history(adapter: NetworkAdapter, graph_mode: str) -> List[float]:
        return adapter.system_bps_history if graph_mode == "master" else adapter.bps_history

    @staticmethod
    def _adapter_traffic_bytes(adapter: NetworkAdapter, graph_mode: str) -> int:
        if graph_mode == "master":
            return adapter.system_bytes_recv + adapter.system_bytes_sent
        return adapter.bytes_recv + adapter.bytes_sent

    def _toggle_graph_mode(self):
        self.graph_mode = "bonded" if self.graph_mode == "master" else "master"
        self._peak_bps = 0.0
        self._style_graph_mode_button()
        self._update_ui()

    def _style_graph_mode_button(self):
        master = self.graph_mode == "master"
        self.btn_graph_mode.configure(
            text="∿ Master Speed" if master else "⇄ Bonded Speed",
            fg=self.TEXT_MAIN if master else self.AMBER,
            highlightbackground="#272734" if master else self.AMBER,
        )

    # -----------------------------------------------------------------
    # 01: ADAPTER BENTO CARDS
    # -----------------------------------------------------------------

    def _draw_adapter_bento_cards(self, adapters: List[NetworkAdapter]):
        c = self.canvas_adapters
        c.delete("all")
        self._adapter_card_regions.clear()

        w = max(280, c.winfo_width())
        h = max(168, c.winfo_height())
        visible_cols = max(1, min(3, len(adapters)))
        cell_w = max(260, w / visible_cols)
        content_w = max(w, int(cell_w * len(adapters)))

        c.create_line(0, 0, content_w, 0, fill=self.BG_HAIRLINE)
        c.create_line(0, h - 1, content_w, h - 1, fill=self.BG_HAIRLINE)

        for idx, a in enumerate(adapters):
            x0 = int(idx * cell_w)
            x1 = int((idx + 1) * cell_w)
            y0, y1 = 1, h - 1
            self._adapter_card_regions.append((x0, y0, x1, y1, a.ip))

            if idx > 0:
                c.create_line(x0, 0, x0, h, fill=self.BG_HAIRLINE)

            pad_x = x0 + 15
            c.create_rectangle(pad_x, 12, pad_x + 24, 29, fill=a.color, outline="")
            c.create_text(pad_x + 12, 20, text=f"{idx + 1:02d}", fill="#09090b", font=("Consolas", 9, "bold"))
            c.create_text(
                x1 - 12, 20,
                text=f"IPV4 · {a.ip} ↗",
                fill=self.TEXT_MUTED,
                anchor="e",
                font=("Consolas", 8),
            )

            c.create_rectangle(pad_x, 38, pad_x + 34, 72, fill=a.badge_bg, outline="")
            c.create_text(
                pad_x + 17, 55,
                text=a.kind[:2].upper(),
                fill="#ffffff",
                font=("Segoe UI", 9, "bold"),
            )

            short_name = a.name if len(a.name) <= 16 else a.name[:14] + ".."
            c.create_text(
                pad_x + 44, 47,
                text=short_name,
                fill=self.TEXT_MAIN,
                anchor="w",
                font=("Segoe UI", 10, "bold"),
            )
            c.create_text(
                pad_x + 44, 63,
                text=f"{a.kind} · {a.latency_ms:.0f}ms RTT",
                fill=self.TEXT_MUTED,
                anchor="w",
                font=("Segoe UI", 8),
            )

            limits = self.engine.adapter_mgr.get_adapter_limit_snapshot(a)
            if limits["quota_exceeded"]:
                pill_text, pill_fg, pill_bg, pill_bd = (
                    "DATA CAP REACHED", "#f87171", "#2b1111", "#991b1b"
                )
            elif a.enabled:
                pill_text, pill_fg, pill_bg, pill_bd = (
                    f"ACTIVE · {a.kind.upper()}", "#34d399", "#06281e", "#059669"
                )
            else:
                pill_text, pill_fg, pill_bg, pill_bd = (
                    "STANDBY · DISABLED", self.TEXT_MUTED, "#141418", self.BG_HAIRLINE
                )
            pill_w = len(pill_text) * 6 + 14
            c.create_rectangle(pad_x, 82, pad_x + pill_w, 100, fill=pill_bg, outline=pill_bd)
            c.create_text(
                pad_x + 7, 91,
                text=pill_text,
                fill=pill_fg,
                anchor="w",
                font=("Consolas", 8, "bold"),
            )

            c.create_text(
                pad_x, 113,
                text=(
                    f"{a.active_conns} Conns · "
                    f"{self._fmt_bytes(self._adapter_traffic_bytes(a, self.graph_mode))} · "
                    f"{self._fmt_speed(self._adapter_speed(a, self.graph_mode))}"
                ),
                fill=self.TEXT_DIM,
                anchor="w",
                font=("Segoe UI", 8),
            )

            btn_y0, btn_y1 = h - 35, h - 9
            c.create_rectangle(
                pad_x, btn_y0, x1 - 14, btn_y1,
                fill="#111118",
                outline="#272732",
                stipple="gray50" if limits["quota_exceeded"] else "",
            )
            c.create_text(
                (pad_x + x1 - 14) / 2,
                (btn_y0 + btn_y1) / 2,
                text=(
                    "LIMIT REACHED · WAIT FOR RESET"
                    if limits["quota_exceeded"]
                    else ("BONDED · CLICK TO TOGGLE" if a.enabled else "DISABLED · CLICK TO ENABLE")
                ),
                fill=self.TEXT_DIM if limits["quota_exceeded"] else (
                    self.TEXT_MAIN if a.enabled else self.TEXT_MUTED
                ),
                font=("Segoe UI", 8, "bold"),
            )
        c.configure(scrollregion=(0, 0, content_w, h))

    # -----------------------------------------------------------------
    # 02: APPLICATION BENTO CARDS WITH LIVE SPEED SPARKLINE & FOCUS BUTTON
    # -----------------------------------------------------------------

    def _draw_app_bento_cards(self, entries: List[Dict], adapters: List[NetworkAdapter]):
        c = self.canvas_apps
        c.delete("all")
        self._app_card_regions.clear()

        w = max(480, c.winfo_width())
        cols = 1 if self.app_view_mode == "list" else (3 if w >= 780 else 2)
        items = entries
        rows = max(1, math.ceil(max(1, len(items)) / cols))
        cell_w = w / cols
        cell_h = 185
        content_h = max(c.winfo_height(), rows * cell_h)

        c.create_line(0, 0, w, 0, fill=self.BG_HAIRLINE)
        ip_to_name = {a.ip: a.name for a in adapters}

        for idx, r in enumerate(items):
            row = idx // cols
            col = idx % cols
            x0 = int(col * cell_w)
            x1 = int((col + 1) * cell_w)
            y0 = int(row * cell_h)
            y1 = int((row + 1) * cell_h)

            if col > 0:
                c.create_line(x0, y0, x0, y1, fill=self.BG_HAIRLINE)
            if row > 0:
                c.create_line(x0, y0, x1, y0, fill=self.BG_HAIRLINE)
            c.create_line(x0, y1, x1, y1, fill=self.BG_HAIRLINE)

            _, accent_col, fill_dark = ADAPTER_PALETTE[idx % len(ADAPTER_PALETTE)]
            pad_x = x0 + 14

            # 1. Number badge and consistent per-app actions.
            c.create_rectangle(pad_x, y0 + 11, pad_x + 24, y0 + 28, fill=accent_col, outline="")
            c.create_text(
                pad_x + 12, y0 + 19,
                text=f"{idx + 1:02d}",
                fill="#09090b",
                font=("Consolas", 9, "bold"),
            )

            fav_x0, fav_y0, fav_x1, fav_y1 = x1 - 172, y0 + 10, x1 - 150, y0 + 28
            favorite = bool(r.get("is_favorite"))
            c.create_rectangle(
                fav_x0, fav_y0, fav_x1, fav_y1,
                fill="#2b2110" if favorite else "#111118",
                outline=self.AMBER if favorite else "#34343e",
            )
            c.create_text(
                (fav_x0 + fav_x1) / 2, (fav_y0 + fav_y1) / 2,
                text="★" if favorite else "☆",
                fill=self.AMBER if favorite else self.TEXT_MUTED,
                font=("Segoe UI Symbol", 9, "bold"),
            )
            self._app_card_regions.append((fav_x0, fav_y0, fav_x1, fav_y1, "favorite", r["app_name"], r["last_pid"]))

            foc_x0, foc_y0, foc_x1, foc_y1 = x1 - 146, y0 + 10, x1 - 82, y0 + 28
            c.create_rectangle(foc_x0, foc_y0, foc_x1, foc_y1, fill="#171720", outline="#34343e")
            c.create_text(
                (foc_x0 + foc_x1) / 2, (foc_y0 + foc_y1) / 2,
                text="▣ FOCUS",
                fill=self.TEXT_MAIN,
                font=("Consolas", 8, "bold"),
            )
            self._app_card_regions.append((foc_x0, foc_y0, foc_x1, foc_y1, "focus", r["app_name"], r["last_pid"]))

            loc_x0, loc_y0, loc_x1, loc_y1 = x1 - 76, y0 + 10, x1 - 12, y0 + 28
            c.create_rectangle(loc_x0, loc_y0, loc_x1, loc_y1, fill="#171720", outline="#34343e")
            c.create_text(
                (loc_x0 + loc_x1) / 2, (loc_y0 + loc_y1) / 2,
                text="↗ LOCATE",
                fill=self.TEXT_MAIN,
                font=("Consolas", 8, "bold"),
            )
            self._app_card_regions.append((loc_x0, loc_y0, loc_x1, loc_y1, "location", r["app_name"], r["last_pid"]))

            # 2. App Identity Row (Icon + Two-Tone Title + Running Window/PID Subtitle)
            disp = r["display_name"]
            if "Turbo Accelerator" in disp:
                part1, part2 = "Turbo", "Engine"
                sub_desc = "Parallel range & stream splitter"
            elif "." in disp:
                dot = disp.rfind(".")
                part1 = disp[:dot].capitalize()
                part2 = disp[dot:]
                sub_desc = r["window_title"][:24] if r.get("window_title") else (
                    f"Running · PID {r['last_pid']}" if r.get("is_running") and r.get("last_pid") else "Pinned Process Rule"
                )
            else:
                part1, part2 = disp.capitalize(), ""
                sub_desc = "Process socket routing rule"

            c.create_rectangle(pad_x, y0 + 36, pad_x + 32, y0 + 68, fill="#14141d", outline=accent_col)
            c.create_text(
                pad_x + 16, y0 + 52,
                text=part1[:2].upper(),
                fill=accent_col,
                font=("Segoe UI", 9, "bold"),
            )

            title_x = pad_x + 40
            short_p1 = part1 if len(part1) <= 12 else part1[:11] + "…"
            t_id = c.create_text(
                title_x, y0 + 44,
                text=short_p1,
                fill=self.TEXT_MAIN,
                anchor="w",
                font=("Segoe UI", 10, "bold"),
            )
            bbox = c.bbox(t_id)
            next_x = bbox[2] if bbox else title_x + len(short_p1) * 7
            c.create_text(
                next_x, y0 + 44,
                text=part2,
                fill=accent_col,
                anchor="w",
                font=("Segoe UI", 10, "bold"),
            )
            c.create_text(
                title_x, y0 + 60,
                text=sub_desc,
                fill=self.TEXT_MUTED,
                anchor="w",
                font=("Segoe UI", 8),
            )

            # 3. Embedded Per-Application Speed Sparkline Graph
            spk_x0, spk_y0 = pad_x, y0 + 76
            spk_x1, spk_y1 = x1 - 12, y0 + 122
            c.create_rectangle(spk_x0, spk_y0, spk_x1, spk_y1, fill="#07070a", outline="#1b1b24")
            c.create_text(
                spk_x0 + 6, spk_y0 + 9,
                text="APP THROUGHPUT",
                fill=self.TEXT_DIM,
                anchor="w",
                font=("Consolas", 7, "bold"),
            )
            c.create_text(
                spk_x1 - 6, spk_y0 + 9,
                text=self._fmt_speed(r.get("bps", 0.0)),
                fill=accent_col,
                anchor="e",
                font=("Consolas", 8, "bold"),
            )

            hist = r.get("bps_history", [])
            if len(hist) >= 2:
                max_app_bps = max(8192.0, max(hist) * 1.15)
                gw = max(20, (spk_x1 - spk_x0) - 8)
                gh = max(12, (spk_y1 - spk_y0) - 20)
                gx0 = spk_x0 + 4
                gy_base = spk_y1 - 3
                s_pts: List[Tuple[float, float]] = []
                for h_i, h_val in enumerate(hist):
                    px = gx0 + (h_i / (len(hist) - 1)) * gw
                    py = gy_base - min(1.0, max(0.0, h_val / max_app_bps)) * gh
                    s_pts.append((px, py))
                spline = self._catmull_rom_spline(s_pts, subdivisions=2)
                if len(spline) >= 4:
                    poly = [gx0, gy_base] + spline + [gx0 + gw, gy_base]
                    c.create_polygon(*poly, fill=fill_dark, stipple="gray50", outline="")
                    c.create_line(*spline, fill=accent_col, width=1.6)
                    lx, ly = s_pts[-1]
                    c.create_oval(lx - 2.5, ly - 2.5, lx + 2.5, ly + 2.5, fill=accent_col, outline="")

            # 4. Status Pill + Telemetry Summary Row
            is_pinned = r["rule"] != "AUTO"
            if r["rule"] == BLOCK_INTERNET_RULE:
                pill_text = "BLOCKED · NO INTERNET"
                pill_bg, pill_bd, pill_fg = "#3f1212", "#dc2626", "#fca5a5"
            elif is_pinned:
                nic_label = ip_to_name.get(r["rule"], r["rule"])
                pill_text = f"PINNED · {nic_label[:10].upper()}"
                pill_bg, pill_bd, pill_fg = "#082f49", "#0284c7", "#38bdf8"
            else:
                pill_text = "AUTO · BONDED"
                pill_bg, pill_bd, pill_fg = "#06281e", "#059669", "#34d399"

            pill_w = len(pill_text) * 6 + 10
            c.create_rectangle(pad_x, y0 + 128, pad_x + pill_w, y0 + 144, fill=pill_bg, outline=pill_bd)
            c.create_text(
                pad_x + 5, y0 + 136,
                text=pill_text,
                fill=pill_fg,
                anchor="w",
                font=("Consolas", 7, "bold"),
            )

            c.create_text(
                x1 - 12, y0 + 136,
                text=f"{r['active_connections']} Conns · {self._fmt_bytes(r['bytes_transferred'])}",
                fill=self.TEXT_DIM,
                anchor="e",
                font=("Consolas", 8),
            )

            # 5. Bottom Policy Action Button
            btn_y0, btn_y1 = y1 - 31, y1 - 7
            c.create_rectangle(pad_x, btn_y0, x1 - 12, btn_y1, fill="#111118", outline="#272732")
            selected_policy = r["rule"]
            if selected_policy == "AUTO":
                selected_name = "AUTO / BONDED"
            elif selected_policy == BLOCK_INTERNET_RULE:
                selected_name = "BLOCK INTERNET"
            else:
                selected_name = ip_to_name.get(selected_policy, selected_policy)
            action_lbl = f"POLICY: {selected_name}  [CLICK TO SELECT]"
            c.create_text(
                (pad_x + x1 - 12) / 2,
                (btn_y0 + btn_y1) / 2,
                text=action_lbl,
                fill=self.TEXT_MAIN,
                font=("Segoe UI", 8, "bold"),
            )
            self._app_card_regions.append((pad_x, btn_y0, x1 - 12, btn_y1, "policy", r["app_name"], r["last_pid"]))
        c.configure(scrollregion=(0, 0, w, content_h))

    # -----------------------------------------------------------------
    # FIXED TWO-TIER NON-OVERLAPPING GOOGLE SPLINE CHART
    # -----------------------------------------------------------------

    @staticmethod
    def _catmull_rom_spline(pts: List[Tuple[float, float]], subdivisions: int = 4) -> List[float]:
        if len(pts) < 2:
            return []
        out: List[float] = []
        n = len(pts)
        for i in range(n - 1):
            p0 = pts[max(0, i - 1)]
            p1 = pts[i]
            p2 = pts[i + 1]
            p3 = pts[min(n - 1, i + 2)]
            for step in range(subdivisions):
                t = step / subdivisions
                t2 = t * t
                t3 = t2 * t
                x = 0.5 * (
                    (2 * p1[0])
                    + (-p0[0] + p2[0]) * t
                    + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                    + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
                )
                y = 0.5 * (
                    (2 * p1[1])
                    + (-p0[1] + p2[1]) * t
                    + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                    + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
                )
                out.extend([x, y])
        out.extend([pts[-1][0], pts[-1][1]])
        return out

    def _draw_google_chart(self, adapters: List[NetworkAdapter]):
        c = self.canvas_chart
        c.delete("all")
        w = max(360, c.winfo_width())
        h = max(200, c.winfo_height())

        pad_l, pad_r, pad_b = 68, 20, 26

        total_bps = sum(self._adapter_speed(a, self.graph_mode) for a in adapters)
        if total_bps > self._peak_bps:
            self._peak_bps = total_bps

        # ROW 1 (y=16): Title on Left | Combined Speed Badge + Peak on Right
        c.create_text(
            18, 16,
            text=(
                "MASTER SPEED · ALL COMPUTER NETWORK TRAFFIC"
                if self.graph_mode == "master"
                else "BONDED SPEED · OMNIBOND ROUTED TRAFFIC"
            ),
            fill=self.TEXT_MUTED,
            anchor="w",
            font=("Consolas", 9, "bold"),
        )

        speed_str = f"LIVE: {self._fmt_speed(total_bps)}   ·   PEAK: {self._fmt_speed(self._peak_bps)}"
        c.create_rectangle(w - len(speed_str) * 6.5 - 26, 6, w - 16, 26, fill="#14141d", outline="#272734")
        c.create_text(
            w - 22, 16,
            text=speed_str,
            fill=self.AMBER,
            anchor="e",
            font=("Consolas", 8, "bold"),
        )

        # Wrap every adapter metric into the available width before sizing the plot.
        leg_x, leg_y = 18, 38
        for idx, a in enumerate(adapters):
            lbl = (
                f"{idx + 1:02d}·{a.name[:11]} "
                f"({self._fmt_speed(self._adapter_speed(a, self.graph_mode))})"
            )
            item_width = 18 + len(lbl) * 6.0
            if leg_x + item_width > w - 12 and leg_x > 18:
                leg_x, leg_y = 18, leg_y + 14
            c.create_oval(leg_x, leg_y - 4, leg_x + 8, leg_y + 4, fill=a.color, outline="")
            tid = c.create_text(
                leg_x + 12, leg_y,
                text=lbl,
                fill=self.TEXT_MUTED,
                anchor="w",
                font=("Consolas", 8),
            )
            bbox = c.bbox(tid)
            leg_x = (bbox[2] + 16) if bbox else (leg_x + 145)
        pad_t = max(62, leg_y + 20)
        plot_w = max(1, w - pad_l - pad_r)
        plot_h = max(1, h - pad_t - pad_b)

        # Compute Dynamic Y-Axis Scale
        max_bps = 64 * 1024.0
        for a in adapters:
            history = self._adapter_speed_history(a, self.graph_mode)
            if history:
                max_bps = max(max_bps, max(history) * 1.18)

        # Y-Axis Labels & Gridlines
        rows = 4
        for r in range(rows + 1):
            y = pad_t + (plot_h / rows) * r
            val = max_bps * (1.0 - r / rows)
            line_col = "#272730" if r == rows else "#16161d"
            dash_pat = () if r == rows else (2, 4)
            c.create_line(pad_l, y, w - pad_r, y, fill=line_col, dash=dash_pat)
            lbl_txt = "0 B/s" if val < 1 else self._fmt_speed(val)
            c.create_text(
                pad_l - 8, y,
                text=lbl_txt,
                fill=self.TEXT_DIM,
                anchor="e",
                font=("Consolas", 8),
            )

        # X-Axis Timeline Ticks
        x_ticks = [("-60s", 0.0), ("-45s", 0.25), ("-30s", 0.50), ("-15s", 0.75), ("LIVE", 1.0)]
        for txt, frac in x_ticks:
            tx = pad_l + plot_w * frac
            c.create_text(
                tx, pad_t + plot_h + 11,
                text=txt,
                fill=self.AMBER if txt == "LIVE" else self.TEXT_DIM,
                anchor="center",
                font=("Consolas", 8, "bold" if txt == "LIVE" else "normal"),
            )

        baseline_y = pad_t + plot_h
        for a in adapters:
            hist = self._adapter_speed_history(a, self.graph_mode)
            if len(hist) < 2:
                continue
            ctrl_pts: List[Tuple[float, float]] = []
            for idx, val in enumerate(hist):
                x = pad_l + (idx / (len(hist) - 1)) * plot_w
                norm = min(1.0, max(0.0, val / max_bps))
                y = baseline_y - norm * plot_h
                ctrl_pts.append((x, y))

            spline_coords = self._catmull_rom_spline(ctrl_pts, subdivisions=3)
            if len(spline_coords) >= 4:
                poly_coords = [pad_l, baseline_y] + spline_coords + [pad_l + plot_w, baseline_y]
                c.create_polygon(*poly_coords, fill=a.fill_dark, stipple="gray50", outline="")
                c.create_line(
                    *spline_coords,
                    fill=a.color,
                    width=2.4,
                    capstyle=tk.ROUND,
                    joinstyle=tk.ROUND,
                )
                lx, ly = ctrl_pts[-1]
                c.create_oval(lx - 6, ly - 6, lx + 6, ly + 6, fill="", outline=a.color, width=1)
                c.create_oval(lx - 3, ly - 3, lx + 3, ly + 3, fill=a.color, outline="")

        # Hover Crosshair Tooltip
        if self._hover_chart_x is not None and pad_l <= self._hover_chart_x <= (pad_l + plot_w) and adapters:
            hx = self._hover_chart_x
            c.create_line(hx, pad_t, hx, baseline_y, fill="#52525b", dash=(2, 2))
            hist_len = len(self._adapter_speed_history(adapters[0], self.graph_mode))
            rel = (hx - pad_l) / max(1.0, plot_w)
            sample_idx = min(hist_len - 1, max(0, int(round(rel * (hist_len - 1)))))

            lines = []
            for idx, a in enumerate(adapters):
                history = self._adapter_speed_history(a, self.graph_mode)
                val = history[sample_idx] if sample_idx < len(history) else 0.0
                px = pad_l + (sample_idx / max(1, hist_len - 1)) * plot_w
                py = baseline_y - min(1.0, max(0.0, val / max_bps)) * plot_h
                c.create_oval(px - 4, py - 4, px + 4, py + 4, fill=a.color, outline="#09090b", width=1.5)
                lines.append((f"{idx + 1:02d} {a.name[:12]}: {self._fmt_speed(val)}", a.color))

            box_w = 180
            box_h = 16 + len(lines) * 16
            bx0 = hx + 12 if hx + 12 + box_w < w - pad_r else hx - box_w - 12
            by0 = pad_t + 6
            c.create_rectangle(bx0, by0, bx0 + box_w, by0 + box_h, fill="#121218", outline="#3f3f46")
            for l_idx, (txt, col) in enumerate(lines):
                c.create_text(
                    bx0 + 10, by0 + 13 + l_idx * 16,
                    text=txt,
                    fill=col,
                    anchor="w",
                    font=("Consolas", 8, "bold"),
                )

    # -----------------------------------------------------------------
    # 03: UNIFIED GLOWING PROGRESS TRACK & BLOCK MATRIX
    # -----------------------------------------------------------------

    def _draw_unified_turbo_bar(self):
        c = self.canvas_dl_unified
        c.delete("all")
        w = max(400, c.winfo_width())

        pct = min(100.0, max(0.0, self.engine.turbo.progress_pct))
        spd = self._fmt_speed(self.engine.turbo.speed_bps)
        state_lbl = "ACTIVE" if self.engine.turbo.is_running else "READY"
        self.lbl_dl_badge.configure(text=f"{state_lbl} · {spd} · {pct:.0f}%")

        # 1. Status & Percentage Header Line (y=8)
        c.create_text(
            2, 7,
            text=self.engine.turbo.status_text,
            fill=self.TEXT_MUTED,
            anchor="w",
            font=("Consolas", 8),
        )
        c.create_text(
            w - 2, 7,
            text=f"{pct:.1f}% COMPLETE",
            fill=self.AMBER if pct > 0 else self.TEXT_DIM,
            anchor="e",
            font=("Consolas", 8, "bold"),
        )

        # 2. Glowing Smooth Progress Bar Track (y=17..25)
        c.create_rectangle(0, 17, w, 25, fill="#12121a", outline="#1e1e2a")
        fill_w = int((pct / 100.0) * w)
        if fill_w > 0:
            c.create_rectangle(1, 18, fill_w, 24, fill=self.EMERALD if pct >= 100 else self.AMBER, outline="")

        # 3. Segmented Multi-NIC Block Allocation Matrix (y=30..44)
        blocks = self.engine.turbo.blocks[:90]
        if blocks:
            num_b = len(blocks)
            gap = 2
            bw = max(6.0, (w - (num_b - 1) * gap) / num_b)
            for idx, b in enumerate(blocks):
                bx0 = idx * (bw + gap)
                col = "#14141d" if b.status == "pending" else b.color
                c.create_rectangle(bx0, 30, bx0 + bw, 43, fill=col, outline="")
        else:
            # Subtle idle placeholder segments aligned with the URL bar
            slots = 48
            gap = 3
            bw = (w - (slots - 1) * gap) / slots
            for i in range(slots):
                bx0 = i * (bw + gap)
                c.create_rectangle(bx0, 31, bx0 + bw, 42, fill="#111118", outline="")

    def _update_ui(self):
        if self.engine.sys_opt.system_proxy_enabled:
            self.btn_proxy.configure(text="◈ Bonding: On")
        else:
            self.btn_proxy.configure(text="◈ Bonding: Off")

        adapters = self.engine.adapter_mgr.get_adapters()
        self._refresh_policy_dropdown(adapters)

        enabled_adapter_count = sum(
            1 for adapter in adapters
            if adapter.enabled and not self.engine.adapter_mgr.is_quota_exceeded(adapter)
        )
        adapter_telemetry_status = self.engine.adapter_mgr.system_counter_status
        adapter_telemetry_label = (
            "OMNIBOND"
            if self.graph_mode == "bonded"
            else (
                "SYSTEM NIC UNAVAILABLE"
                if "unavailable" in adapter_telemetry_status.casefold()
                or "did not match" in adapter_telemetry_status.casefold()
                else "SYSTEM NIC"
            )
        )
        self.lbl_adapter_count_meta.configure(
            text=(
                f"{enabled_adapter_count} / {len(adapters)} INTERFACES BONDED · "
                f"{adapter_telemetry_label}"
            )
        )

        entries = self.engine.routing_mgr.get_all_entries(only_running_or_added=True)
        app_telemetry_status = self.engine.process_tcp_counters.status
        app_telemetry_label = (
            "ADMIN REQUIRED"
            if app_telemetry_status.startswith("Administrator permission required")
            else (
                "PARTIAL TCP"
                if app_telemetry_status.startswith("Partial")
                else (
                    "LIVE TCP"
                    if "active" in app_telemetry_status.casefold()
                    else (
                        "WAITING TCP"
                        if "waiting" in app_telemetry_status.casefold()
                        else "TCP STATUS"
                    )
                )
            )
        )
        self.lbl_running_badge.configure(
            text=f"{len(entries)} ACTIVE / PINNED APPS · {app_telemetry_label}"
        )

        self._draw_adapter_bento_cards(adapters)
        self._draw_app_bento_cards(self._sort_app_entries(self._filter_app_entries(entries)), adapters)
        self._draw_google_chart(adapters)
        self._draw_unified_turbo_bar()

    def _schedule_refresh(self):
        try:
            self._apply_process_scan_result()
            self._update_ui()
        except Exception:
            pass
        self.root.after(1200, self._schedule_refresh)

    def _on_close(self):
        errors = self.engine.stop_services()
        if errors:
            messagebox.showwarning(
                "Network Settings Restoration",
                "OmniBond stopped, but some Windows settings could not be restored:\n\n"
                + "\n".join(errors),
            )
        self.root.destroy()

    def run(self):
        self.root.mainloop()