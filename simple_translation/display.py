"""第三部分：翻译内容显示。"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Display(ABC):
    """显示后端接口。"""

    @abstractmethod
    def show(self, text: str) -> None:
        """显示翻译结果。"""

    def clear(self) -> None:
        """清空显示。"""

    def close(self) -> None:
        """释放资源。"""


class ConsoleDisplay(Display):
    """在终端打印翻译结果。"""

    def show(self, text: str) -> None:
        print("-" * 48)
        print(text)
        print("-" * 48)

    def clear(self) -> None:
        pass

    def close(self) -> None:
        pass


class TkOverlayDisplay(Display):
    """tkinter 覆盖窗口：无边框、置顶、半透明，适合悬浮显示翻译。"""

    def __init__(
        self,
        title: str = "简单翻译",
        font: tuple = ("Microsoft YaHei", 14),
        corner: str = "top-right",
    ):
        self.title = title
        self.font = font
        self.corner = corner
        self._root = None
        self._label = None

    def _build(self) -> None:
        import tkinter as tk

        root = tk.Tk()
        root.title(self.title)
        root.overrideredirect(True)      # 无边框
        root.attributes("-topmost", True)  # 置顶
        root.attributes("-alpha", 0.85)  # 半透明

        label = tk.Label(
            root,
            text="",
            font=self.font,
            bg="black",
            fg="white",
            padx=16,
            pady=10,
            wraplength=600,
            justify="left",
        )
        label.pack()
        root.update_idletasks()

        # 按角落定位窗口
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        width = root.winfo_reqwidth()
        height = root.winfo_reqheight()
        margin = 12
        if self.corner == "top-right":
            x, y = screen_w - width - margin, margin
        elif self.corner == "top-left":
            x, y = margin, margin
        elif self.corner == "bottom-right":
            x, y = screen_w - width - margin, screen_h - height - margin
        else:  # bottom-left
            x, y = margin, screen_h - height - margin
        root.geometry(f"+{x}+{y}")

        self._root = root
        self._label = label

    def show(self, text: str) -> None:
        if self._root is None:
            self._build()
        self._label.config(text=text)
        self._root.update()

    def clear(self) -> None:
        if self._label is not None:
            self._label.config(text="")

    def close(self) -> None:
        if self._root is not None:
            self._root.destroy()
            self._root = None
            self._label = None
