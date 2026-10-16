# Demo script (3-5 minutes, one take)

**Setup before recording** (once): `python scripts/seed_demo.py`, MCP server started in VS Code,
Copilot in **Agent** mode, the Domino UI open in a second window on the *Governance > Bundles* page.
Re-run the seed script to reset the demo between takes (it reuses bundles; if an approval was
decided, send it back in the Domino UI or run `seed_demo.py` after creating fresh bundles with new names).

The seeded bundles: **[DEMO] Claims Triage Model v2** (has an open finding and attachments) and
**[DEMO] Fraud Referral Agent** (waiting on you). A `[TEST]` bundle may also appear in the queue; ignore it.

| # | Say / type to Copilot | What happens | Say to the audience |
|---|---|---|---|
| 1 | "Who am I acting as in Domino?" | `whoami`: name and host | "Every action is tied to a named person, using their own token." |
| 2 | "What's waiting on me in Domino governance?" | `list_my_governance_items`: bundles with links | "Developers see their sign-offs where they already work." |
| 3 | "Tell me about Claims Triage Model v2." | `get_bundle`: stage, approvers, open finding, attachments | "Everything needed to decide, in one answer." |
| 4 | Click the **model card** and **dataset file** links | Opens in Domino | "Links go straight to the evidence, not a search." |
| 5 | "Raise a high finding on Claims Triage: no drift monitoring plan." | `create_finding` preview, nothing written | "It shows exactly what will be written and asks first." |
| 6 | "Yes, submit it." | `create_finding` with `confirm=true`, link back | "The tag in the text shows it came from Copilot." |
| 7 | "Approve Fraud Referral Agent." | `submit_approval` preview: Pending review to Approved | "A human decision, never taken on its own." |
| 8 | "Yes." | Confirmed; status verified; links returned | "Domino re-checked the status and confirms it." |
| 9 | In Domino: open the finding, then the bundle's **History** tab | Finding and approval show as `nick_goble`, with timestamps | "Same audit trail as the UI: actor, time, state change." |

**Say clearly:** Domino records who approved and when, but not an approval comment; reasons for
changes are saved as findings. Approvals can be switched off per team with
`DOMINO_GOV_ALLOW_APPROVALS=false`.

**If something goes wrong:** a tool error always names the fix (for example the env var to set). Run
`whoami` again to confirm the connection.
