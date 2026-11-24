---
name: youtube-bulk-rename-from-orders
description: >-
  Use when someone wants to bulk-rename YouTube videos whose titles are just
  short order-number digits (e.g. delivery bodycam clips titled '4821') to full
  order strings taken from a chat export (WhatsApp self-chat, notes) using the
  YouTube Data API.
---
# Bulk-rename YouTube videos from order strings

Goal: videos titled with only the last 3-4 digits of an order number get renamed to the full order line the owner logged elsewhere, e.g. `M_D - Customer - OrderNumber - Street City`.

Helper scripts live in `scripts/` next to this skill: `auth.py`, `list.py`, `build_preview.py`, and `rename.py`. Paths, item counts, and the export file are flags; do not hard-code a channel, account, or working directory.

## Ground rules
- Only touch the one Google Cloud project you create or are given. Never enable billing. Never change anything on the channel except titles.
- Never print the client secret or refresh token. Store them at `~/.config/yt-rename/` (dir 700, files 600), or another path the owner names.
- Quota: `videos.update` costs 50 units; the free 10,000/day means about 200 renames/day, resetting at midnight Pacific. `videos.list` and `playlistItems.list` cost 1.
- Apps in Testing mode issue refresh tokens that expire after 7 days. Re-run auth if you get `invalid_grant`.
- Exact matches can be applied; anything fuzzy gets shown to the owner first.

## 1. Google Cloud setup (browser, signed in as the owner)
1. Create or open one project. Enable **YouTube Data API v3**.
2. OAuth consent screen: External, Testing. Add the Google account **that owns the channel** as a test user (often a different account than the one that owns the project; ask which account the channel lives on).
3. Credentials, Create OAuth client ID, type **Desktop app**.
4. Gotcha: Google no longer lets you download an existing client secret. If the JSON was never saved, open the client, use **Add secret** (max 2 per client; maximize the window if the panel is hidden), and download the JSON right then. Save it as `~/.config/yt-rename/client.json`.

## 2. Authorize
- Python venv (system pip may be PEP 668 locked): `python3 -m venv .venv && .venv/bin/pip install google-auth-oauthlib google-api-python-client`.
- Run `scripts/auth.py` (loopback on localhost, default port 8765, `access_type=offline`, `prompt=consent`, scope `youtube.force-ssl`). Approve in a browser on the same machine as the channel-owner account; click through the 'unverified app' warning. The script writes `token.json` (0600).
- Verify with `channels.list(part='snippet,contentDetails', mine=True)` and confirm the channel name with the owner.

## 3. List candidates
- Run `scripts/list.py` (optional `--pages`, `--max`, `--out`). It reads the uploads playlist id from `contentDetails.relatedPlaylists.uploads` and pages `playlistItems.list` (newest first). Note: `channels.list` videoCount can undercount; trust the playlist.
- Keep videos whose title, stripped of whitespace, is only 3-4 digits. Take the newest N (default 50; owner may cap by count or time).

## 4. Parse the order log
- WhatsApp export lines look like `3/4/25, 9:00 AM - Sender: 3_4 - Customer Name - ABC000111222 - 123 Main St - Example City`. Join continuation lines to their message.
- Treat a message as an order if it has a long digit or alphanumeric token (order #). When the same order appears more than once, keep the latest, most complete line.

## 5. Match (write a preview CSV: videoId, publishedAt, old_title, new_title, match_type, note)
Run `scripts/build_preview.py` with `--export`, `--recent`, `--csv`, `--n`, and optional `--timezone` (must match the export's timestamps).
- **exact**: the video digits equal the last 3-4 characters of the order number, and the order date is the upload day or up to 6 days before. If several orders tie, pick the one closest to the upload date; note the others.
- **fuzzy**: 4-digit titles only, same length suffix differs by 1-2 digits (Hamming), same date window. Never fuzzy-match 3-digit titles.
- **none**: no candidate. Some digits are not orders (e.g. a store number); leave them.
- Two videos with the same digits may legitimately match the same order; flag it.
- New title is the order line copied exactly, at most 100 characters, with `<` and `>` removed.

## 6. Rename
- Show the owner the preview and wait for a yes before any `videos.update`. Apply `exact` first. Show the fuzzy list (old digits vs the order number) and apply only after a yes. Report the 'none' list.
- Run `scripts/rename.py --csv preview.csv --allow exact` (add `fuzzy` only after approval). For each approved row: `videos.list(part='snippet', id=...)`; skip if the live title (stripped) no longer equals old_title (stripped); set only `snippet.title`, and resend `categoryId`, `description`, `tags`, `defaultLanguage` unchanged (update replaces the whole snippet). `videos.update(part='snippet', body=...)`.
- Log each row (timestamp, id, old, new, type, status). Stop on `quotaExceeded`; resume the next day.
- To undo, run the log back with old and new swapped.

## 7. Report
Counts renamed, skipped (with reason), fuzzy pending, no-match, plus one example video link (`https://youtu.be/<id>`).

## Example prompts
- "Rename my last 50 bodycam videos that are just numbers. The full order info is in this WhatsApp export."
- "Some of my YouTube titles are only the last 4 of the order number. Match them to my order log and show me a preview before you change anything."
- "Keep going on the YouTube renames from yesterday. Do as many as today's quota allows, exact matches only."
- "The refresh token expired. Re-authorize the YouTube rename app on the channel account and finish the remaining videos."
- "Undo the renames from this morning using the rename log."
