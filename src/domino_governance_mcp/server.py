"""FastMCP server: tool names, input schemas and output shapes are the contract."""
from __future__ import annotations

import functools
import logging
import os

from mcp.server.fastmcp import FastMCP

from . import links
from .auth import AuthError
from .client import TAG, Client, DominoError

logging.getLogger("httpx").setLevel(logging.WARNING)
mcp = FastMCP("domino-governance")
_client: Client | None = None

SEVERITIES = {"S0", "S1", "S2", "S3"}
WORDS = {"critical": "S0", "high": "S1", "medium": "S2", "low": "S3"}


def client() -> Client:
    global _client
    if _client is None:
        _client = Client()
    return _client


def safe(fn):
    """Turn expected failures into clear messages, never stack traces."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except (AuthError, DominoError) as e:
            return {"error": str(e)}
    return wrapper


def approvals_enabled() -> bool:
    return os.environ.get("DOMINO_GOV_ALLOW_APPROVALS", "true").strip().lower() not in ("0", "false", "no", "off")


def _finding(f: dict) -> dict:
    return {"finding_id": f["id"], "title": f["name"], "severity": f.get("severity"),
            "status": f.get("status"), "owner": (f.get("assignee") or {}).get("name"),
            "approval": f.get("approvalName") or None, "description": f.get("description")}


# ----------------------------------------------------------------- reads
@mcp.tool()
@safe
def whoami() -> dict:
    """Confirm which Domino user and host this server is acting as. Call this first in a
    session so the user can see who their actions will be attributed to."""
    c = client()
    return {**c.me(), "host": c.creds.ui_base or c.creds.api_base, "auth_mode": c.creds.mode,
            "approvals_enabled": approvals_enabled()}


@mcp.tool()
@safe
def list_my_governance_items() -> dict:
    """List active governance bundles with something waiting on the current user: a stage
    assigned to them, or an approval in review that they (or an org they belong to) must decide.
    Returns bundle_id, bundle_name, policy, stage, what is pending, and a Domino URL.
    Start here for "what's waiting on me?". Pass bundle_id to get_bundle, list_findings,
    create_finding or submit_approval."""
    items = client().my_items()
    return {"items": [i for i in items if "bundle_id" in i],
            "notes": [i["note"] for i in items if "note" in i]}


@mcp.tool()
@safe
def get_bundle(bundle: str) -> dict:
    """Get one governance bundle: stage, policy, approvals and their status, open findings, and
    attachments with direct Domino links. `bundle` is a bundle ID or (part of) its name; IDs
    come from list_my_governance_items."""
    c = client()
    b = c.resolve_bundle(bundle)
    full = c.bundle(b["id"])
    host = c.creds.ui_base
    findings = c.findings(b["id"])
    return {
        "bundle_id": full["id"], "name": full["name"], "policy": full.get("policyName"),
        "policy_version": full.get("policyVersion"), "stage": full.get("stage"),
        "state": full.get("state"), "project": full.get("projectName"),
        "approvals": [{"approval_id": a["id"], "name": a["name"], "status": a["status"],
                       "approvers": [x["name"] for x in a.get("approvers") or []]}
                      for a in c.approvals(b["id"])],
        "open_findings": [{**_finding(f), "url": links.finding(host, full, f["id"])}
                          for f in findings if f.get("status") not in ("Done", "WontDo")],
        "attachments": [{"type": a["type"], "identifier": a["identifier"], "url": links.attachment(host, full, a)}
                        for a in full.get("attachments") or []],
        "url": c.bundle_url(full),
        "findings_url": links.bundle(host, full, "findings"),
        "audit_trail_url": links.bundle(host, full, "history"),
    }


@mcp.tool()
@safe
def list_findings(bundle: str) -> dict:
    """List all findings on a bundle (open and closed) with title, severity, status, owner and URL.
    `bundle` is a bundle ID or name; IDs come from list_my_governance_items."""
    c = client()
    b = c.resolve_bundle(bundle)
    full = c.bundle(b["id"])
    host = c.creds.ui_base
    return {"bundle_id": full["id"],
            "findings": [{**_finding(f), "url": links.finding(host, full, f["id"])} for f in c.findings(full["id"])]}


# ---------------------------------------------------------------- writes
def _preview(action: str, who: dict, **details) -> dict:
    return {"preview": True, "written": False, "action": action, "acting_as": who["userName"], **details,
            "next_step": "NOTHING HAS BEEN WRITTEN. Show this preview to the user. Only if they explicitly "
                         "agree, call this tool again with the same arguments and confirm=true."}


def _severity(s: str) -> str:
    v = WORDS.get(s.strip().lower(), s.strip().upper())
    if v not in SEVERITIES:
        raise DominoError("severity must be S0, S1, S2 or S3 (S0 = most severe) or critical/high/medium/low.")
    return v


@mcp.tool()
@safe
def create_finding(bundle: str, title: str, description: str, severity: str,
                   approval: str | None = None, confirm: bool = False) -> dict:
    """Raise a finding (an issue that must be resolved) on a governance bundle, attributed to the
    current user. Needs a bundle ID or name (from list_my_governance_items), a short title, a
    description, and severity S0-S3 (S0 most severe; critical/high/medium/low also accepted).
    `approval` optionally ties it to one approval by name or ID (from get_bundle).
    `severity` is S0-S3 (S0 most severe) or critical/high/medium/low.
    WRITE TOOL: with confirm=false (default) it only returns a preview and changes nothing.
    Show the preview to the user and call again with confirm=true only after they agree."""
    c = client()
    b = c.resolve_bundle(bundle)
    full = c.bundle(b["id"])
    sev = _severity(severity)
    ap = _pick_approval(c, full, approval, strict=True) if approval else None
    text = description.rstrip() + TAG
    who = c.me()
    if confirm is not True:
        return _preview("create_finding", who, bundle=full["name"], bundle_id=full["id"], title=title,
                        severity=sev, description=text, linked_approval=ap["name"] if ap else None,
                        assignee=who["userName"])
    f = c.create_finding(full, title, text, sev, ap)
    return {"written": True, "finding_id": f["id"], "title": f["name"], "severity": f["severity"],
            "status": f["status"], "created_by": who["userName"],
            "url": links.finding(c.creds.ui_base, full, f["id"]), "bundle_url": c.bundle_url(full)}


# decision -> {current approval status -> Domino event}
DECISIONS = {
    "approve": {s: "RequestApproved" for s in ("PendingReview", "ConditionallyApproved", "PendingExpiration", "Expired")},
    "conditional_approve": {"PendingReview": "RequestConditionalApproved"},
    "request_changes": {"PendingReview": "RequestCancelled", **{s: "RequestRejected" for s in (
        "Approved", "ConditionallyApproved", "PendingExpiration", "Expired")}},
}
RESULT = {"RequestApproved": "Approved", "RequestConditionalApproved": "ConditionallyApproved",
          "RequestCancelled": "PendingSubmission", "RequestRejected": "PendingSubmission"}


def _pick_approval(c: Client, full: dict, ref: str | None, strict: bool = False) -> dict:
    aps = c.approvals(full["id"])
    if ref:
        q = ref.lower()
        hits = [a for a in aps if a["id"] == ref] or [a for a in aps if q in a["name"].lower()]
        if len(hits) != 1:
            names = "; ".join(f"{a['name']} [{a['status']}] ({a['id']})" for a in aps)
            raise DominoError(f"approval '{ref}' matched {len(hits)} approvals on this bundle. Options: {names}")
        return hits[0]
    mine = [a for a in aps if c.is_my_approval(a)]
    live = [a for a in mine if a["status"] in ("PendingReview", "ConditionallyApproved", "PendingExpiration", "Expired")]
    if len(live) == 1:
        return live[0]
    if len(live) > 1:
        raise DominoError("Several approvals are waiting on you here; pass `approval` (name or ID): "
                          + "; ".join(f"{a['name']} ({a['id']})" for a in live))
    if mine:
        raise DominoError("Your approvals on this bundle are not awaiting a decision: "
                          + "; ".join(f"{a['name']} is {a['status']}" for a in mine)
                          + ". An approval must be submitted for review (PendingReview) before it can be decided.")
    raise DominoError("You are not a listed approver on any approval in this bundle, so Domino will not accept your decision.")


@mcp.tool()
@safe
def submit_approval(bundle: str, decision: str, comment: str = "", approval: str | None = None,
                    severity: str = "S2", confirm: bool = False) -> dict:
    """Record the current user's decision on an approval that is waiting for them in Domino.
    `bundle` is a bundle ID or name. `approval` (name or ID, from get_bundle) is optional: if several
    approvals wait on the user and it is omitted, the tool returns an error listing them. `decision` is one of:
      approve              - approve it
      conditional_approve  - approve subject to a condition; `comment` is REQUIRED (the tool errors without it)
      request_changes      - send it back to the submitter (also what "reject" means); `comment` is REQUIRED
    NOTE: Domino's approval API stores who decided and when, but has no comment field, so for
    approve the comment is not stored. For the other two, the comment is saved as a finding
    (tagged, severity from `severity`, default S2) so the reason is visible in Domino.
    WRITE TOOL, and a human decision: never call with confirm=true unless the user has explicitly
    chosen this decision for THIS bundle in this conversation. One decision per call: never approve
    several bundles on a single blanket instruction ("approve everything"); preview and confirm each
    one separately. With confirm=false (default) it only previews."""
    if not approvals_enabled():
        return {"error": "Recording approvals from Copilot is disabled on this machine "
                         "(DOMINO_GOV_ALLOW_APPROVALS=false). Use the Domino UI."}
    d = decision.strip().lower().replace("-", "_").replace(" ", "_")
    if d == "reject":
        d = "request_changes"
    if d not in DECISIONS:
        raise DominoError("decision must be approve, conditional_approve or request_changes.")
    c = client()
    b = c.resolve_bundle(bundle)
    full = c.bundle(b["id"])
    ap = _pick_approval(c, full, approval)
    if not c.is_my_approval(ap):
        raise DominoError(f"You are not a listed approver on '{ap['name']}'; Domino will not accept your decision.")
    event = DECISIONS[d].get(ap["status"])
    if not event:
        raise DominoError(f"'{d}' is not possible while '{ap['name']}' is {ap['status']}. "
                          f"Allowed here: {[k for k, v in DECISIONS.items() if ap['status'] in v] or 'none'}.")
    needs_finding = d in ("conditional_approve", "request_changes")
    if needs_finding and not comment.strip():
        raise DominoError(f"`comment` is required for {d}: it is saved as a finding explaining what must change.")
    sev = _severity(severity)
    who = c.me()
    f_title = ("Conditions for approval: " if d == "conditional_approve" else "Changes requested: ") + comment.strip()[:80]
    f_text = comment.strip() + TAG
    if confirm is not True:
        return _preview("submit_approval", who, bundle=full["name"], bundle_id=full["id"],
                        approval=ap["name"], decision=d, current_status=ap["status"],
                        resulting_status=RESULT[event], domino_event=event,
                        will_also_create_finding=({"title": f_title, "severity": sev, "description": f_text}
                                                  if needs_finding else None),
                        comment_note=None if needs_finding else
                        "Domino stores who approved and when, not a comment. Your comment (if any) will not be saved in Domino.")
    finding = c.create_finding(full, f_title, f_text, sev, ap) if needs_finding else None
    meta = {"requiredFindings": [finding["id"]]} if d == "conditional_approve" else {}
    c.publish_approval_event(full, ap, event, meta)
    after = next((a for a in c.approvals(full["id"]) if a["id"] == ap["id"]), {})
    return {"written": True, "decision": d, "approval": ap["name"], "status_before": ap["status"],
            "status_after": after.get("status"), "verified": after.get("status") == RESULT[event],
            "decided_by": who["userName"],
            "finding_url": links.finding(c.creds.ui_base, full, finding["id"]) if finding else None,
            "audit_trail_url": links.bundle(c.creds.ui_base, full, "history"), "bundle_url": c.bundle_url(full)}


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
