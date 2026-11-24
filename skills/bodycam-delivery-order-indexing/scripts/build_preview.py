#!/usr/bin/env python3
"""Build a YouTube rename preview from a recent-uploads JSON file and an order log.

No API writes. Paths, N, and timezone are flags; this script is channel-independent.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, date, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

LINE_START = re.compile(
    r"^(\d{1,2}/\d{1,2}/\d{2}),\s+(\d{1,2}:\d{2})\s*[\u202f\u00a0 ]?([AP]M)\s+-\s+(.*?):\s?(.*)$"
)
ORDER_PREFIX = re.compile(r"^\s*[A-Za-z]?(\d{1,2}_\d{1,2})\s*-")
# Common order-id shapes: long digit strings, letters+digits, retailer-style prefixes.
# Extend this if a new export uses a different token format.
TOKEN_RE = re.compile(
    r"""
    (?:
        [A-Z]{2,5}[A-Z0-9]*-\d+
      | \d{6,}_\d{6,}
      | [A-Z]{1,5}\d[\dA-Z_-]{4,}
      | \d{6,}
    )
    """,
    re.I | re.X,
)
ADDR_HINT = re.compile(
    r"\b(?:Ave|Av|Avenue|Dr|Drive|St|Street|Ct|Court|Ln|Lane|Blvd|Way|Cir|"
    r"Circle|Ter|Terrace|Pl|Place|Rd|Road|Hwy|Trl|Trail|Pkwy|Parkway|"
    r"Unit|Apt|Ste|Suite|#)\b",
    re.I,
)

DEFAULT_WINDOW_BEFORE = 6  # order date may be up to N days before publish
DEFAULT_WINDOW_AFTER = 1  # timezone slack (days)
DEFAULT_MSG_SLACK_HOURS = 2  # WhatsApp line may land slightly after publish


def parse_wa(path: Path) -> list[dict]:
    msgs = []
    cur = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = LINE_START.match(line)
        if m:
            if cur:
                msgs.append(cur)
            date_s, time_s, ap, sender, body = m.groups()
            dt = datetime.strptime(f"{date_s} {time_s} {ap}", "%m/%d/%y %I:%M %p")
            cur = {"dt": dt, "sender": sender, "body": body.strip()}
        elif cur:
            cur["body"] += "\n" + line
    if cur:
        msgs.append(cur)
    return msgs


def is_order_body(body: str) -> bool:
    return bool(ORDER_PREFIX.match(body.strip()))


def order_date_of(body: str, msg_dt: datetime) -> date:
    m = ORDER_PREFIX.match(body.strip())
    if not m:
        return msg_dt.date()
    month, day = (int(x) for x in m.group(1).split("_"))
    year = msg_dt.year
    try:
        od = datetime(year, month, day)
        if od - msg_dt > timedelta(days=20):
            od = datetime(year - 1, month, day)
        return od.date()
    except ValueError:
        return msg_dt.date()


def extract_tokens(body: str) -> list[str]:
    found = TOKEN_RE.findall(body)
    found = list(dict.fromkeys(found))
    kept = []
    for t in found:
        if any(t != u and t in u and re.fullmatch(r"\d+", t) for u in found):
            continue
        kept.append(t)
    return kept


def digit_suffix(token: str, n: int) -> str | None:
    digits = re.sub(r"\D", "", token)
    if len(digits) >= n:
        return digits[-n:]
    return None


def has_address(body: str) -> bool:
    return bool(re.search(r"\d+\s+\S+", body) and ADDR_HINT.search(body))


def completeness_score(body: str, token: str, msg_dt: datetime) -> tuple:
    toks = extract_tokens(body)
    focused = 1 if len(toks) <= 2 else 0
    return (
        1 if has_address(body) else 0,
        focused,
        len(body),
        msg_dt.timestamp(),
    )


def to_youtube_title(body: str) -> tuple[str, str]:
    """Return (title, note_about_changes)."""
    note_parts = []
    s = " ".join(body.replace("\n", " ").split())
    if "<" in s or ">" in s:
        s = s.replace("<", "").replace(">", "")
        note_parts.append("stripped < > for YouTube")
    if len(s) > 100:
        def shrink(m):
            return m.group(1)[-4:] + (" " if m.group(2) else "")

        shrunk = re.sub(r"\b(\d{8,})(,\s*)?", shrink, s)
        shrunk = " ".join(shrunk.split())
        if len(shrunk) <= 100:
            s = shrunk
            note_parts.append("shortened long order numbers to last 4 digits to fit 100-char limit")
        else:
            s = shrunk
            cut = s[:100]
            for sep in [" - ", " , ", ", ", " "]:
                i = cut.rfind(sep)
                if i >= 60:
                    cut = cut[:i].rstrip(" -,")
                    break
            s = cut[:100]
            note_parts.append(f"truncated to {len(s)} chars (YouTube 100-char limit)")
    return s, "; ".join(note_parts)


def hamming(a: str, b: str) -> int | None:
    if len(a) != len(b):
        return None
    return sum(x != y for x, y in zip(a, b))


def parse_pub(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def in_window(pub: datetime, od: date, window_before: int, window_after: int) -> bool:
    delta = (pub.date() - od).days
    return -window_after <= delta <= window_before


def pub_local(pub: datetime, tz: ZoneInfo) -> datetime:
    """publishedAt is UTC; chat-export timestamps are naive in the export's local zone."""
    return pub.replace(tzinfo=timezone.utc).astimezone(tz).replace(tzinfo=None)


