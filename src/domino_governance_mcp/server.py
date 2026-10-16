"""FastMCP server: tool names, input schemas and output shapes are the contract."""
from __future__ import annotations

import functools

import logging

from mcp.server.fastmcp import FastMCP

from .auth import AuthError
from .client import Client, DominoError

logging.getLogger("httpx").setLevel(logging.WARNING)
mcp = FastMCP("domino-governance")
_client: Client | None = None


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
        except AuthError as e:
            return {"error": str(e)}
        except DominoError as e:
            return {"error": str(e)}
    return wrapper


@mcp.tool()
@safe
def whoami() -> dict:
    """Confirm which Domino user and host this server is acting as. Call this first in a session."""
    c = client()
    return {**c.me(), "host": c.creds.ui_base or c.creds.api_base, "auth_mode": c.creds.mode}


@mcp.tool()
@safe
def list_my_governance_items() -> dict:
    """List active governance bundles with something pending on the current user: a stage
    assigned to them, or an approval they (or an org they belong to) must decide.
    Returns bundle_id, bundle_name, policy, stage, what is pending, and a Domino URL.
    Use the bundle_id with get_bundle, list_findings, create_finding or submit_approval."""
    items = client().my_items()
    return {"items": [i for i in items if "bundle_id" in i],
            "notes": [i["note"] for i in items if "note" in i]}


@mcp.tool()
@safe
def get_bundle(bundle: str) -> dict:
    """Get one governance bundle: stage, policy, approvals, open findings and attachments.
    `bundle` is a bundle ID or (part of) its name; IDs come from list_my_governance_items."""
    c = client()
    b = c.resolve_bundle(bundle)
    full = c.bundle(b["id"])
    atts = b.get("attachments") or []
    return {
        "bundle_id": b["id"], "name": full["name"], "policy": full.get("policyName"),
        "policy_version": full.get("policyVersion"), "stage": full.get("stage"),
        "state": full.get("state"), "project": full.get("projectName"),
        "stage_info": b.get("currentStageInfo"),
        "approvals": [{"approval_id": a["id"], "name": a["name"], "status": a["status"],
                       "approvers": [x["name"] for x in a.get("approvers") or []]}
                      for a in c.approvals(b["id"])],
        "open_findings": [_finding(f) for f in c.findings(b["id"]) if f.get("status") != "Done"],
        "attachments": [{"id": a["id"], "type": a["type"], "identifier": a["identifier"]} for a in atts],
        "url": c.bundle_url(b["id"]),
    }


def _finding(f: dict) -> dict:
    return {"finding_id": f["id"], "title": f["name"], "severity": f.get("severity"),
            "status": f.get("status"), "owner": (f.get("assignee") or {}).get("name"),
            "approval": f.get("approvalName"), "description": f.get("description")}


@mcp.tool()
@safe
def list_findings(bundle: str) -> dict:
    """List all findings on a bundle with title, severity, status and owner.
    `bundle` is a bundle ID or name; IDs come from list_my_governance_items."""
    c = client()
    b = c.resolve_bundle(bundle)
    url = c.bundle_url(b["id"])
    return {"bundle_id": b["id"], "findings": [{**_finding(f), "url": url} for f in c.findings(b["id"])]}


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
