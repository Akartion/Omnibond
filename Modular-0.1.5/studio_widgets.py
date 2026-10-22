#!/usr/bin/env python3
"""
OmniBond - Custom Dark Studio UI Components: Hover Tooltips, Scrollbars & Dropdowns.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from config import _TkFrameBase, tk

_TkCanvasBase = tk.Canvas if tk is not None else object

__all__ = ["StudioTooltip", "StudioDropdown", "StudioScrollbar"]

# =====================================================================
# 9. CUSTOM STUDIO UI COMPONENTS: HOVER TOOLTIPS, SCROLLBAR & DROPDOWN
# =====================================================================

class StudioTooltip:
    """
    Delayed dark-mode Studio Tooltip that explains what any button, dropdown,
    or interactive canvas control does when hovering the mouse over it.
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self._tip_win: Optional[tk.Toplevel] = None
        self._after_id: Optional[str] = None
        self._current_text: str = ""
        self._mouse_x: int = 0
        self._mouse_y: int = 0

    def bind_widget(self, widget: tk.Widget, title: str, description: str, delay_ms: int = 420):
        full_text = f"{title}\n{description}" if description else title

        def on_enter(event):
            self._mouse_x = event.x_root
            self._mouse_y = event.y_root
            self.schedule(full_text, delay_ms)

        def on_motion(event):
            self._mouse_x = event.x_root
            self._mouse_y = event.y_root

        def on_leave(_event):
            self.hide()

        widget.bind("<Enter>", on_enter, add="+")
        widget.bind("<Motion>", on_motion, add="+")
        widget.bind("<Leave>", on_leave, add="+")
        widget.bind("<ButtonPress>", on_leave, add="+")

    def schedule(self, text: str, delay_ms: int = 420):
        if text == self._current_text and self._tip_win is not None:
            return
        self.hide()
        self._current_text = text
        self._after_id = self.root.after(delay_ms, self._show)

    def _show(self):
        if not self._current_text:
            return
        try:
            win = tk.Toplevel(self.root)
            win.wm_overrideredirect(True)
            win.attributes("-topmost", True)
            win.configure(bg="#30303b")

            inner = tk.Frame(win, bg="#101016", padx=10, pady=7)
            inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

            lines = self._current_text.split("\n", 1)
            tk.Label(
                inner,
                text=lines[0],
                bg="#101016",
                fg="#f59e0b",
                font=("Consolas", 8, "bold"),
                anchor="w",
                justify=tk.LEFT,
            ).pack(anchor="w")

            if len(lines) > 1:
                tk.Label(
                    inner,
                    text=lines[1],
                    bg="#101016",
                    fg="#d4d4d8",
                    font=("Segoe UI", 8),
                    anchor="w",
                    justify=tk.LEFT,
                    wraplength=310,
                ).pack(anchor="w", pady=(2, 0))

            x = min(self.root.winfo_screenwidth() - 340, self._mouse_x + 14)
            y = min(self.root.winfo_screenheight() - 90, self._mouse_y + 18)
            win.wm_geometry(f"+{max(10, x)}+{max(10, y)}")
            self._tip_win = win
        except Exception:
            pass

    def hide(self):
        if self._after_id:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if self._tip_win:
            try:
                self._tip_win.destroy()
            except Exception:
                pass
            self._tip_win = None
        self._current_text = ""


