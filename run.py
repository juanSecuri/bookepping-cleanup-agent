"""
Quick-start launcher — LedgerAI

  python run.py            → API + SPA (http://localhost:8000)
  python run.py --port 9000
  python run.py --reload
"""
from __future__ import annotations

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Start LedgerAI server.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
    )
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    print(
        f"\n"
        f"  LedgerAI  v1.0.0\n"
        f"  UI   -> http://localhost:{args.port}/\n"
        f"  API  -> http://localhost:{args.port}/docs\n"
    )

    uvicorn.run(
        "apps.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
