# Example prompts

Use these when asking an agent to run [bodycam-delivery-order-indexing](SKILL.md).

The skill folder also has ready-to-use screenshot prompts a bot can read straight from `prompts/`: `preindex.prp` is for drop-off screenshots, and `preindexpickup.prp` is for "Orders for Pickup" screens.

- "Here are today's drop-off screenshots. Index them with the bodycam delivery indexing skill."
- "Index this pickup screen for me."
- "Rename my last 50 bodycam videos that are just numbers. The full order info is in this WhatsApp export."
- "Some of my YouTube titles are only the last 4 of the order number. Match them to my order log and show me a preview before you change anything."
- "Keep going on the YouTube renames from yesterday. Do as many as today's quota allows, exact matches only."
- "The refresh token expired. Re-authorize the YouTube rename app on the channel account and finish the remaining videos."
- "Undo the renames from this morning using the rename log."
- "These few titles look one digit off from the order log. If you can reasonably match them, show me the proposed titles and rename them after I confirm."
- "Don't rename anything yet. Build a preview of the newest 50 digit-titled videos against this export, and list the ones with no match."
- "Set up a Google Cloud project and OAuth desktop client so I can bulk-rename my YouTube videos from a WhatsApp order export. Don't enable billing, and ask me which Google account owns the channel."