class StudioScrollbar(_TkCanvasBase):
    """
    Sleek dark-mode custom Canvas scrollbar that replaces the thick white native Win32 tk.Scrollbar.
    Supports both vertical and horizontal orientations and automatically hides itself when
    the scrollable content fits inside the viewport.
    """

    def __init__(
        self,
        parent: tk.Widget,
        orient: str = getattr(tk, "VERTICAL", "vertical"),
        command: Optional[Callable] = None,
        thickness: int = 6,
        track_bg: str = "#0c0c0f",
        thumb_bg: str = "#272732",
        thumb_hover_bg: str = "#3f3f46",
        auto_hide: bool = True,
    ):
        self.orient = orient
        self.command = command
        self.thickness = thickness
        self.track_bg = track_bg
        self.thumb_bg = thumb_bg
        self.thumb_hover_bg = thumb_hover_bg
        self.auto_hide = auto_hide
        self._first: float = 0.0
        self._last: float = 1.0
        self._hovered: bool = False
        self._dragging: bool = False
        self._drag_start_coord: float = 0.0
        self._drag_start_first: float = 0.0
        self._grid_kwargs: Optional[Dict] = None

        init_kw = {"bg": track_bg, "highlightthickness": 0, "bd": 0}
        if orient == getattr(tk, "VERTICAL", "vertical"):
            init_kw["width"] = thickness
        else:
            init_kw["height"] = thickness
        super().__init__(parent, **init_kw)

        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

    def grid(self, **kwargs):
        if kwargs:
            self._grid_kwargs = dict(kwargs)
        super().grid(**(self._grid_kwargs or {}))

    def set(self, first: float | str, last: float | str):
        try:
            f_val = max(0.0, min(1.0, float(first)))
            l_val = max(0.0, min(1.0, float(last)))
        except ValueError:
            f_val, l_val = 0.0, 1.0
        self._first, self._last = f_val, l_val

        if self.auto_hide and self._grid_kwargs is not None:
            if f_val <= 0.001 and l_val >= 0.999:
                super().grid_remove()
                return
            if not self.winfo_ismapped():
                super().grid(**self._grid_kwargs)
        self._redraw()

    def _redraw(self):
        self.delete("all")
        if self._first <= 0.001 and self._last >= 0.999:
            return
        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())
        col = self.thumb_hover_bg if (self._hovered or self._dragging) else self.thumb_bg
        if self.orient == getattr(tk, "VERTICAL", "vertical"):
            y0 = max(2, int(self._first * h))
            y1 = min(h - 2, max(y0 + 18, int(self._last * h)))
            self.create_rectangle(1, y0, w - 1, y1, fill=col, outline="")
        else:
            x0 = max(2, int(self._first * w))
            x1 = min(w - 2, max(x0 + 18, int(self._last * w)))
            self.create_rectangle(x0, 1, x1, h - 1, fill=col, outline="")

    def _on_enter(self, _event):
        self._hovered = True
        self._redraw()

    def _on_leave(self, _event):
        self._hovered = False
        self._redraw()

    def _on_press(self, event):
        if not self.command:
            return
        total = max(1, self.winfo_height() if self.orient == tk.VERTICAL else self.winfo_width())
        coord = event.y if self.orient == getattr(tk, "VERTICAL", "vertical") else event.x
        t0 = self._first * total
        t1 = self._last * total
        if t0 <= coord <= t1:
            self._dragging = True
            self._drag_start_coord = coord
            self._drag_start_first = self._first
        else:
            span = self._last - self._first
            target = max(0.0, min(1.0 - span, (coord / total) - span / 2.0))
            self.command("moveto", target)

    def _on_drag(self, event):
        if not self._dragging or not self.command:
            return
        total = max(1, self.winfo_height() if self.orient == tk.VERTICAL else self.winfo_width())
        coord = event.y if self.orient == getattr(tk, "VERTICAL", "vertical") else event.x
        delta = (coord - self._drag_start_coord) / total
        span = self._last - self._first
        target = max(0.0, min(1.0 - span, self._drag_start_first + delta))
        self.command("moveto", target)

    def _on_release(self, _event):
        self._dragging = False
        self._redraw()


