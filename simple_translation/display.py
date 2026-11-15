"""第三部分：翻译内容显示。

支持控制台和 tkinter 悬浮窗两种后端；悬浮窗同时展示原文与译文。
"""

from __future__ import annotations

import queue
import threading
from abc import ABC, abstractmethod


class Display(ABC):
    """显示后端接口。"""

    @abstractmethod
    def show(self, text: str) -> None:
        """显示翻译结果。"""

    def show_pair(self, original: str, translation: str) -> None:
        """同时显示原文与译文。"""
        self.show(f"原文：{original}\n\n译文：{translation}")

    def show_boxes(self, items, origin=(0, 0)) -> None:
        """按文本框显示译文；默认退化为整体原文/译文。"""
        original = "\n".join(box.text for box, _ in items)
        translation = "\n".join(text for _, text in items)
        self.show_pair(original, translation)

    def clear(self) -> None:
        """清空显示。"""

    def wait(self) -> None:
        """等待显示窗口关闭（无窗口的后端立即返回）。"""

    def close(self) -> None:
        """释放资源。"""


def _clip(text: str, max_chars: int = 800) -> str:
    text = (text or "").strip()
    if max_chars and len(text) > max_chars:
        return text[:max_chars].rstrip() + " …"
    return text


def _hex(rgb) -> str:
    values = tuple(max(0, min(255, int(value))) for value in rgb)
    return "#%02x%02x%02x" % values


class ConsoleDisplay(Display):
    """在终端同时打印原文与译文。"""

    def show(self, text: str) -> None:
        print("-" * 48)
        print(text)
        print("-" * 48)

    def show_pair(self, original: str, translation: str) -> None:
        print("=" * 48)
        print("[原文]")
        print(original)
        print("-" * 48)
        print("[译文]")
        print(translation)
        print("=" * 48)

    def clear(self) -> None:
        pass

    def close(self) -> None:
        pass


class CoverOverlayManager:
    """在屏幕上原文位置创建/更新译文覆盖窗。"""

    def __init__(self, master, show_close: bool = False, on_close=None):
        import tkinter as tk

        self._tk = tk
        self.master = master
        self._windows = []
        self._close_window = None
        if show_close and on_close is not None:
            handle = tk.Toplevel(master)
            handle.overrideredirect(True)
            handle.attributes("-topmost", True)
            handle.configure(bg="#1e1e1e")
            label = tk.Label(
                handle,
                text="×",
                bg="#1e1e1e",
                fg="#ffffff",
                font=("Segoe UI", 13, "bold"),
                padx=8,
                pady=1,
                cursor="hand2",
            )
            label.pack()
            label.bind("<Button-1>", lambda _event: on_close())
            handle.geometry("+%d+%d" % (handle.winfo_screenwidth() - 40, 8))
            self._close_window = handle

    def show(self, items, origin=(0, 0)) -> None:
        tk = self._tk
        ox, oy = origin
        for index, (box, text) in enumerate(items):
            background = getattr(box, "background", None) or (30, 30, 30)
            foreground = getattr(box, "foreground", None) or (255, 255, 255)
            bg_hex = _hex(background)
            fg_hex = _hex(foreground)
            if index < len(self._windows):
                top, label = self._windows[index]
            else:
                top = tk.Toplevel(self.master)
                top.overrideredirect(True)
                top.attributes("-topmost", True)
                top.attributes("-alpha", 1.0)
                top.configure(bg=bg_hex)
                label = tk.Label(
                    top,
                    bg=bg_hex,
                    fg=fg_hex,
                    justify="left",
                    anchor="w",
                    padx=4,
                    pady=1,
                )
                label.pack(fill="both", expand=True)
                self._windows.append((top, label))

            font_size = max(9, min(16, int(box.height * 0.65)))
            width = max(int(box.width), 80)
            top.configure(bg=bg_hex)
            label.configure(
                text=text,
                bg=bg_hex,
                fg=fg_hex,
                font=("Microsoft YaHei UI", font_size),
                wraplength=max(width - 8, 80),
            )
            top.update_idletasks()
            req_w = max(width, top.winfo_reqwidth())
            req_h = max(max(int(box.height), 22), top.winfo_reqheight())
            top.geometry(
                f"{req_w}x{req_h}+{int(ox + box.left)}+{int(oy + box.top)}"
            )
            top.lift()

        for top, _label in self._windows[len(items):]:
            top.destroy()
        del self._windows[len(items):]

    def clear(self) -> None:
        for top, _label in self._windows:
            top.destroy()
        self._windows = []

    def close(self) -> None:
        self.clear()
        if self._close_window is not None:
            self._close_window.destroy()
            self._close_window = None


