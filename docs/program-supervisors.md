# Program supervisors — deployed feature under review

This code matches the supervisor release already live at https://snowschool.app, production deployment `dpl_9tV5d5RMDJQFKZBNXHEXMrjCtYGU`, original isolated release commit `7f0f3f38660d26261b4f0338217301b1070d4467`. No additional deployment or assignment is part of this PR.

## Main reconciliation

Before this reconciliation, GitHub `main` remained at `939a4477dd21ce776b0c17dd5a50dce46c82e8f2`, predating the live staff portal, learning, notifications and workbook imports. The baseline branch `release/production-baseline-2026-11-02` preserves the exact 129-file pre-supervisor production source plus existing regression tests. PR #1 initially reviewed the focused supervisor/startup change against that baseline; it now reconciles all already-deployed source into `main` with explicit authorization. No new product functionality is introduced by the reconciliation.

All 131 current production source files were audited against the merge inputs: no added or missing deployment files, and all 130 non-config files match byte for byte. The only intentional source exception is `vercel.json`: exact-name deployment-disable rules cover the baseline and feature review branches so source preservation did not trigger preview deployments. `main` remains enabled and uses the existing Git production deployment path. Tests and this document are excluded from deployment.

The prospective merge tree was checked against the tested branch. Existing non-deployed repository content (including mobile source) is retained. The original dirty local working checkout is not overwritten. Reconciliation uses a normal PR merge, not a force push or a self-approved review. Its equivalent production rebuild is verified against the already-approved runtime source and health checks.

## Behavior and security

An administrator assigns, replaces or removes one active instructor as supervisor per program. An instructor may supervise multiple programs. Coach Today and Classes list every class in supervised programs. A separate read-only page shows class coach, roster, dated attendance, operational status and meeting point.

Every supervised request checks the exact current program assignment and active instructor eligibility. Existing instructor ownership checks are unchanged; their own classes retain editing rights. Supervisor visibility does not authorize attendance/status/evaluation/media mutations or learner-wide history/progression/report/certificate/export access. Date viewing is GET-only; assignment POST uses admin and CSRF checks. Revocation/replacement takes effect on the next request.

No independent school tenant ID exists on User/Program in the current app. `SchoolGroup.school_name` describes visiting schools and is not an authorization tenant. Exact program scoping meets the boundary within this single-school database; shared-database multi-school tenancy would require a separate model and authorization design.

## Schema and startup

`program_supervisor` is additive: program PK/FK, instructor user FK/index, assigning administrator FK and timestamp. No existing user role is changed. All 95 live program controls were verified Unassigned; no real supervisor was assigned.

The approved production startup calls only `db.create_all()` and fails closed on schema errors. Catalogue, curriculum, demo operations/showcase, demo accounts/parent and App Review seeding are no longer called. Existing seed helpers remain available only for explicitly authorized work. This schema update is already live; the PR does not run migrations.

Retain the additive empty table on any code rollback. To preserve the approved safety change, any rollback source should keep the schema-only entrypoint rather than reintroducing automatic seeds. No destructive data rollback or production backup is claimed.

## Validation and evidence limits

From the repository root:

```
python -m unittest discover -s tests -q
node --test tests/test_availability_script.cjs
```

The deployed baseline passed 184 Python tests and 21 JavaScript checks. The reconciled branch was re-tested with the same results. Coverage includes multi-program visibility, unrelated program/school-group denial, forged/ineligible assignments, CSRF, replacement/revocation, denied supervisor-only mutation/history/media/export access, preserved own-class editing, real missing-table creation, unchanged synthetic existing hashes/settings, no seed calls, and schema-error propagation.

Desktop admin and 390px mobile Coach QA used synthetic accounts. Live checks verified healthy database connectivity, schema-only startup logs, all 95 program controls Unassigned, existing session workspace rendering, authentication redirects and unassigned supervision denial. No live forms were submitted.

The abandoned first candidate was automatically probed by Vercel before seed-capable startup was removed. Existing logs did not record per-seed effects. Visible totals remained 94 active programs and 528 registered guests, but historical row/account-hash changes cannot be ruled out without database audit access. There was no supported existing DB credential/connector for a direct SQL count/audit. Live instructor login was not available; instructor flows were tested synthetically, with the shared workspace rendered live under existing admin access.
