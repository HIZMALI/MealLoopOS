"""Single-origin release server. LOCAL is always loopback; public binding is explicit."""
import os
import sys
import socket
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import Settings


def main():
    settings = Settings.from_env()
    if settings.public:
        from app.demo import prepare_demo
        prepare_demo()  # rehydrates after ephemeral reset; no fitting or network
    port_text = os.environ.get("PORT", "8080") if settings.public else "8080"
    if not port_text.isascii() or not port_text.isdecimal() or not 1024 <= int(port_text) <= 65535:
        raise ValueError("PORT must be an integer from 1024 to 65535.")
    import uvicorn
    host = "0.0.0.0" if settings.public else "127.0.0.1"
    config = uvicorn.Config("app.main:app", host=host, port=int(port_text),
                workers=1, proxy_headers=False, access_log=False, limit_concurrency=12,
                backlog=64, timeout_keep_alive=5, h11_max_incomplete_event_size=16_384)
    # Windows otherwise permits an all-interface listener alongside an existing
    # loopback listener on the same port. Own one exclusive socket end to end.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        if os.name == "nt":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind((host, int(port_text)))
        uvicorn.Server(config).run(sockets=[listener])


if __name__ == "__main__":
    main()
