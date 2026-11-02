# Program supervisors — deployed feature under review

This code matches the supervisor release already live at https://snowschool.app, production deployment `dpl_9tV5d5RMDJQFKZBNXHEXMrjCtYGU`, original isolated release commit `7f0f3f38660d26261b4f0338217301b1070d4467`. No additional deployment or assignment is part of this PR.

## GitHub release-source gap

GitHub `main` was still `939a4477dd21ce776b0c17dd5a50dce46c82e8f2`, predating the current staff portal, learning, notifications and workbook imports. Applying this feature directly there would omit its deployed dependencies. The base branch `release/production-baseline-2026-11-02` therefore preserves the exact 129-file pre-feature production source plus its existing regression tests. The feature PR targets that baseline, keeping the PR diff limited to the supervisor feature and approved schema-only startup change. The original dirty working checkout was not changed.

All 131 final deployed source files were checked against the reconciled branch. Runtime application files match byte for byte. The intentional source-only exception is `vercel.json`: exact-name deployment-disable rules cover only the baseline and feature review branches, preventing Git-triggered redeployment. These rules live on both PR branches and do not change the running project, infrastructure settings, or `main` behavior. Documentation/test files are excluded from deployed source as before.

`main` still requires a separate reconciliation of previously deployed work. Do not retarget or squash this PR into `main` without resolving that gap, and do not deploy stale `main`. Review/merge of this draft does not itself authorize deployment.

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
