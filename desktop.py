import os, sys, socket, threading, time, traceback
from pathlib import Path

BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))

LOG_DIR = Path(os.environ.get("LOCALAPPDATA", ".")) / "SmartCampus"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "startup.log"

def log(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

try:
    log("Starting Smart Campus")
    import webview
    import uvicorn
    from backend.app import app
    log("Modules loaded")

    port = free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None, access_log=False)
    server = uvicorn.Server(config)

    def run_server():
        try:
            server.run()
        except BaseException:
            log("Server thread error:\n" + traceback.format_exc())

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    deadline = time.time() + 180
    while not server.started:
        if not thread.is_alive():
            raise RuntimeError("Backend thread stopped, see log above")
        if time.time() > deadline:
            raise RuntimeError("Backend startup timeout")
        time.sleep(0.2)
    log("Backend started")

    webview.create_window("Smart Campus", f"http://127.0.0.1:{port}",
                          width=1400, height=900, min_size=(1000, 650))
    log("Starting Edge Chromium GUI")
    webview.start(gui="edgechromium", debug=False)
    log("Application closed normally")
except BaseException:
    log(traceback.format_exc())
    raise
