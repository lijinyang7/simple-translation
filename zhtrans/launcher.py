"""Start the bundled MTranServer runtime on demand.

The repository ships ``vendor/node``, ``vendor/mtranserver`` and the prepared
en->zh-Hans model.  This module lets the Python client start that server when
the configured localhost port is closed, so users do not need Node or a
separate MTranServer installation.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
_vendor_env = os.environ.get("ZHTRANS_VENDOR", "").strip()
VENDOR = Path(_vendor_env) if _vendor_env else (ROOT / "vendor")
NODE = VENDOR / "node" / "node.exe"
SERVER_MAIN = VENDOR / "mtranserver" / "node_modules" / "mtranserver" / "dist" / "main.js"
MODEL_DIR = VENDOR / "mtranserver-data" / "models"
CONFIG_DIR = VENDOR / "mtranserver-data" / "config"
LOG_DIR = VENDOR / "mtranserver-data" / "logs"


def bundled_paths() -> Optional[Tuple[Path, Path, Path, Path]]:
    if NODE.is_file() and SERVER_MAIN.is_file() and MODEL_DIR.is_dir() and CONFIG_DIR.is_dir():
        return NODE, SERVER_MAIN, MODEL_DIR, CONFIG_DIR
    return None


def is_local_url(base_url: str) -> bool:
    try:
        host = urlsplit(base_url).hostname
    except ValueError:
        return False
    return host in ("127.0.0.1", "localhost", "::1")


def url_port(base_url: str) -> Optional[int]:
    try:
        parsed = urlsplit(base_url)
    except ValueError:
        return None
    if parsed.port:
        return parsed.port
    return 443 if parsed.scheme == "https" else 80


def port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_bundled_server(
    base_url: str,
    token: str = "",
    startup_timeout: float = 30.0,
) -> bool:
    """Start the bundled server if this is a local URL and the port is closed.

    Returns True when a server is reachable afterwards.  Never starts anything
    for a remote URL, when autostart is disabled, or when vendor/ is absent.
    """
    if os.environ.get("ZHTRANS_NO_AUTOSTART", "").strip() in ("1", "true", "yes"):
        return False
    if not is_local_url(base_url):
        return False
    port = url_port(base_url)
    if not port:
        return False
    host = "127.0.0.1"
    if port_open(host, port):
        return True
    paths = bundled_paths()
    if paths is None:
        return False
    node, main, model_dir, config_dir = paths
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "mtranserver.log"
    cmd = [
        str(node),
        str(main),
        "--host", "127.0.0.1",
        "--port", str(port),
        "--model-dir", str(model_dir),
        "--config-dir", str(config_dir),
        "--offline",
        "--no-ui",
        "--no-check-update",
        "--worker-idle-timeout", "3600",
        "--cache-size", "1000",
        "--log-level", "warn",
    ]
    if token:
        cmd.extend(["--api-token", token])
    env = os.environ.copy()
    env["MT_OFFLINE"] = "true"
    env["MT_PORT"] = str(port)
    kwargs = {}
    if os.name == "nt":
        # DETACHED_PROCESS + BREAKAWAY_FROM_JOB keeps the server alive after
        # the short-lived CLI exits (the harness may otherwise close its job).
        detached = (
            0x00000008  # DETACHED_PROCESS
            | 0x00000200  # CREATE_NEW_PROCESS_GROUP
            | 0x01000000  # CREATE_BREAKAWAY_FROM_JOB
        )
        kwargs["creationflags"] = detached
    else:
        kwargs["start_new_session"] = True
    with open(log_path, "ab") as log:
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=env,
                **kwargs,
            )
        except OSError:
            # Some Windows job objects forbid breakaway; fall back to a normal
            # detached process, which still works for the current invocation.
            if os.name == "nt":
                try:
                    proc = subprocess.Popen(
                        cmd,
                        cwd=str(ROOT),
                        stdin=subprocess.DEVNULL,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        env=env,
                        creationflags=0x00000008 | 0x00000200,
                    )
                except OSError:
                    return False
            else:
                return False
    deadline = time.monotonic() + startup_timeout
    while time.monotonic() < deadline:
        if port_open(host, port):
            return True
        if proc.poll() is not None:
            return False
        time.sleep(0.1)
    return False


def stop_bundled_server(port: int) -> bool:
    """Best-effort stop for a server listening on *port*.

    Only used by the optional maintenance helper; normal use never needs it.
    """
    if os.name != "nt":
        return False
    try:
        subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                f"$p=(Get-NetTCPConnection -State Listen -LocalPort {int(port)} -ErrorAction SilentlyContinue).OwningProcess; "
                "if($p){Stop-Process -Id $p -Force}",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except OSError:
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="start/stop bundled MTranServer")
    parser.add_argument("--port", type=int, default=8989)
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    if args.stop:
        print("stopped" if stop_bundled_server(args.port) else "not stopped")
    else:
        ok = ensure_bundled_server(f"http://127.0.0.1:{args.port}")
        print("running" if ok else "not running")
