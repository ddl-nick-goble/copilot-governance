"""Drive every read tool through the MCP client against a live Domino instance."""
import os

import pytest

from conftest import call

live = pytest.mark.skipif(not os.environ.get("DOMINO_API_HOST") and not os.environ.get("DOMINO_API_KEY"),
                          reason="needs Domino credentials")


def test_tools_registered(tools):
    assert {"whoami", "list_my_governance_items", "get_bundle", "list_findings"} <= set(tools)


@live
def test_whoami():
    r = call("whoami")
    assert r["userName"] and r["id"] and r["host"]


@live
def test_ac1_my_queue():
    items = call("list_my_governance_items")["items"]
    assert items, "caller has no items; assign one in the Domino UI"
    for i in items:
        assert i["bundle_name"] and i["policy"] and i["stage"] and i["pending_on_you"]
        if os.environ.get("DOMINO_HOST"):
            assert i["url"].startswith(os.environ["DOMINO_HOST"] + "/")
            assert "/governance/bundle/" in i["url"] or i["url"].endswith("/governance/bundles")  # orphaned-project fallback


@live
def test_ac2_get_bundle():
    bid = call("list_my_governance_items")["items"][0]["bundle_id"]
    b = call("get_bundle", {"bundle": bid})
    assert b["bundle_id"] == bid
    for k in ("stage", "policy", "approvals", "open_findings", "attachments", "url"):
        assert k in b


@live
def test_get_bundle_by_name():
    first = call("list_my_governance_items")["items"][0]
    assert call("get_bundle", {"bundle": first["bundle_name"]})["bundle_id"] == first["bundle_id"]


@live
def test_ac3_list_findings():
    r = call("list_findings", {"bundle": "9c358d99-b30e-4d99-9344-aa052cba079c"})["findings"]
    assert r and {"title", "severity", "status", "owner", "url"} <= set(r[0])


@live
def test_unknown_bundle_is_clean_error():
    assert "error" in call("get_bundle", {"bundle": "no-such-bundle-xyz"})


def test_ac7_missing_credential():
    r = call("whoami", env={})
    assert "DOMINO_API_KEY" in r["error"] and "Traceback" not in r["error"]


def test_ac7_missing_host():
    assert "DOMINO_HOST" in call("whoami", env={"DOMINO_API_KEY": "x"})["error"]


@live
def test_ac7_invalid_key():
    host = os.environ["DOMINO_API_HOST"]
    r = call("list_my_governance_items", env={"DOMINO_API_KEY": "bad", "DOMINO_HOST": host})
    assert "error" in r and "DOMINO_API_KEY" in r["error"]


@live
@pytest.mark.skipif(not os.environ.get("DOMINO_TEST_BUNDLE"), reason="needs DOMINO_TEST_BUNDLE")
def test_queue_shows_review_approval_as_awaiting_decision():
    items = {i["bundle_id"]: i for i in call("list_my_governance_items")["items"]}
    mine = items[os.environ["DOMINO_TEST_BUNDLE"]]
    assert any("awaiting your decision" in p for p in mine["pending_on_you"])


@live
def test_pending_submission_is_not_a_decision():
    """PendingSubmission approvals must not be reported as awaiting the user's decision."""
    for i in call("list_my_governance_items")["items"]:
        for p in i["pending_on_you"]:
            if "awaiting your decision" in p:
                b = call("get_bundle", {"bundle": i["bundle_id"]})
                assert any(a["status"] == "PendingReview" for a in b["approvals"])


@live
@pytest.mark.skipif(not os.environ.get("DOMINO_HOST"), reason="needs DOMINO_HOST for links")
def test_attachment_links_present():
    from conftest import call as c
    import httpx
    tok = httpx.get("http://localhost:8899/access-token").text.strip()
    bs = httpx.get(os.environ["DOMINO_API_HOST"] + "/api/governance/v1/bundles", params={"limit": 200},
                   headers={"Authorization": f"Bearer {tok}"}).json()["data"]
    withatt = next(x for x in bs if x.get("attachments"))
    got = c("get_bundle", {"bundle": withatt["id"]})
    assert got["attachments"] and all(a["url"].startswith(os.environ["DOMINO_HOST"]) for a in got["attachments"])
