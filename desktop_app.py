from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser

import uvicorn

from app.fastapi_server import app


def find_port(start: int = 8011, attempts: int = 20) -> int:
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("No local port is available for the fitting app.")


def open_browser(url: str) -> None:
    time.sleep(1.0)
    opened = False
    try:
        opened = bool(webbrowser.open_new_tab(url))
    except Exception as exc:
        print(f"Could not open the browser automatically: {exc}", flush=True)

    if not opened and sys.platform.startswith("win"):
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            opened = True
        except Exception as exc:
            print(f"Windows browser fallback failed: {exc}", flush=True)

    if not opened:
        print(f"Open this URL manually: {url}", flush=True)


def main() -> None:
    port = find_port()
    url = f"http://127.0.0.1:{port}/"
    print(f"Starting Dark Current Fitting Workbench at {url}", flush=True)
    if os.environ.get("DARK_CURRENT_NO_BROWSER", "").strip().lower() not in {"1", "true", "yes"}:
        threading.Thread(target=open_browser, args=(url,), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, reload=False)


if __name__ == "__main__":
    main()
