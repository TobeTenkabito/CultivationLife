from __future__ import annotations

import argparse
import ctypes
import json
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path

from cultivation_life.application import GameEngine
from cultivation_life.server import build_handler, resolve_runtime_paths


HOST = "127.0.0.1"


def is_game_server(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/config", timeout=0.5) as response:
            data = json.loads(response.read().decode("utf-8"))
            return response.status == 200 and data.get("format") == "cultivation-life-v2"
    except Exception:
        return False


def is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex((HOST, port)) != 0


def show_error(message: str) -> None:
    ctypes.windll.user32.MessageBoxW(0, message, "浮生问道 · 启动失败", 0x10)


def create_instance_mutex(port: int | None) -> tuple[int, bool]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    name = f"Local\\CultivationLifeLauncher_{port if port else 'default'}"
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        raise OSError("无法创建启动器单实例锁")
    return int(handle), ctypes.get_last_error() == 183


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--port", type=int)
    parser.add_argument("--no-browser", action="store_true")
    args, _ = parser.parse_known_args()

    # DLC 与 MOD 始终是可选的外置目录。目录为空或不存在时不会改变本体内容。
    app_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    for extension_directory in ("dlc", "mods"):
        try:
            (app_root / extension_directory).mkdir(exist_ok=True)
        except OSError:
            pass

    ports = [args.port] if args.port else list(range(8000, 8011))
    mutex_handle = 0
    try:
        mutex_handle, already_running = create_instance_mutex(args.port)
        attempts = 20 if already_running else 1
        for _ in range(attempts):
            for port in ports:
                if port and is_game_server(port):
                    if not args.no_browser:
                        webbrowser.open(f"http://{HOST}:{port}")
                    return
            if already_running:
                time.sleep(0.25)
        if already_running:
            show_error("游戏正在启动，请稍候片刻后再试。")
            return

        port = next((candidate for candidate in ports if candidate and is_port_free(candidate)), None)
        if port is None:
            show_error("端口 8000–8010 均被占用，无法启动游戏。")
            return
        paths = resolve_runtime_paths()
        paths.database_path.parent.mkdir(parents=True, exist_ok=True)
        engine = GameEngine(
            paths.database_path,
            content_directory=paths.content_root,
            extension_root=paths.app_root,
        )
        server = ThreadingHTTPServer((HOST, port), build_handler(engine, paths.web_root))
        if not args.no_browser:
            threading.Timer(0.7, lambda: webbrowser.open(f"http://{HOST}:{port}")).start()
        server.serve_forever()
    except Exception as error:
        show_error(str(error))
    finally:
        if mutex_handle:
            ctypes.windll.kernel32.CloseHandle(mutex_handle)


if __name__ == "__main__":
    main()
