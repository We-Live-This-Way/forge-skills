#!/usr/bin/env python3
"""List recent uploads from the authorized channel.

Writes JSON: a list of [videoId, title, publishedAt], newest first.
Does not hard-code a channel; uses channels.list(mine=True).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

DEFAULT_TOKEN = Path.home() / ".config" / "yt-rename" / "token.json"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="List recent uploads from the authorized YouTube channel.")
    p.add_argument("--token", type=Path, default=DEFAULT_TOKEN, help="OAuth token JSON path")
    p.add_argument("--out", type=Path, default=Path("recent.json"), help="Output JSON path")
    p.add_argument("--pages", type=int, default=4, help="playlistItems pages of up to 50 (default: 4)")
    p.add_argument("--max", type=int, default=None, help="Stop after this many uploads")
    p.add_argument(
        "--digit-only",
        action="store_true",
        help="When printing a short sample, show only titles that are 3-4 digits",
    )
    args = p.parse_args(argv)

    token = args.token.expanduser()
    if not token.is_file():
        print(f"Missing token file: {token}", file=sys.stderr)
        return 2

    creds = Credentials.from_authorized_user_file(str(token))
    yt = build("youtube", "v3", credentials=creds)
    items = yt.channels().list(part="snippet,contentDetails,statistics", mine=True).execute().get("items") or []
    if not items:
        print("No channel returned for this token (mine=True).", file=sys.stderr)
        return 2
    ch = items[0]
    print(
        "authorized_channel:",
        ch["snippet"]["title"],
        "videoCount=",
        ch.get("statistics", {}).get("videoCount"),
    )

    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    vids: list[tuple[str, str, str]] = []
    page_token = None
    pages = 0
    limit = args.max if args.max is not None else args.pages * 50
    while pages < args.pages and len(vids) < limit:
        resp = yt.playlistItems().list(
            part="snippet", playlistId=uploads, maxResults=50, pageToken=page_token
        ).execute()
        pages += 1
        for item in resp.get("items") or []:
            s = item["snippet"]
            vids.append((s["resourceId"]["videoId"], s["title"], s["publishedAt"]))
            if len(vids) >= limit:
                break
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    digit = [v for v in vids if re.fullmatch(r"\s*\d{3,4}\s*", v[1])]
    print("scanned", len(vids), "digit-titled", len(digit))
    args.out.write_text(json.dumps(vids), encoding="utf-8")
    sample = digit if args.digit_only else vids
    for row in sample[:15]:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
