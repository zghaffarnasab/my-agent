"""Try the dashboard on your own computer with FAKE data.

    .venv/bin/python tests/demo_server.py      then open  http://127.0.0.1:8765   (password: demo)
    DEMO_HOST=0.0.0.0 .venv/bin/python tests/demo_server.py     also reachable from a phone on the same Wi-Fi

It uses a throw-away database in a temporary folder, and fake Gmail, Calendar and Claude. It never touches your real
database, mailbox, calendar or API keys, and nothing you click is sent anywhere.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demo_data  # noqa: E402

PORT = int(os.environ.get("DEMO_PORT", "8765"))
HOST = os.environ.get("DEMO_HOST", "127.0.0.1")   # 0.0.0.0 = open to your local network (fake data only)
folder = demo_data.configure_env(PORT)

import uvicorn  # noqa: E402

from app import db  # noqa: E402

assert "gmail-ai-demo-" in str(db.engine.url), "refusing to run: not the demo database"
demo_data.seed()
demo_data.install_fakes()
from app.main import app  # noqa: E402



def lan_ip() -> str:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))   # no packet is sent; this only asks which network card would be used
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


print(f"\nDemo with fake data (password: {demo_data.PASSWORD})")
print(f"  this computer: http://127.0.0.1:{PORT}")
if HOST != "127.0.0.1":
    print(f"  your phone, on the same Wi-Fi: http://{lan_ip()}:{PORT}")
print(f"  database: {folder}/demo.db   (throw-away; stop the server with Ctrl+C)\n", flush=True)
uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