class StudioDropdown(_TkFrameBase):
    """
    Custom Dark-Mode Dropdown Selector that matches the Web UI's .styled-select-trigger & .styled-select-menu.
    Supports:
    - Compact mode (clean single-label options without overlapping badges/meta)
    - Rich searchable mode (with Live Search & Category Filter Tabs for Add Program)
    - Global outside-click dismissal across root and modal Toplevel dialogs
    """

    _active_dropdown: Optional["StudioDropdown"] = None
    _global_bind_installed: bool = False

    def __init__(
        self,
        parent: tk.Widget,
        root: tk.Tk,
        width_px: int = 230,
        categories: Optional[List[str]] = None,
        placeholder: str = "Select...",
        on_select: Optional[Callable[[str], None]] = None,
    ):
        super().__init__(
            parent,
            bg="#14141b",
            highlightthickness=1,
            highlightbackground="#272732",
            width=width_px,
            height=31,
        )
        self.pack_propagate(False)
        self.root = root
        self.width_px = width_px
        self.categories = categories or []
        self.on_select = on_select

        self._items: List[Dict[str, str]] = []
        self._selected_value: str = ""
        self._selected_label: str = placeholder
        self._popup: Optional[tk.Toplevel] = None
        self._active_category: str = "ALL"

        self.lbl_text = tk.Label(
            self,
            text=self._selected_label,
            bg="#14141b",
            fg="#fafafa",
            font=("Segoe UI", 8, "bold"),
            anchor="w",
            padx=9,
            cursor="hand2",
        )
        self.lbl_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.lbl_arrow = tk.Label(
            self,
            text="▾",
            bg="#14141b",
            fg="#f59e0b",
            font=("Consolas", 9, "bold"),
            padx=7,
            cursor="hand2",
        )
        self.lbl_arrow.pack(side=tk.RIGHT, fill=tk.Y)

        for w in (self, self.lbl_text, self.lbl_arrow):
            w.bind("<Button-1>", self._toggle_popup)
            w.bind("<Enter>", self._on_hover_enter, add="+")
            w.bind("<Leave>", self._on_hover_leave, add="+")

        self.bind("<Unmap>", lambda _e: self._close_popup(), add="+")
        self.bind("<Destroy>", lambda _e: self._close_popup(), add="+")
        self._ensure_global_click_binding()

    def _ensure_global_click_binding(self):
        if StudioDropdown._global_bind_installed:
            return
        try:
            self.root.bind_all("<Button-1>", StudioDropdown._on_global_button_down, add="+")
            StudioDropdown._global_bind_installed = True
        except Exception:
            pass

    @classmethod
    def _on_global_button_down(cls, event):
        active = cls._active_dropdown
        if active is None or not active._popup:
            return
        w_clicked = event.widget
        if w_clicked in (active, active.lbl_text, active.lbl_arrow):
            return
        try:
            if w_clicked is not None and str(w_clicked).startswith(str(active._popup)):
                return
        except Exception:
            pass
        active._close_popup()

    def _on_hover_enter(self, _e):
        self.configure(bg="#1f1f2a", highlightbackground="#f59e0b")
        self.lbl_text.configure(bg="#1f1f2a")
        self.lbl_arrow.configure(bg="#1f1f2a")

    def _on_hover_leave(self, _e):
        if not self._popup:
            self.configure(bg="#14141b", highlightbackground="#272732")
            self.lbl_text.configure(bg="#14141b")
            self.lbl_arrow.configure(bg="#14141b")

    def set_items(self, items: List[Dict[str, str]]):
        self._items = items
        if not self._selected_value and items:
            self.set_value(items[0]["value"], items[0]["label"])

    def set_value(self, value: str, display_label: Optional[str] = None):
        self._selected_value = value
        if display_label is None:
            found = next((it["label"] for it in self._items if it["value"] == value), value)
            display_label = found
        self._selected_label = display_label
        max_chars = max(12, int((self.width_px - 34) // 6.5))
        short = display_label if len(display_label) <= max_chars else display_label[: max_chars - 1] + "…"
        self.lbl_text.configure(text=short)

    def get_value(self) -> str:
        return self._selected_value

    def _toggle_popup(self, _event=None):
        if self._popup and self._popup.winfo_exists():
            self._close_popup()
            return
        self._open_popup()
        return "break"

    def _close_popup(self):
        if StudioDropdown._active_dropdown is self:
            StudioDropdown._active_dropdown = None
        if self._popup:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None
        try:
            if self.winfo_exists():
                self.configure(bg="#14141b", highlightbackground="#272732")
                self.lbl_text.configure(bg="#14141b")
                self.lbl_arrow.configure(bg="#14141b", text="▾")
        except Exception:
            pass

    def _open_popup(self):
        if StudioDropdown._active_dropdown and StudioDropdown._active_dropdown is not self:
            StudioDropdown._active_dropdown._close_popup()
        StudioDropdown._active_dropdown = self

        self.lbl_arrow.configure(text="▴")
        self.configure(highlightbackground="#f59e0b")

        pop = tk.Toplevel(self.root)
        pop.wm_overrideredirect(True)
        pop.attributes("-topmost", True)
        pop.configure(bg="#3a3a46")
        self._popup = pop

        has_rich_rows = bool(self.categories) or any(it.get("badge") or it.get("meta") for it in self._items)
        row_h = 30 if has_rich_rows else 28
        if self.categories:
            pop_w = max(self.width_px, 380)
            pop_h = 330
        elif has_rich_rows:
            pop_w = max(self.width_px, 290)
            pop_h = min(250, max(90, len(self._items) * row_h + 10))
        else:
            max_lbl_len = max((len(it.get("label", "")) for it in self._items), default=14)
            pop_w = max(self.width_px, max_lbl_len * 7 + 28)
            pop_h = min(240, max(64, len(self._items) * row_h + 10))

        rx = self.winfo_rootx()
        ry = self.winfo_rooty() + self.winfo_height() + 3
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        if rx + pop_w > screen_w - 12:
            rx = screen_w - pop_w - 12
        if ry + pop_h > screen_h - 40:
            ry = self.winfo_rooty() - pop_h - 3
        pop.wm_geometry(f"{pop_w}x{pop_h}+{max(6, rx)}+{max(6, ry)}")

        body = tk.Frame(pop, bg="#101016", padx=4, pady=4)
        body.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        search_var = tk.StringVar()
        ent_search: Optional[tk.Entry] = None

        if self.categories:
            top_filter = tk.Frame(body, bg="#12121a", padx=8, pady=6)
            top_filter.pack(fill=tk.X)

            tk.Label(
                top_filter, text="🔎", bg="#12121a", fg="#f59e0b", font=("Segoe UI", 9)
            ).pack(side=tk.LEFT, padx=(0, 4))

            ent_search = tk.Entry(
                top_filter,
                textvariable=search_var,
                bg="#08080c",
                fg="#fafafa",
                insertbackground="#f59e0b",
                relief=tk.FLAT,
                highlightthickness=1,
                highlightbackground="#272732",
                font=("Consolas", 9),
            )
            ent_search.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)
            ent_search.focus_set()

            cat_bar = tk.Frame(body, bg="#0a0a0f", padx=6, pady=5)
            cat_bar.pack(fill=tk.X)
            cat_btns: Dict[str, tk.Label] = {}

            def select_cat(cat_name: str):
                self._active_category = cat_name
                for cname, lbl in cat_btns.items():
                    if cname == cat_name:
                        lbl.configure(bg="#f59e0b", fg="#09090b")
                    else:
                        lbl.configure(bg="#161620", fg="#a1a1aa")
                render_rows()

            for c_name in self.categories:
                b = tk.Label(
                    cat_bar,
                    text=c_name,
                    bg="#f59e0b" if c_name == self._active_category else "#161620",
                    fg="#09090b" if c_name == self._active_category else "#a1a1aa",
                    font=("Consolas", 8, "bold"),
                    padx=7,
                    pady=2,
                    cursor="hand2",
                )
                b.pack(side=tk.LEFT, padx=2)
                b.bind("<Button-1>", lambda _e, cn=c_name: select_cat(cn))
                cat_btns[c_name] = b

        list_wrap = tk.Frame(body, bg="#101016")
        list_wrap.pack(fill=tk.BOTH, expand=True)
        list_wrap.grid_rowconfigure(0, weight=1)
        list_wrap.grid_columnconfigure(0, weight=1)

        cv = tk.Canvas(list_wrap, bg="#101016", highlightthickness=0, bd=0)
        vscroll = StudioScrollbar(
            list_wrap,
            orient=tk.VERTICAL,
            command=cv.yview,
            thickness=6,
            track_bg="#101016",
            thumb_bg="#272732",
            thumb_hover_bg="#3f3f46",
            auto_hide=True,
        )
        cv.configure(yscrollcommand=vscroll.set)
        cv.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")

        row_regions: List[Tuple[int, int, str, str]] = []
        hover_row_idx = [-1]

        def render_rows(*_args):
            cv.delete("all")
            row_regions.clear()
            q = search_var.get().strip().lower()
            filtered = []
            for it in self._items:
                if self.categories and self._active_category != "ALL":
                    if self._active_category == "PINNED":
                        if not it.get("is_pinned"):
                            continue
                    elif it.get("category") != self._active_category:
                        continue
                if q and q not in it["label"].lower() and q not in it["value"].lower() and q not in it.get("meta", "").lower():
                    continue
                filtered.append(it)

            w_cv = max(140, pop_w - 14)
            if not filtered:
                cv.create_text(
                    w_cv / 2, 34,
                    text="No matching programs found",
                    fill="#71717a",
                    font=("Segoe UI", 8),
                )
                cv.configure(scrollregion=(0, 0, w_cv, 70))
                return

            for idx, it in enumerate(filtered):
                y0 = idx * row_h
                y1 = y0 + row_h
                is_sel = it["value"] == self._selected_value
                is_hov = idx == hover_row_idx[0]
                bg_col = "#1e1e28" if (is_hov or is_sel) else "#101016"
                cv.create_rectangle(0, y0, w_cv, y1, fill=bg_col, outline="")

                badge_txt = it.get("badge", "")
                badge_col = it.get("color", "#38bdf8")
                text_x = 8
                if badge_txt:
                    cv.create_rectangle(8, y0 + 6, 40, y0 + 23, fill="#181824", outline=badge_col)
                    cv.create_text(24, y0 + 14.5, text=badge_txt, fill=badge_col, font=("Consolas", 7, "bold"))
                    text_x = 48

                meta_txt = it.get("meta", "")
                meta_px = (len(meta_txt[:22]) * 6 + 16) if meta_txt else 8
                avail_lbl_px = max(60, w_cv - text_x - meta_px)
                max_lbl_chars = max(10, int(avail_lbl_px // 6.8))
                raw_lbl = it["label"]
                lbl_str = raw_lbl if len(raw_lbl) <= max_lbl_chars else raw_lbl[: max_lbl_chars - 1] + "…"

                lbl_col = "#ffffff" if (is_sel or is_hov) else "#fafafa"
                cv.create_text(
                    text_x, (y0 + y1) / 2,
                    text=lbl_str,
                    fill=lbl_col,
                    anchor="w",
                    font=("Segoe UI", 8, "bold"),
                )
                if meta_txt:
                    cv.create_text(
                        w_cv - 8, (y0 + y1) / 2,
                        text=meta_txt[:22],
                        fill="#71717a",
                        anchor="e",
                        font=("Consolas", 8),
                    )
                row_regions.append((y0, y1, it["value"], it["label"]))

            cv.configure(scrollregion=(0, 0, w_cv, len(filtered) * row_h))

        def on_cv_motion(event):
            cy = cv.canvasy(event.y)
            new_idx = int(cy // row_h)
            if new_idx != hover_row_idx[0]:
                hover_row_idx[0] = new_idx
                render_rows()

        def on_cv_click(event):
            cy = cv.canvasy(event.y)
            for y0, y1, val, lbl in row_regions:
                if y0 <= cy <= y1:
                    self.set_value(val, lbl)
                    self._close_popup()
                    if self.on_select:
                        self.on_select(val)
                    break

        def on_mousewheel(event):
            cv.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        cv.bind("<Motion>", on_cv_motion)
        cv.bind("<Button-1>", on_cv_click)
        for wheel_widget in (pop, body, list_wrap, cv, vscroll):
            wheel_widget.bind("<MouseWheel>", on_mousewheel)
        if ent_search is not None:
            ent_search.bind("<MouseWheel>", on_mousewheel)
        pop.bind("<Escape>", lambda _e: self._close_popup())
        search_var.trace_add("write", render_rows)

        render_rows()