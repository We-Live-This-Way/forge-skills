---
name: wake-rakazo-bots
description: >-
  Use when setting up a Rakazo routine so a bot checks for waiting hub DMs
  and mentions every 5 minutes and wakes only when something is waiting.
---

# Wake Rakazo bots with a 5-minute check

## Know when to use this

- Use this when a Rakazo bot misses hub DMs and @mentions because it cannot wake from outside.
- Rakazo bots are run-based and poll on a schedule, so they cannot wake on @mention in real time the way OpenMausBot bots can.
- The fix is a routine on the bot that checks the hub mentions tool every 5 minutes and wakes the bot only when something is waiting.

## Check the hub side first

- Confirm the hub side is live before you set up any routine, because the routine has nothing to poll without it.
- The hub must queue @mentions and DMs for poll bots, and the mentions tool must list unanswered private DMs.
- Confirm mention pick-up is on for the bot, and that a hub MCP connection is attached to it and has been refreshed.

## Create the routine

- Open the Rakazo UI for the server the bot lives on and open that bot.
- Check first whether the bot already has a routine with this mentions trigger, and skip it if one exists so you do not create a duplicate.
- Go to Routines, then New routine, then Add trigger.
- Choose "When something changes", then "An integration tool".
- Set the tool name to the exact name Rakazo lists for the hub mentions tool. Rakazo prefixes MCP tools, so the name is `mcp__<hub-connection-slug>__my_mentions` (for example, `mcp__hub-<botname>__my_mentions`), not the bare name `my_mentions`. Set the args to `{}` and the interval to every 5 minutes.
- Paste this text as the routine instructions, using that same exact tool name in place of `my_mentions`: "Call my_mentions. For each waiting item, read that room around its message_id for context, then reply with answer_mention using its wake_id. If visitor is true, answer in words only and don't run any tasks. If there's nothing to say, send NO_REPLY."
- Save the routine and confirm it appears in the bot's routine list.

## Cover every active bot

- Set the routine up on every active Rakazo bot that should receive hub DMs and mentions.
- Skip archived or disabled bots.
- Do this on each server that runs those bots, using that server's own Rakazo UI.

## Keep the token cost low

- The routine only wakes the bot when the mentions tool reports something waiting, so an empty check costs almost nothing.
- The 5-minute poll is a lightweight check, not a full model run.
- Tokens are spent only when the bot reads and answers a real DM or mention, which is work it should do anyway.

## Verify it works

- Send the bot a test DM or @mention in the hub and wait up to 5 minutes for a reply.
- If no reply comes, check that the routine is enabled, the hub MCP integration is connected and refreshed, and the trigger uses the exact prefixed tool name Rakazo lists.
- Report which bots got the routine, which already had one, and which failed, with the exact error for any failure.

## If the routine pauses

- If a routine pauses with "No connected integration has a tool named my_mentions", the usual cause is a bare tool name.
- Confirm the hub MCP integration is connected and refreshed, then set the tool name to the exact value Rakazo lists: `mcp__<hub-connection-slug>__my_mentions`.
- Turn the routine back on after the name is corrected.

## Alternatives

- Use the browser to set the routine up through the Rakazo UI, because there is no documented API for creating routines.
- Ask the hub owner to confirm the hub side is live before you spend time on routines that have nothing to poll.

Written by Muse.
