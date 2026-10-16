"""Write tools against the dedicated '[TEST] Copilot MCP verification' bundle.

Requires DOMINO_TEST_BUNDLE (id) pointing at a bundle on TestPolicy123 where the caller is an approver.
Each test restores the approval to PendingReview and closes any finding it created.
"""
import os

import httpx
import pytest

from conftest import call

BID = os.environ.get("DOMINO_TEST_BUNDLE")
pytestmark = pytest.mark.skipif(not BID, reason="set DOMINO_TEST_BUNDLE")
G = "/api/governance/v1"


def _raw():
    base = os.environ.get("DOMINO_API_HOST") or os.environ["DOMINO_HOST"]
    tok = httpx.get("http://localhost:8899/access-token").text.strip() if os.environ.get("DOMINO_API_HOST") \
        else os.environ["DOMINO_API_KEY"]
    return httpx.Client(base_url=base, headers={"Authorization": f"Bearer {tok}"}, timeout=60)


def status(h):
    return h.get(f"{G}/bundles/{BID}/approvals").json()[0]["status"]


def event(h, t):
    b = h.get(f"{G}/bundles/{BID}").json()
    ap = h.get(f"{G}/bundles/{BID}/approvals").json()[0]
    r = h.post(f"{G}/rpc/publish-approval-event", json={"bundleId": BID, "approvalId": ap["id"], "policyId": b["policyId"],
                                                        "projectId": b["projectId"], "eventType": t, "meta": {}})
    assert r.is_success, r.text


@pytest.fixture
def h():
    with _raw() as h:
        # normalise to PendingReview
        walk = {"PendingSubmission": ["RequestSubmitted"], "Approved": ["RequestRejected", "RequestSubmitted"],
                "ConditionallyApproved": ["RequestRejected", "RequestSubmitted"], "PendingReview": []}
        for t in walk[status(h)]:
            event(h, t)
        created = []
        h.created = created
        yield h
        for fid in created:
            h.put(f"{G}/findings/{fid}", json={"status": "WontDo"})
        for t in walk.get(status(h), []):
            event(h, t)


def n_findings(h):
    return len(h.get(f"{G}/bundles/{BID}/findings").json()["data"])


def test_ac6_finding_preview_changes_nothing(h):
    before = n_findings(h)
    r = call("create_finding", {"bundle": BID, "title": "[TEST] preview", "description": "d", "severity": "S3"})
    assert r["preview"] is True and r["written"] is False and "confirm=true" in r["next_step"]
    assert r["description"].endswith("[submitted via GitHub Copilot / Domino Governance MCP]")
    assert n_findings(h) == before


def test_ac4_ac6_create_finding_confirmed(h):
    r = call("create_finding", {"bundle": BID, "title": "[TEST] confirmed", "description": "d", "severity": "low", "confirm": True})
    h.created.append(r["finding_id"])
    assert r["written"] and r["severity"] == "S3" and r["created_by"]
    f = next(f for f in call("list_findings", {"bundle": BID})["findings"] if f["finding_id"] == r["finding_id"])
    assert f["description"].endswith("[submitted via GitHub Copilot / Domino Governance MCP]")
    assert f["owner"] == r["created_by"]


def test_bad_severity_is_clean_error():
    assert "severity" in call("create_finding", {"bundle": BID, "title": "x", "description": "d", "severity": "huge"})["error"]


def test_ac6_approval_preview_changes_nothing(h):
    r = call("submit_approval", {"bundle": BID, "decision": "approve", "comment": "ok"})
    assert r["preview"] and not r["written"] and r["resulting_status"] == "Approved"
    assert status(h) == "PendingReview"


def test_ac5_approve(h):
    r = call("submit_approval", {"bundle": BID, "decision": "approve", "confirm": True})
    assert r["written"] and r["verified"] and r["status_after"] == "Approved"
    assert status(h) == "Approved"


def test_request_changes_creates_finding(h):
    assert "comment" in call("submit_approval", {"bundle": BID, "decision": "request_changes"})["error"]
    r = call("submit_approval", {"bundle": BID, "decision": "request_changes", "comment": "[TEST] fix X", "confirm": True})
    assert r["verified"] and r["status_after"] == "PendingSubmission" and r["finding_url"]
    h.created.append(r["finding_url"].rsplit("/", 1)[-1])


def test_conditional_approve(h):
    r = call("submit_approval", {"bundle": BID, "decision": "conditional_approve", "comment": "[TEST] condition", "confirm": True})
    assert r["verified"] and r["status_after"] == "ConditionallyApproved"
    h.created.append(r["finding_url"].rsplit("/", 1)[-1])


def test_wrong_state_is_clean_error(h):
    event(h, "RequestCancelled")  # -> PendingSubmission
    r = call("submit_approval", {"bundle": BID, "decision": "approve", "confirm": True})
    assert "PendingSubmission" in r["error"] and "Traceback" not in r["error"]


def test_approvals_flag_off():
    r = call("submit_approval", {"bundle": BID, "decision": "approve", "confirm": True},
             env={**{k: v for k, v in os.environ.items()}, "DOMINO_GOV_ALLOW_APPROVALS": "false"})
    assert "DOMINO_GOV_ALLOW_APPROVALS" in r["error"]
