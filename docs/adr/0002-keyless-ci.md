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
   `repo:DiegoTDDD@183739024/olist-cloud-warehouse@1472254812:ref:refs/heads/main` or
   `...:pull_request`, and the repository name, repository id and owner id all match.
2. **Each service account** trusts one of those subjects:

| Identity | Trusted subject | Can do |
|---|---|---|
| `olist-deployer` | pushes, schedules and manual runs on `main` | run jobs; edit raw, staging, marts, ops; read project metadata |
| `olist-pr-builder` | pull requests from this repository | run jobs; read raw; create and own its own `ci_pr_*` datasets. It cannot write any production dataset. |

Analysts, when added (`analyst_members`), can read `marts` only.

GitHub writes the owner and repository into the subject with their numeric ids
(`owner@id/repo@id`). The first deploy failed with "rejected by the attribute condition"
because the condition expected the older `owner/repo` form; a throwaway workflow printed the
token's claims (never the token), and the condition and bindings were rewritten to match.
Pinning the ids is stronger than pinning names: a deleted and re-created account or
repository with the same name gets different ids, so it cannot inherit the trust.

## Consequences

A pull request can run the whole warehouse build in BigQuery, but a malicious change in one
cannot touch production data. The workflow files hold no secret, only the provider name and
the service account emails, stored as repository variables. checkov's GitHub OIDC rule
(CKV_GCP_125) is skipped with a written reason: its parser predates the `owner@id/repo@id`
subject format and cannot read it.
