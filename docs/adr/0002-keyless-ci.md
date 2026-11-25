# 0002: CI authenticates without keys, as two least-privilege identities

## Context

The usual shortcut is a service account JSON key stored as a GitHub secret. A key is a
long-lived credential: it leaks through logs, forks and laptops, never expires by itself, and
works from anywhere.

## Decision

GitHub Actions authenticates through Workload Identity Federation. Each run gets a GitHub OIDC
token, exchanges it for a Google token that lives about an hour, and impersonates a service
account. There is no key to store, rotate or leak.

The trust is narrow at two levels:

1. **The provider** accepts a token only if its subject is exactly
   `repo:DiegoTDDD/olist-cloud-warehouse:ref:refs/heads/main` or `...:pull_request`, the
   repository matches, and the owner's numeric id matches (so a deleted and re-registered
   account with the same name cannot inherit the trust).
2. **Each service account** trusts one of those subjects:

| Identity | Trusted subject | Can do |
|---|---|---|
| `olist-deployer` | pushes, schedules and manual runs on `main` | run jobs; edit raw, staging, marts, ops; read project metadata |
| `olist-pr-builder` | pull requests from this repository | run jobs; read raw; create and own its own `ci_pr_*` datasets. It cannot write any production dataset. |

Analysts, when added (`analyst_members`), can read `marts` only.

## Consequences

A pull request can run the whole warehouse build in BigQuery, but a malicious change in one
cannot touch production data. The workflow files hold no secret, only the provider name and
the service account emails, stored as repository variables. checkov's GitHub OIDC rule
(CKV_GCP_125) passes because the provider's condition pins the subject.
