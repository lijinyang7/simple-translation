"""Windows 全局快捷键（不依赖第三方库）。"""

from __future__ import annotations

import os
import threading
from typing import Callable, Optional


WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_SHIFT = 0x0004
_MOD_WIN = 0x0008


def _key_to_vk(name: str) -> Optional[int]:
    if len(name) == 1 and "A" <= name <= "Z":
        return ord(name)
    if len(name) == 1 and "0" <= name <= "9":
        return ord(name)
    if name.startswith("F") and name[1:].isdigit():
        index = int(name[1:])
        if 1 <= index <= 24:
            return 0x6F + index
    return {
        "SPACE": 0x20,
        "TAB": 0x09,
        "ENTER": 0x0D,
        "ESC": 0x1B,
        "ESCAPE": 0x1B,
        "BACKSPACE": 0x08,
        "DELETE": 0x2E,
        "INSERT": 0x2D,
        "HOME": 0x24,
        "END": 0x23,
        "PAGEUP": 0x21,
        "PAGEDOWN": 0x22,
        "UP": 0x26,
        "DOWN": 0x28,
        "LEFT": 0x25,
        "RIGHT": 0x27,
    }.get(name)


def parse_hotkey(spec: str) -> tuple[int, int]:
    """把 "F8" / "Ctrl+Alt+T" 解析成 (modifiers, virtual_key)。"""
    modifiers = 0
    key = None
    for part in (item.strip().upper() for item in spec.split("+")):
        if not part:
            continue
        if part in ("CTRL", "CONTROL"):
            modifiers |= _MOD_CONTROL
        elif part == "ALT":
            modifiers |= _MOD_ALT
        elif part == "SHIFT":
            modifiers |= _MOD_SHIFT
        elif part in ("WIN", "WINDOWS"):
            modifiers |= _MOD_WIN
        else:
            key = part
    if key is None:
        raise ValueError(f"无效快捷键：{spec}")
    virtual_key = _key_to_vk(key)
    if virtual_key is None:
        raise ValueError(f"不支持的按键：{key}")
    return modifiers, virtual_key


class GlobalHotkey:
    """系统级热键：即使 UI 不在前台也能收到按键。"""

    def __init__(
        self,
        callback: Callable[[], None],
        spec: str = "F8",
        hotkey_id: int = 0xB001,
    ):
        self.callback = callback
        self.spec = spec
        self._hotkey_id = hotkey_id
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._ok = False
        self.error = ""

    @property
    def thread_id(self) -> int:
        return self._thread_id

    @property
    def hotkey_id(self) -> int:
        return self._hotkey_id

    def start(self) -> bool:
        if os.name != "nt":
            self.error = "全局快捷键仅支持 Windows"
            return False
        self._thread = threading.Thread(target=self._run, name="global-hotkey", daemon=True)
        self._thread.start()
        self._ready.wait(2.0)
        return self._ok

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        try:
            modifiers, virtual_key = parse_hotkey(self.spec)
        except ValueError as exc:
            self.error = str(exc)
            self._ready.set()
            return

        if not user32.RegisterHotKey(None, self._hotkey_id, modifiers, virtual_key):
            self.error = f"快捷键 {self.spec} 注册失败（可能被其他程序占用）"
            self._ready.set()
            return

        self._ok = True
        self._ready.set()
        message = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == WM_HOTKEY and message.wParam == self._hotkey_id:
                    try:
                        self.callback()
                    except Exception:
                        pass
        finally:
            user32.UnregisterHotKey(None, self._hotkey_id)

    def stop(self) -> None:
        if os.name == "nt" and self._thread_id:
            import ctypes

            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
