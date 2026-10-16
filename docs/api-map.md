# Domino Governance public API map

> **Updated after build.** The first section is the original T-1 recon; the section below supersedes its
> gaps. The OpenAPI spec is public at `/api/governance/swagger/doc.json` (the Swagger UI is at `/governance/swagger/index`).

Recon date: 2026-10-16. Instance: demo workspace host (`$DOMINO_API_HOST`, in-workspace
auth via `localhost:8899/access-token`). Base path `/api/governance/v1`.
All probes were **GET only**. No write endpoint has been called yet (see "Unverified").

## Coverage table

| Tool | Public endpoint(s) | Exists | Verified | Gaps / notes |
|---|---|---|---|---|
| `whoami` | `GET /api/users/v1/self` (user under `.user`), `GET /v4/users/self` (flat; also returns `organizations`, `roles`) | yes | 200 | Need the user `id` and org memberships for queue filtering. `/v4/users/self` is the one that returns orgs. |
| `list_my_governance_items` | `GET /bundles`, `GET /bundles/{id}/approvals`, `GET /v4/users/self` | partial | 200 | **No server-side "assigned to me" filter** (see Findings). Fetch and filter client-side. |
| `get_bundle` | `GET /bundles/{id}`, `GET /bundles/{id}/approvals`, `GET /bundles/{id}/findings` | yes | 200 | Attachment **URLs are not returned**; they must be constructed (see Gaps). |
| `list_findings` | `GET /bundles/{id}/findings` | yes | 200 | Not in the original endpoint list. Top-level `GET /findings` is 404. |
| `create_finding` | `POST /findings` | **unverified** | not called | Existing findings carry `approvalId`, `evidenceId`, `artifactId`. The request schema is unknown, and the bundle id alone may not be enough. |
| `submit_approval` | `POST /rpc/publish-approval-event` | **unverified** | not called | Caller must be a listed approver. Needs a seeded approval assigned to the demo user (T-2). |

Other endpoints confirmed 200: `GET /attachment-overviews` (0.8 MB), `GET /bundles/{id}/report` (PDF).
Not found (404): `/policies`, `/findings`, `/openapi.json`, `/swagger.json`, `/api-docs`, `/docs`.
No public OpenAPI spec was found, so write schemas must come from the skill, the UI network calls, or a test call on seeded data.

## Findings that shape the build

1. **Auth header answer.** Bearer works with the workspace token. For laptops, `Authorization: Bearer <PAT>`
   is the plan; **not yet tested** with a real PAT from outside the workspace. Verify in T-3.
2. **Pagination.** `GET /bundles` returns everything by default (813 bundles, 2.5 MB). `limit` and `offset` work and
   `meta.pagination.totalCount` is returned. `page` and `pageSize` are ignored. Page in chunks (for example 100).
3. **Server-side filters.** `state=Active` works (813 to 647). `assigneeId`, `stageAssignee` and `projectId` are
   silently ignored (they still return all 813). So "mine" is computed client-side.
4. **"Mine" has three sources**:
   - `bundle.stageAssignee.id` or `bundle.stages[].assignee.id` equals the caller id (4 bundles for the current user)
   - `GET /bundles/{id}/approvals` where `approvers[].id` equals the caller id
   - approvers that are **organizations** (`isOrganizationUser: true`), which need the caller's org ids from
     `/v4/users/self.organizations`
   Reading approvals is N+1. Use `currentStageInfo.pendingApprovalsCount > 0` and `state=Active` to prune
   (475 of 813 have pending approvals, so cap and cache).
5. **Bundle fields are optional.** `attachments`, `stages`, `currentStageInfo` and `stageAssignee` can be missing or
   null, and `approvers` can be null. Code defensively.
6. **Approval statuses seen:** `PendingSubmission`, `Approved`, `Expired`. A "pending on me" item is `PendingSubmission`.
7. **Finding shape:** `id, bundleId, approvalId, approvalName, artifactLabel, evidenceId, artifactId, name,
   description, severity (S3...), status (ToDo...), assignee{id,name}, approver{id,name}, dueDate, createdBy, policyName`.
8. **Attachment types in the data:** `Report` (560), `ModelVersion` (288), `Endpoint` (4), `DatasetSnapshotFile` (3).
   Each has an `identifier` with enough fields to build a Domino UI link (dataset id and snapshot id, model name and
   version, endpoint id, or project, commit and filename). The UI route patterns still need confirming.

