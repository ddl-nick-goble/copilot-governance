#!/usr/bin/env python
"""Create the demo bundles for the Copilot walkthrough. Safe to re-run: existing [DEMO] bundles are reused.

Creates, in YOUR project only (never touches other bundles):
  * two bundles named "[DEMO] ..." on a policy where you are a listed approver
  * attachments on each (a real model version and dataset file already on the instance)
  * one open finding on the first bundle
  * both approvals submitted for review, so each is waiting on you

Usage (workspace):  python scripts/seed_demo.py
Usage (laptop):     DOMINO_HOST=... DOMINO_API_KEY=... python scripts/seed_demo.py --project-id <id>
"""
import argparse
import os
import sys

from domino_governance_mcp.client import GOV, Client, DominoError

SEED_TAG = " [seeded by scripts/seed_demo.py]"

BUNDLES = ["[DEMO] Claims Triage Model v2", "[DEMO] Fraud Referral Agent"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", default=os.environ.get("DOMINO_PROJECT_ID"))
    ap.add_argument("--policy", default="TestPolicy123", help="published policy NAME on which you are a listed approver")
    a = ap.parse_args()
    if not a.project_id:
        sys.exit("Pass --project-id (or run inside a Domino workspace, where DOMINO_PROJECT_ID is set).")
    c = Client()
    me = c.me()
    print(f"Acting as {me['userName']}")

    ov = c.get(f"{GOV}/policy-overviews")
    ov = ov["data"] if isinstance(ov, dict) else ov
    pol = next((p for p in ov if p["name"] == a.policy and p["status"] == "Published" and not p["archived"]), None)
    if not pol:
        sys.exit(f"No published policy named '{a.policy}'.")

    # real attachable objects already on this instance
    ex = {}
    for o in c.get(f"{GOV}/attachment-overviews", limit=300)["data"]:
        ex.setdefault(o["type"], {"type": o["type"], "identifier": o["identifier"], "source": o.get("source", "MANUAL")})
    atts = [ex[t] for t in ("ModelVersion", "DatasetSnapshotFile") if t in ex]

    existing = {b["name"]: b for b in c.bundles(state=None) if b["projectId"] == a.project_id}
    made = []
    for name in BUNDLES:
        b = existing.get(name)
        if b:
            print(f"= reusing {name}")
        else:
            b = c.post(f"{GOV}/bundles", {"name": name, "projectId": a.project_id, "policyId": pol["id"]})
            print(f"+ created {name}")
            for att in atts:
                try:
                    c.post(f"{GOV}/bundles/{b['id']}/attachments", att)
                except DominoError as e:
                    print(f"  ! attachment {att['type']}: {e}")
        full = c.bundle(b["id"])
        for ap_ in c.approvals(full["id"]):
            if ap_["status"] == "PendingSubmission" and c.is_my_approval(ap_):
                c.publish_approval_event(full, ap_, "RequestSubmitted")
                print(f"  submitted '{ap_['name']}' for review")
        made.append(full)

    first = made[0]
    if not any(f["name"].startswith("Missing bias") for f in c.findings(first["id"])):
        c.create_finding(first, "Missing bias test evidence",
                         "Model card lacks a disparate-impact test across protected classes." + SEED_TAG, "S2")
        print("+ created open finding on", first["name"])
    print()
    for b in made:
        print(f"{b['name']}\n  {c.bundle_url(b) or '(set DOMINO_HOST to print links)'}")


if __name__ == "__main__":
    main()
