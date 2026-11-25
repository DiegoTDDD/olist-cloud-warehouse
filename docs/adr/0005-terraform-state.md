# 0005: Terraform state stays with the one person who applies it

## Context

Terraform state belongs in a remote, versioned, locked backend, normally a Cloud Storage
bucket. The sandbox has no Cloud Storage without billing.

## Decision

The infrastructure (datasets, service accounts, Workload Identity Federation) changes rarely
and is applied by the project owner from Cloud Shell with `bash bootstrap`, which keeps the
state in Cloud Shell's persistent home directory. The bootstrap first tries to create a
versioned bucket and switches to the `gcs` backend by itself if that ever succeeds. CI never
applies Terraform: it checks formatting, validates the configuration and scans it with
checkov on every change.

## Consequences

One person applies, so there is no concurrent apply to lock against. If the state were lost,
every resource can be re-imported, since all names are fixed. With billing enabled, the next
step is the bucket backend and a CI job that posts `terraform plan` on pull requests.
