# Demo data

`python scripts/seed_demo.py` (inside a workspace, or with `DOMINO_HOST`, `DOMINO_API_KEY` and
`--project-id` on a laptop) creates, in your own project only:

- `[DEMO] Claims Triage Model v2` and `[DEMO] Fraud Referral Agent` on policy `TestPolicy123`
  (you must be a listed approver on the policy; pass `--policy` for another one)
- a model version and a dataset file attached to each (discovered from existing attachments on the instance)
- one open finding on the first bundle
- both approvals submitted for review, so each is waiting on you

It is safe to re-run. Nothing outside your project is touched.
