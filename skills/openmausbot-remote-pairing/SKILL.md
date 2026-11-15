---
name: openmausbot-remote-pairing
description: >-
  Use when an OpenMausBot server behind a reverse proxy or tunnel (Cloudflare
  Tunnel, Tailscale Serve, nginx) answers every page with 403 'this request came
  through a proxy (pair this device...)' and a desktop app, phone, or browser
  can't pair to it.
---
# Pair a device to a headless OpenMausBot server behind a proxy

## Symptom
- The public URL (and `/pair`) returns HTTP 403 JSON: `forbidden: this request came through a proxy (pair this device to use the server remotely)`.
- The desktop app's "Hosted" panel shows that same JSON. No pairing attempt shows up in the server log.

## Healthy signs (the tunnel is fine, so don't touch it)
- `GET /.well-known/openmausbot/environment` returns 200.
- `POST /api/auth/pair` with a bad code returns 401 `pairing_code_wrong`.
- Tunnel down looks different: Cloudflare 1033, a 502, or a timeout.

## Root cause
A headless install has no web UI directory configured, so `/` and `/pair` fall through to the proxy 403. The package already ships the UI in `<global node_modules>/openmausbot/dist`. The server only serves it when `OMB_STATIC_DIR` is set.

## Fix (on the server, as the user that runs the unit)
1. Confirm that the unit is a user unit and find node: `systemctl --user cat openmausbot | grep ExecStart`. The node path in there is the one to use. The CLI fails over SSH with `env: 'node': No such file` unless that node directory is on PATH.
2. Add a drop-in, then restart (it's reversible: delete the file and restart):
   ```
   mkdir -p ~/.config/systemd/user/openmausbot.service.d
   printf '[Service]\nEnvironment=OMB_STATIC_DIR=%%h/.local/lib/node_modules/openmausbot/dist\n' > ~/.config/systemd/user/openmausbot.service.d/static.conf
   systemctl --user daemon-reload && systemctl --user restart openmausbot
   ```
   Adjust the dist path to wherever the package is installed.
3. Verify that `curl -s -o /dev/null -w '%{http_code}' https://<public-host>/pair` now returns 200.

## Pair
1. The owner runs this on the server (the code is a one-time credential, so never paste it into chat):
   `export PATH=<node bin dir>:$PATH; openmausbot pair --label <device> --public-url https://<public-host> --ttl 24h`
2. Open the printed link ending in `/pair#code=...`, either in the desktop app (＋ → Connect to a server) or in a browser.
3. Confirm with `openmausbot devices`: the new device should be listed.

## Don't
- Don't reinstall the tunnel or put another login wall in front of it. Pairing is the gate.
- Don't point the desktop app at its own local server (`127.0.0.1:<port>`) when the code came from another machine.
- Don't treat the app's grey sample code as a real one.
