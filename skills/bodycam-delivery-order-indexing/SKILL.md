---
name: bodycam-delivery-order-indexing
description: >-
  Use when someone wants to index bodycam videos of delivery orders: turn
  delivery-app screenshots into order strings (drop-off or pickup), then
  bulk-rename YouTube videos titled with just 3-4 order digits to those full
  strings using the YouTube Data API.
---
# Bodycam delivery order indexing

Two stages:
1. **Index the orders.** The driver screenshots the delivery app and an AI turns each screenshot into one order string, which gets pasted into a log (e.g. a WhatsApp self-chat).
2. **Index the videos.** Bodycam clips uploaded to YouTube are titled with only the last 3-4 digits of the order number. Match each one to its full order string and rename it.

## Add-on prompt files (in this skill's `prompts/` folder)
The skill includes two ready-to-use prompts. Read the one that fits and use it exactly as written, or hand it to the owner or another AI to paste in with screenshots.
- `prompts/preindex.prp`: **drop-off**. One or more delivery screenshots (Roadie and similar apps) become one line per delivery: `M_D - Recipient Name - Full Order Number(s) - Street Address City`. Use the long Order number (not the short OSN). Separate two orders for the same recipient with ", ". WH or WN numbers are used as is. Drop the state and ZIP; keep the apartment.
- `prompts/preindexpickup.prp`: **pickup**. An "Orders for Pickup" screen becomes one line: `MM_DD - Name1 - OrderID1 - Name2 - OrderID2 ...`, in screen order, with ALL CAPS names kept and partly cut-off rows skipped.
When asked to index screenshots, apply the matching prompt and output only the string(s).

## Ground rules for renaming
- Only touch the one Google Cloud project you create or are given. Never enable billing. Never change anything on the channel except titles.
- Never print the client secret or refresh token. Store them at `~/.config/yt-rename/` (dir 700, files 600).
- Quota: `videos.update` costs 50 units; the free 10,000/day means about 200 renames/day, resetting at midnight Pacific. `videos.list` and `playlistItems.list` cost 1.
- Apps in Testing mode issue refresh tokens that expire after 7 days. Re-run auth if you get `invalid_grant`.
- Exact matches can be applied; anything fuzzy gets shown to the owner first.
- Scripts for steps 2-6 are in `scripts/` when this skill was installed from its GitHub repo.

## 1. Google Cloud setup (browser, signed in as the owner)
1. Create or open one project. Enable **YouTube Data API v3**.
2. OAuth consent screen: External, Testing. Add the Google account **that owns the channel** as a test user (often a different account than the one that owns the project; ask which account the channel lives on).
3. Credentials, Create OAuth client ID, type **Desktop app**.
4. Gotcha: Google no longer lets you download an existing client secret. If the JSON was never saved, open the client, use **Add secret** (max 2 per client; maximize the window if the panel is hidden), and download the JSON right then. Save it as `~/.config/yt-rename/client.json`.

## 2. Authorize
- Python venv (system pip may be PEP 668 locked): `python3 -m venv .venv && .venv/bin/pip install google-auth-oauthlib google-api-python-client`.
- `InstalledAppFlow.from_client_secrets_file(client.json, scopes=['https://www.googleapis.com/auth/youtube.force-ssl'])`, `run_local_server(port=8765, access_type='offline', prompt='consent')`. Approve in a browser on the same machine, signed in as the channel-owner account; click through the 'unverified app' warning. Write the credentials to `token.json` (0600).
- Verify with `channels.list(part='snippet,contentDetails', mine=True)` and confirm the channel name with the owner.

## 3. List candidates
- Get the uploads playlist id from `contentDetails.relatedPlaylists.uploads` and page `playlistItems.list` (newest first). `channels.list` videoCount can undercount; trust the playlist.
- Keep videos whose title, stripped of whitespace, is only 3-4 digits. Take the newest N (default 50; owner may cap by count or time).

## 4. Parse the order log
- WhatsApp export lines look like `2/16/25, 7:01 AM - Sender: 2_16 - Name - 200012345678901 - 123 Example Ave - City`. Join continuation lines to their message.
- Drop-off lines carry one or two order numbers; pickup lines carry several name and order ID pairs. Every order ID in a line is a match candidate for that line.
- When the same order appears more than once, keep the latest, most complete line.

## 5. Match (write a preview CSV: videoId, publishedAt, old_title, new_title, match_type, note)
- **exact**: the video digits equal the last 3-4 characters of an order ID, and the order date is the upload day or up to 6 days before. If several orders tie, pick the one closest to the upload date; note the others.
- **fuzzy**: 4-digit titles only, the suffix differs by 1-2 digits, same date window. Never fuzzy-match 3-digit titles.
- **none**: no candidate. Some digits are not orders (e.g. a store number); leave them.
- Two videos with the same digits may legitimately match the same order; flag it.
- The new title is the order line copied exactly, at most 100 characters, with `<` and `>` removed. If a long pickup line must be cut, keep the date and the matched name and order pair.

## 6. Rename
- For each approved row, call `videos.list(part='snippet', id=...)`. Skip if the live title (stripped) no longer equals old_title (stripped). Change only `snippet.title`, and send `categoryId`, `description`, `tags` and `defaultLanguage` back unchanged, because the update replaces the whole snippet. Then call `videos.update(part='snippet', body=...)`.
- Log each row (timestamp, id, old, new, type, status). Stop on `quotaExceeded`; resume the next day.
- Apply `exact` first. Show the owner the fuzzy list (old digits next to the order number) and apply only after a yes. Report the 'none' list.
- To undo, run the log back with old and new swapped.

## 7. Report
Counts renamed, skipped (with reason), fuzzy pending and no match, plus one example video link (`https://youtu.be/<id>`).

## Example prompts
- "Here are today's drop-off screenshots. Index them with the bodycam delivery indexing skill."
- "Index this pickup screen for me."
- "Rename my last 50 bodycam videos that are just numbers. The full order info is in this WhatsApp export."
- "Some of my YouTube titles are only the last 4 of the order number. Match them to my order log and show me a preview before you change anything."
- "Keep going on the YouTube renames from yesterday. Do as many as today's quota allows, exact matches only."
- "The refresh token expired. Re-authorize the YouTube rename app on the channel account and finish the remaining videos."
- "Undo the renames from this morning using the rename log."
