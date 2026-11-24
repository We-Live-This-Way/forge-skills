#!/usr/bin/env python3
"""OAuth loopback for the YouTube Data API (youtube.force-ssl). Writes a token file."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPE = ["https://www.googleapis.com/auth/youtube.force-ssl"]
DEFAULT_DIR = Path.home() / ".config" / "yt-rename"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Authorize a YouTube Data API desktop client and save a refresh token."
    )
    p.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_DIR,
        help="Directory for client.json and token.json (default: ~/.config/yt-rename)",
    )
    p.add_argument(
        "--client",
        type=Path,
        help="Path to the OAuth client JSON (default: <config-dir>/client.json)",
    )
    p.add_argument(
        "--token",
        type=Path,
        help="Where to write the token (default: <config-dir>/token.json)",
    )
    p.add_argument("--port", type=int, default=8765, help="Loopback port (default: 8765)")
    args = p.parse_args(argv)

    config_dir = args.config_dir.expanduser()
    client = (args.client or (config_dir / "client.json")).expanduser()
    token = (args.token or (config_dir / "token.json")).expanduser()
    if not client.is_file():
        raise SystemExit(f"Missing client secrets file: {client}")

    config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(config_dir, 0o700)

    flow = InstalledAppFlow.from_client_secrets_file(str(client), SCOPE)
    creds = flow.run_local_server(
        port=args.port,
        open_browser=False,
        access_type="offline",
        prompt="consent",
        authorization_prompt_message="AUTH_URL {url}",
        success_message="Approved. You can close this tab.",
    )
    token.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    token.write_text(creds.to_json(), encoding="utf-8")
    os.chmod(token, 0o600)
    print("TOKEN_SAVED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
