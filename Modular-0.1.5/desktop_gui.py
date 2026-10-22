#!/usr/bin/env python3
"""
OmniBond - Native Tkinter Studio Desktop GUI (1:1 Visual & Feature Parity with Web UI).
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
    BLOCK_INTERNET_RULE,
    TURBO_APP_KEY,
    TURBO_APP_LABEL,
    filedialog,
    messagebox,
    tk,
)
from engine import OmniBondEngine
from process_mapper import ProcessInfo
from studio_widgets import StudioDropdown, StudioScrollbar, StudioTooltip

# =====================================================================
# 10. NATIVE TKINTER STUDIO GUI (1:1 PARITY WITH WEB STUDIO UI)
# =====================================================================

class OmniBondDesktopGUI:
    BG_MAIN = "#09090b"
    BG_HAIRLINE = "#1e1e24"
    BG_PANEL = "#0c0c0f"
    BG_CARD = "#0c0c0f"
    BG_CARD_HOVER = "#121217"
    TEXT_MAIN = "#fafafa"
    TEXT_MUTED = "#a1a1aa"
    TEXT_DIM = "#52525b"
    AMBER = "#f59e0b"
    EMERALD = "#10b981"
    CYAN = "#38bdf8"

    # Expanded 16-color vibrant palette matching Web UI APP_PALETTE_COLORS
    APP_ACCENT_PALETTE: List[Tuple[str, str]] = [
        ("#38bdf8", "#0c2d3e"),  # Sky Cyan
        ("#fb923c", "#3b1d0a"),  # Sunset Orange
        ("#34d399", "#083024"),  # Emerald Mint
        ("#a78bfa", "#24193d"),  # Royal Violet
        ("#facc15", "#362b07"),  # Amber Gold
        ("#f472b6", "#381228"),  # Rose Neon
        ("#f87171", "#3a1212"),  # Coral Red
        ("#2dd4bf", "#092e2a"),  # Cyber Teal
        ("#818cf8", "#191c3d"),  # Indigo Pulse
        ("#a3e635", "#223309"),  # Lime Matrix
        ("#e879f9", "#35123b"),  # Electric Fuchsia
        ("#fb7185", "#3b111b"),  # Crimson Rose
        ("#60a5fa", "#102442"),  # Cobalt Blue
        ("#fdba74", "#38220d"),  # Warm Peach
        ("#6ee7b7", "#0b3022"),  # Seafoam Mint
        ("#fde047", "#383008"),  # Solar Yellow
    ]

    APP_THEME_MAP: Dict[str, Tuple[str, str]] = {
        "CYAN": ("#38bdf8", "#0c2d3e"),
        "ORANGE": ("#fb923c", "#3b1d0a"),
        "EMERALD": ("#34d399", "#083024"),
        "VIOLET": ("#a78bfa", "#24193d"),
        "AMBER": ("#facc15", "#362b07"),
        "ROSE": ("#f472b6", "#381228"),
        "CORAL": ("#f87171", "#3a1212"),
        "TEAL": ("#2dd4bf", "#092e2a"),
        "INDIGO": ("#818cf8", "#191c3d"),
        "LIME": ("#a3e635", "#223309"),
    }

    def __init__(self, engine: OmniBondEngine):
        self.engine = engine
        self.root = tk.Tk()
        self.root.title("OmniBond")
        self.root.geometry("1420x910")
        self.root.minsize(1120, 760)
        self.root.configure(bg=self.BG_HAIRLINE)

        self.tooltip = StudioTooltip(self.root)
        self._hover_chart_x: Optional[int] = None
        self._peak_bps: float = 0.0
        self.graph_mode = "master"
        self.hide_ips: bool = False
        self.app_view_mode = "grid"
        self.app_filter_mode = "ALL"
        self.app_sort_mode = "AZ"
        self.app_color_theme = "MULTI"
        self.dd_app: Optional[StudioDropdown] = None
        self.dd_policy: Optional[StudioDropdown] = None
        self.ent_custom_app: Optional[tk.Entry] = None
        self._process_dropdown_items: List[Dict[str, str]] = []
        self._policy_dropdown_items: List[Dict[str, str]] = []
        self._process_scan_queue: "queue.Queue[Tuple[Optional[List[ProcessInfo]], Optional[Exception]]]" = queue.Queue()
        self._process_scan_in_progress = False
        self._network_tuning_options = {"keep_multi_nic": True, "ipv4": True, "ipv6": False}
        self._adapter_card_regions: List[Tuple[int, int, int, int, str]] = []
        self._app_card_regions: List[Tuple[int, int, int, int, str, str, int, str]] = []
        self._app_card_bounds: List[Tuple[int, int, int, int, str]] = []
        self._hovered_adapter_ip: str = ""
        self._hovered_app_key: str = ""
        self._last_Hovered_region_desc: str = ""
        self._policy_popup: Optional[tk.Toplevel] = None

        self._build_flush_layout()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._schedule_refresh()

    # -----------------------------------------------------------------
    # COLOR, GEOMETRY & GRADIENT DRAWING HELPERS
    # -----------------------------------------------------------------

    @staticmethod
    def _blend_hex(base_hex: str, top_hex: str, alpha: float) -> str:
        """Blends top_hex over base_hex with factor alpha in [0.0, 1.0]."""
        b = base_hex.lstrip("#")
        t = top_hex.lstrip("#")
        if len(b) != 6 or len(t) != 6:
            return top_hex
        a = max(0.0, min(1.0, alpha))
        br, bg, bb = int(b[0:2], 16), int(b[2:4], 16), int(b[4:6], 16)
        tr, tg, tb = int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16)
        rr = int(round(br + (tr - br) * a))
        rg = int(round(bg + (tg - bg) * a))
        rb = int(round(bb + (tb - bb) * a))
        return f"#{rr:02x}{rg:02x}{rb:02x}"

    @staticmethod
    def _draw_rounded_rect(
        c: tk.Canvas,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        radius: float = 6.0,
        fill: str = "",
        outline: str = "",
    ):
        """Draws a crisp rounded rectangle matching CSS border-radius."""
        r = max(1.0, min(radius, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
        pts: List[float] = []
        corners = [
            (x1 - r, y0 + r, -90, 0),
            (x1 - r, y1 - r, 0, 90),
            (x0 + r, y1 - r, 90, 180),
            (x0 + r, y0 + r, 180, 270),
        ]
        for cx, cy, deg_start, deg_end in corners:
            for step in range(5):
                ang = math.radians(deg_start + (deg_end - deg_start) * (step / 4.0))
                pts.extend([cx + r * math.cos(ang), cy + r * math.sin(ang)])
        c.create_polygon(*pts, fill=fill, outline=outline, width=1, smooth=False)

    @staticmethod
    def _quadratic_bezier_curve(
        pts: List[Tuple[float, float]], step_px: float = 2.5
    ) -> List[Tuple[float, float]]:
        """
        Generates a dense, silky-smooth curve using the exact same midpoint quadratic Bezier
        algorithm as the Web UI's `ctx.quadraticCurveTo`.
        """
        if len(pts) < 2:
            return list(pts)
        if len(pts) == 2:
            return [pts[0], pts[1]]

        out: List[Tuple[float, float]] = [pts[0]]
        anchors: List[Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]]] = []
        p_start = pts[0]
        for i in range(len(pts) - 1):
            ctrl = pts[i]
            if i < len(pts) - 2:
                p_end = ((pts[i][0] + pts[i + 1][0]) * 0.5, (pts[i][1] + pts[i + 1][1]) * 0.5)
            else:
                p_end = pts[-1]
            anchors.append((p_start, ctrl, p_end))
            p_start = p_end

        for p0, p1, p2 in anchors:
            span_x = abs(p2[0] - p0[0])
            steps = max(4, int(math.ceil(span_x / max(1.0, step_px))))
            for s in range(1, steps + 1):
                t = s / steps
                inv = 1.0 - t
                x = (inv * inv) * p0[0] + 2.0 * inv * t * p1[0] + (t * t) * p2[0]
                y = (inv * inv) * p0[1] + 2.0 * inv * t * p1[1] + (t * t) * p2[1]
                out.append((x, y))
        return out

    @classmethod
    def _draw_gradient_area(
        cls,
        c: tk.Canvas,
        curve_pts: List[Tuple[float, float]],
        baseline_y: float,
        line_col: str,
        bg_col: str,
        top_alpha: float = 0.25,
        bands: int = 16,
    ):
        """
        Draws a smooth vertical gradient area fill beneath `curve_pts` down to `baseline_y`
        using horizontal color-interpolated polygon slices (matching HTML5 createLinearGradient).
        """
        if len(curve_pts) < 2:
            return
        min_y = min(p[1] for p in curve_pts)
        if baseline_y - min_y < 1.5:
            return

        x_first = curve_pts[0][0]
        x_last = curve_pts[-1][0]
        total_h = max(1.0, baseline_y - min_y)

        for b_idx in range(bands):
            frac0 = b_idx / bands
            frac1 = (b_idx + 1) / bands
            band_y0 = min_y + total_h * frac0
            band_y1 = min_y + total_h * frac1
            alpha = top_alpha * (1.0 - (frac0 * 0.92))
            if alpha <= 0.015:
                continue
            band_col = cls._blend_hex(bg_col, line_col, alpha)
            poly: List[float] = [x_first, band_y1]
            for px, py in curve_pts:
                clamped_y = max(band_y0, min(band_y1, py))
                poly.extend([px, clamped_y])
            poly.extend([x_last, band_y1])
            if len(poly) >= 6:
                c.create_polygon(*poly, fill=band_col, outline="")

    @classmethod
    def _draw_smooth_curve_with_gradient(
        cls,
        c: tk.Canvas,
        pts: List[Tuple[float, float]],
        baseline_y: float,
        line_col: str,
        bg_col: str,
        line_width: float = 2.0,
        top_alpha: float = 0.25,
        bands: int = 16,
        draw_end_dot: bool = False,
    ):
        if len(pts) < 2:
            return
        curve_pts = cls._quadratic_bezier_curve(pts, step_px=2.5)
        cls._draw_gradient_area(
            c,
            curve_pts,
            baseline_y=baseline_y,
            line_col=line_col,
            bg_col=bg_col,
            top_alpha=top_alpha,
            bands=bands,
        )
        flat_coords: List[float] = []
        for px, py in curve_pts:
            flat_coords.extend([px, py])
        if len(flat_coords) >= 4:
            # Subtle anti-aliasing glow under-stroke + crisp main curve
            glow_col = cls._blend_hex(bg_col, line_col, 0.35)
            c.create_line(
                *flat_coords,
                fill=glow_col,
                width=line_width + 1.4,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
            )
            c.create_line(
                *flat_coords,
                fill=line_col,
                width=line_width,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
            )
        if draw_end_dot:
            lx, ly = curve_pts[-1]
            c.create_oval(lx - 2.3, ly - 2.3, lx + 2.3, ly + 2.3, fill=line_col, outline="")

    def _get_app_accent(self, idx: int) -> Tuple[str, str]:
        if self.app_color_theme != "MULTI" and self.app_color_theme in self.APP_THEME_MAP:
            return self.APP_THEME_MAP[self.app_color_theme]
        return self.APP_ACCENT_PALETTE[idx % len(self.APP_ACCENT_PALETTE)]

    def _mask_ip(self, ip: str) -> str:
        s = str(ip or "").strip()
        if not s or s == "-":
            return s or "-"
        return "•••.•••.•••.•••" if self.hide_ips else s

    def _make_studio_btn(
        self,
        parent: tk.Widget,
        text: str,
        tooltip_title: str,
        tooltip_desc: str,
        variant: str = "dark",  # dark | primary | amber | active
        cmd: Optional[Callable] = None,
        px: int = 12,
        py: int = 6,
    ) -> tk.Frame:
        """
        Creates a crisp 1px-bordered Studio button matching the Web UI's `.btn` without
        Win32 thick native button bevels or double outlines.
        """
        palette = {
            "dark": ("#14141b", "#fafafa", "#272732", "#1f1f2a", "#f59e0b"),
            "primary": ("#fafafa", "#09090b", "#fafafa", "#f59e0b", "#f59e0b"),
            "amber": ("#f59e0b", "#09090b", "#f59e0b", "#fbbf24", "#fafafa"),
            "active": ("#14141b", "#f59e0b", "#f59e0b", "#1f1f2a", "#f59e0b"),
        }
        bg, fg, bd_col, hov_bg, hov_bd = palette.get(variant, palette["dark"])

        wrap = tk.Frame(
            parent,
            bg=bg,
            highlightthickness=1,
            highlightbackground=bd_col,
            highlightcolor=bd_col,
            bd=0,
            cursor="hand2",
        )
        lbl = tk.Label(
            wrap,
            text=text,
            bg=bg,
            fg=fg,
            padx=px,
            pady=py,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
        )
        lbl.pack(fill=tk.BOTH, expand=True)

        wrap._studio_variant = variant  # type: ignore
        wrap._studio_label = lbl  # type: ignore
        wrap._studio_cmd = cmd  # type: ignore

        def configure_override(**kw):
            if "text" in kw:
                lbl.configure(text=kw.pop("text"))
            if "fg" in kw:
                lbl.configure(fg=kw.pop("fg"))
            if "bg" in kw:
                b_val = kw.pop("bg")
                lbl.configure(bg=b_val)
                tk.Frame.configure(wrap, bg=b_val)
            if kw:
                tk.Frame.configure(wrap, **kw)

        wrap.configure = configure_override  # type: ignore
        wrap.config = configure_override  # type: ignore

        def on_enter(_e):
            v = getattr(wrap, "_studio_variant", variant)
            _, _, _, h_bg, h_bd = palette.get(v, palette["dark"])
            h_fg = "#09090b" if v in ("primary", "amber") else (self.AMBER if v == "active" else self.TEXT_MAIN)
            tk.Frame.configure(wrap, bg=h_bg, highlightbackground=h_bd)
            lbl.configure(bg=h_bg, fg=h_fg)

        def on_leave(_e):
            v = getattr(wrap, "_studio_variant", variant)
            b_bg, b_fg, b_bd, _, _ = palette.get(v, palette["dark"])
            tk.Frame.configure(wrap, bg=b_bg, highlightbackground=b_bd)
            lbl.configure(bg=b_bg, fg=b_fg)

        def on_click(_e):
            cb = getattr(wrap, "_studio_cmd", None)
            if callable(cb):
                cb()

        for w_el in (wrap, lbl):
            w_el.bind("<Enter>", on_enter, add="+")
            w_el.bind("<Leave>", on_leave, add="+")
            w_el.bind("<Button-1>", on_click, add="+")

        self.tooltip.bind_widget(wrap, tooltip_title, tooltip_desc)
        self.tooltip.bind_widget(lbl, tooltip_title, tooltip_desc)
        return wrap

    def _set_btn_variant(self, btn: tk.Frame, variant: str):
        palette = {
            "dark": ("#14141b", "#fafafa", "#272732"),
            "primary": ("#fafafa", "#09090b", "#fafafa"),
            "amber": ("#f59e0b", "#09090b", "#f59e0b"),
            "active": ("#14141b", "#f59e0b", "#f59e0b"),
        }
        bg, fg, bd_col = palette.get(variant, palette["dark"])
        btn._studio_variant = variant  # type: ignore
        tk.Frame.configure(btn, bg=bg, highlightbackground=bd_col)
        lbl = getattr(btn, "_studio_label", None)
        if lbl is not None:
            lbl.configure(bg=bg, fg=fg)

    @staticmethod
    def _split_app_title(display_name: str, app_name: str = "") -> Tuple[str, str]:
        if "Turbo Accelerator" in display_name:
            return "Turbo Accelerator", "ENGINE"
        if app_name and display_name and display_name.lower() != app_name.lower():
            return display_name, app_name
        dot = display_name.rfind(".")
        if dot > 0:
            base = display_name[:dot]
            return base[:1].upper() + base[1:], display_name
        return display_name, app_name or ""

    def _build_flush_layout(self):
        self.root.grid_columnconfigure(0, weight=100)
        self.root.grid_columnconfigure(1, weight=118)
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_rowconfigure(2, weight=0)

        # -----------------------------------------------------------------
        # CONTAINER 0: TOP BAR (Matches Web UI .topbar)
        # -----------------------------------------------------------------
        topbar = tk.Frame(self.root, bg=self.BG_PANEL, padx=20, pady=13)
        topbar.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=0, pady=(0, 1))

        brand_left = tk.Frame(topbar, bg=self.BG_PANEL)
        brand_left.pack(side=tk.LEFT)

        tk.Label(
            brand_left,
            text="OB",
            bg=self.AMBER,
            fg="#09090b",
            font=("Segoe UI", 10, "bold"),
            padx=7,
            pady=4,
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
        self.lbl_server_endpoints = tk.Label(
            title_col,
            text=f"• HTTP/HTTPS 127.0.0.1:{self.engine.http_port}  • SOCKS5 127.0.0.1:{self.engine.socks_port}  • Web Dashboard 127.0.0.1:{self.engine.web_port}",
            bg=self.BG_PANEL,
            fg=self.TEXT_MUTED,
            font=("Consolas", 9),
        )
        self.lbl_server_endpoints.pack(anchor="w", pady=(1, 0))

        actions_right = tk.Frame(topbar, bg=self.BG_PANEL)
        actions_right.pack(side=tk.RIGHT)

        self.btn_proxy = self._make_studio_btn(
            actions_right,
            "◈ Bonding: Off",
            "SYSTEM-WIDE BONDING PROXY",
            "Route all Windows HTTP/HTTPS & SOCKS5 traffic across active adapters.",
            variant="primary",
            cmd=self._toggle_system_proxy,
            px=13,
            py=5,
        )
        self.btn_proxy.pack(side=tk.LEFT, padx=(0, 8))

        self._make_studio_btn(
            actions_right,
            "⚙ Network Tuning",
            "NETWORK TUNING & ADAPTER LIMITS",
            "Configure Windows multi-network and IP route optimization plus per-adapter data and speed limits.",
            variant="dark",
            cmd=self._show_network_tuning,
            px=12,
            py=5,
        ).pack(side=tk.LEFT, padx=(0, 8))

        self._make_studio_btn(
            actions_right,
            "✚ Repair Network",
            "REPAIR NETWORK",
            "Reset Windows proxy to Direct, restore automatic interface metrics, and flush DNS.",
            variant="dark",
            cmd=self._repair_network_gui,
            px=12,
            py=5,
        ).pack(side=tk.LEFT, padx=(0, 8))

        self.btn_graph_mode = self._make_studio_btn(
            actions_right,
            "∿ Master Speed",
            "MASTER OR BONDED SPEED",
            "Showing live traffic on the computer network interfaces. Click to toggle OmniBond bonded traffic.",
            variant="dark",
            cmd=self._toggle_graph_mode,
            px=12,
            py=5,
        )
        self.btn_graph_mode.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_hide_ips = self._make_studio_btn(
            actions_right,
            "👁 Hide IPs",
            "HIDE OR SHOW IP ADDRESSES",
            "Mask or reveal all IPv4 addresses across adapter cards, application cards, and server endpoints.",
            variant="dark",
            cmd=self._toggle_hide_ips,
            px=12,
            py=5,
        )
        self.btn_hide_ips.pack(side=tk.LEFT, padx=(0, 8))

        self._make_studio_btn(
            actions_right,
            "⟳ Rescan Adapters",
            "RESCAN ADAPTERS",
            "Re-scan Windows network adapters and IPv4 addresses.",
            variant="dark",
            cmd=self._rescan_nics,
            px=12,
            py=5,
        ).pack(side=tk.LEFT)

        # -----------------------------------------------------------------
        # CONTAINER 1: 01 / HARDWARE INTERFACES & CHART (Matches Web UI Section 01)
        # -----------------------------------------------------------------
        c01 = tk.Frame(self.root, bg=self.BG_PANEL)
        c01.grid(row=1, column=0, sticky="nsew", padx=(0, 1), pady=(0, 1))
        c01.grid_columnconfigure(0, weight=1)
        c01.grid_rowconfigure(0, weight=0)
        c01.grid_rowconfigure(1, weight=0)
        c01.grid_rowconfigure(2, weight=0)
        c01.grid_rowconfigure(3, weight=1)

        c01_head = tk.Frame(c01, bg=self.BG_PANEL, padx=18, pady=12)
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
        ).pack(anchor="w", pady=(2, 0))

        self.lbl_adapter_count_meta = tk.Label(
            c01_head,
            text="0 / 0 INTERFACES BONDED · SYSTEM NIC",
            bg=self.BG_PANEL,
            fg=self.TEXT_MUTED,
            font=("Consolas", 8),
        )
        self.lbl_adapter_count_meta.pack(side=tk.RIGHT, anchor="s")

        tk.Frame(c01, bg=self.BG_HAIRLINE, height=1).grid(row=1, column=0, sticky="ew")

        adapter_scroll_frame = tk.Frame(c01, bg=self.BG_PANEL)
        adapter_scroll_frame.grid(row=2, column=0, sticky="ew")
        adapter_scroll_frame.grid_columnconfigure(0, weight=1)
        self.canvas_adapters = tk.Canvas(
            adapter_scroll_frame,
            height=184,
            bg=self.BG_PANEL,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.canvas_adapters.grid(row=0, column=0, sticky="ew")
        self.adapter_hscroll = StudioScrollbar(
            adapter_scroll_frame,
            orient=tk.HORIZONTAL,
            command=self.canvas_adapters.xview,
            thickness=6,
            track_bg=self.BG_PANEL,
            thumb_bg="#272732",
            thumb_hover_bg="#3f3f46",
            auto_hide=True,
        )
        self.adapter_hscroll.grid(row=1, column=0, sticky="ew")
        self.canvas_adapters.configure(xscrollcommand=self.adapter_hscroll.set)
        self.canvas_adapters.bind("<Button-1>", self._on_adapter_card_click)
        self.canvas_adapters.bind("<Motion>", self._on_adapter_card_motion)
        self.canvas_adapters.bind("<Leave>", self._on_adapter_card_leave)
        self.canvas_adapters.bind("<Shift-MouseWheel>", self._on_adapter_mousewheel)
        self.canvas_adapters.bind("<MouseWheel>", self._on_adapter_mousewheel)
        self.tooltip.bind_widget(
            self.canvas_adapters,
            "NETWORK ADAPTER BENTO CARDS",
            "Click any network adapter card button to enable or disable it in the bonding pool.",
            delay_ms=550,
        )

        self.canvas_chart = tk.Canvas(
            c01,
            bg=self.BG_PANEL,
            highlightthickness=0,
            bd=0,
        )
        self.canvas_chart.grid(row=3, column=0, sticky="nsew")
        self.canvas_chart.bind("<Motion>", self._on_chart_hover)
        self.canvas_chart.bind("<Leave>", self._on_chart_leave)

        # -----------------------------------------------------------------
        # CONTAINER 2: 02 / APPLICATION ROUTER (Matches Web UI Section 02)
        # -----------------------------------------------------------------
        c02 = tk.Frame(self.root, bg=self.BG_PANEL)
        c02.grid(row=1, column=1, sticky="nsew", padx=0, pady=(0, 1))
        c02.grid_columnconfigure(0, weight=1)
        c02.grid_rowconfigure(0, weight=0)
        c02.grid_rowconfigure(1, weight=0)
        c02.grid_rowconfigure(2, weight=0)
        c02.grid_rowconfigure(3, weight=0)
        c02.grid_rowconfigure(4, weight=1)

        c02_head = tk.Frame(c02, bg=self.BG_PANEL, padx=18, pady=12)
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
        ).pack(anchor="w", pady=(2, 0))

        self.lbl_running_badge = tk.Label(
            c02_head,
            text="RUNNING APPS",
            bg=self.BG_PANEL,
            fg=self.TEXT_MUTED,
            font=("Consolas", 8),
        )
        self.lbl_running_badge.pack(side=tk.RIGHT, anchor="s")

        tk.Frame(c02, bg=self.BG_HAIRLINE, height=1).grid(row=1, column=0, sticky="ew")

        # Router Toolbar matching Web UI (.router-toolbar)
        toolbar = tk.Frame(c02, bg="#08080b", padx=18, pady=9)
        toolbar.grid(row=2, column=0, sticky="ew")
        toolbar_actions = tk.Frame(toolbar, bg="#08080b")
        toolbar_actions.pack(fill=tk.X)

        left_controls = tk.Frame(toolbar_actions, bg="#08080b")
        left_controls.pack(side=tk.LEFT)

        self.dd_app_filter = StudioDropdown(
            left_controls,
            self.root,
            width_px=132,
            placeholder="All programs",
        )
        self.dd_app_filter.pack(side=tk.LEFT, padx=(0, 6))
        self.dd_app_filter.set_items([
            {"value": "ALL", "label": "All programs"},
            {"value": "APPS", "label": "Apps"},
            {"value": "SERVICES", "label": "Services"},
            {"value": "FAVORITES", "label": "Favorites"},
        ])
        self.dd_app_filter.set_value("ALL", "All programs")
        self.dd_app_filter.on_select = self._set_app_filter
        self.tooltip.bind_widget(
            self.dd_app_filter,
            "APPLICATION CATEGORY FILTER",
            "Choose which application group to show (All programs, Apps, Services, or Favorites).",
        )

        view_switch = tk.Frame(left_controls, bg="#08080b")
        view_switch.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_grid_view = self._make_studio_btn(
            view_switch,
            "▦ Grid",
            "GRID APPLICATION VIEW",
            "Show applications as a multi-column Bento grid.",
            variant="active",
            cmd=lambda: self._set_app_view("grid"),
            px=9,
            py=4,
        )
        self.btn_grid_view.pack(side=tk.LEFT, padx=(0, 4))
        self.btn_list_view = self._make_studio_btn(
            view_switch,
            "☷ List",
            "LIST APPLICATION VIEW",
            "Show applications in a full-width list.",
            variant="dark",
            cmd=lambda: self._set_app_view("list"),
            px=9,
            py=4,
        )
        self.btn_list_view.pack(side=tk.LEFT)

        self.dd_app_sort = StudioDropdown(
            left_controls,
            self.root,
            width_px=144,
            placeholder="Name: A-Z",
        )
        self.dd_app_sort.pack(side=tk.LEFT, padx=(0, 6))
        self.dd_app_sort.set_items([
            {"value": "AZ", "label": "Name: A-Z"},
            {"value": "ZA", "label": "Name: Z-A"},
            {"value": "FAST", "label": "Speed: High–Low"},
            {"value": "SLOW", "label": "Speed: Low–High"},
        ])
        self.dd_app_sort.set_value(self.app_sort_mode, "Name: A-Z")
        self.dd_app_sort.on_select = self._set_app_sort
        self.tooltip.bind_widget(
            self.dd_app_sort,
            "SORT APPLICATIONS",
            "Sort apps by name or current network speed.",
        )

        self.dd_app_color = StudioDropdown(
            left_controls,
            self.root,
            width_px=148,
            placeholder="Palette: Multi (16)",
        )
        self.dd_app_color.pack(side=tk.LEFT)
        self.dd_app_color.set_items([
            {"value": "MULTI", "label": "Palette: Multi (16)"},
            {"value": "CYAN", "label": "Theme: Sky Cyan"},
            {"value": "ORANGE", "label": "Theme: Sunset Orange"},
            {"value": "EMERALD", "label": "Theme: Emerald Mint"},
            {"value": "VIOLET", "label": "Theme: Royal Violet"},
            {"value": "AMBER", "label": "Theme: Amber Gold"},
            {"value": "ROSE", "label": "Theme: Rose Neon"},
            {"value": "CORAL", "label": "Theme: Coral Red"},
            {"value": "TEAL", "label": "Theme: Cyber Teal"},
            {"value": "INDIGO", "label": "Theme: Indigo Pulse"},
            {"value": "LIME", "label": "Theme: Lime Matrix"},
        ])
        self.dd_app_color.set_value("MULTI", "Palette: Multi (16)")
        self.dd_app_color.on_select = self._set_app_color_theme
        self.tooltip.bind_widget(
            self.dd_app_color,
            "APPLICATION CARD COLOR PALETTE",
            "Choose between the 16-color cycling palette or a unified studio color theme.",
        )

        right_actions = tk.Frame(toolbar_actions, bg="#08080b")
        right_actions.pack(side=tk.RIGHT)
        self._make_studio_btn(
            right_actions,
            "⌕ Scan",
            "SCAN RUNNING APPLICATIONS",
            "Refreshes active Windows processes, visible application windows, and open sockets.",
            variant="dark",
            cmd=self._refresh_process_dropdown,
            px=10,
            py=4,
        ).pack(side=tk.LEFT, padx=(0, 6))
        self._make_studio_btn(
            right_actions,
            "＋ Add Program",
            "ADD APPLICATION & ROUTING POLICY",
            "Choose an application or built-in engine and its network policy.",
            variant="amber",
            cmd=self._open_add_program_popup,
            px=11,
            py=4,
        ).pack(side=tk.LEFT)

        tk.Frame(c02, bg=self.BG_HAIRLINE, height=1).grid(row=3, column=0, sticky="ew")

        self.app_scroll_frame = tk.Frame(c02, bg=self.BG_PANEL)
        self.app_scroll_frame.grid(row=4, column=0, sticky="nsew")
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
        self.app_vscroll = StudioScrollbar(
            self.app_scroll_frame,
            orient=tk.VERTICAL,
            command=self.canvas_apps.yview,
            thickness=6,
            track_bg=self.BG_PANEL,
            thumb_bg="#272732",
            thumb_hover_bg="#3f3f46",
            auto_hide=True,
        )
        self.app_vscroll.grid(row=0, column=1, sticky="ns")
        self.canvas_apps.configure(
            yscrollcommand=self.app_vscroll.set,
            yscrollincrement=40,
        )
        self.canvas_apps.bind("<Button-1>", self._on_app_card_click)
        self.canvas_apps.bind("<Motion>", self._on_app_card_motion)
        self.canvas_apps.bind("<Leave>", self._on_app_card_leave)
        self.canvas_apps.bind("<MouseWheel>", self._on_app_mousewheel)

        # -----------------------------------------------------------------
        # CONTAINER 3: 03 / PARALLEL DOWNLOAD ENGINE (Matches Web UI .bottom-container)
        # -----------------------------------------------------------------
        c03 = tk.Frame(self.root, bg=self.BG_PANEL, padx=20, pady=14)
        c03.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=0, pady=0)

        tk.Label(
            c03,
            text="03 / PARALLEL RANGE & HLS (.M3U8) ENGINE · ENDGAME RACING",
            bg=self.BG_PANEL,
            fg=self.AMBER,
            font=("Consolas", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            c03,
            text="Download & Stream Accelerator",
            bg=self.BG_PANEL,
            fg=self.TEXT_MAIN,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", pady=(2, 10))

        url_bar_frame = tk.Frame(c03, bg=self.BG_PANEL)
        url_bar_frame.pack(fill=tk.X)

        tk.Label(
            url_bar_frame,
            text="URL",
            bg=self.BG_PANEL,
            fg=self.AMBER,
            font=("Consolas", 9, "bold"),
            padx=2,
            pady=7,
        ).pack(side=tk.LEFT, padx=(0, 8))

        self.ent_url = tk.Entry(
            url_bar_frame,
            bg="#0c0c12",
            fg=self.TEXT_MAIN,
            insertbackground=self.AMBER,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground="#22222c",
            highlightcolor=self.AMBER,
            font=("Consolas", 10),
        )
        self.ent_url.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=7)
        self.tooltip.bind_widget(
            self.ent_url,
            "STREAM OR FILE URL",
            "https://example.com/largefile.iso or https://example.com/stream.m3u8",
        )

        self._make_studio_btn(
            url_bar_frame,
            "⬇ Download",
            "START MULTI-NIC PARALLEL DOWNLOAD",
            "Download across bonded adapters using parallel HTTP ranges.",
            variant="primary",
            cmd=self._start_turbo_download,
            px=15,
            py=6,
        ).pack(side=tk.LEFT)

        self.canvas_dl_unified = tk.Canvas(
            c03,
            height=54,
            bg=self.BG_PANEL,
            highlightthickness=0,
            bd=0,
        )
        self.canvas_dl_unified.pack(fill=tk.X, pady=(10, 0))
        self.tooltip.bind_widget(
            self.canvas_dl_unified,
            "LIVE PROGRESS & MULTI-NIC BLOCK STRIP",
            "Top bar shows overall download progress; bottom row shows individual blocks color-coded by adapter.",
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
                "label": f"[ENGINE] {TURBO_APP_LABEL}",
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
                badge, col = "SVC", "#a1a1aa"

            friendly_lbl = getattr(p, "display_name", "") or p.exe_name
            label_str = (
                f"{friendly_lbl} ({p.exe_name})"
                if friendly_lbl.lower() != p.exe_name.lower()
                else p.exe_name
            )
            meta_parts = [f"PID {p.pid}"]
            if p.window_title:
                meta_parts.append(p.window_title[:24])
            elif p.has_active_socket:
                meta_parts.append("Active Socket")

            dd_items.append({
                "value": p.exe_name,
                "label": label_str,
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
                "label": "Auto / Bonded (All adapters)",
            },
            {
                "value": BLOCK_INTERNET_RULE,
                "label": "Block Internet",
            },
        ]
        for a in adapters:
            pol_items.append({
                "value": a.ip,
                "label": f"Pin to {a.name} ({self._mask_ip(a.ip)})",
            })
        self._policy_dropdown_items = pol_items
        if self.dd_policy is not None and self.dd_policy.winfo_exists():
            self.dd_policy.set_items(pol_items)

    def _assign_app_rule(self) -> bool:
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
        self._close_card_policy_popup()
        popup = tk.Toplevel(self.root)
        popup.title("Add application to OmniBond")
        popup.configure(bg="#30303b")
        popup.resizable(False, False)
        popup.transient(self.root)
        popup.grab_set()
        popup.geometry(f"460x360+{self.root.winfo_rootx() + 240}+{self.root.winfo_rooty() + 180}")

        def close_popup():
            if self.dd_app is not None:
                self.dd_app._close_popup()
            if self.dd_policy is not None:
                self.dd_policy._close_popup()
            self.dd_app = None
            self.dd_policy = None
            self.ent_custom_app = None
            popup.destroy()

        popup.protocol("WM_DELETE_WINDOW", close_popup)

        tk.Frame(popup, bg=self.AMBER, height=2).pack(fill=tk.X, side=tk.TOP)
        body = tk.Frame(popup, bg="#0c0c12", padx=20, pady=18)
        body.pack(fill=tk.BOTH, expand=True, padx=1, pady=(0, 1))

        tk.Label(
            body,
            text="Add application to OmniBond",
            bg="#0c0c12",
            fg=self.TEXT_MAIN,
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(0, 14))

        tk.Label(
            body,
            text="ENGINE / APPLICATION",
            bg="#0c0c12",
            fg=self.TEXT_MUTED,
            font=("Consolas", 8, "bold"),
        ).pack(anchor="w")
        self.dd_app = StudioDropdown(
            body,
            self.root,
            width_px=418,
            categories=["ALL", "USER APPS", "ACTIVE NET", "PINNED", "SERVICES / BG"],
            placeholder="Select a running application...",
        )
        self.dd_app.pack(fill=tk.X, pady=(6, 13))
        self.dd_app.set_items(self._process_dropdown_items)

        tk.Label(
            body,
            text="OR ENTER AN EXECUTABLE NAME",
            bg="#0c0c12",
            fg=self.TEXT_MUTED,
            font=("Consolas", 8, "bold"),
        ).pack(anchor="w")
        self.ent_custom_app = tk.Entry(
            body,
            bg="#09090d",
            fg=self.TEXT_MAIN,
            insertbackground=self.AMBER,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground="#30303b",
            highlightcolor=self.AMBER,
            font=("Segoe UI", 10),
        )
        self.ent_custom_app.pack(fill=tk.X, pady=(6, 13), ipady=6)

        tk.Label(
            body,
            text="NETWORK POLICY",
            bg="#0c0c12",
            fg=self.TEXT_MUTED,
            font=("Consolas", 8, "bold"),
        ).pack(anchor="w")
        self.dd_policy = StudioDropdown(
            body,
            self.root,
            width_px=418,
            categories=[],
            placeholder="Auto / Bonded (All adapters)",
        )
        self.dd_policy.pack(fill=tk.X, pady=(6, 14))
        self.dd_policy.set_items(self._policy_dropdown_items)

        actions = tk.Frame(body, bg="#0c0c12")
        actions.pack(fill=tk.X, side=tk.BOTTOM)
        self._make_studio_btn(
            actions,
            "Add & apply policy",
            "ADD APPLICATION AND APPLY POLICY",
            "Save the selected application with the chosen adapter policy.",
            variant="amber",
            cmd=lambda: self._assign_app_rule_and_close(popup),
            px=12,
            py=6,
        ).pack(side=tk.RIGHT, padx=(8, 0))
        self._make_studio_btn(
            actions,
            "Cancel",
            "CANCEL",
            "Close without adding an application.",
            variant="dark",
            cmd=close_popup,
            px=12,
            py=6,
        ).pack(side=tk.RIGHT)

    def _assign_app_rule_and_close(self, popup: tk.Toplevel):
        if self._assign_app_rule():
            if self.dd_app is not None:
                self.dd_app._close_popup()
            if self.dd_policy is not None:
                self.dd_policy._close_popup()
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
        self._set_btn_variant(self.btn_grid_view, "active" if self.app_view_mode == "grid" else "dark")
        self._set_btn_variant(self.btn_list_view, "active" if self.app_view_mode == "list" else "dark")
        self.canvas_apps.yview_moveto(0)
        self._draw_app_bento_cards(
            self._sort_app_entries(
                self._filter_app_entries(self.engine.routing_mgr.get_all_entries(only_running_or_added=True))
            ),
            self.engine.adapter_mgr.get_adapters(),
        )

    def _set_app_filter(self, mode: str):
        self.app_filter_mode = mode if mode in ("ALL", "APPS", "SERVICES", "FAVORITES") else "ALL"
        label = {
            "ALL": "All programs",
            "APPS": "Apps",
            "SERVICES": "Services",
            "FAVORITES": "Favorites",
        }[self.app_filter_mode]
        self.dd_app_filter.set_value(self.app_filter_mode, label)
        self.canvas_apps.yview_moveto(0)
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

    def _set_app_color_theme(self, theme: str):
        self.app_color_theme = theme or "MULTI"
        labels = {
            "MULTI": "Palette: Multi (16)",
            "CYAN": "Theme: Sky Cyan",
            "ORANGE": "Theme: Sunset Orange",
            "EMERALD": "Theme: Emerald Mint",
            "VIOLET": "Theme: Royal Violet",
            "AMBER": "Theme: Amber Gold",
            "ROSE": "Theme: Rose Neon",
            "CORAL": "Theme: Coral Red",
            "TEAL": "Theme: Cyber Teal",
            "INDIGO": "Theme: Indigo Pulse",
            "LIME": "Theme: Lime Matrix",
        }
        self.dd_app_color.set_value(self.app_color_theme, labels.get(self.app_color_theme, "Palette: Multi (16)"))
        self._update_ui()

    def _toggle_hide_ips(self):
        self.hide_ips = not self.hide_ips
        self.btn_hide_ips.configure(text="👁 Show IPs" if self.hide_ips else "👁 Hide IPs")
        self._set_btn_variant(self.btn_hide_ips, "active" if self.hide_ips else "dark")
        self._update_ui()

    def _sort_app_entries(self, entries: List[Dict]) -> List[Dict]:
        if self.app_sort_mode == "ZA":
            return sorted(entries, key=lambda entry: entry["display_name"].casefold(), reverse=True)
        if self.app_sort_mode == "FAST":
            return sorted(entries, key=lambda entry: (-entry.get("bps", 0.0), entry["display_name"].casefold()))
        if self.app_sort_mode == "SLOW":
            return sorted(entries, key=lambda entry: (entry.get("bps", 0.0), entry["display_name"].casefold()))
        return sorted(entries, key=lambda entry: entry["display_name"].casefold())

    def _close_card_policy_popup(self):
        if self._policy_popup is not None:
            try:
                self._policy_popup.destroy()
            except Exception:
                pass
            self._policy_popup = None

    def _show_card_policy_menu(
        self,
        app_key: str,
        x0_canvas: int,
        y0_canvas: int,
        x1_canvas: int,
        y1_canvas: int,
        accent_col: str,
    ):
        self._close_card_policy_popup()
        selected = self.engine.routing_mgr.get_rule(app_key)
        options: List[Tuple[str, str]] = [
            ("AUTO", "Auto / Bonded"),
            (BLOCK_INTERNET_RULE, "Block Internet"),
        ]
        options.extend(
            (adapter.ip, f"{adapter.name} ({self._mask_ip(adapter.ip)})")
            for adapter in self.engine.adapter_mgr.get_adapters()
        )

        pop = tk.Toplevel(self.root)
        pop.wm_overrideredirect(True)
        pop.attributes("-topmost", True)
        pop.configure(bg="#30303b")
        self._policy_popup = pop

        btn_w = max(180, int(x1_canvas - x0_canvas))
        row_h = 28
        pop_h = len(options) * row_h + 10

        root_x = self.canvas_apps.winfo_rootx() + int(x0_canvas - self.canvas_apps.canvasx(0))
        root_y_below = self.canvas_apps.winfo_rooty() + int(y1_canvas - self.canvas_apps.canvasy(0)) + 2
        root_y_above = self.canvas_apps.winfo_rooty() + int(y0_canvas - self.canvas_apps.canvasy(0)) - pop_h - 2
        screen_h = self.root.winfo_screenheight()
        screen_w = self.root.winfo_screenwidth()
        final_x = max(8, min(root_x, screen_w - btn_w - 8))
        final_y = root_y_above if (root_y_below + pop_h > screen_h - 32 and root_y_above > 8) else root_y_below
        pop.wm_geometry(f"{btn_w}x{pop_h}+{final_x}+{final_y}")

        inner = tk.Frame(pop, bg="#101016", padx=4, pady=4)
        inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        for value, label in options:
            is_sel = value == selected
            row_frame = tk.Frame(inner, bg="#1e1e28" if is_sel else "#101016", height=row_h)
            row_frame.pack(fill=tk.X)
            row_frame.pack_propagate(False)
            if is_sel:
                tk.Frame(row_frame, bg=accent_col, width=2).pack(side=tk.LEFT, fill=tk.Y)
            lbl = tk.Label(
                row_frame,
                text=label,
                bg="#1e1e28" if is_sel else "#101016",
                fg=accent_col if is_sel else self.TEXT_MAIN,
                font=("Segoe UI", 8, "bold"),
                anchor="w",
                padx=8,
                cursor="hand2",
            )
            lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            def on_enter(_e, rf=row_frame, lb=lbl):
                rf.configure(bg="#1e1e28")
                lb.configure(bg="#1e1e28", fg=accent_col)

            def on_leave(_e, rf=row_frame, lb=lbl, sel=is_sel):
                rf.configure(bg="#1e1e28" if sel else "#101016")
                lb.configure(bg="#1e1e28" if sel else "#101016", fg=accent_col if sel else self.TEXT_MAIN)

            def on_pick(_e, chosen=value):
                self._close_card_policy_popup()
                self._select_card_policy(app_key, chosen)

            for w_item in (row_frame, lbl):
                w_item.bind("<Enter>", on_enter)
                w_item.bind("<Leave>", on_leave)
                w_item.bind("<Button-1>", on_pick)

        pop.bind("<Escape>", lambda _e: self._close_card_policy_popup())
        pop.bind("<FocusOut>", lambda _e: self._close_card_policy_popup())
        pop.focus_force()

    def _select_card_policy(self, app_key: str, policy: str):
        self.engine.routing_mgr.set_rule(app_key, policy, explicit_add=True)
        self._update_ui()

    def _filter_app_entries(self, entries: List[Dict]) -> List[Dict]:
        if self.app_filter_mode == "APPS":
            return [
                entry for entry in entries
                if entry.get("is_running")
                and not entry.get("is_builtin")
                and entry.get("category") == "USER APPS"
            ]
        if self.app_filter_mode == "SERVICES":
            return [
                entry for entry in entries
                if entry.get("is_running") and entry.get("category") in ("SERVICES / BG", "ACTIVE NET")
            ]
        if self.app_filter_mode == "FAVORITES":
            return [entry for entry in entries if entry.get("is_favorite")]
        return entries

    def _on_app_mousewheel(self, event):
        self._close_card_policy_popup()
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

    def _on_adapter_card_motion(self, event):
        cx = self.canvas_adapters.canvasx(event.x)
        cy = self.canvas_adapters.canvasy(event.y)
        hov_ip = ""
        for x0, y0, x1, y1, ip in self._adapter_card_regions:
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                hov_ip = ip
                break
        if hov_ip != self._hovered_adapter_ip:
            self._hovered_adapter_ip = hov_ip
            self._draw_adapter_bento_cards(self.engine.adapter_mgr.get_adapters())

    def _on_adapter_card_leave(self, _event):
        if self._hovered_adapter_ip:
            self._hovered_adapter_ip = ""
            self._draw_adapter_bento_cards(self.engine.adapter_mgr.get_adapters())

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

    def _on_app_card_leave(self, _event):
        self.tooltip.hide()
        if self._hovered_app_key:
            self._hovered_app_key = ""
            entries = self.engine.routing_mgr.get_all_entries(only_running_or_added=True)
            self._draw_app_bento_cards(
                self._sort_app_entries(self._filter_app_entries(entries)),
                self.engine.adapter_mgr.get_adapters(),
            )

    def _on_app_card_motion(self, event):
        canvas_x = self.canvas_apps.canvasx(event.x)
        canvas_y = self.canvas_apps.canvasy(event.y)

        hov_app = ""
        for bx0, by0, bx1, by1, a_key in self._app_card_bounds:
            if bx0 <= canvas_x <= bx1 and by0 <= canvas_y <= by1:
                hov_app = a_key
                break
        if hov_app != self._hovered_app_key:
            self._hovered_app_key = hov_app
            entries = self.engine.routing_mgr.get_all_entries(only_running_or_added=True)
            self._draw_app_bento_cards(
                self._sort_app_entries(self._filter_app_entries(entries)),
                self.engine.adapter_mgr.get_adapters(),
            )

        for x0, y0, x1, y1, rtype, app_key, _pid, _accent in self._app_card_regions:
            if x0 <= canvas_x <= x1 and y0 <= canvas_y <= y1:
                desc_key = f"{rtype}:{app_key}"
                if desc_key != self._last_Hovered_region_desc:
                    self._last_Hovered_region_desc = desc_key
                    if rtype == "focus":
                        self.tooltip.schedule(
                            f"FOCUS ({app_key.upper()})\nBring the program window forward.",
                            delay_ms=280,
                        )
                    elif rtype == "favorite":
                        self.tooltip.schedule(
                            f"FAVORITE ({app_key.upper()})\nAdd or remove this program from Favorites.",
                            delay_ms=280,
                        )
                    elif rtype == "location":
                        self.tooltip.schedule(
                            f"LOCATION ({app_key.upper()})\nOpen this program's file or installation location.",
                            delay_ms=280,
                        )
                    elif rtype == "policy":
                        self.tooltip.schedule(
                            f"ROUTING POLICY ({app_key.upper()})\nSelect and apply a routing policy for this application.",
                            delay_ms=350,
                        )
                return
        self._last_Hovered_region_desc = ""
        self.tooltip.hide()

    def _on_app_card_click(self, event):
        canvas_x = self.canvas_apps.canvasx(event.x)
        canvas_y = self.canvas_apps.canvasy(event.y)
        for x0, y0, x1, y1, rtype, app_key, last_pid, accent_col in self._app_card_regions:
            if x0 <= canvas_x <= x1 and y0 <= canvas_y <= y1:
                if rtype == "focus":
                    self._close_card_policy_popup()
                    ok, msg = self.engine.process_mapper.focus_or_locate_app(app_key, last_pid)
                    if not ok:
                        messagebox.showinfo("Application", msg)
                    return
                if rtype == "location":
                    self._close_card_policy_popup()
                    ok, msg = self.engine.process_mapper.locate_app(app_key, last_pid)
                    if not ok:
                        if messagebox.askyesno("Program Location", f"{msg}\n\nChoose the executable or installation folder now?"):
                            self._choose_app_location(app_key)
                    return
                if rtype == "favorite":
                    self._close_card_policy_popup()
                    saved = self.engine.routing_mgr.set_favorite(
                        app_key, not self.engine.routing_mgr.is_favorite(app_key)
                    )
                    if not saved:
                        messagebox.showwarning("Favorites", "Could not update favorite.")
                    self._update_ui()
                    return
                if rtype == "policy":
                    self._show_card_policy_menu(app_key, x0, y0, x1, y1, accent_col)
                    return
        self._close_card_policy_popup()

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
        self._close_card_policy_popup()
        window = tk.Toplevel(self.root)
        window.title("Network Tuning")
        window.configure(bg="#30303b")
        window.geometry("680x680")
        window.minsize(560, 520)
        window.transient(self.root)
        window.grab_set()

        tk.Frame(window, bg=self.AMBER, height=2).pack(fill=tk.X, side=tk.TOP)
        panel = tk.Frame(window, bg="#0c0c12", padx=20, pady=18)
        panel.pack(fill=tk.BOTH, expand=True, padx=1, pady=(0, 1))

        tk.Label(
            panel,
            text="Network Tuning",
            bg="#0c0c12",
            fg=self.TEXT_MAIN,
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(0, 12))

        options = {
            "keep_multi_nic": tk.BooleanVar(value=self._network_tuning_options["keep_multi_nic"]),
            "ipv4": tk.BooleanVar(value=self._network_tuning_options["ipv4"]),
            "ipv6": tk.BooleanVar(value=self._network_tuning_options["ipv6"]),
        }
        option_specs = (
            (
                "keep_multi_nic",
                "Keep multiple adapters active",
                "Disable Windows connection minimization so Wi-Fi, Ethernet, and tethering can remain available together.",
            ),
            (
                "ipv4",
                "Balance IPv4 routes",
                "Set active IPv4 interface metrics to the OmniBond preferred value.",
            ),
            (
                "ipv6",
                "Balance IPv6 routes",
                "Set active IPv6 interface metrics to the OmniBond preferred value.",
            ),
        )
        for key, heading, subtext in option_specs:
            box = tk.Frame(
                panel,
                bg="#101016",
                highlightthickness=1,
                highlightbackground="#272732",
                padx=12,
                pady=9,
            )
            box.pack(fill=tk.X, pady=4)
            cb = tk.Checkbutton(
                box,
                text=heading,
                variable=options[key],
                bg="#101016",
                fg=self.TEXT_MAIN,
                activebackground="#101016",
                activeforeground=self.TEXT_MAIN,
                selectcolor="#14141c",
                font=("Segoe UI", 9, "bold"),
                anchor="w",
            )
            cb.pack(fill=tk.X)
            tk.Label(
                box,
                text=subtext,
                bg="#101016",
                fg=self.TEXT_MUTED,
                font=("Segoe UI", 8),
                anchor="w",
                justify=tk.LEFT,
                wraplength=600,
            ).pack(fill=tk.X, padx=(24, 0), pady=(2, 0))

        tk.Label(
            panel,
            text="PER-ADAPTER DATA & SPEED LIMITS",
            bg="#0c0c12",
            fg=self.AMBER,
            font=("Consolas", 9, "bold"),
        ).pack(anchor="w", pady=(14, 4))
        tk.Label(
            panel,
            text=(
                "Data caps count all adapter traffic; at the cap, OmniBond excludes the adapter from new connections "
                "without disrupting existing ones or other Windows apps. Custom upload/download limits apply to "
                "OmniBond-routed traffic only. Choose Unlimited or Custom for each cap and speed."
            ),
            bg="#0c0c12",
            fg=self.TEXT_MUTED,
            font=("Segoe UI", 8),
            justify=tk.LEFT,
            wraplength=620,
        ).pack(fill=tk.X, pady=(0, 8))

        limits_frame = tk.Frame(panel, bg="#0c0c12")
        limits_frame.pack(fill=tk.BOTH, expand=True)
        limits_frame.grid_rowconfigure(0, weight=1)
        limits_frame.grid_columnconfigure(0, weight=1)
        limits_canvas = tk.Canvas(
            limits_frame,
            bg="#0c0c12",
            highlightthickness=0,
            bd=0,
        )
        limits_canvas.grid(row=0, column=0, sticky="nsew")
        limits_scrollbar = StudioScrollbar(
            limits_frame,
            orient=tk.VERTICAL,
            command=limits_canvas.yview,
            thickness=6,
            track_bg="#0c0c12",
            thumb_bg="#272732",
            thumb_hover_bg="#3f3f46",
            auto_hide=True,
        )
        limits_scrollbar.grid(row=0, column=1, sticky="ns")
        limits_canvas.configure(yscrollcommand=limits_scrollbar.set)
        limits_content = tk.Frame(limits_canvas, bg="#0c0c12")
        limits_window_id = limits_canvas.create_window((0, 0), window=limits_content, anchor="nw")
        limits_content.bind(
            "<Configure>",
            lambda _event: limits_canvas.configure(scrollregion=limits_canvas.bbox("all")),
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

        def add_dropdown(parent, variable, values, width=11, command=None):
            dropdown = tk.OptionMenu(parent, variable, *values, command=command)
            dropdown.configure(
                bg="#14141b",
                fg=self.TEXT_MAIN,
                activebackground="#1f1f2c",
                activeforeground=self.TEXT_MAIN,
                highlightthickness=1,
                highlightbackground="#272732",
                relief=tk.FLAT,
                bd=0,
                width=width,
                font=("Segoe UI", 8, "bold"),
                anchor="w",
            )
            dropdown["menu"].configure(
                bg="#101016",
                fg=self.TEXT_MAIN,
                activebackground="#1e1e28",
                activeforeground=self.TEXT_MAIN,
                font=("Segoe UI", 8, "bold"),
                bd=0,
            )
            return dropdown

        for adapter in adapters:
            snapshot = self.engine.adapter_mgr.get_adapter_limit_snapshot(adapter)
            card = tk.Frame(
                limits_content,
                bg="#101016",
                highlightthickness=1,
                highlightbackground="#272732",
                padx=12,
                pady=10,
            )
            card.pack(fill=tk.X, pady=(0, 6))
            tk.Label(
                card,
                text=f"{adapter.name}  ·  {adapter.kind}",
                bg="#101016",
                fg=self.TEXT_MAIN,
                font=("Segoe UI", 9, "bold"),
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
                    padx=(0, 6) if column == 0 else (6, 0),
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
            data_mode = tk.StringVar(value="Custom" if snapshot["data_limit_bytes"] else "Unlimited")
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
            data_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
            add_dropdown(
                data_mode_wrap,
                data_mode,
                ("Unlimited", "Custom"),
                width=9,
                command=lambda choice, entry=data_entry: entry.configure(
                    state=tk.NORMAL if choice == "Custom" else tk.DISABLED
                ),
            ).pack(side=tk.RIGHT, padx=(4, 0))

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
            cycle_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
            cycle_unit_var = tk.StringVar(value=cycle_unit)
            add_dropdown(cycle_wrap, cycle_unit_var, ("minutes", "hours", "days"), width=8).pack(
                side=tk.RIGHT, padx=(4, 0)
            )

            dl_cell = add_field(card, "DOWNLOAD LIMIT (Mbps)", 2, 0)
            download_mode = tk.StringVar(
                value="Custom" if snapshot["download_limit_mbps"] > 0 else "Unlimited"
            )
            dl_wrap = tk.Frame(dl_cell, bg="#101016")
            dl_wrap.pack(fill=tk.X)
            download_entry = tk.Entry(
                dl_wrap,
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
            if snapshot["download_limit_mbps"] > 0:
                download_entry.insert(0, f"{snapshot['download_limit_mbps']:g}")
            else:
                download_entry.configure(state=tk.DISABLED)
            download_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
            add_dropdown(
                dl_wrap,
                download_mode,
                ("Unlimited", "Custom"),
                width=9,
                command=lambda choice, entry=download_entry: entry.configure(
                    state=tk.NORMAL if choice == "Custom" else tk.DISABLED
                ),
            ).pack(side=tk.RIGHT, padx=(4, 0))

            ul_cell = add_field(card, "UPLOAD LIMIT (Mbps)", 2, 1)
            upload_mode = tk.StringVar(
                value="Custom" if snapshot["upload_limit_mbps"] > 0 else "Unlimited"
            )
            ul_wrap = tk.Frame(ul_cell, bg="#101016")
            ul_wrap.pack(fill=tk.X)
            upload_entry = tk.Entry(
                ul_wrap,
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
            upload_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
            add_dropdown(
                ul_wrap,
                upload_mode,
                ("Unlimited", "Custom"),
                width=9,
                command=lambda choice, entry=upload_entry: entry.configure(
                    state=tk.NORMAL if choice == "Custom" else tk.DISABLED
                ),
            ).pack(side=tk.RIGHT, padx=(4, 0))

            reset_at = time.strftime(
                "%Y-%m-%d %H:%M",
                time.localtime(snapshot["period_started_at"] + cycle_hours * 3600),
            )
            current_cap = (
                self._fmt_bytes(snapshot["data_limit_bytes"])
                if snapshot["data_limit_bytes"]
                else "No data cap"
            )
            status_text = (
                "LIMIT REACHED · excluded from new OmniBond connections"
                if snapshot["quota_exceeded"]
                else f"{self._fmt_bytes(snapshot['usage_bytes'])} / {current_cap} · window resets {reset_at}"
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
                    cycle_multiplier = {"minutes": 1 / 60, "hours": 1, "days": 24}[unit_var.get()]
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
                status.configure(text=message, fg="#34d399" if ok else "#f87171")
                if ok:
                    self._update_ui()

            self._make_studio_btn(
                card,
                "Save Limits",
                "SAVE ADAPTER LIMITS",
                "Save the data cap, reset window, and speed limits for this adapter.",
                variant="amber",
                cmd=save_limits,
                px=9,
                py=4,
            ).grid(row=3, column=1, sticky="e", pady=(4, 0))

        optimization_status = tk.Label(
            panel,
            text="",
            bg="#0c0c12",
            fg=self.TEXT_MUTED,
            font=("Consolas", 8),
            justify=tk.LEFT,
            wraplength=620,
        )
        optimization_status.pack(fill=tk.X, pady=(8, 4))

        actions = tk.Frame(panel, bg="#0c0c12")
        actions.pack(fill=tk.X, pady=(6, 0))

        def apply_options():
            selected = {key: variable.get() for key, variable in options.items()}
            ok, msg = self.engine.sys_opt.optimize_multi_nic(
                keep_multi_nic=selected["keep_multi_nic"],
                optimize_ipv4=selected["ipv4"],
                optimize_ipv6=selected["ipv6"],
            )
            if ok:
                self._network_tuning_options.update(selected)
            optimization_status.configure(text=msg, fg="#34d399" if ok else "#f87171")

        self._make_studio_btn(
            actions,
            "Apply settings",
            "APPLY NETWORK TUNING",
            "Apply the selected Windows multi-network, IPv4, and IPv6 route settings.",
            variant="amber",
            cmd=apply_options,
            px=12,
            py=6,
        ).pack(side=tk.RIGHT, padx=(8, 0))
        self._make_studio_btn(
            actions,
            "Close",
            "CLOSE NETWORK TUNING",
            "Close Network Tuning dialog.",
            variant="dark",
            cmd=window.destroy,
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
        self.btn_graph_mode.configure(text="∿ Master Speed" if master else "⇄ Bonded Speed")
        self._set_btn_variant(self.btn_graph_mode, "dark" if master else "active")

    # -----------------------------------------------------------------
    # 01: ADAPTER BENTO CARDS (Matches Web UI #adapterBentoGrid .bento-card)
    # -----------------------------------------------------------------

    def _draw_adapter_bento_cards(self, adapters: List[NetworkAdapter]):
        c = self.canvas_adapters
        c.delete("all")
        self._adapter_card_regions.clear()

        w = max(280, c.winfo_width())
        h = max(182, c.winfo_height())
        cell_w = 280.0
        content_w = max(w, int(cell_w * max(1, len(adapters))))

        for idx, a in enumerate(adapters):
            x0 = int(idx * cell_w)
            x1 = int((idx + 1) * cell_w)
            y0, y1 = 0, h - 1
            self._adapter_card_regions.append((x0, y0, x1, y1, a.ip))

            card_bg = self.BG_CARD_HOVER if a.ip == self._hovered_adapter_ip else self.BG_PANEL
            c.create_rectangle(x0, 0, x1, h - 1, fill=card_bg, outline="")
            c.create_line(x1 - 1, 0, x1 - 1, h - 1, fill=self.BG_HAIRLINE)
            c.create_line(x0, h - 1, x1, h - 1, fill=self.BG_HAIRLINE)

            pad_x = x0 + 16
            # Top row: 01 sharp badge + IPV4 · ip ↗
            c.create_rectangle(pad_x, 14, pad_x + 25, 31, fill=a.color, outline="")
            c.create_text(
                pad_x + 12.5, 22.5,
                text=f"{idx + 1:02d}",
                fill="#09090b",
                font=("Consolas", 8, "bold"),
            )
            c.create_text(
                x1 - 16, 22.5,
                text=f"IPV4 · {self._mask_ip(a.ip)} ↗",
                fill=self.TEXT_MUTED,
                anchor="e",
                font=("Consolas", 8),
            )

            # Identity row: 34x34 rounded icon (radius=6) + Name + rounded Kind badge (radius=3)
            self._draw_rounded_rect(
                c, pad_x, 42, pad_x + 34, 76,
                radius=6.0,
                fill=a.badge_bg,
                outline=a.badge_bg,
            )
            c.create_text(
                pad_x + 17, 59,
                text=a.kind[:2].upper(),
                fill="#ffffff",
                font=("Segoe UI", 9, "bold"),
            )

            title_x = pad_x + 44
            kind_txt = a.kind
            kind_w = len(kind_txt) * 6 + 12
            avail_name_px = max(60, (x1 - 16) - title_x - kind_w - 8)
            max_name_chars = max(8, int(avail_name_px // 7))
            short_name = a.name if len(a.name) <= max_name_chars else a.name[: max_name_chars - 1] + "…"
            tid = c.create_text(
                title_x, 50,
                text=short_name,
                fill=self.TEXT_MAIN,
                anchor="w",
                font=("Segoe UI", 10, "bold"),
            )
            tb = c.bbox(tid)
            kx0 = (tb[2] + 6) if tb else (title_x + len(short_name) * 7 + 6)
            if kx0 + kind_w <= x1 - 12:
                subtle_kind_bd = self._blend_hex("#14141d", a.color, 0.32)
                self._draw_rounded_rect(
                    c, kx0, 42, kx0 + kind_w, 58,
                    radius=3.0,
                    fill="#14141d",
                    outline=subtle_kind_bd,
                )
                c.create_text(
                    kx0 + kind_w / 2, 50,
                    text=kind_txt,
                    fill=a.color,
                    font=("Consolas", 8, "bold"),
                )

            c.create_text(
                title_x, 67,
                text=f"{a.latency_ms:.1f}ms RTT · {a.active_conns} Conns",
                fill=self.TEXT_MUTED,
                anchor="w",
                font=("Segoe UI", 8),
            )

            # Status box (subtle 1px border matching rgba(16, 185, 129, 0.35))
            limits = self.engine.adapter_mgr.get_adapter_limit_snapshot(a)
            if limits["quota_exceeded"]:
                pill_text, pill_fg, pill_bg, pill_bd = (
                    "DATA CAP REACHED", "#f87171", "#201114", "#6b2128"
                )
            elif a.enabled:
                pill_text, pill_fg, pill_bg, pill_bd = (
                    f"ACTIVE · {a.kind.upper()}", "#34d399", "#0c1f1b", "#14533e"
                )
            else:
                pill_text, pill_fg, pill_bg, pill_bd = (
                    "DISABLED", "#34d399", "#0c1f1b", "#14533e"
                )
            pill_w = len(pill_text) * 6 + 14
            c.create_rectangle(pad_x, 86, pad_x + pill_w, 104, fill=pill_bg, outline=pill_bd, width=1)
            c.create_text(
                pad_x + 7, 95,
                text=pill_text,
                fill=pill_fg,
                anchor="w",
                font=("Consolas", 8, "bold"),
            )

            # Traffic & Live Speed line matching Web UI
            c.create_text(
                pad_x, 120,
                text=(
                    f"Traffic: {self._fmt_bytes(self._adapter_traffic_bytes(a, self.graph_mode))} · "
                    f"Live: {self._fmt_speed(self._adapter_speed(a, self.graph_mode))}"
                ),
                fill=self.TEXT_DIM,
                anchor="w",
                font=("Segoe UI", 8),
            )

            # Bottom Action Button
            btn_y0, btn_y1 = h - 40, h - 12
            btn_bg = "#14141c" if a.ip == self._hovered_adapter_ip else "#09090d"
            btn_bd = self.AMBER if (a.ip == self._hovered_adapter_ip and not limits["quota_exceeded"]) else "#272732"
            c.create_rectangle(pad_x, btn_y0, x1 - 16, btn_y1, fill=btn_bg, outline=btn_bd, width=1)
            c.create_text(
                (pad_x + x1 - 16) / 2,
                (btn_y0 + btn_y1) / 2,
                text=(
                    "LIMIT REACHED · WAIT FOR RESET"
                    if limits["quota_exceeded"]
                    else ("BONDED · CLICK TO TOGGLE" if a.enabled else "DISABLED · CLICK TO ENABLE")
                ),
                fill=self.TEXT_DIM if limits["quota_exceeded"] else self.TEXT_MAIN,
                font=("Segoe UI", 8, "bold"),
            )

        if content_w > w:
            c.create_rectangle(len(adapters) * cell_w, 0, content_w, h - 1, fill=self.BG_PANEL, outline="")
            c.create_line(0, h - 1, content_w, h - 1, fill=self.BG_HAIRLINE)
        else:
            c.create_line(0, h - 1, w, h - 1, fill=self.BG_HAIRLINE)
        c.configure(scrollregion=(0, 0, content_w, h))

    # -----------------------------------------------------------------
    # 02: APPLICATION BENTO CARDS (Matches Web UI #appBentoGrid .bento-card)
    # -----------------------------------------------------------------

    def _draw_app_bento_cards(self, entries: List[Dict], adapters: List[NetworkAdapter]):
        c = self.canvas_apps
        c.delete("all")
        self._app_card_regions.clear()
        self._app_card_bounds.clear()

        w = max(480, c.winfo_width())
        cols = 1 if self.app_view_mode == "list" else max(1, int(w // 245))
        items = entries
        rows = max(1, math.ceil(max(1, len(items)) / cols))
        cell_w = w / cols
        cell_h = 212  # Generous vertical space matching Web UI min-height: 208px
        content_h = max(c.winfo_height(), rows * cell_h)

        ip_to_name = {a.ip: a.name for a in adapters}

        for idx, r in enumerate(items):
            row = idx // cols
            col = idx % cols
            x0 = int(col * cell_w)
            x1 = int((col + 1) * cell_w)
            y0 = int(row * cell_h)
            y1 = int((row + 1) * cell_h)

            app_key = r["app_name"]
            self._app_card_bounds.append((x0, y0, x1, y1, app_key))

            is_hov = app_key == self._hovered_app_key
            card_bg = self.BG_CARD_HOVER if is_hov else self.BG_PANEL
            c.create_rectangle(x0, y0, x1, y1, fill=card_bg, outline="")
            c.create_line(x1 - 1, y0, x1 - 1, y1, fill=self.BG_HAIRLINE)
            c.create_line(x0, y1 - 1, x1, y1 - 1, fill=self.BG_HAIRLINE)

            accent_col, _fill_dark = self._get_app_accent(idx)
            pad_x = x0 + 16
            right_x = x1 - 16

            # 1. Card Top Row: Number badge on left + [★] [▣ FOCUS] [↗ LOCATION] on right
            c.create_rectangle(pad_x, y0 + 15, pad_x + 25, y0 + 32, fill=accent_col, outline="")
            c.create_text(
                pad_x + 12.5, y0 + 23.5,
                text=f"{idx + 1:02d}",
                fill="#09090b",
                font=("Consolas", 8, "bold"),
            )

            loc_x1 = right_x
            loc_x0 = loc_x1 - 72
            foc_x1 = loc_x0 - 5
            foc_x0 = foc_x1 - 72
            fav_x1 = foc_x0 - 5
            fav_x0 = fav_x1 - 28
            ctl_y0, ctl_y1 = y0 + 11, y0 + 37

            favorite = bool(r.get("is_favorite"))
            c.create_rectangle(
                fav_x0, ctl_y0, fav_x1, ctl_y1,
                fill="#121218",
                outline=self.AMBER if favorite else "#30303b",
                width=1,
            )
            c.create_text(
                (fav_x0 + fav_x1) / 2, (ctl_y0 + ctl_y1) / 2,
                text="★" if favorite else "☆",
                fill=self.AMBER if favorite else self.TEXT_MAIN,
                font=("Segoe UI Symbol", 10, "bold"),
            )
            self._app_card_regions.append((fav_x0, ctl_y0, fav_x1, ctl_y1, "favorite", app_key, r["last_pid"], accent_col))

            c.create_rectangle(foc_x0, ctl_y0, foc_x1, ctl_y1, fill="#121218", outline="#30303b", width=1)
            c.create_text(
                (foc_x0 + foc_x1) / 2, (ctl_y0 + ctl_y1) / 2,
                text="▣ FOCUS",
                fill=self.TEXT_MAIN,
                font=("Consolas", 8, "bold"),
            )
            self._app_card_regions.append((foc_x0, ctl_y0, foc_x1, ctl_y1, "focus", app_key, r["last_pid"], accent_col))

            c.create_rectangle(loc_x0, ctl_y0, loc_x1, ctl_y1, fill="#121218", outline="#30303b", width=1)
            c.create_text(
                (loc_x0 + loc_x1) / 2, (ctl_y0 + ctl_y1) / 2,
                text="↗ LOCATION",
                fill=self.TEXT_MAIN,
                font=("Consolas", 8, "bold"),
            )
            self._app_card_regions.append((loc_x0, ctl_y0, loc_x1, ctl_y1, "location", app_key, r["last_pid"], accent_col))

            # 2. Card Identity Row (34x34 rounded Icon + Main Title + rounded Exe Badge + Subtitle)
            main_title, sub_ext = self._split_app_title(r["display_name"], app_key)
            if r["rule"] == BLOCK_INTERNET_RULE:
                sub_desc = "Internet Disabled"
            elif r.get("window_title"):
                sub_desc = r["window_title"]
            elif r.get("is_running"):
                pid_str = r.get("last_pid") or "-"
                if r.get("category") == "SERVICES / BG":
                    sub_desc = f"Background Service · PID {pid_str}"
                else:
                    sub_desc = f"Running Process · PID {pid_str}"
            else:
                sub_desc = "Pinned Rule"

            subtle_icon_bd = self._blend_hex("#14141d", accent_col, 0.40)
            self._draw_rounded_rect(
                c, pad_x, y0 + 48, pad_x + 34, y0 + 82,
                radius=6.0,
                fill="#14141d",
                outline=subtle_icon_bd,
            )
            c.create_text(
                pad_x + 17, y0 + 65,
                text=main_title[:2].upper(),
                fill=accent_col,
                font=("Segoe UI", 9, "bold"),
            )

            title_x = pad_x + 44
            avail_px = max(80, right_x - title_x)
            ext_txt = sub_ext if len(sub_ext) <= 15 else sub_ext[:14] + "…"
            badge_px = (len(ext_txt) * 6 + 12) if ext_txt else 0
            max_p1_chars = max(8, int((avail_px - badge_px - 6) // 7.2))
            short_p1 = main_title if len(main_title) <= max_p1_chars else main_title[: max_p1_chars - 1] + "…"
            t_id = c.create_text(
                title_x, y0 + 56,
                text=short_p1,
                fill=self.TEXT_MAIN,
                anchor="w",
                font=("Segoe UI", 10, "bold"),
            )
            bbox = c.bbox(t_id)
            next_x = (bbox[2] + 6) if bbox else (title_x + len(short_p1) * 7 + 6)
            if ext_txt and next_x + badge_px <= right_x:
                subtle_ext_bd = self._blend_hex("#14141d", accent_col, 0.34)
                self._draw_rounded_rect(
                    c, next_x, y0 + 48, next_x + badge_px, y0 + 64,
                    radius=3.0,
                    fill="#14141d",
                    outline=subtle_ext_bd,
                )
                c.create_text(
                    next_x + badge_px / 2, y0 + 56,
                    text=ext_txt,
                    fill=accent_col,
                    font=("Consolas", 8, "bold"),
                )

            max_sub_chars = max(14, int(avail_px // 6.2))
            short_sub = sub_desc if len(sub_desc) <= max_sub_chars else sub_desc[: max_sub_chars - 1] + "…"
            c.create_text(
                title_x, y0 + 74,
                text=short_sub,
                fill=self.TEXT_MUTED,
                anchor="w",
                font=("Segoe UI", 8),
            )

            # 3. Sparkline Box (.sparkline-box: APP SPEED on left, speed on right, smooth gradient curve below)
            spk_x0, spk_y0 = pad_x, y0 + 93
            spk_x1, spk_y1 = right_x, y0 + 139
            c.create_rectangle(spk_x0, spk_y0, spk_x1, spk_y1, fill="#07070a", outline="#181820", width=1)
            c.create_text(
                spk_x0 + 7, spk_y0 + 10,
                text="APP SPEED",
                fill=self.TEXT_MUTED,
                anchor="w",
                font=("Consolas", 8),
            )
            c.create_text(
                spk_x1 - 7, spk_y0 + 10,
                text=self._fmt_speed(r.get("bps", 0.0)),
                fill=accent_col,
                anchor="e",
                font=("Consolas", 8, "bold"),
            )

            hist = r.get("bps_history", [])
            if len(hist) >= 2:
                max_app_bps = max(4096.0, max(hist) * 1.18)
                gw = max(20, (spk_x1 - spk_x0) - 8)
                gh = max(14, (spk_y1 - spk_y0) - 22)
                gx0 = spk_x0 + 4
                gy_base = spk_y1 - 3
                s_pts: List[Tuple[float, float]] = []
                for h_i, h_val in enumerate(hist):
                    px = gx0 + (h_i / (len(hist) - 1)) * gw
                    py = gy_base - min(1.0, max(0.0, h_val / max_app_bps)) * gh
                    s_pts.append((px, py))
                self._draw_smooth_curve_with_gradient(
                    c,
                    s_pts,
                    baseline_y=gy_base,
                    line_col=accent_col,
                    bg_col="#07070a",
                    line_width=1.7,
                    top_alpha=0.26,
                    bands=12,
                    draw_end_dot=True,
                )

            # 4. Telemetry Summary Line matching Web UI:
            # IP: <last_adapter_ip> · Conns: <active_connections> (<total_connections>) · <bytes>
            c.create_text(
                pad_x, y0 + 153,
                text=(
                    f"IP: {self._mask_ip(r['last_adapter_ip'])} · "
                    f"Conns: {r['active_connections']} ({r['total_connections']}) · "
                    f"{self._fmt_bytes(r['bytes_transferred'])}"
                ),
                fill=self.TEXT_DIM,
                anchor="w",
                font=("Segoe UI", 8),
            )

            # 5. Bottom Policy Selector: Neutral border (#22222c) while keeping inside text & chevron colored
            btn_y0, btn_y1 = y1 - 43, y1 - 12
            pol_bd = "#3a3a48" if is_hov else "#22222c"
            c.create_rectangle(pad_x, btn_y0, right_x, btn_y1, fill="#09090d", outline=pol_bd, width=1)
            selected_policy = r["rule"]
            if selected_policy == "AUTO":
                selected_name = "AUTO / BONDED"
            elif selected_policy == BLOCK_INTERNET_RULE:
                selected_name = "BLOCK INTERNET"
            else:
                nic_name = ip_to_name.get(selected_policy, selected_policy)
                selected_name = f"{nic_name} ({self._mask_ip(selected_policy)})".upper()

            max_pol_chars = max(14, int((right_x - pad_x - 28) // 6.5))
            short_pol = selected_name if len(selected_name) <= max_pol_chars else selected_name[: max_pol_chars - 1] + "…"
            c.create_text(
                pad_x + 10,
                (btn_y0 + btn_y1) / 2,
                text=short_pol,
                fill=accent_col,
                anchor="w",
                font=("Segoe UI", 8, "bold"),
            )
            c.create_text(
                right_x - 9,
                (btn_y0 + btn_y1) / 2,
                text="▾",
                fill=accent_col,
                anchor="e",
                font=("Consolas", 9, "bold"),
            )
            self._app_card_regions.append((pad_x, btn_y0, right_x, btn_y1, "policy", app_key, r["last_pid"], accent_col))

        c.configure(scrollregion=(0, 0, w, content_h))

    # -----------------------------------------------------------------
    # 01: GOOGLE-STYLE MULTI-NIC SPLINE CHART (Matches Web UI .chart-section)
    # -----------------------------------------------------------------

    def _draw_google_chart(self, adapters: List[NetworkAdapter]):
        c = self.canvas_chart
        c.delete("all")
        w = max(360, c.winfo_width())
        h = max(200, c.winfo_height())

        pad_l, pad_r, pad_b = 64, 18, 24

        total_bps = sum(self._adapter_speed(a, self.graph_mode) for a in adapters)
        if total_bps > self._peak_bps:
            self._peak_bps = total_bps

        # Row 1: Source label on left + Two separate speed chips (LIVE & PEAK) on right
        c.create_text(
            18, 19,
            text=(
                "MASTER SPEED · ALL COMPUTER NETWORK TRAFFIC"
                if self.graph_mode == "master"
                else "BONDED SPEED · OMNIBOND ROUTED TRAFFIC"
            ),
            fill=self.TEXT_MUTED,
            anchor="w",
            font=("Consolas", 8, "bold"),
        )

        peak_txt = f"PEAK {self._fmt_speed(self._peak_bps)}"
        live_txt = f"LIVE {self._fmt_speed(total_bps)}"
        peak_w = len(peak_txt) * 6.5 + 16
        live_w = len(live_txt) * 6.5 + 16

        px1 = w - 18
        px0 = px1 - peak_w
        lx1 = px0 - 8
        lx0 = lx1 - live_w

        c.create_rectangle(lx0, 7, lx1, 30, fill="#14141d", outline="#272732", width=1)
        c.create_text(
            (lx0 + lx1) / 2, 18.5,
            text=live_txt,
            fill=self.AMBER,
            font=("Consolas", 8, "bold"),
        )
        c.create_rectangle(px0, 7, px1, 30, fill="#14141d", outline="#272732", width=1)
        c.create_text(
            (px0 + px1) / 2, 18.5,
            text=peak_txt,
            fill=self.AMBER,
            font=("Consolas", 8, "bold"),
        )

        # Row 2: Legend pills (smooth circle dot + 01 · Name (Speed))
        leg_x, leg_y = 18, 42
        for idx, a in enumerate(adapters):
            lbl = f"{idx + 1:02d} · {a.name} ({self._fmt_speed(self._adapter_speed(a, self.graph_mode))})"
            item_width = 18 + len(lbl) * 6.2
            if leg_x + item_width > w - 14 and leg_x > 18:
                leg_x, leg_y = 18, leg_y + 16
            self._draw_rounded_rect(
                c, leg_x, leg_y - 4, leg_x + 8, leg_y + 4,
                radius=4.0,
                fill=a.color,
                outline=a.color,
            )
            tid = c.create_text(
                leg_x + 13, leg_y,
                text=lbl,
                fill=self.TEXT_MUTED,
                anchor="w",
                font=("Consolas", 8),
            )
            bbox = c.bbox(tid)
            leg_x = (bbox[2] + 16) if bbox else (leg_x + 150)

        pad_t = max(64, leg_y + 18)
        plot_w = max(1, w - pad_l - pad_r)
        plot_h = max(1, h - pad_t - pad_b)

        max_bps = 64 * 1024.0
        for a in adapters:
            history = self._adapter_speed_history(a, self.graph_mode)
            if history:
                max_bps = max(max_bps, max(history) * 1.18)

        rows = 4
        for r in range(rows + 1):
            y = pad_t + (plot_h / rows) * r
            val = max_bps * (1.0 - r / rows)
            line_col = "#27272a" if r == rows else "#18181f"
            dash_pat = () if r == rows else (3, 3)
            c.create_line(pad_l, y, w - pad_r, y, fill=line_col, dash=dash_pat)
            lbl_txt = "0 B/s" if val <= 1 else self._fmt_speed(val)
            c.create_text(
                pad_l - 8, y,
                text=lbl_txt,
                fill="#71717a",
                anchor="e",
                font=("Consolas", 8),
            )

        x_ticks = [("-60s", 0.0), ("-45s", 0.25), ("-30s", 0.50), ("-15s", 0.75), ("LIVE", 1.0)]
        for txt, frac in x_ticks:
            tx = pad_l + plot_w * frac
            c.create_text(
                tx, pad_t + plot_h + 10,
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

            self._draw_smooth_curve_with_gradient(
                c,
                ctrl_pts,
                baseline_y=baseline_y,
                line_col=a.color,
                bg_col=self.BG_PANEL,
                line_width=2.2,
                top_alpha=0.28,
                bands=20,
                draw_end_dot=False,
            )

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
            c.create_rectangle(bx0, by0, bx0 + box_w, by0 + box_h, fill="#121218", outline="#3f3f46", width=1)
            for l_idx, (txt, col) in enumerate(lines):
                c.create_text(
                    bx0 + 10, by0 + 13 + l_idx * 16,
                    text=txt,
                    fill=col,
                    anchor="w",
                    font=("Consolas", 8, "bold"),
                )

    # -----------------------------------------------------------------
    # 03: PROGRESS TRACK, META ROW & BLOCK STRIP (Matches Web UI Section 03)
    # -----------------------------------------------------------------

    def _draw_unified_turbo_bar(self):
        c = self.canvas_dl_unified
        c.delete("all")
        w = max(400, c.winfo_width())

        pct = min(100.0, max(0.0, self.engine.turbo.progress_pct))
        spd = self._fmt_speed(self.engine.turbo.speed_bps)

        # 1. 8px Progress Track at top (y=0..8) matching Web UI .progress-track
        c.create_rectangle(0, 0, w, 8, fill="#12121a", outline="")
        fill_w = int((pct / 100.0) * w)
        if fill_w > 0:
            c.create_rectangle(0, 0, fill_w, 8, fill=self.EMERALD if pct >= 100 else self.AMBER, outline="")

        # 2. Meta Row below progress track (y=21) matching Web UI .dl-meta-row
        c.create_text(
            0, 21,
            text=self.engine.turbo.status_text,
            fill=self.TEXT_MUTED,
            anchor="w",
            font=("Consolas", 9),
        )
        c.create_text(
            w, 21,
            text=f"{pct:.0f}% · {spd}",
            fill=self.AMBER,
            anchor="e",
            font=("Consolas", 9, "bold"),
        )

        # 3. Block Strip below meta row (y=34..44) matching Web UI .block-strip (.blk 12x10, gap 3px)
        blocks = self.engine.turbo.blocks[:160]
        bx = 0
        by = 34
        for b in blocks:
            if bx + 12 > w:
                break
            col = "#181822" if b.status == "pending" else b.color
            c.create_rectangle(bx, by, bx + 12, by + 10, fill=col, outline="")
            bx += 15

    def _update_ui(self):
        ep_host = self._mask_ip("127.0.0.1")
        self.lbl_server_endpoints.configure(
            text=(
                f"• HTTP/HTTPS {ep_host}:{self.engine.http_port}  "
                f"• SOCKS5 {ep_host}:{self.engine.socks_port}  "
                f"• Web Dashboard {ep_host}:{self.engine.web_port}"
            )
        )
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
            text=f"{enabled_adapter_count} / {len(adapters)} INTERFACES BONDED · {adapter_telemetry_label}"
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
        self._close_card_policy_popup()
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