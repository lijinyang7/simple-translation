"""Small stdlib client for a locally running MTranServer.

Default endpoint: http://127.0.0.1:8989
API: POST /translate  {"from":"en","to":"zh-Hans","text":"...","html":false}
Response: {"result": "..."}

The client keeps one HTTP connection open, caches repeated sentences, and
batches requests.  No third-party package is required.
"""

from __future__ import annotations

import http.client
import json
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

DEFAULT_URL = "http://127.0.0.1:8989"


class MTranError(RuntimeError):
    """The server answered, but the request failed."""

    def __init__(self, message: str, status: Optional[int] = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class MTranUnavailable(MTranError):
    """No MTranServer is reachable at the configured address."""


class MTranClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = 30.0,
        cache_size: int = 2048,
        retries: int = 1,
        auto_start: bool = True,
    ) -> None:
        url = (base_url or os.environ.get("MTRAN_SERVER_URL")
               or os.environ.get("MT_SERVER") or os.environ.get("MT_URL"))
        if not url:
            port = os.environ.get("MT_PORT", "").strip()
            url = f"http://127.0.0.1:{port}" if port else DEFAULT_URL
        if "://" not in url:
            url = "http://" + url
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError(f"invalid MTranServer URL: {url!r}")
        self.base_url = url.rstrip("/")
        self.scheme = parsed.scheme
        self.host = parsed.hostname
        self.port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self.prefix = (parsed.path or "").rstrip("/")
        self.token = token if token is not None else os.environ.get("MT_API_TOKEN", "")
        self.timeout = float(timeout)
        self.retries = max(0, int(retries))
        self.cache_size = max(0, int(cache_size))
        self.auto_start = bool(auto_start)
        self._autostart_done = False
        self._cache: "OrderedDict[Tuple[str, str, str, bool], str]" = OrderedDict()
        self._lock = threading.RLock()
        self._conn: Optional[http.client.HTTPConnection] = None

    # ------------------------------------------------------------------ public
    @classmethod
    def from_env(cls, **kwargs: Any) -> "MTranClient":
        return cls(**kwargs)

    def ensure_server(self) -> bool:
        """Start the bundled local server if needed (localhost only)."""
        if not self.auto_start:
            return False
        if self._autostart_done:
            return True
        try:
            from .launcher import ensure_bundled_server

            self._autostart_done = ensure_bundled_server(self.base_url, self.token)
            return self._autostart_done
        except Exception:
            self._autostart_done = False
            return False

    def translate(
        self,
        text: str,
        source: str = "en",
        target: str = "zh-Hans",
        html: bool = False,
    ) -> str:
        return self.translate_batch([text], source=source, target=target, html=html)[0]

    def translate_batch(
        self,
        texts: Sequence[str],
        source: str = "en",
        target: str = "zh-Hans",
        html: bool = False,
        batch_size: int = 32,
    ) -> List[str]:
        if not texts:
            return []
        results: List[Optional[str]] = [None] * len(texts)
        missing: List[Tuple[int, str]] = []
        for i, text in enumerate(texts):
            key = (source, target, text, bool(html))
            if self.cache_size:
                hit = self._cache.get(key)
                if hit is not None:
                    results[i] = hit
                    self._cache.move_to_end(key)
                    continue
            missing.append((i, text))
        if not missing:
            return [r or "" for r in results]

        if self.auto_start:
            self.ensure_server()

        size = max(1, int(batch_size))
        for start in range(0, len(missing), size):
            chunk = missing[start:start + size]
            chunk_texts = [text for _, text in chunk]
            translated: Optional[List[str]] = None
            if len(chunk_texts) > 1:
                translated = self._try_batch(chunk_texts, source, target, html)
            if translated is None:
                translated = [
                    self._translate_one(text, source, target, html) for text in chunk_texts
                ]
            for (idx, text), out in zip(chunk, translated):
                results[idx] = out
                if self.cache_size:
                    key = (source, target, text, bool(html))
                    self._cache[key] = out
                    self._cache.move_to_end(key)
                    while len(self._cache) > self.cache_size:
                        self._cache.popitem(last=False)
        return [r if r is not None else "" for r in results]

    def languages(self) -> Any:
        data = self._request("GET", "/languages")
        return data

    def ping(self) -> bool:
        try:
            self.ensure_server()
            self.languages()
            return True
        except MTranError:
            return False

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                finally:
                    self._conn = None

    def __enter__(self) -> "MTranClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ----------------------------------------------------------------- private
    def _translate_one(self, text: str, source: str, target: str, html: bool) -> str:
        data = self._request(
            "POST",
            "/translate",
            {"from": source, "to": target, "text": text, "html": bool(html)},
        )
        value = _extract_text(data)
        if value is None:
            raise MTranError("MTranServer response has no translation field", body=_short(data))
        return value

    def _try_batch(
        self, texts: Sequence[str], source: str, target: str, html: bool
    ) -> Optional[List[str]]:
        try:
            data = self._request(
                "POST",
                "/translate/batch",
                {"from": source, "to": target, "texts": list(texts), "html": bool(html)},
            )
        except MTranError as exc:
            # Older server versions may not provide the batch route.  Fall
            # back to single requests instead of failing the whole article.
            if exc.status in (400, 404, 405, 501):
                return None
            raise
        values = _extract_list(data)
        if values is None or len(values) != len(texts):
            return None
        return values

    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        last_error: Optional[BaseException] = None
        for attempt in range(self.retries + 1):
            try:
                with self._lock:
                    conn = self._get_conn()
                    body = None
                    headers = {
                        "Accept": "application/json",
                        "User-Agent": "zhtrans/1.0",
                    }
                    if payload is not None:
                        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                        headers["Content-Type"] = "application/json; charset=utf-8"
                    if self.token:
                        headers["Authorization"] = f"Bearer {self.token}"
                    conn.request(method, self.prefix + path, body=body, headers=headers)
                    resp = conn.getresponse()
                    raw = resp.read()
                    status = resp.status
                    if status >= 400:
                        text = raw.decode("utf-8", errors="replace")
                        message = _error_message(text) or f"HTTP {status}"
                        if status >= 500:
                            raise MTranError(message, status, text)
                        raise MTranError(message, status, text)
                text = raw.decode("utf-8", errors="replace")
                if not text.strip():
                    return {}
                try:
                    return json.loads(text)
                except json.JSONDecodeError as exc:
                    raise MTranError("MTranServer returned invalid JSON", status, text) from exc
            except MTranError:
                raise
            except (OSError, http.client.HTTPException, TimeoutError) as exc:
                last_error = exc
                self._drop_conn()
                if attempt < self.retries:
                    time.sleep(0.15 * (attempt + 1))
                    continue
        self._autostart_done = False
        raise MTranUnavailable(
            f"cannot connect to MTranServer at {self.base_url}: {last_error}"
        )

    def _get_conn(self) -> http.client.HTTPConnection:
        if self._conn is None:
            cls = http.client.HTTPSConnection if self.scheme == "https" else http.client.HTTPConnection
            self._conn = cls(self.host, self.port, timeout=self.timeout)
        return self._conn

    def _drop_conn(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except OSError:
                    pass
                self._conn = None


def _extract_text(data: Any) -> Optional[str]:
    if isinstance(data, str):
        return data
    if not isinstance(data, dict):
        return None
    for key in ("result", "translatedText", "translation", "text", "output"):
        value = data.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, list) and value and isinstance(value[0], str):
            return value[0]
        if isinstance(value, dict):
            nested = _extract_text(value)
            if nested is not None:
                return nested
    # Some compatible APIs nest the payload.
    for key in ("data", "response"):
        value = data.get(key)
        if isinstance(value, dict):
            nested = _extract_text(value)
            if nested is not None:
                return nested
    return None


def _extract_list(data: Any) -> Optional[List[str]]:
    if isinstance(data, list):
        return [str(x) if not isinstance(x, str) else x for x in data]
    if not isinstance(data, dict):
        return None
    for key in ("results", "translations", "texts", "data", "result"):
        value = data.get(key)
        if isinstance(value, list):
            out: List[str] = []
            for item in value:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict):
                    nested = _extract_text(item)
                    if nested is None:
                        return None
                    out.append(nested)
                else:
                    return None
            return out
        if isinstance(value, dict):
            nested = _extract_list(value)
            if nested is not None:
                return nested
    return None


def _error_message(body: str) -> str:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return body.strip()[:300]
    if isinstance(data, dict):
        for key in ("error", "message", "detail", "result"):
            value = data.get(key)
            if isinstance(value, str):
                return value
    return body.strip()[:300]


def _short(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False)[:300]
    except (TypeError, ValueError):
        return str(data)[:300]
