#!/usr/bin/env python3
"""Apply YouTube title updates from a preview CSV.

Reads an allowlist of match types (exact, fuzzy, ...). For each allowed row:
  1. videos.list(part=snippet)
  2. Skip if the live title is no longer old_title
  3. Set snippet.title to new_title, keeping categoryId, description, tags,
     and defaultLanguage unchanged
  4. videos.update(part=snippet) unless --dry-run
  5. Append a row to the log CSV

Stops on YouTube quota errors. Does not print tokens or client secrets.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

DEFAULT_TOKEN = Path.home() / ".config" / "yt-rename" / "token.json"
VALID_TYPES = ("exact", "fuzzy", "ambiguous", "none")


def is_quota_error(exc: HttpError) -> bool:
    status = getattr(exc, "status_code", None) or (
        exc.resp.status if getattr(exc, "resp", None) is not None else None
    )
    text = str(exc).lower()
    reasons = ("quotaexceeded", "dailylimitexceeded", "usageratelimitexceeded", "quota exceeded")
    return status in (403, 429) and any(r in text.replace(" ", "") or r in text for r in reasons)


def log_row(log_path: Path, fieldnames: list[str], row: dict) -> None:
    exists = log_path.exists() and log_path.stat().st_size > 0
    with log_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            w.writeheader()
        w.writerow(row)


def load_rows(csv_path: Path, allow: set[str]) -> list[dict]:
    with csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    selected = []
    for r in rows:
        if r.get("match_type") not in allow:
            continue
        if not (r.get("new_title") or "").strip():
            continue
        if not r.get("videoId") or not r.get("old_title"):
            continue
        selected.append(r)
    return selected


def snippet_for_update(snippet: dict, new_title: str) -> dict:
    out = {
        "title": new_title,
        "categoryId": snippet.get("categoryId") or "22",
        "description": snippet.get("description", ""),
    }
    if "tags" in snippet:
        out["tags"] = snippet["tags"]
    if "defaultLanguage" in snippet:
        out["defaultLanguage"] = snippet["defaultLanguage"]
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Rename YouTube videos from a preview CSV")
    p.add_argument("--csv", type=Path, required=True, help="Preview CSV path")
    p.add_argument(
        "--allow",
        default="exact",
        help="Comma-separated match types to apply (default: exact). "
        "One or more of: exact,fuzzy,ambiguous,none",
    )
    p.add_argument("--log", type=Path, default=Path("rename-log.csv"), help="Log CSV path")
    p.add_argument("--token", type=Path, default=DEFAULT_TOKEN, help="OAuth token JSON path")
    p.add_argument("--dry-run", action="store_true", help="List and validate, but do not call videos.update")
    args = p.parse_args(argv)

    allow = {s.strip().lower() for s in args.allow.split(",") if s.strip()}
    unknown = allow - set(VALID_TYPES)
    if unknown:
        print(f"Unknown match types: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    if not args.csv.exists():
        print(f"Missing preview file: {args.csv}", file=sys.stderr)
        return 2
    token = args.token.expanduser()
    if not token.is_file():
        print(f"Missing token file: {token}", file=sys.stderr)
        return 2

    rows = load_rows(args.csv, allow)
    print(f"{'DRY RUN: ' if args.dry_run else ''}{len(rows)} row(s) with allow={sorted(allow)}")

    creds = Credentials.from_authorized_user_file(str(token))
    yt = build("youtube", "v3", credentials=creds)

    log_fields = [
        "timestamp",
        "videoId",
        "old_title",
        "new_title",
        "match_type",
        "status",
        "detail",
    ]

    updated = skipped = failed = 0
    for r in rows:
        vid = r["videoId"]
        old = r["old_title"]
        new = r["new_title"]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        base = {
            "timestamp": now,
            "videoId": vid,
            "old_title": old,
            "new_title": new,
            "match_type": r.get("match_type", ""),
        }
        try:
            resp = yt.videos().list(part="snippet", id=vid).execute()
        except HttpError as e:
            if is_quota_error(e):
                log_row(args.log, log_fields, {**base, "status": "quota", "detail": "quota error on videos.list; stopping"})
                print("Quota error on videos.list; stopping.", file=sys.stderr)
                return 3
            failed += 1
            log_row(args.log, log_fields, {**base, "status": "error", "detail": "list failed"})
            print(f"list failed for {vid}", file=sys.stderr)
            continue

        items = resp.get("items") or []
        if not items:
            skipped += 1
            log_row(args.log, log_fields, {**base, "status": "skipped", "detail": "video not found"})
            print(f"skip {vid}: video not found")
            continue

        snippet = items[0]["snippet"]
        current = snippet.get("title", "")
        if current.strip() != old.strip():
            skipped += 1
            log_row(
                args.log,
                log_fields,
                {**base, "status": "skipped", "detail": "live title no longer matches old_title"},
            )
            print(f"skip {vid}: live title no longer matches old_title")
            continue

        body = {"id": vid, "snippet": snippet_for_update(snippet, new)}
        if args.dry_run:
            updated += 1
            log_row(args.log, log_fields, {**base, "status": "dry_run", "detail": "would call videos.update"})
            print(f"dry-run {vid}: {old!r} -> {new!r}")
            continue

        try:
            yt.videos().update(part="snippet", body=body).execute()
        except HttpError as e:
            if is_quota_error(e):
                log_row(args.log, log_fields, {**base, "status": "quota", "detail": "quota error on videos.update; stopping"})
                print("Quota error on videos.update; stopping.", file=sys.stderr)
                return 3
            failed += 1
            log_row(args.log, log_fields, {**base, "status": "error", "detail": "update failed"})
            print(f"update failed for {vid}", file=sys.stderr)
            continue

        updated += 1
        log_row(args.log, log_fields, {**base, "status": "updated", "detail": ""})
        print(f"updated {vid}: {old!r} -> {new!r}")

    print(f"done. updated_or_dry={updated} skipped={skipped} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
