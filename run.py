"""
Quick-start launcher — Bookkeeping Clean-up Agent
===================================================
Run from the project root:

  python run.py            → start API server (default: http://localhost:8000)
  python run.py --port 9000
  python run.py --reload   → hot-reload for development

The HTML interface is served at http://localhost:8000/
The interactive API docs are at http://localhost:8000/docs
"""
import argparse
import sys

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Bookkeeping Clean-up Agent server.")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable hot-reload (dev mode)")
    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════════╗
║        Bookkeeping Clean-up Agent  v0.3.0                ║
║                                                          ║
║   UI  →  http://localhost:{args.port:<5}                        ║
║   API →  http://localhost:{args.port:<5}/docs                   ║
╚══════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "apps.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