## Gaps and risks (for Nick's decision)

- **G1, create finding:** a finding appears to attach to an approval and an evidence or artifact item, not just a
  bundle. The AC-4 wording ("title, description, severity on a bundle") may need an extra input (approval name, or
  default to the current stage's approval). Needs one real test call on a seeded bundle, T-2 first.
- **G2, write path unverified:** the stop rule asks whether the writes are public. `POST /findings` and
  `POST /rpc/publish-approval-event` sit under the public `/api/governance/v1` prefix and are documented in the
  plugin skill, but I have not confirmed their schemas or that they succeed. **Not blocking yet**, but T-4 stays gated
  on a test against seeded data.
- **G3, attachment URLs:** the API gives identifiers, not links. Links are built from `DOMINO_HOST` plus UI route
  patterns, which I must derive and check by opening them.
- **G4, no demo data for the caller:** no approval currently lists `nick_goble` as an approver, so AC-1/AC-5 have
  nothing to show until T-2. The instance is shared (813 bundles from other users), so seeding must create
  clearly labelled demo bundles and never write to existing ones.

## Endpoints used (to be updated as tools are built)

| Method | Path | Tool |
|---|---|---|
| GET | /api/users/v1/self | whoami |
| GET | /v4/users/self | whoami, list_my_governance_items |
| GET | /api/governance/v1/bundles | list_my_governance_items |
| GET | /api/governance/v1/bundles/{id} | get_bundle |
| GET | /api/governance/v1/bundles/{id}/approvals | list_my_governance_items, get_bundle |
| GET | /api/governance/v1/bundles/{id}/findings | list_findings, get_bundle |
| POST | /api/governance/v1/findings | create_finding (unverified) |
| POST | /api/governance/v1/rpc/publish-approval-event | submit_approval (unverified) |

## Final state after build (supersedes the gaps above)

| Item | Result |
|---|---|
| Auth | `Authorization: Bearer <PAT>` against the public host works. A legacy API key as Bearer returns 403; it only works as `X-Domino-Api-Key` (deprecated, not used). |
| `create_finding` | `POST /findings` works. Required: `bundleId, policyVersionId, name, severity (S0-S3), assignee{id,name}, approver{id,name}`. `approvalId` is optional (G1 resolved). |
| `submit_approval` | `POST /rpc/publish-approval-event` works. Needs `bundleId, policyId, projectId, approvalId, eventType`. |
| Approval comment | **No field.** `meta` carries only evidence or `requiredFindings`. Domino records `updatedBy` and `updatedAt`. |
| Valid transitions | `PendingReview`: Approved / ConditionallyApproved / `RequestCancelled` (back to PendingSubmission). `RequestRejected` is not valid from `PendingReview`. `PendingSubmission` cannot be decided. |
| `conditional_approve` | Requires `requiredFindings` (finding IDs), so the comment becomes a finding. |
| "Awaiting decision" | Status `PendingReview` (not `PendingSubmission`). |
| `openFindingsCount` | Did not change after creating a finding. Not trusted; open findings are computed from `/bundles/{id}/findings`. |
| Org approvers | Approver `id` is the org's user id from `GET /api/organizations/v1/organizations` (`members[].userId`), not the id in `/v4/users/self.organizations`. |
| Bundle detail | `GET /bundles/{id}` includes `attachments` (key omitted when empty). |

### UI link routes (from the Domino frontend router; the SPA returns 200 for any path, so click-test)

| Link | Route |
|---|---|
| Bundle | `/u/{owner}/{project}/governance/bundle/{id}/policy/{policyId}` (+ `/findings`, `/finding/{fid}`, `/attachments`, `/history`, `/evidence`) |
| Model version | `/model-registry/{name}/model-card?version={n}` |
| Endpoint | `/endpoints/{endpointId}` |
| Dataset file | `/data/dataset/view/{datasetId}/{snapshotId}/{filename}` |
| Project file | `/u/{owner}/{project}/view/{filename}` |
| Orphaned bundle (project deleted) | falls back to `/governance/bundles` |

### Additional endpoints used

| Method | Path | Used by |
|---|---|---|
| GET | /api/organizations/v1/organizations | queue, approver checks |
| GET | /api/governance/v1/policy-overviews, `/attachment-overviews` | seed script |
| POST | /api/governance/v1/bundles, `/bundles/{id}/attachments` | seed script |
| PUT | /api/governance/v1/findings/{id} | tests (close test findings) |
