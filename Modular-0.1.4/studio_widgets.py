#!/usr/bin/env python3
"""
OmniBond - Custom Dark Studio UI Components: Hover Tooltips & Dropdowns.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from config import _TkFrameBase, tk

__all__ = ["StudioTooltip", "StudioDropdown"]

# =====================================================================
# 9. CUSTOM STUDIO UI COMPONENTS: HOVER TOOLTIPS, MODERN DROPDOWN & BUTTONS
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
            win.configure(bg="#f59e0b")

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


class StudioDropdown(_TkFrameBase):
    """
    Custom Dark-Mode Dropdown Selector that replaces the glaring white Win32 ttk.Combobox.
    Supports:
    - Live Search / Filter input box inside the popup
    - Category Filter Tabs (e.g. ALL | USER APPS | ACTIVE NET | PINNED | BG)
    - Rich item rows with category badge, main label, and right-aligned subtitle
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
            bg="#121218",
            highlightthickness=1,
            highlightbackground="#272732",
            width=width_px,
            height=30,
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
            bg="#121218",
            fg="#fafafa",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
            padx=10,
            cursor="hand2",
        )
        self.lbl_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.lbl_arrow = tk.Label(
            self,
            text="▾",
            bg="#181822",
            fg="#f59e0b",
            font=("Consolas", 10, "bold"),
            width=3,
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
        self.configure(highlightbackground="#f59e0b")
        self.lbl_arrow.configure(bg="#272734")

    def _on_hover_leave(self, _e):
        if not self._popup:
            self.configure(highlightbackground="#272732")
            self.lbl_arrow.configure(bg="#181822")

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
        short = display_label if len(display_label) <= 34 else display_label[:32] + ".."
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
                self.configure(highlightbackground="#272732")
                self.lbl_arrow.configure(bg="#181822", text="▾")
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
        pop.configure(bg="#f59e0b")
        self._popup = pop

        pop_w = max(self.width_px, 370 if self.categories else 270)
        pop_h = 330 if self.categories else min(250, max(110, len(self._items) * 34 + 16))

        rx = self.winfo_rootx()
        ry = self.winfo_rooty() + self.winfo_height() + 2
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        if rx + pop_w > screen_w - 12:
            rx = screen_w - pop_w - 12
        if ry + pop_h > screen_h - 40:
            ry = self.winfo_rooty() - pop_h - 2
        pop.wm_geometry(f"{pop_w}x{pop_h}+{max(6, rx)}+{max(6, ry)}")

        body = tk.Frame(pop, bg="#0d0d12")
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

        list_wrap = tk.Frame(body, bg="#0d0d12")
        list_wrap.pack(fill=tk.BOTH, expand=True)

        cv = tk.Canvas(list_wrap, bg="#0d0d12", highlightthickness=0, bd=0)
        vscroll = tk.Scrollbar(
            list_wrap,
            orient=tk.VERTICAL,
            command=cv.yview,
            width=8,
            bg="#3f3f46",
            troughcolor="#0d0d12",
            activebackground="#52525b",
            bd=0,
            highlightthickness=0,
            relief=tk.FLAT,
        )
        cv.configure(yscrollcommand=vscroll.set)
        cv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)

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

            row_h = 32
            w_cv = pop_w - 12
            if not filtered:
                cv.create_text(
                    w_cv / 2, 40,
                    text="No matching programs found",
                    fill="#71717a",
                    font=("Segoe UI", 9),
                )
                cv.configure(scrollregion=(0, 0, w_cv, 80))
                return

            for idx, it in enumerate(filtered):
                y0 = idx * row_h
                y1 = y0 + row_h
                is_sel = it["value"] == self._selected_value
                is_hov = idx == hover_row_idx[0]
                bg_col = "#1f1f2b" if is_hov else ("#161621" if is_sel else "#0d0d12")
                cv.create_rectangle(0, y0, w_cv, y1, fill=bg_col, outline="")
                cv.create_line(0, y1 - 1, w_cv, y1 - 1, fill="#181820")

                badge_txt = it.get("badge", "")
                badge_col = it.get("color", "#38bdf8")
                text_x = 10
                if badge_txt:
                    cv.create_rectangle(8, y0 + 7, 42, y0 + 24, fill="#181824", outline=badge_col)
                    cv.create_text(25, y0 + 15, text=badge_txt, fill=badge_col, font=("Consolas", 7, "bold"))
                    text_x = 50

                lbl_col = "#f59e0b" if is_sel else "#fafafa"
                cv.create_text(
                    text_x, y0 + 16,
                    text=it["label"][:28],
                    fill=lbl_col,
                    anchor="w",
                    font=("Segoe UI", 9, "bold" if is_sel else "normal"),
                )
                meta_txt = it.get("meta", "")
                if meta_txt:
                    cv.create_text(
                        w_cv - 10, y0 + 16,
                        text=meta_txt[:26],
                        fill="#71717a",
                        anchor="e",
                        font=("Consolas", 8),
                    )
                row_regions.append((y0, y1, it["value"], it["label"]))

            cv.configure(scrollregion=(0, 0, w_cv, len(filtered) * row_h))

        def on_cv_motion(event):
            cy = cv.canvasy(event.y)
            new_idx = int(cy // 32)
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