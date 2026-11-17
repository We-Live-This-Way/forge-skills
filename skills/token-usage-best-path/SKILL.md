---
name: token-usage-best-path
description: Use when someone asks what their AI agent server(s) actually used in tokens, why the bill is what it is, or which model provider would be cheapest for that usage; audits real token logs per model and provider, prices them across hosts, and recommends a switch.
---

# Token usage audit and best-path pricing

Different hosts charge very different prices for the *same* open model. This skill turns a server's real token logs into a ranked, dollar-priced recommendation. Never estimate usage; read it.

## 1. Collect real usage (per server)

1. Find the app's per-turn usage log. Common spots:
   - OpenMausBot: `~/.openmausbot/usage/<YYYY-MM>.jsonl` (one JSON row per turn or side call).
   - Other harnesses: a usage/ or logs/ folder, a SQLite table, or the provider dashboard export.
2. Read it on the **host** that runs the app. A bot inside a sandbox or VM usually cannot see the host log; that is the usual reason a bot answers "unavailable". Go in over SSH or a registered machine instead.
3. Pick a window (last 7 days is standard; note if the log starts later).
4. Total per **provider + model**: turns, side calls, input tokens, cached input tokens, output tokens, recorded cost.
5. Also map **which bots use which provider/model**, and each bot's current default.
6. Mark any missing figure as *unavailable*. Many logs record no cost for routed models, and some record no cached-token count; say so rather than filling gaps.

Example (Python; adjust field names to the log you have):

```python
import json, collections, datetime as dt
PATH = "usage.jsonl"
since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)
agg = collections.defaultdict(collections.Counter)
for line in open(PATH):
    r = json.loads(line)
    t = dt.datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))
    if t < since:
        continue
    a = agg[(r.get("provider"), r.get("model"))]
    a["rows"] += 1
    a["input"] += r.get("inputTokens") or 0
    a["cached"] += r.get("cachedInputTokens") or 0
    a["output"] += r.get("outputTokens") or 0
    a["cost"] += r.get("costUsd") or 0
for k, a in sorted(agg.items(), key=lambda x: -x[1]["input"]):
    print(k, dict(a))
```

## 2. Read the shape of the usage

- Compute the **input : output ratio**. Agent fleets are usually input-heavy (50:1 to 100:1) because every turn resends tools, history and files. When input dominates, the **input price and the cached-input price decide the bill**; output price barely matters.
- If the log records cached tokens, compute the cache hit share. If it doesn't, price two cases: no caching (worst case) and about 90% cached (typical for long agent sessions on a host with prompt caching).

## 3. Gather current prices (live, not from memory)

For each model in use, and for any model you would switch to:

- **Router endpoints**: OpenRouter lists every host for a model with input, cached-input and output prices, quantization, uptime and context: `https://openrouter.ai/api/v1/models/<author>/<model>/endpoints` (public, no key).
- **First-party API**: the model maker's own pricing page (check peak/off-peak windows and data-use terms).
- **Direct hosts**: DeepInfra, Together, Fireworks and similar (check promos and their end dates; budget at list price).
- **Subscriptions / coding plans**: read the terms. Many only allow approved tools and can't power a custom agent fleet.

Note per host: quantization (fp4/fp8 can lower quality), uptime, data retention or training use, and tool-calling support.

## 4. Price the real usage

For each candidate (prices per 1M tokens):

`cost = (input − cached) × in_price + cached × cached_price + output × out_price`

Do it for both cache cases and present a small table: candidate, worst case, cached case, caveats.

## 5. Recommend

1. Lead with one path: the cheapest host that passes quality, uptime and privacy checks for the bots' real work.
2. Rank two to four fallbacks.
3. Call out the **biggest savings first**, usually moving the heaviest-input bots off the most expensive input price.
4. If using a router, **pin** the chosen host (for OpenRouter, provider routing `order: ["HostA", "HostB"]`, `allow_fallbacks: false`) so requests don't drift to pricier hosts.
5. Say where real spend can be confirmed (the provider's activity or billing page), and flag a low prepaid balance before switching.
6. Test a pinned cheap host on a real task before moving the whole fleet, especially a heavily quantized one.

## 6. Make the change (only with the owner's go-ahead)

- Back up the bot and app config, wait for active turns to finish, stop the app, edit, restart.
- Verify each bot's default model and provider, and one real turn in the usage log afterwards.
- Never print API keys or tokens while doing any of this.

## Gotchas

- A bot asked to report its own usage often can't: its sandbox can't see the host log, and the app may not record routed-model costs.
- The cheapest headline price can lose once cached-input pricing is counted, and the reverse.
- When a model refuses a task, switching providers rarely fixes it; a fresh chat session usually does, because refusals stick to the session's history.
