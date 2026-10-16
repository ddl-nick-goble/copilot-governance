"""Domino UI deep links.

Routes were taken from the Domino frontend router (se-demo, Oct 2026):
  /u/{owner}/{project}/governance/bundle/{bundleId}/policy/{policyId}[/findings|/finding/{id}|/attachments|/history|/evidence]
The SPA answers 200 for any path, so these cannot be verified server-side; click one to confirm.
"""
from __future__ import annotations

from urllib.parse import quote


def _q(x) -> str:
    return quote(str(x), safe="")


def _base(host: str | None, b: dict) -> str | None:
    if not host or not b.get("projectOwner") or not b.get("projectName") or not b.get("policyId"):
        return None
    return (f"{host}/u/{_q(b['projectOwner'])}/{_q(b['projectName'])}/governance/bundle/"
            f"{_q(b['id'])}/policy/{_q(b['policyId'])}")


def bundle(host, b, tab: str = "") -> str | None:
    """Bundle link. Bundles whose project was deleted have no project-scoped route, so fall back to
    the global bundles list rather than returning nothing."""
    if not host:
        return None
    base = _base(host, b)
    if not base:
        return f"{host}/governance/bundles"
    return f"{base}/{tab}" if tab else base


def finding(host, b, finding_id: str) -> str | None:
    base = _base(host, b)
    return f"{base}/finding/{_q(finding_id)}" if base else bundle(host, b)


def attachment(host, b, a: dict) -> str | None:
    """Direct link to the attached object where the UI has a route, else the bundle's attachments tab."""
    if not host:
        return None
    i, t = a.get("identifier") or {}, a.get("type")
    owner, project = _q(b.get("projectOwner", "")), _q(b.get("projectName", ""))
    if t == "Endpoint" and i.get("endpointId"):
        return f"{host}/endpoints/{_q(i['endpointId'])}"
    if t == "ModelVersion" and i.get("name"):
        return f"{host}/model-registry/{_q(i['name'])}/model-card?version={_q(i.get('version', ''))}"
    if t == "DatasetSnapshotFile" and i.get("datasetId") and i.get("snapshotId"):
        path = quote(i.get("filename", ""), safe="/")
        return f"{host}/data/dataset/view/{_q(i['datasetId'])}/{_q(i['snapshotId'])}/{path}"
    if t == "Report" and i.get("filename") and owner and project:
        return f"{host}/u/{owner}/{project}/view/{quote(i['filename'], safe='/')}"
    return bundle(host, b, "attachments")
