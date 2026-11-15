---
name: bot-server-office-page
description: >-
  Use when publishing a public status page for an OpenMausBot (or similar)
  server: a pixel-art office scene with live bot status cards, a time-of-day
  window, and a wall TV showing a sibling server's status, fed by a no-token
  status pusher.
---
# Bot server office page

Builds a public subdirectory page (e.g. `<domain>/<servername>/`) that shows a bot server's live state as an animated pixel-art office. Costs no AI tokens: the feed reads local APIs only.

## Inputs to gather first
- Server name, and the subdirectory slug to publish under.
- Each bot's name, role, model, and avatar. A screenshot of the bot app's team list is enough: note each avatar's shape (e.g. hexagon, triangle, droplet) and color.
- How you'll upload to the web host (for example a cPanel API token stored in a file with mode 600 on the server, never in chat). Give each server its own revocable token.
- Sibling servers the wall TV should show.
- The owner's time zone, for the window.

## 1. Art (delegate to an artist)
Ask for a fixed stage, for example 1280x720 at 4x room scale, containing:
- The room background, with the TV frame baked in, plus foreground, shadow, tint, and lamp layers.
- A sprite sheet for each bot at 3x with idle and working frames.
- Status card art (for example 360x108 with a text box and a status-light slot) and status lights for working, waiting, idle, error, and sleeping.
- Window tint overlays for dawn, day, sunset, and night.
- A TV screen, static, a server icon, and online and offline badges (a green check and a red X).
- A manifest.json giving every layer's position and z-order.

### Matching sprites to app avatars
- Reuse one sprite generator across servers so every office looks like the same family: same sprite size, frames, desk, and shared round face (two dots and a smile) unless an avatar clearly differs.
- Build each bot from its avatar's shape and light, mid, and dark colors sampled from the avatar screenshot. Bots that share a shape share a base sprite, recolored.
- List the lead bot (e.g. the right-hand bot) first so it gets the front-center desk.
- Keep job text out of the art config.
- If a shape or color is ambiguous, pick the closest and tell the owner the mapping used.

## 2. Status pusher (on each bot server)
- Write a small script, run as a user systemd service at low priority (nice 15), looping every 15 seconds.
- Each cycle, read the local bot API (health, plus each bot's current or last job) and the bot list, then write `status.json`.
  - Bot fields: id, name, role, model, state, and a job string or null.
  - Server fields: host, online, cpu_pct, mem_used_gb, mem_total_gb, bots_working, bots_total, uptime_s, and updated.
  - Publish the configured bot order, then any other bots the API reports.
  - If the bot API is down, publish host CPU, memory, and uptime only, and omit bot rows and counts rather than guessing.
- Upload the file to the subdirectory through the host's API.
- Every server pushes its own feed directly. Don't relay one server's status through another; it adds a dependency.
- For a remote headless server the owner reaches only by SSH from a phone, ship the pusher as a one-command installer: host it briefly, run it with `bash <(curl -fsSL <url>)`, have it prompt for the token through `/dev/tty` and save it with mode 600 (never printed), then delete the hosted copy.
- Reread the config each cycle so flags like `SHOW_TASK_TEXT` apply without a restart.
- Never invent job text.
  - Scrub emails, URLs, phone numbers, IPs, tokens, file paths, and personal names, then cap the result at the card's line width (about 41 characters).
  - If no real text is available, send null so the page falls back to a status word.
- Ask the owner before showing real prompt text on a public page.
- Turn on linger so the service survives reboots without a login:

```
sudo loginctl enable-linger <user>
```

- Add an `.htaccess` that makes `status.json` no-cache. Don't use host-specific cache directives that can break the file; test that it returns 200.

## 3. Page
- Use the same layout as the other server pages: a centered text column, with the office scene capped at about 960px wide and scaled responsively.
- Poll `status.json` every 15 seconds with a cache-busting query string. Render with textContent only.
- If the feed is stale for more than 2 minutes, show everything as sleeping or offline.
- Each card has 3 lines:
  1. Name and role.
  2. Model.
  3. The real job text, or else Working…, Waiting…, or Idle.
- Animate the sprites by state.
- Render the "who lives here" list (name, role, model) from `status.json` too, with a static HTML fallback if the feed fails.
- Every office, including a second server's, gets the window: pick the tint from the owner's time zone using Intl: dawn 6–8, day 8–17, sunset 17–19, night 19–6, with a 20-minute crossfade. Add a `?phase=` override for testing that also accepts morning, afternoon, and evening as aliases.
- The wall TV fetches the sibling server's `status.json` and links to the sibling's page; give the sibling a mirror TV that links back.
  - When fresh, show a green check plus readable stats. Keep each stat line to about 17 characters (e.g. `CPU 12% RAM 3/12G`, dropping the word RAM if it overflows).
  - When missing or stale, show OFFLINE, a red X, "never seen" or the last-seen time, and blank stats.
  - Never create a fake sibling file.
- Link the footer brand name to the site's home page in the same tab, styled only slightly brighter than muted text with a faint dotted underline that turns solid on hover.

## 4. Verify and deliver
- Every asset and `status.json` returns 200, and `status.json` timestamps advance about every 15 seconds.
- Take screenshots on desktop and mobile, and in each `?phase`. Send them with the live link.

## Public page rules
The page must never show Tailscale URLs, internal IPs, serial numbers, tokens, or personal names. Keep bot servers' admin ports off the public internet.