def usable_order(o: dict, pub: datetime, tz: ZoneInfo, window_before: int, window_after: int, slack: timedelta) -> bool:
    if not in_window(pub, o["od"], window_before, window_after):
        return False
    return o["dt"] <= pub_local(pub, tz) + slack


def claim_from_already_renamed(already, orders):
    """Tokens and 3-4 digit suffixes already used in titles that are not digit-only."""
    claimed_tokens: set[str] = set()
    claimed_suffixes: set[str] = set()
    bodies = {o["body"]: o for o in orders}
    for _vid, title, _pub in already:
        claimed_tokens |= set(extract_tokens(title))
        for n in re.findall(r"\b\d{3,6}\b", title):
            if len(n) in (3, 4):
                claimed_suffixes.add(n)
            if len(n) > 4:
                claimed_suffixes.add(n[-4:])
                claimed_suffixes.add(n[-3:])
        if title in bodies:
            o = bodies[title]
            claimed_tokens |= set(o["toks"])
            for tok in o["toks"]:
                for k in (3, 4):
                    s = digit_suffix(tok, k)
                    if s:
                        claimed_suffixes.add(s)
        else:
            # Shortened titles that still contain every order's last 4 digits
            for o in orders:
                last4 = [digit_suffix(t, 4) for t in o["toks"]]
                last4 = [s for s in last4 if s]
                if len(last4) >= 2 and all(s in title for s in last4):
                    claimed_tokens |= set(o["toks"])
                    claimed_suffixes.update(last4)
    return claimed_tokens, claimed_suffixes


def unique_best_for_token(cands: list[dict], token: str) -> dict:
    return max(cands, key=lambda o: completeness_score(o["body"], token, o["dt"]))


