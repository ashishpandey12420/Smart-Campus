"""Smart Campus launcher.

    python run.py                 -> http://127.0.0.1:8000
    python run.py --reload        -> auto-reload for development
    python run.py --port 8080     -> another port
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def open_browser(url: str) -> None:
    webbrowser.open(url)


def free_port(host: str, port: int, tries: int = 20) -> int:
    """First port at or after `port` that can be bound (so a second launch does not crash)."""
    bind_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    for candidate in range(port, port + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((bind_host, candidate))
            except OSError:
                continue
            return candidate
    return port


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Smart Campus")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    import uvicorn

    from backend.config import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME

    port = free_port(args.host, args.port)
    if port != args.port:
        print(f"  Port {args.port} busy -> using {port}")
    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host}:{port}"
    print("=" * 66)
    print("  SMART CAMPUS — Student & Faculty Management System")
    print("=" * 66)
    print(f"  Open:      {url}")
    print(f"  API docs:  {url}/api/docs")
    print(f"  Login:     {DEFAULT_ADMIN_USERNAME} / {DEFAULT_ADMIN_PASSWORD}")
    print(f"             (or {DEFAULT_ADMIN_EMAIL}) — change it after first sign-in")
    if not (Path(__file__).parent / "backend" / "static" / "index.html").exists():
        print("  NOTE: frontend not built yet -> cd frontend && npm install && npm run build")
    print("=" * 66)

    if not args.no_browser:
        threading.Timer(1.5, open_browser, args=(url,)).start()

    uvicorn.run(
        "backend.app:app",
        host=args.host,
        port=port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