class TkOverlayDisplay(Display):
    """置顶、无边框、可拖动的双语悬浮窗。

    Tk 的窗口必须在创建它的线程内操作。这里让窗口在独立线程中运行
    mainloop，调用方通过线程安全队列提交更新，避免阻塞读取/翻译循环。
    """

    _SENTINEL = object()

    def __init__(
        self,
        title: str = "简单翻译",
        font: tuple | None = None,
        corner: str = "top-right",
        alpha: float = 0.92,
        max_chars: int = 800,
        width: int = 640,
    ):
        self.title = title
        self.font = font or ("Microsoft YaHei", 15, "bold")
        self.corner = corner
        self.alpha = alpha
        self.max_chars = max_chars
        self.width = width
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._root = None
        self._original_var = None
        self._translation_var = None

    # ---- 线程管理 ----
    def _ensure_thread(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="tk-overlay", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            import tkinter as tk
        except ImportError:
            print("[display] tkinter 不可用，无法显示悬浮窗。")
            return

        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", self.alpha)
        root.configure(bg="#1e1e1e")
        self._root = root

        shell = tk.Frame(root, bg="#1e1e1e", padx=16, pady=12)
        shell.pack(fill="both", expand=True)

        header = tk.Frame(shell, bg="#1e1e1e")
        header.pack(fill="x")
        tk.Label(
            header,
            text=self.title,
            font=("Microsoft YaHei", 11, "bold"),
            bg="#1e1e1e",
            fg="#f0c674",
        ).pack(side="left")
        close = tk.Label(
            header,
            text="×",
            font=("Segoe UI", 14, "bold"),
            bg="#1e1e1e",
            fg="#bfbfbf",
            cursor="hand2",
        )
        close.pack(side="right")
        close.bind("<Button-1>", lambda _event: root.destroy())

        tk.Label(
            shell,
            text="原文",
            font=("Microsoft YaHei", 9),
            bg="#1e1e1e",
            fg="#8a8a8a",
            anchor="w",
        ).pack(fill="x", pady=(8, 0))
        self._original_var = tk.StringVar()
        tk.Label(
            shell,
            textvariable=self._original_var,
            font=("Microsoft YaHei", 10),
            bg="#1e1e1e",
            fg="#b8b8b8",
            wraplength=self.width - 32,
            justify="left",
            anchor="w",
        ).pack(fill="x")

        tk.Frame(shell, bg="#3a3a3a", height=1).pack(fill="x", pady=8)

        tk.Label(
            shell,
            text="译文",
            font=("Microsoft YaHei", 9),
            bg="#1e1e1e",
            fg="#8a8a8a",
            anchor="w",
        ).pack(fill="x")
        self._translation_var = tk.StringVar()
        tk.Label(
            shell,
            textvariable=self._translation_var,
            font=self.font,
            bg="#1e1e1e",
            fg="#ffffff",
            wraplength=self.width - 32,
            justify="left",
            anchor="w",
        ).pack(fill="x")

        # 拖动窗口
        drag = {"x": 0, "y": 0}

        def start_drag(event):
            drag["x"] = event.x_root - root.winfo_x()
            drag["y"] = event.y_root - root.winfo_y()

        def do_drag(event):
            root.geometry(f"+{event.x_root - drag['x']}+{event.y_root - drag['y']}")

        root.bind_all("<Button-1>", start_drag)
        root.bind_all("<B1-Motion>", do_drag)

        root.update_idletasks()
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        win_w = root.winfo_reqwidth()
        win_h = root.winfo_reqheight()
        margin = 16
        if self.corner == "top-right":
            x, y = screen_w - win_w - margin, margin
        elif self.corner == "top-left":
            x, y = margin, margin
        elif self.corner == "bottom-right":
            x, y = screen_w - win_w - margin, screen_h - win_h - margin
        else:
            x, y = margin, screen_h - win_h - margin
        root.geometry(f"+{x}+{y}")

        def pump() -> None:
            try:
                while True:
                    item = self._queue.get_nowait()
                    if item is self._SENTINEL:
                        root.destroy()
                        return
                    kind, original, translation = item
                    if kind == "pair":
                        self._original_var.set(_clip(original, self.max_chars))
                        self._translation_var.set(_clip(translation, self.max_chars))
                    elif kind == "text":
                        self._original_var.set("")
                        self._translation_var.set(_clip(original, self.max_chars))
                    elif kind == "clear":
                        self._original_var.set("")
                        self._translation_var.set("")
            except queue.Empty:
                pass
            try:
                root.after(80, pump)
            except Exception:
                pass

        root.after(80, pump)
        root.mainloop()

        # 在创建 Tk 对象的线程内释放引用，避免跨线程析构警告。
        try:
            root.destroy()
        except Exception:
            pass
        self._original_var = None
        self._translation_var = None
        self._root = None
        try:
            tk._default_root = None
        except Exception:
            pass
        del root

    # ---- 对外接口 ----
    def show(self, text: str) -> None:
        self._ensure_thread()
        self._queue.put(("text", text or "", ""))

    def show_pair(self, original: str, translation: str) -> None:
        self._ensure_thread()
        self._queue.put(("pair", original or "", translation or ""))

    def clear(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            self._queue.put(("clear", "", ""))

    def wait(self) -> None:
        if self._thread is not None:
            self._thread.join()

    def close(self) -> None:
        if self._thread is None:
            return
        self._queue.put(self._SENTINEL)
        self._thread.join(timeout=3)
        self._thread = None


class TkCoverDisplay(Display):
    """按原文行位置覆盖显示的 tkinter 后端（独立线程）。"""

    prefers_boxes = True
    _SENTINEL = object()

    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._root = None
        self._manager = None

    def _ensure_thread(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="tk-cover", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        import warnings

        warnings.filterwarnings("ignore", message=".*Tcl interpreter is leaked.*")
        try:
            import tkinter as tk
        except ImportError:
            print("[display] tkinter 不可用，无法显示覆盖层。")
            return

        root = tk.Tk()
        root.withdraw()
        self._root = root
        self._manager = CoverOverlayManager(
            root, show_close=True, on_close=root.destroy
        )

        def pump() -> None:
            try:
                while True:
                    item = self._queue.get_nowait()
                    if item is self._SENTINEL:
                        root.destroy()
                        return
                    kind, data, origin = item
                    if kind == "boxes":
                        self._manager.show(data, origin)
                    elif kind == "clear":
                        self._manager.clear()
            except queue.Empty:
                pass
            try:
                root.after(60, pump)
            except Exception:
                pass

        root.after(60, pump)
        root.mainloop()
        self._manager = None
        self._root = None
        try:
            tk._default_root = None
        except Exception:
            pass

    def show(self, text: str) -> None:
        pass

    def show_boxes(self, items, origin=(0, 0)) -> None:
        self._ensure_thread()
        self._queue.put(("boxes", items, origin))

    def clear(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            self._queue.put(("clear", None, (0, 0)))

    def wait(self) -> None:
        if self._thread is not None:
            self._thread.join()

    def close(self) -> None:
        if self._thread is None:
            return
        self._queue.put(self._SENTINEL)
        self._thread.join(timeout=3)
        self._thread = None