def build_rows(
    orders: list[dict],
    videos: list,
    n_limit: int,
    tz: ZoneInfo,
    window_before: int,
    window_after: int,
    slack: timedelta,
) -> list[dict]:
    digit = [v for v in videos if re.fullmatch(r"\s*\d{3,4}\s*", v[1])]
    already = [v for v in videos if not re.fullmatch(r"\s*\d{3,4}\s*", v[1])]
    target = digit[:n_limit]

    claimed_tokens, claimed_suffixes = claim_from_already_renamed(already, orders)

    exact_maps = []
    for vid, title, pub in target:
        pubdt = parse_pub(pub)
        needle = title.strip()
        n = len(needle)
        hits = []
        for o in orders:
            if not usable_order(o, pubdt, tz, window_before, window_after, slack):
                continue
            for tok in o["toks"]:
                suf = digit_suffix(tok, n)
                if suf == needle:
                    hits.append((tok, o, suf))
        exact_maps.append(hits)

    for hits in exact_maps:
        for tok, o, s in hits:
            claimed_tokens.add(tok)
            claimed_suffixes.add(s)

    rows = []
    for (vid, title, pub), hits in zip(target, exact_maps):
        pubdt = parse_pub(pub)
        needle = title.strip()
        n = len(needle)
        note_bits = []

        by_tok: dict[str, list] = defaultdict(list)
        for tok, o, suf in hits:
            by_tok[tok].append(o)
        best_per_tok = {tok: unique_best_for_token(cands, tok) for tok, cands in by_tok.items()}
        bodies: dict[str, list] = {}
        for tok, o in best_per_tok.items():
            bodies.setdefault(o["body"], []).append(tok)

        if len(bodies) == 1:
            body = next(iter(bodies))
            toks = bodies[body]
            new_title, tnote = to_youtube_title(body)
            if tnote:
                note_bits.append(tnote)
            all_bodies = sorted({o["body"] for _, o, _ in hits})
            if len(all_bodies) > 1:
                others = [b for b in all_bodies if b != body]
                note_bits.append(
                    "chose latest/most complete string"
                    + (f" (also saw: {others[0][:80]})" if others else "")
                )
            od = order_date_of(body, best_per_tok[toks[0]]["dt"])
            delta = (pubdt.date() - od).days
            note_bits.append(
                f"exact suffix {needle} of {', '.join(toks)}; order {delta}d before publish"
            )
            rows.append(
                {
                    "videoId": vid,
                    "publishedAt": pub,
                    "old_title": needle,
                    "new_title": new_title,
                    "match_type": "exact",
                    "candidates_note": "; ".join(note_bits),
                    "_toks": toks,
                    "_body": body,
                }
            )
            continue
        if len(bodies) > 1:
            parts = []
            for body, toks in bodies.items():
                od = None
                for tok, o, _ in hits:
                    if o["body"] == body:
                        od = o["od"]
                        break
                parts.append(f"{'/'.join(toks)} ({od}): {to_youtube_title(body)[0]}")
            rows.append(
                {
                    "videoId": vid,
                    "publishedAt": pub,
                    "old_title": needle,
                    "new_title": "",
                    "match_type": "ambiguous",
                    "candidates_note": "multiple exact suffix matches in date window: " + " || ".join(parts),
                    "_toks": [],
                    "_body": "",
                }
            )
            continue

        # Fuzzy: Hamming distance 1-2 on the same-length suffix only.
        # 3-digit titles are not fuzzed — too many 1-off collisions among last-3 digits.
        if n < 4:
            rows.append(
                {
                    "videoId": vid,
                    "publishedAt": pub,
                    "old_title": needle,
                    "new_title": "",
                    "match_type": "none",
                    "candidates_note": (
                        "No exact suffix match in the date window. Fuzzy matching is not applied "
                        "to 3-digit titles (too many last-3 collisions)."
                    ),
                    "_toks": [],
                    "_body": "",
                }
            )
            continue

        fuzzy = []
        for o in orders:
            if not usable_order(o, pubdt, tz, window_before, window_after, slack):
                continue
            for tok in o["toks"]:
                suf = digit_suffix(tok, n)
                if not suf:
                    continue
                if tok in claimed_tokens or suf in claimed_suffixes:
                    continue
                dist = hamming(suf, needle)
                if dist is None or not (1 <= dist <= 2):
                    continue
                fuzzy.append((dist, tok, o, suf))

        if fuzzy:
            min_d = min(d for d, *_ in fuzzy)
            at_min = [f for f in fuzzy if f[0] == min_d]
            by_tok = defaultdict(list)
            for d, tok, o, suf in at_min:
                by_tok[tok].append(o)
            best_per_tok = {tok: unique_best_for_token(cands, tok) for tok, cands in by_tok.items()}
            bodies = {}
            for tok, o in best_per_tok.items():
                bodies.setdefault(o["body"], []).append(tok)
            shown = []
            for tok, o in best_per_tok.items():
                suf = digit_suffix(tok, n)
                shown.append(
                    f"{needle}~{suf} (Hamming {min_d}) {tok} {o['od']}: {to_youtube_title(o['body'])[0]}"
                )
            if len(bodies) == 1:
                body = next(iter(bodies))
                new_title, tnote = to_youtube_title(body)
                note = f"FUZZY off-by-{min_d} digit(s): " + "; ".join(shown)
                if tnote:
                    note = tnote + "; " + note
                rows.append(
                    {
                        "videoId": vid,
                        "publishedAt": pub,
                        "old_title": needle,
                        "new_title": new_title,
                        "match_type": "fuzzy",
                        "candidates_note": note,
                        "_toks": bodies[body],
                        "_body": body,
                    }
                )
            else:
                rows.append(
                    {
                        "videoId": vid,
                        "publishedAt": pub,
                        "old_title": needle,
                        "new_title": "",
                        "match_type": "ambiguous",
                        "candidates_note": f"multiple fuzzy Hamming-{min_d} matches: " + " || ".join(shown),
                        "_toks": [],
                        "_body": "",
                    }
                )
            continue

        rows.append(
            {
                "videoId": vid,
                "publishedAt": pub,
                "old_title": needle,
                "new_title": "",
                "match_type": "none",
                "candidates_note": (
                    "No exact or 1-2 digit suffix match in the publish-date window "
                    "(order same day or up to 6 days before, chat line not after the upload)."
                ),
                "_toks": [],
                "_body": "",
            }
        )

    body_counts = Counter(r["_body"] for r in rows if r["_body"] and r["match_type"] == "exact")
    for r in rows:
        if r["_body"] and body_counts[r["_body"]] > 1:
            r["candidates_note"] += (
                f"; NOTE: {body_counts[r['_body']]} digit-titled videos share this exact order string"
            )
    return rows


