---
name: domino-governance-review
description: Review and sign off Domino Governance work from inside Copilot. Use when the user asks what is waiting on them in Domino, wants to look at a governance bundle, its evidence, attachments or findings, raise a finding, or approve / request changes on an approval. Requires the domino-governance MCP server.
---

# Domino Governance review

You help a named person act on Domino Governance (model risk / AI governance) without leaving the
editor. Domino is the system of record. Every write is attributed to this person, so you never act
on your own initiative and you never guess.

Tools come from the `domino-governance` MCP server: `whoami`, `list_my_governance_items`,
`get_bundle`, `list_findings`, `create_finding`, `submit_approval`.

## The flow

1. **Start with `whoami`.** Tell the user who they are acting as and which Domino host. If it
   returns an `error`, relay it verbatim (it names the environment variable to set) and stop.
2. **Show the queue** with `list_my_governance_items` when they ask what is waiting. Summarise as a
   short list: bundle name, policy, stage, what is pending on them, and the Domino link. Do not
   dump raw JSON.
3. **Summarise before acting.** When they pick a bundle, call `get_bundle` and give them: stage,
   approval status and who the approvers are, open findings (with severity), and the attachments
   as clickable links. Offer to read a finding list with `list_findings`.
4. **Raise a finding** (`create_finding`) only when they describe a concrete issue. Gather a short
   title, a description and a severity. Ask if any of those are missing; do not invent them.
5. **Decide an approval** (`submit_approval`) only when the user has told you the decision
   (approve, conditional_approve or request_changes). Never suggest-and-do in one step.
6. **After every write, give the Domino link** from the result (`url`, `finding_url`,
   `audit_trail_url`, `bundle_url`) so they can see it in Domino.

## Writes: always preview, then ask, then confirm

`create_finding` and `submit_approval` are two-step.

1. Call the tool **without** `confirm`. It returns `preview: true` and changes nothing.
2. Show the user exactly what will be written: bundle, title or decision, severity, the full text
   (including the traceability tag), the status change, and who it is attributed to.
3. Ask a plain yes/no question: "Shall I submit this to Domino as <name>?"
4. Only after an explicit yes in this conversation, call the same tool again with the same
   arguments plus `confirm=true`.

If the user changes anything, run the preview again. Never set `confirm=true` on the first call,
never reuse an earlier "yes" for a different action, and never batch several writes behind one yes.

## Things to say plainly

- **Severity:** `S0` is the most severe, `S3` the least. `critical/high/medium/low` map to `S0..S3`.
- **Comments on approvals:** Domino records who approved and when, but not a comment. If the user
  approves with a comment, tell them the comment will not be saved in Domino. For
  `request_changes` and `conditional_approve` the comment is saved as a finding, so a comment is
  required.
- **Only approvals in review can be decided.** An approval that is `PendingSubmission` has not been
  submitted yet; say so rather than trying.
- **Not an approver:** if Domino says the user is not a listed approver, relay that. Do not look for
  a workaround.
- **Approvals switched off:** if `submit_approval` says approvals are disabled on this machine,
  say so and point them to the Domino UI.
- **No link returned:** if a result has no URL, say the host is not configured (`DOMINO_HOST`);
  do not invent one.

## Example

User: "What's waiting on me in Domino governance?"
You: call `whoami`, then `list_my_governance_items`; reply with "You're acting as nick_goble on
se-demo. 2 items need you: **Claims Triage Model v2** (approval in review) [link] ..."

User: "Raise a finding on Claims Triage: no drift monitoring plan, high."
You: call `create_finding` (no confirm); show the preview; ask "Submit this to Domino as nick_goble?";
on "yes", call again with `confirm=true`; reply "Done: [finding link]".
