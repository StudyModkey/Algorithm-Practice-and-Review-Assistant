"""Arrow-free, DPI-scaled scrollbars drawn with native Canvas primitives."""
from __future__ import annotations

import math
import tkinter as tk


class RoundedScrollbar(tk.Canvas):
    """A vertical scrollbar with a rounded blue thumb and a wide drag target."""

    def __init__(self, master, *, command, scale=1.0, background="#FFFFFF"):
        self.scale = scale
        self.command = command
        self.first, self.last = 0.0, 1.0
        self._drag_offset = None
        self._hover = False
        self._wheel_remainder = 0.0
        super().__init__(master, width=self.px(16), height=0, highlightthickness=0, bd=0,
                         bg=background, takefocus=False)
        self.bind("<Configure>", self._draw)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Button-4>", lambda event: self.command("scroll", -3, "units"))
        self.bind("<Button-5>", lambda event: self.command("scroll", 3, "units"))

    def px(self, value):
        return max(1, round(value * self.scale))

    def set(self, first, last):
        first, last = float(first), float(last)
        if not math.isfinite(first) or not math.isfinite(last):
            return
        self.first = min(1.0, max(0.0, first))
        self.last = min(1.0, max(self.first, last))
        self._draw()

    def get(self):
        return self.first, self.last

    def _geometry(self):
        pad = self.px(5)
        length = max(1, self.winfo_height() - 2 * pad)
        visible = self.last - self.first
        thumb = min(length, max(self.px(34), length * visible))
        travel = max(0, length - thumb)
        maximum = max(0.0, 1.0 - visible)
        top = pad + (self.first / maximum * travel if maximum else 0)
        return pad, length, thumb, travel, maximum, top

    def _draw(self, event=None):
        self.delete("all")
        if self.winfo_height() < self.px(14) or self.last - self.first >= .999999:
            self.configure(cursor="arrow")
            return
        self.configure(cursor="hand2")
        pad, length, thumb, travel, maximum, top = self._geometry()
        x = self.winfo_width() / 2
        self.create_line(x, pad, x, pad + length, fill="#EBF1FF",
                         width=self.px(4), capstyle=tk.ROUND, tags="track")
        width = self.px(7)
        color = "#2457D9" if self._drag_offset is not None else (
            "#3569F1" if self._hover else "#5B86F6")
        if self._hover or self._drag_offset is not None:
            self.create_line(x, top + width / 2, x, top + thumb - width / 2,
                             fill="#DDE8FF", width=self.px(12), capstyle=tk.ROUND,
                             tags="glow")
        self.create_line(x, top + width / 2, x, top + thumb - width / 2,
                         fill=color, width=width, capstyle=tk.ROUND, tags="thumb")

    def _enter(self, event):
        self._hover = True
        self._draw()

    def _leave(self, event):
        self._hover = False
        self._draw()

    def _press(self, event):
        if self.last - self.first >= .999999:
            return
        pad, length, thumb, travel, maximum, top = self._geometry()
        if top <= event.y <= top + thumb:
            self._drag_offset = event.y - top
        else:
            self.command("scroll", -1 if event.y < top else 1, "pages")
        self._draw()

    def _drag(self, event):
        if self._drag_offset is None:
            return
        pad, length, thumb, travel, maximum, top = self._geometry()
        if travel:
            position = min(travel, max(0, event.y - self._drag_offset - pad))
            self.command("moveto", position / travel * maximum)

    def _release(self, event):
        self._drag_offset = None
        self._draw()

    def _wheel(self, event):
        self._wheel_remainder += -event.delta / 120
        units = math.trunc(self._wheel_remainder)
        if units:
            self._wheel_remainder -= units
            self.command("scroll", units * 3, "units")
        return "break"
