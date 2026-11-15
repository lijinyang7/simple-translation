"""图形界面：简洁的屏幕翻译控制台。"""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from .config import AppConfig, load_config
from .display import Display
from .factory import build_reader, build_translator
from .models import ScreenRegion
from .pipeline import Pipeline


BG = "#f4f5f7"
CARD = "#ffffff"
BORDER = "#e3e6ea"
TEXT = "#1f2328"
MUTED = "#6b7280"
ACCENT = "#2f6fed"
ACCENT_DARK = "#2459c8"
DANGER = "#e05454"
OK = "#2ca56a"


class QueueDisplay(Display):
    """把显示请求投递到 UI 线程的队列。"""

    def __init__(self, target: queue.Queue):
        self._queue = target

    def show(self, text: str) -> None:
        self._queue.put(("pair", "", text))

    def show_pair(self, original: str, translation: str) -> None:
        self._queue.put(("pair", original, translation))

    def clear(self) -> None:
        self._queue.put(("clear", "", ""))

    def close(self) -> None:
        pass


class TranslationApp:
    def __init__(self, root: tk.Tk, config: AppConfig):
        self.root = root
        self.config = config
        self.queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.running = False
        self.worker: threading.Thread | None = None
        self.original_text = ""
        self.translation_text = ""
        self.overlay = None
        self.overlay_orig_var = None
        self.overlay_trans_var = None
        self._build_window()
        self._build_ui()
        self.root.after(100, self._poll_queue)

    # ---- 窗口与布局 ----
    def _build_window(self) -> None:
        self.root.title("简单翻译")
        self.root.configure(bg=BG)
        self.root.minsize(680, 520)
        self.root.update_idletasks()
        width, height = 760, 600
        x = (self.root.winfo_screenwidth() - width) // 2
        y = (self.root.winfo_screenheight() - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg=BG, padx=22, pady=18)
        outer.pack(fill="both", expand=True)

        header = tk.Frame(outer, bg=BG)
        header.pack(fill="x")
        tk.Label(
            header,
            text="简单翻译",
            bg=BG,
            fg=TEXT,
            font=("Microsoft YaHei UI", 20, "bold"),
        ).pack(side="left")
        status = tk.Frame(header, bg=BG)
        status.pack(side="right", pady=6)
        self.status_dot = tk.Label(status, text="●", bg=BG, fg="#9aa0a6", font=("Segoe UI", 10))
        self.status_dot.pack(side="left")
        self.status_label = tk.Label(
            status, text="就绪", bg=BG, fg=MUTED, font=("Microsoft YaHei UI", 10)
        )
        self.status_label.pack(side="left", padx=(4, 0))

        tk.Label(
            outer,
            text="屏幕取词 · 英译中",
            bg=BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(0, 14))

        toolbar = tk.Frame(outer, bg=BG)
        toolbar.pack(fill="x", pady=(0, 14))
        tk.Label(toolbar, text="间隔", bg=BG, fg=MUTED, font=("Microsoft YaHei UI", 10)).pack(side="left")
        self.interval_var = tk.StringVar(value=str(self.config.interval))
        self.interval_spin = tk.Spinbox(
            toolbar,
            from_=0.5,
            to=10.0,
            increment=0.5,
            textvariable=self.interval_var,
            width=5,
            font=("Microsoft YaHei UI", 10),
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            bg=CARD,
            fg=TEXT,
            justify="center",
        )
        self.interval_spin.pack(side="left", padx=(6, 4), ipady=3)
        tk.Label(toolbar, text="秒", bg=BG, fg=MUTED, font=("Microsoft YaHei UI", 10)).pack(side="left")

        tk.Label(toolbar, text="读取", bg=BG, fg=MUTED, font=("Microsoft YaHei UI", 10)).pack(side="left", padx=(16, 0))
        self.reader_var = tk.StringVar(value="演示" if self.config.reader == "demo" else "真实屏幕")
        self.reader_combo = ttk.Combobox(
            toolbar,
            textvariable=self.reader_var,
            values=["真实屏幕", "演示"],
            state="readonly",
            width=9,
            font=("Microsoft YaHei UI", 10),
        )
        self.reader_combo.pack(side="left", padx=(6, 0))

        self.overlay_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            toolbar,
            text="悬浮窗",
            variable=self.overlay_var,
            command=self._toggle_overlay,
            bg=BG,
            fg=TEXT,
            activebackground=BG,
            selectcolor=CARD,
            font=("Microsoft YaHei UI", 10),
            bd=0,
            highlightthickness=0,
        ).pack(side="left", padx=(18, 0))

        self.once_btn = tk.Button(
            toolbar,
            text="翻译一次",
            command=self._translate_once,
            bg=CARD,
            fg=TEXT,
            activebackground="#eef1f5",
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            padx=14,
            pady=7,
            cursor="hand2",
            font=("Microsoft YaHei UI", 10),
        )
        self.once_btn.pack(side="right")
        self.start_btn = tk.Button(
            toolbar,
            text="开始翻译",
            command=self._toggle_run,
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_DARK,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=18,
            pady=7,
            cursor="hand2",
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        self.start_btn.pack(side="right", padx=(0, 8))

        self.original_text_widget = self._make_card(outer, "原文", height=6)
        self.translation_text_widget = self._make_card(outer, "译文", height=5, accent=True)

        tk.Label(
            outer,
            text="提示：点击“开始翻译”后按设定间隔持续读取屏幕；“翻译一次”只执行一次。",
            bg=BG,
            fg="#9aa0a6",
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(2, 0))

    def _make_card(self, parent, title: str, height: int, accent: bool = False) -> tk.Text:
        card = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="both", expand=True, pady=(0, 12))
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="both", expand=True, padx=14, pady=10)
        head = tk.Frame(inner, bg=CARD)
        head.pack(fill="x")
        tk.Label(
            head,
            text=title,
            bg=CARD,
            fg=ACCENT if accent else MUTED,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(side="left")
        text = tk.Text(
            inner,
            height=height,
            wrap="word",
            bg=CARD,
            fg=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Microsoft YaHei UI", 11),
            padx=0,
            pady=6,
            state="disabled",
            cursor="arrow",
        )
        text.pack(fill="both", expand=True)
        return text

    # ---- 结果渲染 ----
    def _render(self, original: str, translation: str) -> None:
        self.original_text = original or ""
        self.translation_text = translation or ""
        self._set_text(self.original_text_widget, self.original_text)
        self._set_text(self.translation_text_widget, self.translation_text)
        if self.overlay is not None:
            self.overlay_orig_var.set(self.original_text[:600])
            self.overlay_trans_var.set(self.translation_text[:600])

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value or "")
        widget.configure(state="disabled")

    def _set_status(self, text: str, color: str) -> None:
        self.status_label.configure(text=text, fg=color)
        self.status_dot.configure(fg=color)

    def _show_error(self, message: str) -> None:
        self._set_text(self.translation_text_widget, f"发生错误：{message}")

    # ---- 运行控制 ----
    def _make_reader(self):
        kind = "tesseract" if self.reader_var.get() == "真实屏幕" else "demo"
        return build_reader(
            kind,
            ScreenRegion.from_list(self.config.region),
            self.config.max_side,
            self.config.workers,
            self.config.diff,
        )

    def _make_translator(self):
        return build_translator(self.config.translator, self.config.openai_model)

    def _parse_interval(self) -> float:
        try:
            value = float(self.interval_var.get())
        except ValueError:
            value = self.config.interval
        return max(0.3, min(60.0, value))

    def _toggle_run(self) -> None:
        if self.running:
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        if self.running:
            return
        try:
            reader = self._make_reader()
            translator = self._make_translator()
        except Exception as exc:
            self._show_error(str(exc))
            self._set_status("错误", DANGER)
            return

        interval = self._parse_interval()
        self.stop_event.clear()
        self.running = True
        self.start_btn.configure(text="停止", bg=DANGER, activebackground="#c94545")
        self.interval_spin.configure(state="disabled")
        self._set_status("运行中", OK)

        pipeline = Pipeline(
            reader,
            translator,
            QueueDisplay(self.queue),
            self.config.source_lang,
            self.config.target_lang,
        )
        self.worker = threading.Thread(
            target=self._run_loop, args=(pipeline, interval), daemon=True
        )
        self.worker.start()

    def _run_loop(self, pipeline: Pipeline, interval: float) -> None:
        try:
            while not self.stop_event.is_set():
                try:
                    pipeline.run_once()
                except Exception as exc:
                    self.queue.put(("error", str(exc), ""))
                    return
                deadline = time.monotonic() + interval
                while time.monotonic() < deadline:
                    if self.stop_event.is_set():
                        return
                    time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
        finally:
            self.queue.put(("stopped", "", ""))

    def _stop(self) -> None:
        if not self.running:
            return
        self.running = False
        self.stop_event.set()
        self.start_btn.configure(text="开始翻译", bg=ACCENT, activebackground=ACCENT_DARK)
        self.interval_spin.configure(state="normal")
        self._set_status("正在停止…", MUTED)

    def _translate_once(self) -> None:
        if self.running:
            return
        try:
            reader = self._make_reader()
            translator = self._make_translator()
        except Exception as exc:
            self._show_error(str(exc))
            self._set_status("错误", DANGER)
            return

        self.once_btn.configure(state="disabled")
        self._set_status("翻译中…", ACCENT)

        def work() -> None:
            try:
                text = reader.read()
                if not text.strip():
                    self.queue.put(("pair", "", ""))
                else:
                    translated = translator.translate(
                        text, self.config.source_lang, self.config.target_lang
                    )
                    self.queue.put(("pair", text, translated))
                self.queue.put(("once_done", "", ""))
            except Exception as exc:
                self.queue.put(("error", str(exc), ""))

        threading.Thread(target=work, daemon=True).start()

    # ---- 队列轮询 ----
    def _poll_queue(self) -> None:
        try:
            while True:
                kind, first, second = self.queue.get_nowait()
                if kind == "pair":
                    self._render(first, second)
                elif kind == "clear":
                    self._render("", "")
                elif kind == "error":
                    self._show_error(first)
                    self._set_status("错误", DANGER)
                    self.running = False
                    self.stop_event.set()
                    self.start_btn.configure(text="开始翻译", bg=ACCENT, activebackground=ACCENT_DARK)
                    self.interval_spin.configure(state="normal")
                    self.once_btn.configure(state="normal")
                elif kind == "stopped":
                    self.running = False
                    self.start_btn.configure(text="开始翻译", bg=ACCENT, activebackground=ACCENT_DARK)
                    self.interval_spin.configure(state="normal")
                    self._set_status("已停止", MUTED)
                elif kind == "once_done":
                    self.once_btn.configure(state="normal")
                    self._set_status("就绪", MUTED)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    # ---- 悬浮窗 ----
    def _toggle_overlay(self) -> None:
        if self.overlay_var.get():
            self._create_overlay()
        else:
            self._destroy_overlay()

    def _create_overlay(self) -> None:
        if self.overlay is not None:
            return
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.attributes("-alpha", 0.94)
        top.configure(bg="#1e1e1e")

        shell = tk.Frame(top, bg="#1e1e1e", padx=16, pady=12)
        shell.pack(fill="both", expand=True)
        head = tk.Frame(shell, bg="#1e1e1e")
        head.pack(fill="x")
        tk.Label(
            head, text="简单翻译", bg="#1e1e1e", fg="#f0c674",
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(side="left")
        close = tk.Label(
            head, text="×", bg="#1e1e1e", fg="#bfbfbf",
            font=("Segoe UI", 13, "bold"), cursor="hand2",
        )
        close.pack(side="right")
        close.bind("<Button-1>", lambda _event: (self.overlay_var.set(False), self._destroy_overlay()))

        self.overlay_orig_var = tk.StringVar(value=self.original_text[:600])
        self.overlay_trans_var = tk.StringVar(value=self.translation_text[:600])
        tk.Label(
            shell, text="原文", bg="#1e1e1e", fg="#8a8a8a",
            font=("Microsoft YaHei UI", 8), anchor="w",
        ).pack(fill="x", pady=(8, 0))
        orig_label = tk.Label(
            shell, textvariable=self.overlay_orig_var, bg="#1e1e1e", fg="#b8b8b8",
            font=("Microsoft YaHei UI", 9), wraplength=440, justify="left", anchor="w",
        )
        orig_label.pack(fill="x")
        tk.Frame(shell, bg="#3a3a3a", height=1).pack(fill="x", pady=8)
        tk.Label(
            shell, text="译文", bg="#1e1e1e", fg="#8a8a8a",
            font=("Microsoft YaHei UI", 8), anchor="w",
        ).pack(fill="x")
        trans_label = tk.Label(
            shell, textvariable=self.overlay_trans_var, bg="#1e1e1e", fg="#ffffff",
            font=("Microsoft YaHei UI", 13, "bold"), wraplength=440, justify="left", anchor="w",
        )
        trans_label.pack(fill="x")

        drag = {"x": 0, "y": 0}

        def start_drag(event):
            drag["x"] = event.x_root - top.winfo_x()
            drag["y"] = event.y_root - top.winfo_y()

        def do_drag(event):
            top.geometry(f"+{event.x_root - drag['x']}+{event.y_root - drag['y']}")

        for widget in (top, shell, head, orig_label, trans_label):
            widget.bind("<Button-1>", start_drag)
            widget.bind("<B1-Motion>", do_drag)

        top.update_idletasks()
        width = top.winfo_reqwidth()
        margin = 16
        top.geometry(f"+{top.winfo_screenwidth() - width - margin}+{margin}")
        self.overlay = top

    def _destroy_overlay(self) -> None:
        if self.overlay is not None:
            try:
                self.overlay.destroy()
            finally:
                self.overlay = None
                self.overlay_orig_var = None
                self.overlay_trans_var = None

    # ---- 关闭 ----
    def _on_close(self) -> None:
        self.stop_event.set()
        self._destroy_overlay()
        self.root.destroy()


def run_ui(config_path: str | None = None, demo: bool = False) -> int:
    config = load_config(config_path)
    if demo:
        config.reader = "demo"
        config.translator = "demo"
    root = tk.Tk()
    TranslationApp(root, config)
    root.mainloop()
    return 0
