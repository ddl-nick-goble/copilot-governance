"""Thin Domino Governance API client and the 'my queue' logic."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import httpx

from .auth import AuthError, Credentials, resolve

GOV = "/api/governance/v1"
MAX_APPROVAL_SCAN = 200  # cap on per-bundle approval lookups


class DominoError(Exception):
    """User-facing API error."""


class Client:
    def __init__(self, creds: Credentials | None = None):
        self.creds = creds or resolve()
        self.http = httpx.Client(base_url=self.creds.api_base, timeout=60)

    def get(self, path: str, **params):
        try:
            r = self.http.get(path, params=params or None,
                              headers={"Authorization": f"Bearer {self.creds.bearer()}"})
        except httpx.HTTPError as e:
            raise DominoError(f"Could not reach Domino: {type(e).__name__}") from None
        if r.status_code in (401, 403):
            env = "DOMINO_API_KEY" if self.creds.mode == "pat" else "the workspace token"
            raise AuthError(f"Domino rejected the credential ({r.status_code}). Check {env}; it may be invalid or expired.")
        if r.status_code == 404:
            raise DominoError(f"Not found: {path}")
        if not r.is_success:
            raise DominoError(f"Domino returned {r.status_code} for {path}")
        return r.json()

    # --- identity -------------------------------------------------------
    def me(self) -> dict:
        u = self.get("/v4/users/self")
        return {"id": u["id"], "userName": u["userName"], "fullName": u.get("fullName"), "email": u.get("email")}

    def my_org_ids(self, uid: str) -> set[str]:
        try:
            orgs = self.get("/api/organizations/v1/organizations").get("orgs", [])
        except DominoError:
            return set()
        return {o["id"] for o in orgs if any(m.get("userId") == uid for m in o.get("members") or [])}

    # --- links ----------------------------------------------------------
    def bundle_url(self, bundle_id: str) -> str | None:
        # TODO: confirm UI route pattern against the live UI.
        return f"{self.creds.ui_base}/governance/bundle/{bundle_id}" if self.creds.ui_base else None

    # --- governance reads -----------------------------------------------
    def bundles(self, state: str | None = "Active") -> list[dict]:
        out, offset = [], 0
        while True:
            p = {"limit": 200, "offset": offset}
            if state:
                p["state"] = state
            page = self.get(f"{GOV}/bundles", **p)
            out += page["data"]
            offset += 200
            if offset >= page["meta"]["pagination"]["totalCount"] or not page["data"]:
                return out

    def bundle(self, bundle_id: str) -> dict:
        return self.get(f"{GOV}/bundles/{bundle_id}")

    def approvals(self, bundle_id: str) -> list[dict]:
        return self.get(f"{GOV}/bundles/{bundle_id}/approvals")

    def findings(self, bundle_id: str) -> list[dict]:
        return self.get(f"{GOV}/bundles/{bundle_id}/findings").get("data", [])

    def resolve_bundle(self, id_or_name: str) -> dict:
        """Accept a bundle ID or a (partial) name."""
        try:
            return self.bundle(id_or_name)
        except DominoError:
            pass
        q = id_or_name.lower()
        hits = [b for b in self.bundles(state=None) if q in b["name"].lower()]
        exact = [b for b in hits if b["name"].lower() == q]
        hits = exact or hits
        if not hits:
            raise DominoError(f"No bundle found matching '{id_or_name}'. Use list_my_governance_items to find IDs.")
        if len(hits) > 1:
            names = "; ".join(f"{b['name']} ({b['id']})" for b in hits[:5])
            raise DominoError(f"'{id_or_name}' matches {len(hits)} bundles: {names}. Use the bundle ID.")
        return hits[0]

    # --- my queue -------------------------------------------------------
    def my_items(self) -> list[dict]:
        me = self.me()
        ids = {me["id"]} | self.my_org_ids(me["id"])
        items: dict[str, dict] = {}

        def entry(b):
            return items.setdefault(b["id"], {
                "bundle_id": b["id"], "bundle_name": b["name"], "policy": b.get("policyName"),
                "stage": b.get("stage"), "project": b.get("projectName"),
                "pending_on_you": [], "url": self.bundle_url(b["id"]),
            })

        bundles = self.bundles("Active")
        for b in bundles:
            assignees = [(b.get("stageAssignee") or {}).get("id")] + [
                (s.get("assignee") or {}).get("id") for s in b.get("stages") or []
                if s.get("stage", {}).get("name") == b.get("stage")]
            if me["id"] in assignees:
                entry(b)["pending_on_you"].append(f"You are assigned to stage '{b.get('stage')}'")

        cand = [b for b in bundles if (b.get("currentStageInfo") or {}).get("pendingApprovalsCount", 0) > 0]
        truncated = len(cand) > MAX_APPROVAL_SCAN
        cand = cand[:MAX_APPROVAL_SCAN]

        def look(b):
            try:
                return b, self.approvals(b["id"])
            except DominoError:
                return b, []

        with ThreadPoolExecutor(8) as ex:
            for b, aps in ex.map(look, cand):
                for a in aps:
                    if a.get("status") == "PendingSubmission" and any(
                            x.get("id") in ids for x in a.get("approvers") or []):
                        entry(b)["pending_on_you"].append(
                            f"Approval '{a['name']}' awaiting your decision (approval_id {a['id']})")
        result = list(items.values())
        if truncated:
            result.append({"note": f"Scanned the first {MAX_APPROVAL_SCAN} bundles with pending approvals only."})
        return result