def write_preview(rows: list[dict], csv_path: Path, md_path: Path | None, n_limit: int) -> None:
    fields = ["videoId", "publishedAt", "old_title", "new_title", "match_type", "candidates_note"]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in fields})

    if md_path is None:
        return

    counts = Counter(r["match_type"] for r in rows)
    exact_examples = [r for r in rows if r["match_type"] == "exact"][:5]
    fuzzy = [r for r in rows if r["match_type"] == "fuzzy"]
    ambig = [r for r in rows if r["match_type"] == "ambiguous"]
    none = [r for r in rows if r["match_type"] == "none"]

    def md_row(r):
        nt = r["new_title"] or "(none)"
        return (
            f"- `{r['videoId']}` published {r['publishedAt']}  \n"
            f"  old: `{r['old_title']}` → new: `{nt}`  \n"
            f"  {r['candidates_note']}"
        )

    md = [
        "# YouTube rename preview",
        "",
        "Preview only — no YouTube titles were changed.",
        "",
        f"## Counts ({n_limit} newest digit-titled videos)",
        "",
        f"- exact: {counts.get('exact', 0)}",
        f"- fuzzy: {counts.get('fuzzy', 0)}",
        f"- ambiguous: {counts.get('ambiguous', 0)}",
        f"- none: {counts.get('none', 0)}",
        "",
        "## Rules used for new titles",
        "",
        "- Format is an exact copy of the latest, most complete order string, usually `M_D - Name - OrderNumber - Street City`.",
        "- YouTube titles cannot contain `<` or `>` and are capped at 100 characters. If a string exceeds 100 characters, shorten long numeric order IDs to their last 4 digits and join them with spaces, and only then truncate.",
        "- Prefer the latest individual string that includes an address over an earlier name-and-number-only line or a multi-stop combo line, when the video matches a single order number.",
        "- The order date in the string should be the same day as the upload or up to a few days before (batch uploads). Default window: 0–6 days before publish, plus 1 day of timezone slack. A chat line posted more than 2 hours after the upload is not used.",
        "- The digit title is the last 3–4 digits of the order number. Off-by-one or off-by-two suffix matches (Hamming distance on the same-length suffix) are flagged `fuzzy`. 3-digit titles are exact-only, because last-3 collisions are common.",
        "",
        "## Fuzzy rows (review before renaming)",
        "",
    ]
    if fuzzy:
        md.extend(md_row(r) for r in fuzzy)
    else:
        md.append("_None._")
    md += ["", "## Ambiguous rows", ""]
    if ambig:
        md.extend(md_row(r) for r in ambig)
    else:
        md.append("_None._")
    md += ["", "## None (no match)", ""]
    if none:
        md.extend(md_row(r) for r in none)
    else:
        md.append("_None._")
    md += ["", "## Example exact rows", ""]
    if exact_examples:
        md.extend(md_row(r) for r in exact_examples)
    else:
        md.append("_None._")
    md.append("")
    md_path.write_text("\n".join(md), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Match digit-titled YouTube uploads to an order-log export.")
    p.add_argument("--export", type=Path, required=True, help="Chat export or order log (WhatsApp .txt or similar)")
    p.add_argument("--recent", type=Path, required=True, help="JSON from list.py: [[videoId, title, publishedAt], ...]")
    p.add_argument("--csv", type=Path, default=Path("preview.csv"), help="Preview CSV output path")
    p.add_argument("--md", type=Path, default=None, help="Optional markdown preview path")
    p.add_argument("--n", type=int, default=50, help="Newest digit-titled videos to consider (default: 50)")
    p.add_argument(
        "--timezone",
        default="America/New_York",
        help="IANA timezone of naive timestamps in the export (default: America/New_York)",
    )
    p.add_argument("--window-before", type=int, default=DEFAULT_WINDOW_BEFORE, help="Max days the order date may precede publish")
    p.add_argument("--window-after", type=int, default=DEFAULT_WINDOW_AFTER, help="Days of timezone slack after publish date")
    p.add_argument("--slack-hours", type=int, default=DEFAULT_MSG_SLACK_HOURS, help="Hours a chat line may land after publish")
    args = p.parse_args(argv)

    if not args.export.is_file():
        print(f"Missing export: {args.export}", file=sys.stderr)
        return 2
    if not args.recent.is_file():
        print(f"Missing recent-uploads JSON: {args.recent}", file=sys.stderr)
        return 2

    tz = ZoneInfo(args.timezone)
    slack = timedelta(hours=args.slack_hours)

    msgs = parse_wa(args.export)
    orders = []
    for m in msgs:
        body = m["body"].strip()
        if not is_order_body(body):
            continue
        toks = extract_tokens(body)
        if not toks:
            continue
        od = order_date_of(body, m["dt"])
        orders.append({"dt": m["dt"], "od": od, "body": body, "toks": toks})

    videos = json.loads(args.recent.read_text(encoding="utf-8"))
    rows = build_rows(orders, videos, args.n, tz, args.window_before, args.window_after, slack)
    write_preview(rows, args.csv, args.md, args.n)

    counts = Counter(r["match_type"] for r in rows)
    print("Wrote", args.csv, end="")
    if args.md:
        print(" and", args.md)
    else:
        print()
    print("counts", dict(counts))
    print("\nEXACT examples:")
    for r in [row for row in rows if row["match_type"] == "exact"][:5]:
        print(f"  {r['old_title']} -> {r['new_title']}")
    print("\nFUZZY:")
    for r in [row for row in rows if row["match_type"] == "fuzzy"]:
        print(f"  {r['old_title']} -> {r['new_title']}")
        print(f"    {r['candidates_note']}")
    print("\nAMBIGUOUS:")
    for r in [row for row in rows if row["match_type"] == "ambiguous"]:
        print(f"  {r['old_title']}: {r['candidates_note']}")
    print("\nNONE:")
    for r in [row for row in rows if row["match_type"] == "none"]:
        print(f"  {r['old_title']} {r['publishedAt']}: {r['candidates_note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
