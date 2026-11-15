"""第二部分：内容翻译。"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod


class Translator(ABC):
    """翻译器接口。"""

    @abstractmethod
    def translate(self, text: str, source: str = "auto", target: str = "zh") -> str:
        """把 text 从 source 语言翻译成 target 语言。"""


class DemoTranslator(Translator):
    """演示用翻译器：不调用外部服务，仅用于跑通流程。"""

    def translate(self, text: str, source: str = "auto", target: str = "zh") -> str:
        if not text.strip():
            return ""
        return f"[{source} -> {target}] {text}"


class OpenAiTranslator(Translator):
    """调用 OpenAI 兼容接口翻译（可自定义 base_url 以接入第三方模型）。"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model or os.environ.get("OPENAI_TRANSLATE_MODEL", "gpt-4o-mini")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL")

    def translate(self, text: str, source: str = "auto", target: str = "zh") -> str:
        if not text.strip():
            return ""
        if not self.api_key:
            raise RuntimeError("未找到 OPENAI_API_KEY，请通过环境变量或调用参数提供。")

        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, base_url=self.base_url or None)
        prompt = (
            f"请将以下文本从 {source} 翻译成 {target}。"
            "保持原意、语气和格式，只输出译文，不要添加任何解释。\n\n"
            f"{text}"
        )
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        return response.choices[0].message.content.strip()


class ZhtransTranslator(Translator):
    """离线英译中翻译器：zhtrans + 本地 MTranServer。

    zhtrans 是随仓库附带的纯 Python 包，实际翻译由本地 MTranServer 完成。
    运行时（Node + 模型）体积较大，不随仓库提交；可用 ``ZHTRANS_VENDOR``
    环境变量指向已有的 vendor 目录。
    """

    def __init__(
        self,
        server: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
        correct: bool = True,
        auto_start: bool = True,
    ):
        self.server = server
        self.token = token
        self.timeout = timeout
        self.correct = correct
        self.auto_start = auto_start
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            from zhtrans import TranslationEngine

            self._engine = TranslationEngine(
                server=self.server,
                token=self.token,
                timeout=self.timeout,
                auto_start=self.auto_start,
            )
        return self._engine

    @staticmethod
    def _normalize_source(source: str) -> str:
        if source.lower() in ("", "auto", "en", "eng"):
            return "en"
        return source

    @staticmethod
    def _normalize_target(target: str) -> str:
        mapping = {
            "zh": "zh-Hans",
            "zh-cn": "zh-Hans",
            "zh-hans": "zh-Hans",
            "zh-tw": "zh-Hant",
        }
        return mapping.get(target.lower(), target)

    def translate(self, text: str, source: str = "auto", target: str = "zh") -> str:
        if not text.strip():
            return ""
        engine = self._get_engine()
        return engine.translate_text(
            text,
            correct=self.correct,
            source=self._normalize_source(source),
            target=self._normalize_target(target),
        )

    def close(self) -> None:
        if self._engine is not None:
            self._engine.close()
            self._engine = None
