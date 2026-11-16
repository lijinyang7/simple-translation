"""图形界面：简洁的屏幕翻译控制台。

界面只负责控制；译文按原文行位置覆盖显示，不再整体展示原文/译文。
"""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from .config import AppConfig, load_config
from .display import CoverOverlayManager, Display
from .factory import build_reader, build_translator
from .hotkey import GlobalHotkey
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

    def show_boxes(self, items, origin=(0, 0)) -> None:
        self._queue.put(("boxes", items, origin))

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
        self.accept_updates = False
        self.once_busy = False
        self.worker: threading.Thread | None = None
        self.cover = None
        self.hotkey = None
        self._build_window()
        self._build_ui()
        self.cover = CoverOverlayManager(self.root)
        self.hotkey = GlobalHotkey(
            lambda: self.queue.put(("hotkey", "", "")),
            self.config.hotkey,
        )
        if not self.hotkey.start():
            self.hotkey_label.configure(
                text=f"快捷键 {self.config.hotkey} 不可用", fg=DANGER
            )
        self.root.after(100, self._poll_queue)

    # ---- 窗口与布局 ----
    def _build_window(self) -> None:
        self.root.title("简单翻译")
        self.root.configure(bg=BG)
        self.root.minsize(700, 300)
        self.root.update_idletasks()
        width, height = 760, 330
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
            text="持续读取屏幕 · 原位覆盖",
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

        self.hotkey_label = tk.Label(
            toolbar,
            text=f"快捷键 {self.config.hotkey}",
            bg=BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
        )
        self.hotkey_label.pack(side="left", padx=(14, 0))

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

        card = tk.Frame(outer, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="both", expand=True)
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="both", expand=True, padx=16, pady=14)
        tk.Label(
            inner,
            text="原位覆盖",
            bg=CARD,
            fg=ACCENT,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(anchor="w")
        self.detail_label = tk.Label(
            inner,
            text="译文会直接覆盖在屏幕上原文的位置，不再整体显示原文/译文。",
            bg=CARD,
            fg=TEXT,
            wraplength=690,
            justify="left",
            anchor="w",
            font=("Microsoft YaHei UI", 11),
        )
        self.detail_label.pack(anchor="w", pady=(8, 0))

        tk.Label(
            outer,
            text=f"提示：按 {self.config.hotkey} 开始或结束翻译；若控制面板也被读取，可用 config.json 的 region 限定区域。",
            bg=BG,
            fg="#9aa0a6",
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(10, 0))

    # ---- 状态 ----
    def _set_status(self, text: str, color: str) -> None:
        self.status_label.configure(text=text, fg=color)
        self.status_dot.configure(fg=color)

    def _set_detail(self, text: str) -> None:
        self.detail_label.configure(text=text)

    def _reset_controls(self) -> None:
        self.start_btn.configure(text="开始翻译", bg=ACCENT, activebackground=ACCENT_DARK)
        self.interval_spin.configure(state="normal")
        self.once_btn.configure(state="normal")

    # ---- 运行控制 ----
    def _reader_kind(self) -> str:
        return "tesseract" if self.reader_var.get() == "真实屏幕" else "demo"

    def _make_pipeline(self, reader_kind: str) -> Pipeline:
        reader = build_reader(
            reader_kind,
            ScreenRegion.from_list(self.config.region),
            self.config.max_side,
            self.config.workers,
            self.config.diff,
            self.config.continuous,
            self.config.capture_fps,
        )
        translator = build_translator(self.config.translator, self.config.openai_model)
        return Pipeline(
            reader,
            translator,
            QueueDisplay(self.queue),
            self.config.source_lang,
            self.config.target_lang,
        )

    def _step(self, pipeline: Pipeline, reader_kind: str):
        if reader_kind == "tesseract":
            return pipeline.run_boxes_once()
        return pipeline.run_once()

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
        reader_kind = self._reader_kind()
        try:
            pipeline = self._make_pipeline(reader_kind)
        except Exception as exc:
            self._set_detail(f"发生错误：{exc}")
            self._set_status("错误", DANGER)
            return

        self.cover.clear()
        self.accept_updates = True
        self.stop_event.clear()
        self.running = True
        self.start_btn.configure(text="停止", bg=DANGER, activebackground="#c94545")
        self.interval_spin.configure(state="disabled")
        self._set_status("运行中", OK)
        self._set_detail("正在读取屏幕并按原文位置覆盖译文…")

        interval = self._parse_interval()
        self.worker = threading.Thread(
            target=self._run_loop, args=(pipeline, interval, reader_kind), daemon=True
        )
        self.worker.start()

    def _run_loop(self, pipeline: Pipeline, interval: float, reader_kind: str) -> None:
        try:
            while not self.stop_event.is_set():
                try:
                    self._step(pipeline, reader_kind)
                except Exception as exc:
                    self.queue.put(("error", str(exc), ""))
                    return
                deadline = time.monotonic() + interval
                while time.monotonic() < deadline:
                    if self.stop_event.is_set():
                        return
                    time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
        finally:
            pipeline.close()
            self.queue.put(("stopped", "", ""))

    def _stop(self) -> None:
        if not self.running:
            return
        self.running = False
        self.stop_event.set()
        self.accept_updates = False
        self.start_btn.configure(text="开始翻译", bg=ACCENT, activebackground=ACCENT_DARK)
        self.interval_spin.configure(state="normal")
        self.cover.clear()
        self._set_status("正在停止…", MUTED)

    def _translate_once(self) -> None:
        if self.running:
            return
        reader_kind = self._reader_kind()
        try:
            pipeline = self._make_pipeline(reader_kind)
        except Exception as exc:
            self._set_detail(f"发生错误：{exc}")
            self._set_status("错误", DANGER)
            return

        self.once_btn.configure(state="disabled")
        self.accept_updates = True
        self.once_busy = True
        self._set_status("翻译中…", ACCENT)
        self._set_detail("正在读取并翻译…")

        def work() -> None:
            try:
                self._step(pipeline, reader_kind)
                self.queue.put(("once_done", "", ""))
            except Exception as exc:
                self.queue.put(("error", str(exc), ""))
            finally:
                pipeline.close()

        threading.Thread(target=work, daemon=True).start()

    # ---- 队列轮询 ----
    def _poll_queue(self) -> None:
        try:
            while True:
                kind, first, second = self.queue.get_nowait()
                if kind == "boxes":
                    if not self.accept_updates:
                        continue
                    self.cover.show(first, second)
                    self._set_detail(f"已将 {len(first)} 段译文覆盖到屏幕原文位置。")
                elif kind == "hotkey":
                    if not self.once_busy:
                        self._toggle_run()
                elif kind == "pair":
                    if not self.accept_updates:
                        continue
                    self._set_detail(
                        f"原文：{first[:36]}\n译文：{second[:36]}"
                    )
                elif kind == "clear":
                    self.cover.clear()
                elif kind == "error":
                    self.accept_updates = False
                    self.once_busy = False
                    self.running = False
                    self.stop_event.set()
                    self._reset_controls()
                    self._set_status("错误", DANGER)
                    self._set_detail(f"发生错误：{first}")
                elif kind == "stopped":
                    self.running = False
                    self.accept_updates = False
                    self._reset_controls()
                    self.cover.clear()
                    self._set_status("已停止", MUTED)
                    self._set_detail("已停止，屏幕覆盖已清除。")
                elif kind == "once_done":
                    self.accept_updates = False
                    self.once_busy = False
                    self.once_btn.configure(state="normal")
                    self._set_status("就绪", MUTED)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    # ---- 关闭 ----
    def _on_close(self) -> None:
        self.accept_updates = False
        self.stop_event.set()
        if self.cover is not None:
            self.cover.close()
            self.cover = None
        if self.hotkey is not None:
            self.hotkey.stop()
            self.hotkey = None
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
