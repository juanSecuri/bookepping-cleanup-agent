"""
One-time Google Drive OAuth for LedgerAI.

  1. Create OAuth Desktop credentials in Google Cloud Console
  2. Download client_secret.json
  3. python -m apps.cli.google_drive_auth --secrets path/to/client_secret.json

Token is saved to .google_drive_token.json (gitignored).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.infrastructure.drive.google_drive_client import run_oauth_flow


def main() -> None:
    parser = argparse.ArgumentParser(description="Authorize Google Drive for LedgerAI")
    parser.add_argument("--secrets", required=True, help="Path to OAuth client_secret.json")
    args = parser.parse_args()
    path = Path(args.secrets)
    if not path.exists():
        raise SystemExit(f"Secrets file not found: {path}")
    creds = run_oauth_flow(path)
    print("Drive authorized.")
    print(f"Refresh token present: {bool(creds.refresh_token)}")
    print("Token saved to .google_drive_token.json — keep this file private.")


if __name__ == "__main__":
    main()
