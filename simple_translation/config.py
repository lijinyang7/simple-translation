"""配置加载。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class AppConfig:
    source_lang: str = "auto"
    target_lang: str = "zh"
    reader: str = "demo"       # demo | tesseract | rapidocr
    translator: str = "demo"   # demo | openai
    display: str = "console"   # console | overlay
    interval: float = 2.0      # 循环读取间隔（秒）
    region: Optional[list[int]] = None  # [left, top, width, height]
    openai_model: str = "gpt-4o-mini"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        known = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in data.items() if key in known})


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def load_config(path: Optional[str] = None) -> AppConfig:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return AppConfig()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return AppConfig.from_dict(data)


def save_default_config(path: Optional[str] = None) -> Path:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    config_path.write_text(
        json.dumps(asdict(AppConfig()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return config_path
